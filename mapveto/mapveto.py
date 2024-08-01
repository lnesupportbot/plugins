import asyncio
import discord  # type: ignore
from discord.ext import commands  # type: ignore
from discord.ui import View, Button, Select  # type: ignore
import json
import os

from core import checks
from core.models import PermissionLevel  # type: ignore

from .core.templateveto import MapVetoConfig, TemplateManager, vetos
from .core.tournament import TournamentManager, TournamentConfig
from .core.teams import TeamManager, TeamConfig
from .core.veto import MapVeto

# Charger les configurations
veto_config = MapVetoConfig()
veto_config.load_vetos()
tournament_config = TournamentConfig()
tournaments = tournament_config.load_tournaments()
team_config = TeamConfig()
teams = team_config.load_teams()
vetos = {}

class SelectTeamForMapVeto(Select):
    def __init__(self, team_a_name, team_b_name, template_name, bot):
        self.template_name = template_name
        self.team_a_name = team_a_name
        self.team_b_name = team_b_name
        self.bot = bot

        options = [
            discord.SelectOption(label=team_a_name, description=f"{team_a_name} commence", value=team_a_name),
            discord.SelectOption(label=team_b_name, description=f"{team_b_name} commence", value=team_b_name),
        ]

        super().__init__(placeholder="Choisir l'équipe qui commence...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        starting_team = self.values[0]
        other_team = self.team_b_name if starting_team == self.team_a_name else self.team_a_name

        # Obtenir les IDs des capitaines des équipes
        starting_team_id = int(teams[starting_team]["captain_discord_id"])
        other_team_id = int(teams[other_team]["captain_discord_id"])

        maps = veto_config.vetos[self.template_name]["maps"]
        rules = veto_config.vetos[self.template_name]["rules"]
        ticket_channel = interaction.channel

        veto = MapVeto(self.template_name, maps, starting_team_id, starting_team, other_team_id, other_team, rules, ticket_channel, self.bot)
        vetos[self.template_name] = veto

        await interaction.response.send_message(f"Le Map Veto commence avec {starting_team} contre {other_team}.", ephemeral=True)
        await veto.send_ticket_message(ticket_channel)

class TeamSelect(Select):
    def __init__(self, tournament_name, template_name, bot):
        self.template_name = template_name
        self.tournament_name = tournament_name
        self.bot = bot

        # Reload teams to get the latest data
        team_config.load_teams()

        tournament_teams = [team for team, details in team_config.teams.items() if details["tournament"] == tournament_name]

        options = []
        for team in tournament_teams:
            captain_id = int(team_config.teams[team]["captain_discord_id"])
            captain_user = self.bot.get_user(captain_id)
            if captain_user:
                description = f"Capitaine : {captain_user.name}"
            else:
                description = "Capitaine non trouvé"
            options.append(discord.SelectOption(label=team, description=description, value=team))

        super().__init__(placeholder="Choisir deux équipes...", min_values=2, max_values=2, options=options)

    async def callback(self, interaction: discord.Interaction):
        team_a_name, team_b_name = self.values
        team_a_id = int(team_config.teams[team_a_name]["captain_discord_id"])
        team_b_id = int(team_config.teams[team_b_name]["captain_discord_id"])

        if not team_a_id or not team_b_id:
            await interaction.response.send_message("Un ou les deux capitaines ne sont pas trouvés sur le serveur.", ephemeral=True)
            return

        # Fetch user objects from IDs
        team_a_user = await self.bot.fetch_user(team_a_id)
        team_b_user = await self.bot.fetch_user(team_b_id)

        if not team_a_user or not team_b_user:
            await interaction.response.send_message("Un ou les deux capitaines ne sont pas trouvés sur le serveur.", ephemeral=True)
            return

        # Check if threads already exist for users
        errors = []
        modmail_cog = self.bot.get_cog("Modmail")
        if modmail_cog is None:
            await interaction.response.send_message("Le cog Modmail n'est pas chargé.", ephemeral=True)
            return

        existing_thread_a = await self.bot.threads.find(recipient=team_a_user)
        existing_thread_b = await self.bot.threads.find(recipient=team_b_user)

        if existing_thread_a:
            errors.append(f"Un thread pour **{team_a_user.name}**({team_a_name}) existe déjà.")
        if existing_thread_b:
            errors.append(f"Un thread pour **{team_b_user.name}**({team_b_name}) existe déjà.")

        if errors:
            await interaction.response.send_message("\n".join(errors), ephemeral=True)
            return

        # Create the ticket with team captains
        category = None  # Specify a category if needed
        users = [team_a_user, team_b_user]

        # Create a fake context to call the `contact` command
        fake_context = await self.bot.get_context(interaction.message)

        # Create the thread
        await modmail_cog.contact(
            fake_context,  # Pass the fake command context
            users,
            category=category,
            manual_trigger=False
        )

        # Explicit pause to wait for the thread to fully create
        await asyncio.sleep(2)

        # Find the thread to ensure it is ready
        thread = await self.bot.threads.find(recipient=team_a_user)

        if not thread or not thread.channel:
            await interaction.response.send_message("Erreur lors de la création du thread.", ephemeral=True)
            return

        ticket_channel = thread.channel  # Get the channel of the created thread

        # Send the embed with the dropdown list and button in the thread
        embed = discord.Embed(
            title="Sélection de l'équipe qui commence le MapVeto",
            description=f"Veuillez choisir quelle équipe commence le MapVeto :",
            color=discord.Color.blue()
        )

        select = SelectTeamForMapVeto(team_a_name, team_b_name, self.template_name, self.bot)
        view = View(timeout=None)
        view.add_item(select)

        await ticket_channel.send(embed=embed, view=view)
        
    def __init__(self, tournament_name, template_name, bot):
        self.template_name = template_name
        self.tournament_name = tournament_name
        self.bot = bot
        
        team_config.load_teams()
        tournament_teams = team_config.get_teams_by_tournament(tournament_name)
        
        options = []
        for team in tournament_teams:
            captain_id = int(teams[team]["captain_discord_id"])
            captain_user = self.bot.get_user(captain_id)
            if captain_user:
                description = f"Capitaine : {captain_user.name}"
            else:
                description = "Capitaine non trouvé"
            options.append(discord.SelectOption(label=team, description=description, value=team))

        super().__init__(placeholder="Choisir deux équipes...", min_values=2, max_values=2, options=options)


    async def callback(self, interaction: discord.Interaction):
        team_a_name, team_b_name = self.values
        team_a_id = int(teams[team_a_name]["captain_discord_id"])
        team_b_id = int(teams[team_b_name]["captain_discord_id"])

        if not team_a_id or not team_b_id:
            await interaction.response.send_message("Un ou les deux capitaines ne sont pas trouvés sur le serveur.", ephemeral=True)
            return

        # Récupérer les objets utilisateur à partir des IDs
        team_a_user = await self.bot.fetch_user(team_a_id)
        team_b_user = await self.bot.fetch_user(team_b_id)

        if not team_a_user or not team_b_user:
            await interaction.response.send_message("Un ou les deux capitaines ne sont pas trouvés sur le serveur.", ephemeral=True)
            return

        # Vérifier si des threads existent déjà pour les utilisateurs
        errors = []
        modmail_cog = self.bot.get_cog("Modmail")
        if modmail_cog is None:
            await interaction.response.send_message("Le cog Modmail n'est pas chargé.", ephemeral=True)
            return

        existing_thread_a = await self.bot.threads.find(recipient=team_a_user)
        existing_thread_b = await self.bot.threads.find(recipient=team_b_user)

        if existing_thread_a:
            errors.append(f"Un thread pour **{team_a_user.name}**({team_a_name}) existe déjà.")
        if existing_thread_b:
            errors.append(f"Un thread pour **{team_b_user.name}**({team_b_name}) existe déjà.")

        if errors:
            await interaction.response.send_message("\n".join(errors), ephemeral=True)
            return

        # Crée le ticket avec les capitaines d'équipe
        category = None  # Vous pouvez spécifier une catégorie si besoin
        users = [team_a_user, team_b_user]

        # Créez un contexte factice pour appeler la commande `contact`
        fake_context = await self.bot.get_context(interaction.message)

        # Créer le thread
        await modmail_cog.contact(
            fake_context,  # passez le contexte de commande factice
            users,
            category=category,
            manual_trigger=False
        )

        # Pause explicite pour attendre la création complète du thread
        await asyncio.sleep(2)

        # Trouver le thread pour s'assurer qu'il est prêt
        thread = await self.bot.threads.find(recipient=team_a_user)

        if not thread or not thread.channel:
            await interaction.response.send_message("Erreur lors de la création du thread.", ephemeral=True)
            return

        ticket_channel = thread.channel  # Obtenir le canal du thread créé

        # Envoyer l'embed avec la liste déroulante et le bouton dans le thread
        embed = discord.Embed(
            title="Sélection de l'équipe qui commence le MapVeto",
            description=f"Veuillez choisir quelle équipe commence le MapVeto :",
            color=discord.Color.blue()
        )

        select = SelectTeamForMapVeto(team_a_name, team_b_name, self.template_name, self.bot)
        view = View(timeout=None)
        view.add_item(select)

        await ticket_channel.send(embed=embed, view=view)

class TournamentSelect(Select):
    def __init__(self, template_name, bot):
        self.template_name = template_name
        self.bot = bot

        # Reload configurations each time the select is initialized
        tournament_config.load_tournaments()
        team_config.load_teams()

        # Use the latest teams data
        tournaments_set = {details["tournament"] for details in team_config.teams.values()}
        options = [
            discord.SelectOption(label=tournament, description=f"Tournament {tournament}")
            for tournament in tournaments_set
        ]

        super().__init__(placeholder="Choisir un tournoi...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        tournament_name = self.values[0]
        select = TeamSelect(tournament_name, self.template_name, self.bot)
        view = View()
        view.add_item(select)
        await interaction.response.send_message(f"Tournament choisi: {tournament_name}", view=view, ephemeral=True)

class TemplateSelect(Select):
    def __init__(self, bot):
        self.bot = bot

        # Reload vetos to ensure the latest data
        veto_config.load_vetos()

        options = [
            discord.SelectOption(
                label=template, 
                description=f"{veto_config.vetos[template]['rules']}",
                value=template
            )
            for template in veto_config.vetos.keys()
        ]
        super().__init__(placeholder="Choisir un template de veto...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        template_name = self.values[0]
        select = TournamentSelect(template_name, self.bot)
        view = View()
        view.add_item(select)
        await interaction.response.send_message(f"Template choisi: {template_name}", view=view, ephemeral=True)

class MapVetoButton(Button):
    def __init__(self):
        super().__init__(label="Lancer un MapVeto", style=discord.ButtonStyle.primary)

    async def callback(self, interaction: discord.Interaction):
        # Reload all configurations when the button is clicked
        veto_config.load_vetos()
        tournament_config.load_tournaments()
        team_config.load_teams()

        select = TemplateSelect(interaction.client)
        view = View(timeout=None)
        view.add_item(select)
        await interaction.response.send_message("Choisissez un template de veto:", view=view, ephemeral=True)

class MapVetoCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.template_veto = TemplateManager(bot)
        self.tournament = TournamentManager(bot)
        self.teams = TeamManager(bot)
        self.current_veto = None

    def set_veto_params(self, name, maps, team_a_id, team_a_name, team_b_id, team_b_name, rules, channel):
        self.current_veto = MapVeto(name, maps, team_a_id, team_a_name, team_b_id, team_b_name, rules, channel, self.bot)

    @commands.command(name='mapveto_setup')
    @commands.has_permissions(administrator=True)
    async def mapveto_setup(self, ctx):
        """Crée ou met à jour le message avec les boutons pour gérer les templates de veto."""
        await self.template_veto.update_setup_message(ctx.channel)

    @commands.command(name='tournament_setup')
    @commands.has_permissions(administrator=True)
    async def tournament_setup(self, ctx):
        await self.tournament.update_setup_message(ctx.channel)

    @commands.command(name='team_setup')
    @commands.has_permissions(administrator=True)
    async def team_setup(self, ctx):
        await self.teams.update_setup_message(ctx.channel)

    @commands.command()
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def start_mapveto(self, ctx, name: str, team_a_id: int, team_a_name: str, team_b_id: int, team_b_name: str):
        """Démarre un veto et envoie des messages en DM aux équipes spécifiées."""
        if name not in veto_config.vetos:
            await ctx.send(f"Aucun template de veto trouvé avec le nom '{name}'.")
            return

        maps = veto_config.vetos[name]["maps"]
        rules = veto_config.vetos[name]["rules"]

        veto = MapVeto(name, maps, team_a_id, team_a_name, team_b_id, team_b_name, rules, ctx.channel, self.bot)
        vetos[name] = veto

        await veto.send_ticket_message(ctx.channel)

    @commands.command()
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def pause_mapveto(self, ctx, name: str):
        """Met en pause le veto spécifié."""
        if name not in vetos:
            await ctx.send(f"Aucun veto en cours avec le nom '{name}'.")
            return

        veto = vetos[name]
        veto.pause()
        await ctx.send(f"Le veto '{name}' a été mis en pause.")

    @commands.command()
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def resume_mapveto(self, ctx, name: str):
        """Reprend le veto spécifié."""
        if name not in vetos:
            await ctx.send(f"Aucun veto en cours avec le nom '{name}'.")
            return

        veto = vetos[name]
        veto.resume()
        await ctx.send(f"Le veto '{name}' a repris.")

    @commands.command()
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def stop_mapveto(self, ctx, name: str):
        """Arrête complètement le veto spécifié mais ne supprime pas le template."""
        if name not in vetos:
            await ctx.send(f"Aucun veto en cours avec le nom '{name}'.")
            return

        veto = vetos[name]
        veto.stop()

        await ctx.send(f"Le veto '{name}' a été arrêté.")

    @commands.command(name='mapveto_button')
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def mapveto_button(self, ctx):
        """Affiche un embed avec un bouton pour lancer un map veto."""
        embed = discord.Embed(
            title="Lancer un MapVeto",
            description="Cliquez sur le bouton ci-dessous pour lancer un MapVeto.",
            color=discord.Color.blue()
        )
        view = View(timeout=None)
        view.add_item(MapVetoButton())
        await ctx.send(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(MapVetoCog(bot))
