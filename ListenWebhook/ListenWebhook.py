import asyncio
import discord  # type: ignore
from discord.ext import commands  # type: ignore
import json
import os

from core import checks
from core.models import PermissionLevel  # type: ignore

class ListenWebhook:
    def __init__(self, bot, filename="webhooklist.json"):
        self.bot = bot
        self.filename = os.path.join(os.path.dirname(__file__), '.', filename)


    def load_webhooks(self):
        """Charge les webhooks enregistrés depuis un fichier JSON."""
        if os.path.exists(filename):
            try:
                with open(filename, "r") as file:
                    return json.load(file)
            except json.JSONDecodeError:
                return {}  # Retourne un dictionnaire vide si le JSON est corrompu
        return {}

    def save_webhooks(self):
        """Sauvegarde les webhooks dans un fichier JSON."""
        with open(filename, "w") as file:
            json.dump(self.webhooks, file, indent=4)

class listenWebhookCog(commands.Cog):

    def __init__(self, bot: commands.bot):
        self.bot = bot
        self.webhooks = ListenWebhook.load_webhooks()

    @commands.command(name="lstweb_add")
    @commands.has_permissions(administrator=True)
    async def lstweb_add(self, ctx, webhook_name: str):
        """Ajoute un webhook à écouter."""
        if not webhook_name.strip():
            await ctx.send("⚠️ Le nom du webhook ne peut pas être vide.")
            return

        if webhook_name in self.webhooks:
            await ctx.send(f"🔄 Le webhook `{webhook_name}` est déjà enregistré.")
        else:
            self.webhooks[webhook_name] = True
            self.save_webhooks()
            await ctx.send(f"✅ Webhook `{webhook_name}` ajouté avec succès !")

    @commands.command(name="lstweb_remove")
    @commands.has_permissions(administrator=True)
    async def lstweb_remove(self, ctx, webhook_name: str):
        """Supprime un webhook de la liste."""
        if webhook_name in self.webhooks:
            del self.webhooks[webhook_name]
            self.save_webhooks()
            await ctx.send(f"❌ Webhook `{webhook_name}` supprimé avec succès !")
        else:
            await ctx.send(f"⚠️ Le webhook `{webhook_name}` n'est pas enregistré.")

    @commands.Cog.listener()
    async def on_message(self, message):
        """Gère les messages provenant de webhooks enregistrés."""
        if message.author.bot and message.author.name in self.webhooks:
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
