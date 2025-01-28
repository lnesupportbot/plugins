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
        """Gère les messages provenant de webhooks enregistrés."""
        if message.author.bot:
            webhook_id = str(message.author.id)  # ID du webhook
            if webhook_id in webhooks:  # Vérifie si le webhook est enregistré
                webhook_name = webhooks[webhook_id]["name"]

                # Log du message reçu
                print(f"Message reçu du webhook : ID = {webhook_id}, Nom = {webhook_name}, Contenu = {message.content}")


            if message.content.startswith("?"):
                parts = message.content.split()
                command = parts[0][1:]  # Enlève le "!"
                args = parts[1:]
                print(f"le nombre de message est : {args}")
                await execute_webhook_command(command, args, message.channel, webhook_name)


        async def execute_webhook_command(command, args, channel, webhook_name):
            if command == "ping":
                await channel.send("Pong!")
            elif command == "hello":
                await channel.send(f"Bonjour depuis le webhook `{webhook_name}` !")
            elif command == "purge":
                try:
                    number_of_messages = int(args[0])
                    await channel.purge(limit=number_of_messages)
                    await send_temporary_message(message.channel, f"✅ {number_of_messages} messages supprimés par le webhook `{webhook_name}`.")
                except (ValueError, IndexError):
                    await send_temporary_message(message.channel, "⚠️ Veuillez spécifier un nombre valide de messages à supprimer.")

                        # Ajoutez ici d'autres commandes spécifiques selon vos besoins

        async def send_temporary_message(channel, content, delay=5):
            """Envoie un message temporaire dans le canal."""
            msg = await channel.send(content)
            await asyncio.sleep(delay)
            await msg.delete()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(listenWebhookCog(bot))
