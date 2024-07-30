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

# Charger les configurations de veto
veto_config = MapVetoConfig()
veto_config.load_vetos()
tournament_config = TournamentConfig()
tournaments = tournament_config.load_tournaments()
team_config = TeamConfig()
teams = team_config.load_teams()
vetos = {}


class TeamSelect(Select):
    def __init__(self, tournament_name, template_name):
        self.template_name = template_name
        self.tournament_name = tournament_name

        tournament_teams = [team for team, details in teams.items() if details["tournament"] == tournament_name]

        options = [
            discord.SelectOption(label=team, description=f"Team {team}", value=team)
            for team in tournament_teams
        ]

        super().__init__(placeholder="Choisir deux équipes...", min_values=2, max_values=2, options=options)

    async def callback(self, interaction: discord.Interaction):
        team_a_name, team_b_name = self.values
        team_a_id = int(teams[team_a_name]["captain_discord_id"])
        team_b_id = int(teams[team_b_name]["captain_discord_id"])

        maps = veto_config.vetos[self.template_name]["maps"]
        rules = veto_config.vetos[self.template_name]["rules"]

        veto = MapVeto(self.template_name, maps, team_a_id, team_a_name, team_b_id, team_b_name, rules, interaction.channel, interaction.client)
        vetos[self.template_name] = veto

        await veto.send_ticket_message(interaction.channel)


class TournamentSelect(Select):
    def __init__(self, template_name):
        self.template_name = template_name

        tournaments_set = {details["tournament"] for details in teams.values()}
        options = [
            discord.SelectOption(label=tournament, description=f"Tournament {tournament}")
            for tournament in tournaments_set
        ]

        super().__init__(placeholder="Choisir un tournoi...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        tournament_name = self.values[0]
        select = TeamSelect(tournament_name, self.template_name)
        view = View()
        view.add_item(select)
        await interaction.response.send_message(f"Tournament choisi: {tournament_name}", view=view)


class TemplateSelect(Select):
    def __init__(self):
        options = [
            discord.SelectOption(label=template, description=f"Template {template}")
            for template in veto_config.vetos.keys()
        ]
        super().__init__(placeholder="Choisir un template de veto...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        template_name = self.values[0]
        select = TournamentSelect(template_name)
        view = View()
        view.add_item(select)
        await interaction.response.send_message(f"Template choisi: {template_name}", view=view)


class MapVetoButton(Button):
    def __init__(self):
        super().__init__(label="Lancer un MapVeto", style=discord.ButtonStyle.primary)

    async def callback(self, interaction: discord.Interaction):
        select = TemplateSelect()
        view = View()
        view.add_item(select)
        await interaction.response.send_message("Choisissez un template de veto:", view=view)


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
        """Affiche un embed avec un bouton pour lancer un mapveto."""
        embed = discord.Embed(title="MapVeto", description="Cliquez sur le bouton pour lancer un mapveto.")
        view = View()
        view.add_item(MapVetoButton())
        await ctx.send(embed=embed, view=view)


async def setup(bot):
    await bot.add_cog(MapVetoCog(bot))
