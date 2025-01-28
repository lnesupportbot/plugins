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
                return json.load(f)
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

webhook_config = ListenWebhook()
webhooks = webhook_config.load_webhooks()

class listenWebhookCog(commands.Cog):

    def __init__(self, bot: commands.bot):
        self.bot = bot

    @commands.command(name="lstweb_add")
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def lstweb_add(self, ctx, webhook_name: str):
        """Ajoute un webhook à écouter."""

        if webhook_name not in webhooks:
            webhook_config.create_lstwebhook(webhook_name)
            await ctx.send(f"✅ Webhook `{webhook_name}` ajouté avec succès !")
            return
        else:
            await ctx.send(f"🔄 Le webhook `{webhook_name}` est déjà enregistré.")

    @commands.command(name="lstweb_remove")
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def lstweb_remove(self, ctx, webhook_name: str):
        """Supprime un webhook de la liste."""
        if webhook_name in webhooks:
            del webhooks[webhook_name]
            webhook_config.save_webhooks()
            await ctx.send(f"❌ Webhook `{webhook_name}` supprimé avec succès !")
        else:
            await ctx.send(f"⚠️ Le webhook `{webhook_name}` n'est pas enregistré.")
            
    @commands.Cog.listener()
    async def on_message(self, message):
        """Transfère les commandes envoyées par des webhooks enregistrés."""
        # Affiche dans la console les informations pertinentes
        if message.author.bot:
            print(f"Message reçu - Author.bot: {message.author.bot}, Author.name: {message.author.name} ID : {message.author.id}")

        # Vérifie que le message provient d'un bot et que le nom de l'auteur est dans la liste des webhooks
        if message.author.bot:
            if message.author.name in webhooks:
                # Transforme le message du webhook en commande du bot
                print(f"Webhook détecté : name : {message.author.name} ID : {message.author.id}")
                ctx = await self.bot.get_context(message)
                print(f"le message est {message}")
                print(f"le ctx est {ctx}")
                if ctx.valid:
                    print(f"le ctx est {ctx}")
                    # Exécute la commande comme si elle venait d'un utilisateur
                    await self.bot.invoke(ctx)
                return
            
        # Force le traitement des commandes pour tous les messages, y compris ceux des webhooks
        await self.bot.process_commands(message)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(listenWebhookCog(bot))
