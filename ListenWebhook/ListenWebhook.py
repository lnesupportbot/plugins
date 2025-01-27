import asyncio
import discord  # type: ignore
from discord.ext import commands  # type: ignore
import json
import os

from core import checks
from core.models import PermissionLevel  # type: ignore

class ListenWebhook:
    def __init__(self, filename="webhooklist.json"):
        self.filename = os.path.join(os.path.dirname(__file__), '.', filename)
        self.webhooks = self.load_webhooks()

    def load_webhooks(self):
        """Charge les webhooks enregistrés depuis un fichier JSON."""
        if os.path.exists(self.filename):
            with open(self.filename, "r") as f:
                data = json.load(f)
        return{}

    def save_webhooks(self):
        """Sauvegarde les webhooks dans un fichier JSON."""
        with open(self.filename, "w") as f:
            json.dump(self.webhooks, f, indent=4)

    def create_lstwebhook(self, webhook_name):
        if webhook_name not in self.webhooks:
            self.webhooks[webhook_name] = {}
            self.save_webhooks()
            return True
        return False

webhooks = ListenWebhook()

class listenWebhookCog(commands.Cog):

    def __init__(self, bot: commands.bot):
        self.bot = bot

    @commands.command(name="lstweb_add")
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def lstweb_add(self, ctx, webhook_name: str):
        """Ajoute un webhook à écouter."""

        if webhook_name not in webhooks.load_webhooks():
            webhooks.create_lstwebhook(webhook_name)
            await ctx.send(f"✅ Webhook `{webhook_name}` ajouté avec succès !", ephemeral=True)
        else:
            await ctx.send(f"🔄 Le webhook `{webhook_name}` est déjà enregistré.")


    @commands.command(name="lstweb_remove")
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def lstweb_remove(self, ctx, webhook_name: str):
        """Supprime un webhook de la liste."""
        if webhook_name in webhooks.load_webhooks():
            del webhooks.load_webhooks()[webhook_name]
            webhooks.save_webhooks()
            await ctx.send(f"❌ Webhook `{webhook_name}` supprimé avec succès !")
        else:
            await ctx.send(f"⚠️ Le webhook `{webhook_name}` n'est pas enregistré.")

    @commands.Cog.listener()
    async def on_message(self, message):
        """Gère les messages provenant de webhooks enregistrés."""
        if message.author.bot and message.author.name in webhooks.load_webhooks():
            if "purge" in message.content.lower():
                try:
                    if message.content.split()[-1].isdigit():
                        number_of_messages = int(message.content.split()[-1])
                        await message.channel.purge(limit=number_of_messages)
                        await message.channel.send(f"✅ {number_of_messages} messages supprimés.")
                    else:
                        await message.channel.send("⚠️ Le nombre de messages à purger est invalide.")
                except Exception as e:
                    await message.channel.send(f"Erreur : {e}")
        await self.bot.process_commands(message)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(listenWebhookCog(bot))
