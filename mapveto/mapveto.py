import discord
from discord.ext import commands
import random
from pymongo import MongoClient
from core import checks
from core.models import PermissionLevel

# Configuration MongoDB
class MapVetoConfig:
    def __init__(self, db):
        self.db = db

    async def create_veto(self, name):
        if await self.db.find_one({"name": name}):
            return False
        await self.db.insert_one({"name": name, "maps": [], "rules": []})
        return True

    async def add_maps(self, name, map_names):
        result = await self.db.find_one_and_update(
            {"name": name},
            {"$addToSet": {"maps": {"$each": map_names}}},
            return_document=True
        )
        return result is not None

    async def set_rules(self, name, rules):
        result = await self.db.find_one_and_update(
            {"name": name},
            {"$set": {"rules": rules.split()}},
            return_document=True
        )
        return result is not None

    async def delete_veto(self, name):
        result = await self.db.delete_one({"name": name})
        return result.deleted_count > 0

    async def get_veto(self, name):
        return await self.db.find_one({"name": name})

    async def list_vetos(self):
        templates = await self.db.find({}).to_list(length=None)
        return [template["name"] for template in templates]

# Logique du veto
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
                # Allow the same team to play again
                return
            else:
                # Normal action, switch turn
                self.current_turn = self.team_a_id if self.current_turn == self.team_b_id else self.team_b_id
                self.current_action += 1

                # Handle consecutive "Continue" rules
                while self.current_action < len(self.rules) and self.rules[self.current_action] == "Continue":
                    self.current_action += 1
                    if self.current_action < len(self.rules) and self.rules[self.current_action] != "Continue":
                        # Switch turn after exiting consecutive "Continue"
                        self.current_turn = self.team_a_id if self.current_turn == self.team_b_id else self.team_b_id
        else:
            # No more actions, end the veto
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

# Interaction des boutons
class MapButton(discord.ui.Button):
    def __init__(self, label, veto_name, action_type, channel):
        super().__init__(label=label, style=discord.ButtonStyle.primary, custom_id=f"{veto_name}_{label}_{action_type}")
        self.veto_name = veto_name
        self.action_type = action_type
        self.channel = channel

    async def callback(self, interaction: discord.Interaction):
        veto = vetos.get(self.veto_name)
        if not veto:
            await interaction.response.send_message("Veto non trouvé.", ephemeral=True)
            return
        
        if veto.paused or veto.stopped:
            await interaction.response.send_message("Le veto est actuellement en pause ou a été arrêté.", ephemeral=True)
            return
        
        if interaction.user.id != veto.get_current_turn():
            await interaction.response.send_message("Ce n'est pas votre tour.", ephemeral=True)
            return

        if self.action_type == "ban":
            veto.ban_map(self.label)
            message = f"Map {self.label} bannie par {interaction.user.mention}."
        elif self.action_type == "pick":
            veto.pick_map(self.label)
            message = f"**Map {self.label} choisie par {interaction.user.mention}.**"
        elif self.action_type == "side":
            veto.pick_side(self.label)
            message = f"*Side {self.label} choisi par {interaction.user.mention}.*"

        await interaction.response.send_message(message)
        await self.channel.send(message)

        opponent_user = interaction.client.get_user(veto.team_b_id if interaction.user.id == veto.team_a_id else veto.team_b_id)
        if opponent_user:
            await opponent_user.send(message)

        veto.next_turn()
        if veto.current_turn is not None:
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

# Envoi des messages de veto
async def send_ticket_message(bot, veto, channel):
    action = veto.current_action_type()
    if action is None:
        return

    current_user = bot.get_user(veto.get_current_turn())
    if not current_user:
        return

    components = []
    if action == "Side":
        components.append(MapButton(label="Attaque", veto_name=veto.name, action_type="side", channel=channel))
        components.append(MapButton(label="Défense", veto_name=veto.name, action_type="side", channel=channel))
    else:
        for map_name in veto.maps:
            components.append(MapButton(label=map_name, veto_name=veto.name, action_type=action.lower(), channel=channel))

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
            random_map = random.choice(veto.maps)
            if action == "ban":
                veto.ban_map(random_map)
                await current_user.send(f"Map {random_map} bannie automatiquement.")
            elif action == "pick":
                veto.pick_map(random_map)
                await current_user.send(f"Map {random_map} choisie automatiquement.")
            veto.next_turn()
            if veto.current_turn is not None:
                await send_ticket_message(bot, veto, channel)
            else:
                await current_user.send("Le veto est terminé!")
                await channel.send("Le veto est terminé!")

    bot.loop.create_task(timeout())

