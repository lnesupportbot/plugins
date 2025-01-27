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
        # Affiche le message et son contexte pour débogage
        print(f"Message reçu : {message}")
        
        # Vérifie si l'auteur est un bot (comme un webhook) et s'il est enregistré dans les webhooks
        if message.author.bot and message.author.name in webhooks:
            print(f"Webhook détecté : {message.author.name}")

            # Traite le message comme une commande
            ctx = await self.bot.get_context(message)
            print(f"Contexte généré : {ctx}")
            print(f"Contexte valide : {ctx.valid}")

            # Si le contexte est valide, invoque la commande
            if ctx.valid:
                await self.bot.invoke(ctx)
            else:
                print("Le message n'a pas été interprété comme une commande valide.")
        
        # Force le traitement des commandes pour tous les messages, y compris ceux des webhooks
        await self.bot.process_commands(message)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(listenWebhookCog(bot))
