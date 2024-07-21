import discord
from discord.ext import commands
import random
import pymongo
import os
from dotenv import load_dotenv

from core import checks
from core.models import PermissionLevel

# Charger les variables d'environnement depuis le fichier .env
load_dotenv()

# Configurer la connexion à MongoDB
CONNECTION_URI = os.getenv('CONNECTION_URI')
client = pymongo.MongoClient(CONNECTION_URI)
db = client['veto_db']
templates_collection = db['templates']
vetos_collection = db['vetos']

class MapVetoConfig:
    def __init__(self):
        pass

    def create_veto(self, name):
        if templates_collection.find_one({"name": name}):
            return False
        templates_collection.insert_one({
            "name": name,
            "maps": [],
            "rules": []
        })
        return True

    def add_maps(self, name, map_names):
        result = templates_collection.find_one_and_update(
            {"name": name},
            {"$addToSet": {"maps": {"$each": map_names}}},
            return_document=pymongo.ReturnDocument.AFTER
        )
        return result is not None

    def set_rules(self, name, rules):
        result = templates_collection.find_one_and_update(
            {"name": name},
            {"$set": {"rules": rules.split()}},
            return_document=pymongo.ReturnDocument.AFTER
        )
        return result is not None

    def delete_veto(self, name):
        result = templates_collection.delete_one({"name": name})
        return result.deleted_count > 0

    def get_veto(self, name):
        return templates_collection.find_one({"name": name})

class MapButton(discord.ui.Button):
    def __init__(self, label, veto_name, action_type, channel):
        super().__init__(label=label, style=discord.ButtonStyle.primary, custom_id=f"{veto_name}_{label}_{action_type}")
        self.veto_name = veto_name
        self.action_type = action_type
        self.channel = channel

    async def callback(self, interaction: discord.Interaction):
        veto = vetos_collection.find_one({"name": self.veto_name})
        if not veto:
            await interaction.response.send_message("Veto non trouvé.", ephemeral=True)
            return
        
        if veto.get('paused', False) or veto.get('stopped', False):
            await interaction.response.send_message("Le veto est actuellement en pause ou a été arrêté.", ephemeral=True)
            return
        
        if interaction.user.id != veto['current_turn']:
            await interaction.response.send_message("Ce n'est pas votre tour.", ephemeral=True)
            return

        if self.action_type == "ban":
            veto['maps'].remove(self.label)
            veto.setdefault('banned_maps', []).append(self.label)
            message = f"Map {self.label} bannie par {interaction.user.mention}."
        elif self.action_type == "pick":
            veto['maps'].remove(self.label)
            veto.setdefault('picked_maps', []).append(self.label)
            message = f"**Map {self.label} choisie par {interaction.user.mention}.**"
        elif self.action_type == "side":
            veto.setdefault('picked_maps', []).append(f"{self.label} choisi")
            message = f"*Side {self.label} choisi par {interaction.user.mention}.*"

        vetos_collection.update_one({"name": self.veto_name}, {"$set": veto})

        await interaction.response.send_message(message)
        await self.channel.send(message)

        opponent_user_id = veto['team_b_id'] if interaction.user.id == veto['team_a_id'] else veto['team_a_id']
        opponent_user = interaction.client.get_user(opponent_user_id)
        if opponent_user:
            await opponent_user.send(message)

        veto['current_turn'] = veto['team_a_id'] if veto['current_turn'] == veto['team_b_id'] else veto['team_b_id']
        vetos_collection.update_one({"name": self.veto_name}, {"$set": veto})

        if veto['current_turn'] is not None:
            await send_ticket_message(interaction.client, veto, self.channel)
        else:
            await interaction.user.send("Le veto est terminé!")
            await self.channel.send("Le veto est terminé!")

        # Disable the button and update the message
        view = interaction.message.view
        for item in view.children:
            if isinstance(item, discord.ui.Button) and item.custom_id == self.custom_id:
                item.disabled = True
        await interaction.message.edit(view=view)

