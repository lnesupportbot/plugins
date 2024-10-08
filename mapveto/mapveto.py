import asyncio
import discord  # type: ignore
from discord.ext import commands  # type: ignore
from discord.ui import View, Button  # type: ignore
import json
import os

from core import checks
from core.models import PermissionLevel  # type: ignore

from .core.templateveto import MapVetoConfig, TemplateManager
from .core.tournament import TournamentManager, TournamentConfig
from .core.teams import TeamManager, TeamConfig
from .core.veto import MapVeto, VetoManager
from core import checks


# Charger les configurations
veto_config = MapVetoConfig()
template_message_config = TemplateManager()
vetos = veto_config.load_vetos()

tournament_config = TournamentConfig()
tournament_message_config = TournamentManager()
tournaments = tournament_config.load_tournaments()

team_config = TeamConfig()
teams = team_config.load_teams()

class SetupButtonConfig:
    def __init__(self, bot, filename="message_id.json"):
        self.bot = bot  # Store the bot instance
        self.filename = os.path.join(os.path.dirname(__file__), '.', filename)
        self.setup_channel_id = self.load_setup_button_message_id()
        self.setup_button_message_id = self.load_setup_button_message_id()

    # Charger l'ID du message depuis le fichier, s'il existe
    def load_setup_button_message_id(self):
        if os.path.exists(self.filename):
            with open(self.filename, "r") as f:
                data = json.load(f)
                self.setup_button_message_id = data.get('setup_button_message_id')
                self.setup_channel_id = data.get('setup_button_channel_id')
        else:
            self.setup_button_message_id = None
            self.setup_channel_id = None

    # Sauvegarder l'ID du message dans un fichier
    def save_setup_button_message_id(self, message_id, channel_id):
        data = {}
        # Load existing data
        if os.path.exists(self.filename):
            with open(self.filename, 'r') as f:
                data = json.load(f)
        
        # Update setup_message_id while preserving existing keys
        data['setup_button_message_id'] = message_id
        
        with open(self.filename, "w") as f:
            json.dump({
                'setup_button_message_id': message_id,
                'setup_button_channel_id': channel_id
            }, f, indent=4)

    def refresh_setup_button_message_id(self):
        """Refresh the setup button message id from the file."""
        print(self.setup_button_message_id)
        print(self.setup_channel_id)
        self.load_setup_button_message_id()

    async def update_setup_button_message(self, channel):
        print(self.setup_button_message_id)
        if self.setup_button_message_id:
            try:
                message = await channel.fetch_message(self.setup_button_message_id)
                await message.edit(embed=self.create_setup_button_embed(), view=self.create_setup_button_view())
            except discord.NotFound:
                await self.send_setup_button_message(channel)
        else:
            await self.send_setup_button_message(channel)

    def create_setup_button_embed(self):
        return discord.Embed(
            title="Configuration des Événements",
            description="Utilisez les boutons ci-dessous pour configurer les différents éléments.",
            color=discord.Color.blue()
        )

    def create_setup_button_view(self):
        return SetupView(self.bot)

    async def send_setup_button_message(self, channel):
        embed = self.create_setup_button_embed()
        view = self.create_setup_button_view()
        message = await channel.send(embed=embed, view=view)
        self.setup_message_id = message.id
        self.setup_channel_id = channel.id
        self.save_setup_button_message_id(message.id, channel.id)

class SetupView(View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        self.template_veto = TemplateManager()
        self.tournament = TournamentManager()
        self.teams = TeamManager(bot)
        self.veto_start_manager = VetoManager(bot)

    @discord.ui.button(label="Gestion des templates d'événements", custom_id="mapveto_setup", style=discord.ButtonStyle.grey)
    async def mapveto_setup_button(self, interaction: discord.Interaction, button: Button):
        template_message_config.refresh_setup_message_id()
        await self.template_veto.update_setup_message(interaction.channel)
        await interaction.response.defer()

    @discord.ui.button(label="Gestion des tournois", custom_id="tournament_setup", style=discord.ButtonStyle.green)
    async def tournament_setup_button(self, interaction: discord.Interaction, button: Button):
        tournament_message_config.refresh_setup_message_id()
        await self.tournament.update_setup_message(interaction.channel)
        await interaction.response.defer()

    @discord.ui.button(label="Gestion des teams", custom_id="team_setup", style=discord.ButtonStyle.red)
    async def team_setup_button(self, interaction: discord.Interaction, button: Button):
        team_message_config = TeamManager(self.bot)  # Use self.bot to initialize
        team_message_config.refresh_setup_message_id()
        await self.teams.update_setup_message(interaction.channel)
        await interaction.response.defer()
    
    @discord.ui.button(label="Lancer un MapVeto", custom_id="veto_start_button", style=discord.ButtonStyle.primary)
    async def veto_start_button(self, interaction: discord.Interaction, button: Button):
        veto_start_manager = VetoManager(self.bot)  # Use self.bot to initialize
        veto_start_manager.refresh_veto_setup_message_id()
        await self.veto_start_manager.update_veto_setup_message(interaction.channel)
        await interaction.response.defer()

    async def refresh(self, channel_id, message_id):
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            return
        try:
            message = await channel.fetch_message(message_id)
            await message.edit(view=self)
        except discord.NotFound:
            print("Message not found.")

class MapVetoCog(commands.Cog):
    def __init__(self, bot: commands.bot):
        self.bot = bot
        self.template_veto = TemplateManager()
        self.tournament = TournamentManager()
        self.teams = TeamManager(bot)
        self.veto_start_manager = VetoManager(bot)
        self.setupbutton_config = SetupButtonConfig(bot)  # Pass the bot instance
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
        self.veto_start_manager.load_veto_setup_message_id()
        await self.veto_start_manager.update_veto_setup_message(ctx.channel)

    @commands.command(name='setup_buttons')
    @commands.has_permissions(administrator=True)
    async def setup_buttons(self, ctx):
        self.setupbutton_config.refresh_setup_button_message_id()
        await self.setupbutton_config.update_setup_button_message(ctx.channel)

    @commands.Cog.listener()
    async def on_ready(self):
        """Rafraîchit automatiquement le message de configuration lors du démarrage du bot."""
        await self.bot.wait_until_ready()
        if self.setupbutton_config.setup_channel_id and self.setupbutton_config.setup_button_message_id:
            setup_view = SetupView(self.bot)
            # Register the view with the bot
            self.bot.add_view(setup_view)
            await setup_view.refresh(self.setupbutton_config.setup_channel_id, self.setupbutton_config.setup_button_message_id)
        print("Bot is ready, views are registered.")

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MapVetoCog(bot))
    # Register the view globally at the startup
    bot.add_view(SetupView(bot))
