import asyncio
import discord  # type: ignore
from discord.ext import commands  # type: ignore
import json
import os

from core import checks
from core.models import PermissionLevel  # type: ignore

# Chemin du fichier pour stocker les webhooks
WEBHOOK_LIST_FILE = "webhooklist.json"

# Chargement des webhooks depuis le fichier JSON
def load_webhooks():
    if os.path.exists(WEBHOOK_LIST_FILE):
        with open(WEBHOOK_LIST_FILE, "r") as file:
            return json.load(file)
    return {}

# Sauvegarde des webhooks dans le fichier JSON
def save_webhooks(webhooks):
    with open(WEBHOOK_LIST_FILE, "w") as file:
        json.dump(webhooks, file, indent=4)

# Initialisation des webhooks enregistrés
webhooks = load_webhooks()

@bot.command()
async def listenWebhook(ctx, webhook_name: str):
    """Ajoute un webhook à écouter."""
    if webhook_name in webhooks:
        await ctx.send(f"🔄 Le webhook `{webhook_name}` est déjà enregistré.")
    else:
        webhooks[webhook_name] = True
        save_webhooks(webhooks)
        await ctx.send(f"✅ Webhook `{webhook_name}` ajouté avec succès !")

@bot.command()
async def removeWebhook(ctx, webhook_name: str):
    """Supprime un webhook de la liste."""
    if webhook_name in webhooks:
        del webhooks[webhook_name]
        save_webhooks(webhooks)
        await ctx.send(f"❌ Webhook `{webhook_name}` supprimé avec succès !")
    else:
        await ctx.send(f"⚠️ Le webhook `{webhook_name}` n'est pas enregistré.")

@bot.event
async def on_message(message):
    # Vérifie si le message provient d'un webhook enregistré
    if message.author.bot and message.author.name in webhooks:
        if "purge" in message.content.lower():
            try:
                # Exemple : "purge 100"
                number_of_messages = int(message.content.split()[-1])
                await message.channel.purge(limit=number_of_messages)
                await message.channel.send(f"✅ {number_of_messages} messages supprimés.")
            except Exception as e:
                await message.channel.send(f"Erreur : {e}")
    # Permet au bot de traiter les autres commandes
    await bot.process_commands(message)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MapVetoCog(bot))
