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
        
        class SetupView(View):
            def __init__(self):
                super().__init__()

                self.add_item(Button(label="Gestion des templates d'événements", custom_id="mapveto_setup", style=discord.ButtonStyle.blurple))
                self.add_item(Button(label="Gestion des tournois", custom_id="tournament_setup", style=discord.ButtonStyle.green))
                self.add_item(Button(label="Gestion des teams", custom_id="team_setup", style=discord.ButtonStyle.red))

            async def interaction_check(self, interaction: discord.Interaction) -> bool:
                return interaction.user == ctx.author

            @discord.ui.button(label="Gestion des templates d'événements", custom_id="mapveto_setup", style=discord.ButtonStyle.blurple)
            async def mapveto_setup_button(self, interaction: discord.Interaction, button: Button):
                await ctx.invoke(self.mapveto_setup)

            @discord.ui.button(label="Gestion des tournois", custom_id="tournament_setup", style=discord.ButtonStyle.green)
            async def tournament_setup_button(self, interaction: discord.Interaction, button: Button):
                await ctx.invoke(self.tournament_setup)

            @discord.ui.button(label="Gestion des teams", custom_id="team_setup", style=discord.ButtonStyle.red)
            async def team_setup_button(self, interaction: discord.Interaction, button: Button):
                await ctx.invoke(self.team_setup)

        embed = discord.Embed(
            title="Configuration des Événements",
            description="Utilisez les boutons ci-dessous pour configurer les différents éléments.",
            color=discord.Color.blue()
        )
        
        await ctx.send(embed=embed, view=SetupView(timeout=None))

async def setup(bot):
    await bot.add_cog(MapVetoCog(bot))