# Cog des commandes
class MapVetoCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.veto_config = MapVetoConfig(bot.plugin_db.get_partition(self))
        self.vetos = {}

    @commands.group(name='mapveto', invoke_without_command=True)
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def mapveto(self, ctx):
        """Affiche les options de gestion des templates de veto."""
        await ctx.send_help(ctx.command)

    @mapveto.command(name='create')
    @checks.has_permissions(PermissionLevel.MODERATOR)
    async def mapveto_create(self, ctx, name: str):
        """Crée un template de veto avec le nom donné."""
        if await self.veto_config.create_veto(name):
            await ctx.send(f"Template de veto '{name}' créé avec succès.")
        else:
            await ctx.send(f"Un template de veto avec le nom '{name}' existe déjà.")

    @mapveto.command(name='add')
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def add_map(self, ctx, name: str, *map_names):
        """Ajoute plusieurs maps au template de veto spécifié."""
        if await self.veto_config.add_maps(name, map_names):
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
            if await self.veto_config.set_rules(name, rules):
                await ctx.send(f"Règles définies pour le template de veto '{name}' : {rules}.")
            else:
                await ctx.send(f"Aucun template de veto trouvé avec le nom '{name}'.")
        else:
            await ctx.send(f"Règles invalides. Les règles valides sont : {', '.join(valid_rules)}.")

    @mapveto.command(name='delete')
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def mapveto_delete(self, ctx, name: str):
        """Supprime le template de veto spécifié."""
        if await self.veto_config.delete_veto(name):
            await ctx.send(f"Template de veto '{name}' supprimé avec succès.")
        else:
            await ctx.send(f"Aucun template de veto trouvé avec le nom '{name}'.")

    @mapveto.command(name='list')
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def mapveto_list(self, ctx):
        """Liste tous les templates de veto disponibles."""
        templates = await self.veto_config.list_vetos()
        if templates:
            await ctx.send(f"Templates de veto disponibles : {', '.join(templates)}")
        else:
            await ctx.send("Aucun template de veto disponible.")

    @commands.command()
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def start_mapveto(self, ctx, name: str, team_a_id: int, team_b_id: int):
        """Démarre un veto et envoie des messages en DM aux équipes spécifiées."""
        veto_data = await self.veto_config.get_veto(name)
        if not veto_data:
            await ctx.send(f"Aucun template de veto trouvé avec le nom '{name}'.")
            return

        veto = MapVeto(name, veto_data["maps"], team_a_id, team_b_id, veto_data["rules"])
        self.vetos[name] = veto

        await send_ticket_message(self.bot, veto, ctx.channel)

    @commands.command()
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def pause_mapveto(self, ctx, name: str):
        """Met en pause le veto spécifié."""
        if name not in self.vetos:
            await ctx.send(f"Aucun veto en cours avec le nom '{name}'.")
            return

        veto = self.vetos[name]
        veto.pause()
        await ctx.send(f"Le veto '{name}' a été mis en pause.")

    @commands.command()
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def resume_mapveto(self, ctx, name: str):
        """Reprend le veto spécifié."""
        if name not in self.vetos:
            await ctx.send(f"Aucun veto en cours avec le nom '{name}'.")
            return

        veto = self.vetos[name]
        veto.resume()
        await ctx.send(f"Le veto '{name}' a repris.")

    @commands.command()
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def stop_mapveto(self, ctx, name: str):
        """Arrête complètement le veto spécifié et le supprime des enregistrements."""
        if name not in self.vetos:
            await ctx.send(f"Aucun veto en cours avec le nom '{name}'.")
            return

        veto = self.vetos[name]
        veto.stop()
        del self.vetos[name]
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
