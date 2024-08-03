import asyncio
import discord  # type: ignore
from discord.ext import commands  # type: ignore
from discord.ui import View, Button, Select  # type: ignore
import json
import os

from core import checks
from core.models import PermissionLevel  # type: ignore

from .core.templateveto import MapVetoConfig, TemplateManager, veto_config
from .core.tournament import TournamentManager, TournamentConfig, tournament_config
from .core.teams import TeamManager, TeamConfig, team_config
from .core.veto import MapVeto, MapVetoButton

# Charger les configurations
veto_config = MapVetoConfig()
vetos = veto_config.load_vetos()
tournament_config = TournamentConfig()
tournaments = tournament_config.load_tournaments()
team_config = TeamConfig()
teams = team_config.load_teams()

class SetupButtonConfig:
    def __init__(self, filename="message_id.json"):
        self.filename = os.path.join(os.path.dirname(__file__), '.', filename)
        self.setup_message_id = None
        self.load_setup_message_id()

    # Charger l'ID du message depuis le fichier, s'il existe
    def load_setup_message_id():
        if os.path.exists("message_id.json"):
            with open("message_id.json", "r") as f:
                return json.load(f).get("setup_button_message_id")
        return None

    # Sauvegarder l'ID du message dans un fichier
    def save_setup_message_id(message_id):
        with open("message_id.json", "w") as f:
            json.dump({"setup_button_message_id": message_id}, f)
            
    def refresh_setup_message_id(self):
        """Refresh the message id from the file."""
        self.message_id = self.load_setup_message_id()

    async def update_setup_message(self, channel):
        self.refresh_setup_message_id()
        if self.setup_message_id:
            try:
                message = await channel.fetch_message(self.setup_message_id)
                await message.edit(embed=self.create_setup_embed(), view=self.create_setup_view())
            except discord.NotFound:
                await self.send_setup_message(channel)
        else:
            await self.send_setup_message(channel)

setupbutton_config = SetupButtonConfig()

class SetupView(View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Gestion des templates d'événements", custom_id="mapveto_setup", style=discord.ButtonStyle.blurple)
    async def mapveto_setup_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("Gestion des templates d'événements", ephemeral=True)
        await interaction.message.edit(content="Configuration des templates d'événements mise à jour.", view=self)

    @discord.ui.button(label="Gestion des tournois", custom_id="tournament_setup", style=discord.ButtonStyle.green)
    async def tournament_setup_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("Gestion des tournois", ephemeral=True)
        await interaction.message.edit(content="Configuration des tournois mise à jour.", view=self)

    @discord.ui.button(label="Gestion des teams", custom_id="team_setup", style=discord.ButtonStyle.red)
    async def team_setup_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("Gestion des teams", ephemeral=True)
        await interaction.message.edit(content="Configuration des teams mise à jour.", view=self)


class MapVetoCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.template_veto = TemplateManager()
        self.tournament = TournamentManager()
        self.teams = TeamManager(bot)
        self.message_id = setupbutton_config.load_setup_message_id()
        self.current_veto = None

    def set_veto_params(self, name, maps, team_a_id, team_a_name, team_b_id, team_b_name, rules, channel):
        self.current_veto = MapVeto(name, maps, team_a_id, team_a_name, team_b_id, team_b_name, rules, channel, self.bot)

    @commands.command(name='mapveto_setup')
    @commands.has_permissions(administrator=True)
    async def mapveto_setup(self, ctx):
        """Crée ou met à jour le message avec les boutons pour gérer les templates de veto."""
        veto_config.load_vetos()
        await self.template_veto.update_setup_message(ctx.channel)

    @commands.command(name='tournament_setup')
    @commands.has_permissions(administrator=True)
    async def tournament_setup(self, ctx):
        tournament_config.load_tournaments()
        await self.tournament.update_setup_message(ctx.channel)

    @commands.command(name='team_setup')
    @commands.has_permissions(administrator=True)
    async def team_setup(self, ctx):
        team_config.load_teams()
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
        view = View()
        view.add_item(MapVetoButton())
        await ctx.send(embed=embed, view=view)

    @commands.command(name='setup_buttons')
    @commands.has_permissions(administrator=True)
    async def setup_buttons(self, ctx):
        """Affiche trois boutons pour lancer les commandes de configuration."""
        embed = discord.Embed(
            title="Configuration des Événements",
            description="Utilisez les boutons ci-dessous pour configurer les différents éléments.",
            color=discord.Color.blue()
        )
        view = SetupView(self.bot)

        if self.message_id:
            try:
                # Vérifier si le message existe encore
                channel = ctx.channel
                message = await channel.fetch_message(self.message_id)
                await message.edit(embed=embed, view=view)
            except discord.NotFound:
                # Si le message n'existe plus, envoyer un nouveau message
                message = await ctx.send(embed=embed, view=view)
                setupbutton_config.save_setup_message_id(message.id)
        else:
            # Envoyer le message pour la première fois
            message = await ctx.send(embed=embed, view=view)
            setupbutton_config.save_setup_message_id(message.id)

    @commands.Cog.listener()
    async def on_ready(self):
        """Vérifier si un message doit être restauré au démarrage du bot."""
        if self.message_id:
            try:
                channel = self.bot.get_channel(self.channel_id)  # Assurez-vous que vous avez l'ID du canal
                await channel.fetch_message(self.message_id)  # Vérifier si le message existe toujours
            except discord.NotFound:
                # Si le message n'existe plus, supprimez l'ID enregistré
                #os.remove("message_id.json")
                print(f"le message est inactif")

async def setup(bot):
    await bot.add_cog(MapVetoCog(bot))

