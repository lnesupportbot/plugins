
import discord  # type: ignore
from discord.ext import commands  # type: ignore
from discord.ui import View, Button, Select # type: ignore
import asyncio
import json
import os

from core import checks
from core.models import PermissionLevel  # type: ignore

from .core.templateveto import MapVetoConfig, TemplateManager, vetos
from .core.tournament import TournamentManager
from .core.teams import TeamManager
from .core.veto import MapVeto

veto_config = MapVetoConfig()
veto_config.load_vetos()
vetos = {}

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

        await ctx.send(embed=embed)
    
    @commands.command(name='setup_mapveto')
    @commands.has_permissions(administrator=True)
    async def setup_mapveto(self, ctx):
        """Envoie un embed avec un bouton pour initialiser le Map Veto dans le canal de configuration."""
        embed = discord.Embed(
            title="Initialiser le Map Veto",
            description="Cliquez sur le bouton ci-dessous pour démarrer le processus de sélection du tournoi et des équipes.",
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed, view=VetoSetupView(self.bot))

class VetoSetupView(View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        self.add_item(InitVetoButton(bot))

class InitVetoButton(Button):
    def __init__(self, bot):
        super().__init__(label="Initialiser le Map Veto", style=discord.ButtonStyle.primary)
        self.bot = bot

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "Sélectionnez un tournoi et deux équipes pour lancer le Map Veto.",
            view=TournamentSelectView(self.bot),
            ephemeral=True
        )

class TournamentSelectView(View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        self.add_item(TournamentSelect(bot))

class TournamentSelect(Select):
    def __init__(self, bot):
        tournaments = bot.tournament.get_all_tournaments()  # Assurez-vous que cette méthode existe
        options = [discord.SelectOption(label=t, value=t) for t in tournaments]
        super().__init__(placeholder="Choisissez un tournoi...", options=options)
        self.bot = bot

    async def callback(self, interaction: discord.Interaction):
        selected_tournament = self.values[0]
        await interaction.response.send_message(
            f"Tournoi sélectionné : {selected_tournament}. Sélectionnez les deux équipes.",
            view=TeamSelectView(self.bot, selected_tournament),
            ephemeral=True
        )

class TeamSelectView(View):
    def __init__(self, bot, tournament):
        super().__init__(timeout=None)
        self.bot = bot
        self.tournament = tournament
        self.add_item(TeamASelect(bot, tournament))
        self.add_item(TeamBSelect(bot, tournament))

class TeamASelect(Select):
    def __init__(self, bot, tournament):
        teams = bot.teams.get_teams_by_tournament(tournament)  # Assurez-vous que cette méthode existe
        options = [discord.SelectOption(label=t["name"], value=t["id"]) for t in teams]
        super().__init__(placeholder="Choisissez la première équipe...", options=options)
        self.bot = bot
        self.tournament = tournament

    async def callback(self, interaction: discord.Interaction):
        team_a_id = self.values[0]
        team_a = self.bot.teams.get_team_by_id(team_a_id)  # Assurez-vous que cette méthode existe
        await interaction.response.send_message(
            f"Équipe A sélectionnée : {team_a['name']}.",
            view=TeamBSelectView(self.bot, self.tournament, team_a),
            ephemeral=True
        )

class TeamBSelect(Select):
    def __init__(self, bot, tournament, team_a):
        teams = bot.teams.get_teams_by_tournament(tournament)  # Assurez-vous que cette méthode existe
        options = [discord.SelectOption(label=t["name"], value=t["id"]) for t in teams if t["id"] != team_a["id"]]
        super().__init__(placeholder="Choisissez la deuxième équipe...", options=options)
        self.bot = bot
        self.tournament = tournament
        self.team_a = team_a

    async def callback(self, interaction: discord.Interaction):
        team_b_id = self.values[0]
        team_b = self.bot.teams.get_team_by_id(team_b_id)  # Assurez-vous que cette méthode existe
        await interaction.response.send_message(
            f"Équipe B sélectionnée : {team_b['name']}.",
            view=VetoConfirmationView(self.bot, self.team_a, team_b),
            ephemeral=True
        )

class VetoConfirmationView(View):
    def __init__(self, bot, team_a, team_b):
        super().__init__(timeout=None)
        self.bot = bot
        self.team_a = team_a
        self.team_b = team_b
        self.add_item(VetoConfirmationButton(bot, team_a, team_b))

class VetoConfirmationButton(Button):
    def __init__(self, bot, team_a, team_b):
        super().__init__(label="Confirmer le lancement du MapVeto", style=discord.ButtonStyle.success)
        self.bot = bot
        self.team_a = team_a
        self.team_b = team_b

    async def callback(self, interaction: discord.Interaction):
        # Ouverture du ticket avec les informations des équipes
        channel = await interaction.guild.create_text_channel(
            f"mapveto-{self.team_a['name']}-vs-{self.team_b['name']}"
        )
        await channel.send(
            embed=discord.Embed(
                title="Map Veto",
                description=f"Le map veto pour le match entre {self.team_a['name']} et {self.team_b['name']} est prêt !",
                color=discord.Color.blue()
            ),
            view=StartVetoView(self.bot, self.team_a, self.team_b)
        )
        await interaction.response.send_message("Le map veto a été lancé.", ephemeral=True)

class StartVetoView(View):
    def __init__(self, bot, team_a, team_b):
        super().__init__(timeout=None)
        self.bot = bot
        self.team_a = team_a
        self.team_b = team_b
        self.add_item(StartVetoButton(bot, team_a, team_b))

class StartVetoButton(Button):
    def __init__(self, bot, team_a, team_b):
        super().__init__(label="Lancer le MapVeto", style=discord.ButtonStyle.primary)
        self.bot = bot
        self.team_a = team_a
        self.team_b = team_b

    async def callback(self, interaction: discord.Interaction):
        await self.bot.get_cog("MapVetoCog").start_mapveto(
            interaction,
            name="Votre_nom_de_template",
            team_a_id=self.team_a["id"],
            team_a_name=self.team_a["name"],
            team_b_id=self.team_b["id"],
            team_b_name=self.team_b["name"]
        )
        self.disabled = True
        await interaction.response.edit_message(view=self)
        await interaction.followup.send("Le map veto a commencé.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(MapVetoCog(bot))
