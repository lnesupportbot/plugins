import discord
from discord.ext import commands
import random

from core import checks
from core.models import PermissionLevel

class MapVetoConfig:
    def __init__(self, bot):
        self.bot = bot
        self.db = self.bot.plugin_db.get_partition(self)
        self.vetos = {}

    async def load_vetos(self):
        collection = self.db.vetos
        vetos = await collection.find().to_list(length=None)
        self.vetos = {veto['name']: veto for veto in vetos}
        print(f"Loaded vetos: {self.vetos}")  # Debugging line

    async def create_veto(self, name):
        collection = self.db.vetos
        if await collection.find_one({"name": name}):
            return False
        await collection.insert_one({"name": name, "maps": [], "rules": []})
        self.vetos[name] = {"name": name, "maps": [], "rules": []}
        print(f"Created veto: {self.vetos}")  # Debugging line
        return True

    async def add_maps(self, name, map_names):
        collection = self.db.vetos
        result = await collection.find_one({"name": name})
        if result:
            maps = result["maps"]
            maps.extend(map_names)
            await collection.update_one({"name": name}, {"$set": {"maps": maps}})
            self.vetos[name]["maps"] = maps
            print(f"Added maps: {self.vetos}")  # Debugging line
            return True
        return False

    async def set_rules(self, name, rules):
        collection = self.db.vetos
        valid_rules = {"Ban", "Pick", "Side", "Continue"}
        rules_list = rules.split()
        if all(rule in valid_rules for rule in rules_list):
            await collection.update_one({"name": name}, {"$set": {"rules": rules_list}})
            self.vetos[name]["rules"] = rules_list
            print(f"Set rules: {self.vetos}")  # Debugging line
            return True
        return False

    async def delete_veto(self, name):
        collection = self.db.vetos
        result = await collection.delete_one({"name": name})
        if result.deleted_count > 0:
            del self.vetos[name]
            print(f"Deleted veto: {self.vetos}")  # Debugging line
            return True
        return False

    async def get_veto(self, name):
        print(f"Retrieving veto: {self.vetos.get(name)}")  # Debugging line
        return self.vetos.get(name, None)

class MapButton(discord.ui.Button):
    def __init__(self, label, veto_name, action_type, channel):
        super().__init__(label=label, style=discord.ButtonStyle.primary, custom_id=f"{veto_name}_{label}_{action_type}")
        self.veto_name = veto_name
        self.action_type = action_type
        self.channel = channel

    async def callback(self, interaction: discord.Interaction):
        veto = self.view.vetos.get(self.veto_name)
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

        opponent_user = interaction.client.get_user(veto.team_b_id if interaction.user.id == veto.team_a_id else veto.team_a_id)
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
        self.veto_config = MapVetoConfig(bot)
        self.vetos = {}

    @commands.Cog.listener()
    async def on_ready(self):
        await self.veto_config.load_vetos()
        self.vetos = self.veto_config.vetos
        print(f"Vetoes on_ready: {self.vetos}")

    @commands.group(name='mapveto', invoke_without_command=True)
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def mapveto(self, ctx):
        """Affiche les options de gestion des templates de veto."""
        await ctx.send("Utilisez les sous-commandes pour gérer les templates de veto.")

    @mapveto.command(name='create')
    @checks.has_permissions(PermissionLevel.MODERATOR)
    async def mapveto_create(self, ctx, name: str):
        """Crée un nouveau template de veto avec le nom spécifié."""
        if await self.veto_config.create_veto(name):
            await ctx.send(f"Template de veto '{name}' créé avec succès.")
        else:
            await ctx.send(f"Un template de veto avec le nom '{name}' existe déjà.")
        print(f"Create command invoked: {self.vetos}")

    @mapveto.command(name='addmaps')
    @checks.has_permissions(PermissionLevel.MODERATOR)
    async def mapveto_addmaps(self, ctx, name: str, *maps: str):
        """Ajoute des maps à un template de veto existant."""
        if await self.veto_config.add_maps(name, maps):
            await ctx.send(f"Maps ajoutées au veto '{name}' avec succès.")
        else:
            await ctx.send(f"Template de veto '{name}' non trouvé.")
        print(f"Add maps command invoked: {self.vetos}")

    @mapveto.command(name='setrules')
    @checks.has_permissions(PermissionLevel.MODERATOR)
    async def mapveto_setrules(self, ctx, name: str, *, rules: str):
        """Définit les règles pour un template de veto existant."""
        if await self.veto_config.set_rules(name, rules):
            await ctx.send(f"Règles définies pour le veto '{name}' avec succès.")
        else:
            await ctx.send(f"Les règles spécifiées sont invalides ou le veto '{name}' n'a pas été trouvé.")
        print(f"Set rules command invoked: {self.vetos}")

    @mapveto.command(name='delete')
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def mapveto_delete(self, ctx, name: str):
        """Supprime un template de veto existant."""
        if await self.veto_config.delete_veto(name):
            await ctx.send(f"Template de veto '{name}' supprimé avec succès.")
        else:
            await ctx.send(f"Template de veto '{name}' non trouvé.")
        print(f"Delete command invoked: {self.vetos}")

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

        print(f"Starting veto: {self.vetos[name]}")

        await send_ticket_message(self.bot, veto, ctx.channel)
