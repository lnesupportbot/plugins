import asyncio
import discord  # type: ignore
from discord.ext import commands  # type: ignore
import json
import os

from core import checks
from core.models import PermissionLevel  # type: ignore

# Chemin du fichier pour stocker les webhooks
WEBHOOK_LIST_FILE = "webhooklist.json"

# Initialisation des webhooks enregistrés
webhooks = load_webhooks()

class listenWebhookCog(commands.Cog):
    def __init__(self, bot: commands.bot):
        self.bot = bot

    # Chargement des webhooks depuis le fichier JSON
    def load_webhooks():
        if os.path.exists(WEBHOOK_LIST_FILE):
            try:
                with open(WEBHOOK_LIST_FILE, "r") as file:
                    return json.load(file)
            except json.JSONDecodeError:
                return {}  # Retourne un dictionnaire vide en cas d'erreur
        return {}

    # Sauvegarde des webhooks dans le fichier JSON
    def save_webhooks(webhooks):
        with open(WEBHOOK_LIST_FILE, "w") as file:
            json.dump(webhooks, file, indent=4)

    @commands.command(name="add")
    @commands.has_permissions(administrator=True)
    async def listenWebhook(ctx, webhook_name: str):
        """Ajoute un webhook à écouter."""
        if not webhook_name.strip():
            await ctx.send("⚠️ Le nom du webhook ne peut pas être vide.")
            return
        if webhook_name in webhooks:
            await ctx.send(f"🔄 Le webhook `{webhook_name}` est déjà enregistré.")
        else:
            webhooks[webhook_name] = True
            save_webhooks(webhooks)
            await ctx.send(f"✅ Webhook `{webhook_name}` ajouté avec succès !")

    @commands.command(name="remove")
    @commands.has_permissions(administrator=True)
    async def removeWebhook(ctx, webhook_name: str):
        """Supprime un webhook de la liste."""
        if webhook_name in webhooks:
            del webhooks[webhook_name]
            save_webhooks(webhooks)
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
    await bot.add_cog(MapVetoCog(bot))
