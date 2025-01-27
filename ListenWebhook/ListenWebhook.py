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

    def create_lstwebhook(self, webhook_id, webhook_name):
        """Ajoute un webhook avec son ID et son nom."""
        if webhook_id not in self.webhooks:
            self.webhooks[webhook_id] = {"name": webhook_name}
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
    async def lstweb_add(self, ctx, webhook_id: int):
        """Ajoute un webhook à écouter en récupérant automatiquement son nom."""
        webhook_id = str(webhook_id)  # Convertit l'ID en chaîne pour le stockage JSON
        
        # Tente de récupérer le webhook à partir de l'API Discord
        try:
            webhook = await self.bot.fetch_webhook(webhook_id)
            webhook_name = webhook.name  # Récupère le nom du webhook
            print(f"le nom du webhook est : {webhook_name}")
        except discord.NotFound:
            await ctx.send(f"⚠️ Aucun webhook trouvé avec l'ID `{webhook_id}`.")
            return
        except discord.Forbidden:
            await ctx.send("⚠️ Le bot n'a pas les permissions nécessaires pour accéder à ce webhook.")
            return
        except Exception as e:
            await ctx.send(f"❌ Une erreur s'est produite : {e}")
            return

        # Ajoute le webhook à la liste si non enregistré
        if webhook_id not in webhooks:
            webhook_config.create_lstwebhook(webhook_id, webhook_name)
            await ctx.send(f"✅ Webhook ajouté avec succès : `{webhook_name}` (ID : `{webhook_id}`)")
        else:
            await ctx.send(f"🔄 Le webhook avec l'ID `{webhook_id}` est déjà enregistré.")

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
        print(f"Message reçu - Author.bot: {message.author.bot}, Author.name: {message.author.name} ID : {message.author.id}")

        # Vérifie que le message provient d'un bot et que le nom de l'auteur est dans la liste des webhooks
        if message.author.bot:
            if message.author.id in webhooks:
                # Transforme le message du webhook en commande du bot
                print(f"Webhook détecté : name : {message.author.name} ID : {message.author.id}")
                ctx = await self.bot.get_context(message)
                print(f"Contexte généré : {ctx}")
                print(f"Contexte valide : {ctx.valid}")
                if ctx.valid:
                    print(f"le ctx est {ctx}")
                    # Exécute la commande comme si elle venait d'un utilisateur
                    await self.bot.invoke(ctx)
                return


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(listenWebhookCog(bot))
