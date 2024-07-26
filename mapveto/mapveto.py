import discord # type: ignore
from discord.ext import commands # type: ignore
import asyncio
import json
import os

from core import checks
from core.models import PermissionLevel

from .config import veto_config  # Importer veto_config depuis config.py
from .templateveto import (
    MapVetoConfig,
    VetoCreateModal,
    VetoEditModal,
    MapButton,
    send_ticket_message,
    MapVeto,
    ListButton,
    CreateButton,
    EditButton,
    DeleteButton,
    ConfirmDeleteButton
)

from .tournament import (
    TournamentConfig,
    TournamentCreateModal,
    TournamentEditModal,
    TournamentDeleteButton,
    TournamentCog,
    ListTournamentsButton,
    CreateTournamentButton,
    EditTournamentButton,
    DeleteTournamentButton,
    ConfirmTournamentDeleteButton
)

tournament_config = TournamentConfig()
veto_config = MapVetoConfig()
vetos = {}

class MapVetoCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.setup_message_id = None
        self.load_setup_message_id()

    def save_setup_message_id(self, message_id):
        with open('setup_message_id.json', 'w') as f:
            json.dump({'setup_message_id': message_id}, f)

    def load_setup_message_id(self):
        if os.path.exists('setup_message_id.json'):
            with open('setup_message_id.json', 'r') as f:
                data = json.load(f)
                self.setup_message_id = data.get('setup_message_id')

    async def update_setup_message(self, channel):
        if self.setup_message_id:
            try:
                message = await channel.fetch_message(self.setup_message_id)
                await message.edit(embed=self.create_setup_embed(), view=self.create_setup_view())
            except discord.NotFound:
                await self.send_setup_message(channel)
        else:
            await self.send_setup_message(channel)

    async def send_setup_message(self, channel):
        message = await channel.send(embed=self.create_setup_embed(), view=self.create_setup_view())
        self.setup_message_id = message.id
        self.save_setup_message_id(message.id)

    def create_setup_embed(self):
        embed = discord.Embed(
            title="Configuration des Templates de Veto",
            description="Utilisez les boutons ci-dessous pour gérer les templates de veto.",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="Créer un Template",
            value="Cliquez sur le bouton pour créer un nouveau template de veto.",
            inline=False
        )
        embed.add_field(
            name="Éditer un Template",
            value="Cliquez sur le bouton pour éditer un template de veto existant.",
            inline=False
        )
        embed.add_field(
            name="Supprimer un Template",
            value="Cliquez sur le bouton pour supprimer un template de veto existant.",
            inline=False
        )
        embed.add_field(
            name="Liste des Templates",
            value="Cliquez sur le bouton pour voir la liste des templates enregistrés.",
            inline=False
        )
        return embed

    def create_setup_view(self):
        view = discord.ui.View()
        view.add_item(ListButton())
        view.add_item(CreateButton())
        view.add_item(EditButton())
        view.add_item(DeleteButton())
        return view

    @commands.command(name='mapveto_setup')
    @commands.has_permissions(administrator=True)
    async def mapveto_setup(self, ctx):
        """Crée ou met à jour le message avec les boutons pour gérer les templates de veto."""
        await self.update_setup_message(ctx.channel)

    @commands.command()
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def start_mapveto(self, ctx, name: str, team_a_id: int, team_a_name: str, team_b_id: int, team_b_name: str):
        """Démarre un veto et envoie des messages en DM aux équipes spécifiées."""
        if name not in veto_config.vetos:
            await ctx.send(f"Aucun template de veto trouvé avec le nom '{name}'.")
            return

        veto = MapVeto(name, veto_config.vetos[name]["maps"], team_a_id, team_a_name, team_b_id, team_b_name, veto_config.vetos[name]["rules"], ctx.channel, self.bot)
        vetos[name] = veto
    
        await send_ticket_message(self.bot, veto, ctx.channel)

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

async def setup(bot):
    await bot.add_cog(MapVetoCog(bot))
