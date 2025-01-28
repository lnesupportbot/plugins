import asyncio
import discord  # type: ignore
from discord.ext import commands  # type: ignore
import json
import os

from core import checks
from core.models import PermissionLevel  # type: ignore


class ListenWebhook:
    def __init__(self, filename="webhooklist.json"):
        self.filename = os.path.join(os.path.dirname(__file__), ".", filename)
        self.webhooks = self.load_webhooks()

    def load_webhooks(self):
        """Charge les webhooks enregistrés depuis un fichier JSON."""
        if os.path.exists(self.filename):
            with open(self.filename, "r") as f:
                return json.load(f)
        return {}

    def save_webhooks(self):
        """Sauvegarde les webhooks dans un fichier JSON."""
        with open(self.filename, "w") as f:
            json.dump(self.webhooks, f, indent=4)

    def create_lstwebhook(self, webhook_id, webhook_data):
        """Ajoute un webhook avec son ID et son nom."""
        if webhook_id not in self.webhooks:
            self.webhooks[webhook_id] = webhook_data
            self.save_webhooks()
            return True
        return False


webhook_config = ListenWebhook()

class listenWebhookCog(commands.Cog):
    def __init__(self, bot: commands.bot):
        self.bot = bot

    @commands.command(name="lstweb_add")
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def lstweb_add(self, ctx, webhook_id: int):
        """Ajoute un webhook à écouter."""
        webhook_config.load_webhooks()
        webhook_id = str(webhook_id)  # Convertit l'ID en chaîne pour le stockage JSON

        try:
            webhook = await self.bot.fetch_webhook(webhook_id)
            webhook_name = webhook.name  # Récupère le nom du webhook

            # Récupère la catégorie et le nom du canal
            channel_name = webhook.channel.name if webhook.channel else "Inconnu"
            category_name = (
                webhook.channel.category.name if webhook.channel and webhook.channel.category else "Sans catégorie"
            )

        except discord.NotFound:
            await ctx.send(f"⚠️ Aucun webhook trouvé avec l'ID `{webhook_id}`.")
            return
        except discord.Forbidden:
            await ctx.send("⚠️ Le bot n'a pas les permissions nécessaires pour accéder à ce webhook.")
            return
        except Exception as e:
            await ctx.send(f"❌ Une erreur s'est produite : {e}")
            return

        # Ajoute le webhook avec les informations supplémentaires
        if webhook_id not in webhook_config.webhooks:
            webhook_config.create_lstwebhook(
                webhook_id,
                {
                    "name": webhook_name,
                    "channel": channel_name,
                    "category": category_name,
                },
            )
            await ctx.send(
                f"✅ Webhook ajouté avec succès : `{webhook_name}` (ID : `{webhook_id}`) dans le canal `{channel_name}` de la catégorie `{category_name}`."
            )
        else:
            await ctx.send(f"🔄 Le webhook avec l'ID `{webhook_id}` est déjà enregistré.")

    @commands.command(name="lstweb_list")
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def lstweb_list(self, ctx):
        """
        Affiche la liste des webhooks enregistrés.
        """
        if not webhook_config.webhooks:
            await ctx.send("⚠️ Aucun webhook n'est enregistré pour le moment.")
            return

        # Construire une liste des webhooks enregistrés
        description = []
        for webhook_id, data in webhook_config.webhooks.items():
            name = data.get("name", "Inconnu")
            channel = data.get("channel", "Inconnu")
            category = data.get("category", "Inconnu")
            description.append(f"**Nom**: `{name}`\n**ID**: `{webhook_id}`\n**Canal**: `{channel}`\n**Catégorie**: `{category}`\n")

        embed = discord.Embed(
            title="📜 Liste des Webhooks enregistrés",
            description="\n\n".join(description),
            color=discord.Color.blue(),
        )

        await ctx.send(embed=embed)


    @commands.command(name="lstweb_remove")
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def lstweb_remove(self, ctx, webhook_id: int):
        """Supprime un webhook de la liste."""
        webhook_id = str(webhook_id)  # Convertit l'ID en chaîne pour correspondre au stockage JSON

        if webhook_id in webhook_config.webhooks:
            # Récupère les informations avant suppression
            webhook_data = webhook_config.webhooks[webhook_id]
            webhook_name = webhook_data.get("name", "Inconnu")
            channel_name = webhook_data.get("channel", "Inconnu")
            category_name = webhook_data.get("category", "Sans catégorie")

            # Supprime le webhook de la liste
            del webhook_config.webhooks[webhook_id]
            webhook_config.save_webhooks()

            # Envoie un message de confirmation avec les détails
            await ctx.send(
                f"❌ Webhook `{webhook_name}` supprimé avec succès ! "
                f"(Canal : `{channel_name}`, Catégorie : `{category_name}`)"
            )
        else:
            await ctx.send(f"⚠️ Le webhook avec l'ID `{webhook_id}` n'est pas enregistré.")

    @commands.Cog.listener()
    async def on_message(self, message):
        """Gère les messages provenant de webhooks enregistrés."""
        if message.author.bot:
            webhook_id = str(message.author.id)  # ID du webhook
            if webhook_id in webhook_config.webhooks:  # Vérifie si le webhook est enregistré
                webhook_name = webhook_config.webhooks[webhook_id]["name"]

                # Log du message reçu avec nom du canal et catégorie
                channel_name = message.channel.name
                category_name = message.channel.category.name if message.channel.category else "Aucune catégorie"
                print(
                    f"Message reçu du webhook : ID = {webhook_id}, Nom = {webhook_name}, "
                    f"Contenu = {message.content}, Canal = {channel_name}, Catégorie = {category_name}"
                )

                if message.content.startswith("!"):
                    parts = message.content.split()
                    command = parts[0][1:]  # Enlève le "!"
                    args = parts[1:]
                    await self.execute_webhook_command(command, args, message.channel, webhook_name)

    async def execute_webhook_command(self, command, args, channel, webhook_name):
        """Exécute une commande en fonction du message reçu."""
        if command == "ping":
            await self.send_temporary_message(channel, "Pong!")
        elif command == "hello":
            await self.send_temporary_message(channel, f"Bonjour depuis le webhook `{webhook_name}` !")
        elif command == "purge":
            try:
                if args:  # Si un argument est donné
                    number_of_messages = int(args[0])
                else:  # Sinon, calcule tous les messages présents
                    number_of_messages = 0
                    async for _ in channel.history(limit=None):
                        number_of_messages += 1

                await channel.purge(limit=number_of_messages)
                await self.send_temporary_message(
                    channel, f"✅ {number_of_messages} messages supprimés."
                )
            except (ValueError, IndexError):
                await self.send_temporary_message(channel, "⚠️ Une erreur est survenue lors de la suppression.")

        else:
            await self.send_temporary_message(channel, f"Commande inconnue : `{command}`")

    async def send_temporary_message(self, channel, content, delay=5):
        """Envoie un message temporaire dans le canal."""
        msg = await channel.send(content)
        await asyncio.sleep(delay)
        await msg.delete()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(listenWebhookCog(bot))