async def send_ticket_message(bot, veto, channel):
    action = veto.get('rules')[veto.get('current_action', 0)]
    if action is None:
        return

    current_user = bot.get_user(veto['current_turn'])
    if not current_user:
        return

    components = []
    if action == "Side":
        components.append(MapButton(label="Attaque", veto_name=veto['name'], action_type="side", channel=channel))
        components.append(MapButton(label="Défense", veto_name=veto['name'], action_type="side", channel=channel))
    else:
        for map_name in veto['maps']:
            components.append(MapButton(label=map_name, veto_name=veto['name'], action_type=action.lower(), channel=channel))

    view = discord.ui.View(timeout=60)
    for component in components:
        view.add_item(component)

    try:
        await current_user.send(f"{current_user.mention}, c'est votre tour de {action} une map.", view=view)
    except discord.Forbidden:
        print(f"Cannot DM user {current_user.id}")

    async def timeout():
        await view.wait()
        if not view.is_finished():
            random_map = random.choice(veto['maps'])
            if action == "ban":
                veto['maps'].remove(random_map)
                veto.setdefault('banned_maps', []).append(random_map)
                await current_user.send(f"Map {random_map} bannie automatiquement.")
            elif action == "pick":
                veto['maps'].remove(random_map)
                veto.setdefault('picked_maps', []).append(random_map)
                await current_user.send(f"Map {random_map} choisie automatiquement.")
            vetos_collection.update_one({"name": veto['name']}, {"$set": veto})

            veto['current_turn'] = veto['team_a_id'] if veto['current_turn'] == veto['team_b_id'] else veto['team_b_id']
            if veto['current_turn'] is not None:
                await send_ticket_message(bot, veto, channel)
            else:
                embed = discord.Embed(title="Le Map Veto est terminé!", description="Voici le résumé des choix de cartes et des côtés.")
                for i, map_name in enumerate(veto.get('picked_maps', [])):
                    team_name = veto['team_a_name'] if i % 2 == 0 else veto['team_b_name']
                    side = veto.get('side_choices', {}).get(veto['team_a_id'] if i % 2 == 0 else veto['team_b_id'], "Non choisi")
                    embed.add_field(name=f"Carte {i + 1}", value=f"{map_name} / {team_name} ({side})", inline=False)

                for user_id in [veto['team_a_id'], veto['team_b_id']]:
                    user = bot.get_user(user_id)
                    if user:
                        await user.send(embed=embed)
                await channel.send(embed=embed)

    bot.loop.create_task(timeout())

class MapVeto:
    def __init__(self, name, maps, team_a_id, team_b_id, rules):
        self.name = name
        self.maps = maps
        self.team_a_id = team_a_id
        self.team_b_id = team_b_id
        self.rules = rules
        self.current_turn = team_a_id
        self.current_action = 0
        self.picked_maps = []
        self.banned_maps = []
        self.paused = False
        self.stopped = False
        self.side_choices = {}

    def current_action_type(self):
        if self.current_action < len(self.rules):
            return self.rules[self.current_action]
        return None

    def get_current_turn(self):
        return self.current_turn

    def next_turn(self):
        if self.stopped or self.paused:
            return

        if self.current_action < len(self.rules):
            current_rule = self.rules[self.current_action]
            if current_rule == "Continue":
                return
            else:
                self.current_turn = self.team_a_id if self.current_turn == self.team_b_id else self.team_b_id
                self.current_action += 1

                while self.current_action < len(self.rules) and self.rules[self.current_action] == "Continue":
                    self.current_action += 1
                    if self.current_action < len(self.rules) and self.rules[self.current_action] != "Continue":
                        self.current_turn = self.team_a_id if self.current_turn == self.team_b_id else self.team_b_id
        else:
            self.stopped = True

    def ban_map(self, map_name):
        if map_name in self.maps:
            self.maps.remove(map_name)
            self.banned_maps.append(map_name)

    def pick_map(self, map_name):
        if map_name in self.maps:
            self.maps.remove(map_name)
            self.picked_maps.append(map_name)

    def pick_side(self, side):
        self.picked_maps.append(f"{side} choisi")

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def stop(self):
        self.stopped = True
        self.paused = False

class MapVetoCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.veto_config = MapVetoConfig()

    @commands.group(name='mapveto', invoke_without_command=True)
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def mapveto(self, ctx):
        """Affiche les options de gestion des templates de veto."""
        await ctx.send_help(ctx.command)

    @mapveto.command(name='create')
    @checks.has_permissions(PermissionLevel.MODERATOR)
    async def mapveto_create(self, ctx, name: str):
        """Crée un template de veto avec le nom donné."""
        if self.veto_config.create_veto(name):
            await ctx.send(f"Template de veto '{name}' créé avec succès.")
        else:
            await ctx.send(f"Un template de veto avec le nom '{name}' existe déjà.")

    @mapveto.command(name='add')
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def add_map(self, ctx, name: str, *map_names):
        """Ajoute plusieurs maps au template de veto spécifié."""
        if self.veto_config.add_maps(name, map_names):
            await ctx.send(f"Maps ajoutées au template de veto '{name}' : {', '.join(map_names)}.")
        else:
            await ctx.send(f"Aucun template de veto trouvé avec le nom '{name}'.")

    @mapveto.command(name='rules')
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def mapveto_rules(self, ctx, name: str, *, rules: str):
        """Définit les règles pour le template de veto spécifié."""
        valid_rules = {"Ban", "Pick", "Side", "Continue"}
        rules_list = rules.split()
        if all(rule in valid_rules for rule in rules_list):
            if self.veto_config.set_rules(name, rules):
                await ctx.send(f"Règles définies pour le template de veto '{name}' : {rules}.")
            else:
                await ctx.send(f"Aucun template de veto trouvé avec le nom '{name}'.")
        else:
            await ctx.send(f"Règles invalides. Les règles valides sont : {', '.join(valid_rules)}.")

    @mapveto.command(name='delete')
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def mapveto_delete(self, ctx, name: str):
        """Supprime le template de veto spécifié."""
        if self.veto_config.delete_veto(name):
            await ctx.send(f"Template de veto '{name}' supprimé avec succès.")
        else:
            await ctx.send(f"Aucun template de veto trouvé avec le nom '{name}'.")

    @mapveto.command(name='list')
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def mapveto_list(self, ctx):
        """Liste tous les templates de veto disponibles."""
        templates = templates_collection.find()
        if templates:
            await ctx.send(f"Templates de veto disponibles : {', '.join(t['name'] for t in templates)}")
        else:
            await ctx.send("Aucun template de veto disponible.")

    @commands.command()
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def start_mapveto(self, ctx, name: str, team_a_id: int, team_b_id: int):
        """Démarre un veto et envoie des messages en DM aux équipes spécifiées."""
        veto = self.veto_config.get_veto(name)
        if not veto:
            await ctx.send(f"Aucun template de veto trouvé avec le nom '{name}'.")
            return

        veto['team_a_id'] = team_a_id
        veto['team_b_id'] = team_b_id
        veto['current_turn'] = team_a_id
        veto['current_action'] = 0
        veto['paused'] = False
        veto['stopped'] = False

        vetos_collection.replace_one({"name": name}, veto, upsert=True)

        await send_ticket_message(self.bot, veto, ctx.channel)

    @commands.command()
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def pause_mapveto(self, ctx, name: str):
        """Met en pause le veto spécifié."""
        veto = vetos_collection.find_one({"name": name})
        if not veto:
            await ctx.send(f"Aucun veto en cours avec le nom '{name}'.")
            return

        veto['paused'] = True
        vetos_collection.update_one({"name": name}, {"$set": veto})
        await ctx.send(f"Le veto '{name}' a été mis en pause.")

    @commands.command()
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def resume_mapveto(self, ctx, name: str):
        """Reprend le veto spécifié."""
        veto = vetos_collection.find_one({"name": name})
        if not veto:
            await ctx.send(f"Aucun veto en cours avec le nom '{name}'.")
            return

        veto['paused'] = False
        vetos_collection.update_one({"name": name}, {"$set": veto})
        await ctx.send(f"Le veto '{name}' a repris.")

    @commands.command()
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def stop_mapveto(self, ctx, name: str):
        """Arrête complètement le veto spécifié et le supprime des enregistrements."""
        veto = vetos_collection.find_one({"name": name})
        if not veto:
            await ctx.send(f"Aucun veto en cours avec le nom '{name}'.")
            return

        veto['stopped'] = True
        vetos_collection.update_one({"name": name}, {"$set": veto})
        vetos_collection.delete_one({"name": name})
        await ctx.send(f"Le veto '{name}' a été arrêté et supprimé.")

    @commands.command()
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def help_veto(self, ctx):
        """Affiche les commandes disponibles pour la gestion des veto de cartes."""
        embed = discord.Embed(title="Aide pour les Commandes MapVeto", description="Voici un résumé des commandes disponibles pour la gestion des veto de cartes.")

        embed.add_field(
            name="mapveto create <name>",
            value="Crée un template de veto avec le nom donné.",
            inline=False
        )
        embed.add_field(
            name="mapveto add <name> <map_name>",
            value="Ajoute plusieurs maps au template de veto spécifié.",
            inline=False
        )
        embed.add_field(
            name="mapveto rules <name> <rules>",
            value="Définit les règles pour le template de veto spécifié.",
            inline=False
        )
        embed.add_field(
            name="mapveto delete <name>",
            value="Supprime le template de veto spécifié.",
            inline=False
        )
        embed.add_field(
            name="mapveto list",
            value="Liste tous les templates de veto disponibles.",
            inline=False
        )
        embed.add_field(
            name="start_mapveto <name> <team_a_id> <team_b_id>",
            value="Démarre un veto et envoie des messages en DM aux équipes spécifiées.",
            inline=False
        )
        embed.add_field(
            name="pause_mapveto <name>",
            value="Met en pause le veto spécifié.",
            inline=False
        )
        embed.add_field(
            name="resume_mapveto <name>",
            value="Reprend le veto spécifié.",
            inline=False
        )
        embed.add_field(
            name="stop_mapveto <name>",
            value="Arrête complètement le veto spécifié et le supprime des enregistrements.",
            inline=False
        )

        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(MapVetoCog(bot))
