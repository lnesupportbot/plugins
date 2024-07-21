import discord
from discord.ext import commands
import random

from core import checks
from core.models import PermissionLevel

class MapVetoConfig:
    def __init__(self):
        self.vetos = {}

    def create_veto(self, name):
        if name not in self.vetos:
            self.vetos[name] = {
                "maps": [],
                "rules": [],
            }
            return True
        return False

    def add_maps(self, name, map_names):
        if name in self.vetos:
            self.vetos[name]["maps"].extend(map_names)
            return True
        return False

    def set_rules(self, name, rules):
        if name in self.vetos:
            self.vetos[name]["rules"] = rules.split()
            return True
        return False

    def delete_veto(self, name):
        if name in self.vetos:
            del self.vetos[name]
            return True
        return False

    def get_veto(self, name):
        return self.vetos.get(name, None)

veto_config = MapVetoConfig()
vetos = {}

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
        await current_user.send(f"{current_user.mention} ({veto.team_a_name if current_user.id == veto.team_a_id else veto.team_b_name}), c'est votre tour de {action} une map.", view=view)
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
                # Send final embed message when veto ends
                embed = discord.Embed(title="Le Map Veto est terminé!", description="Voici le résumé des choix de cartes et des côtés.")
                for i, map_name in enumerate(veto.picked_maps):
                    team_name = veto.team_a_name if i % 2 == 0 else veto.team_b_name
                    side = veto.get_side_choice(veto.team_a_id if i % 2 == 0 else veto.team_b_id)
                    embed.add_field(name=f"Carte {i + 1}", value=f"{map_name} / {team_name} ({side})", inline=False)

                for user_id in [veto.team_a_id, veto.team_b_id]:
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
        self.team_a_name = ""
        self.team_b_name = ""
        self.rules = rules
        self.current_turn = team_a_id
        self.current_action = 0
        self.picked_maps = []
        self.banned_maps = []
        self.paused = False
        self.stopped = False
        self.side_choices = {}  # Dict to keep track of sides chosen by each team

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
        self.side_choices[self.current_turn] = side
        self.picked_maps.append(f"{side} choisi")

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def stop(self):
        self.stopped = True
        self.paused = False

    def get_side_choice(self, team_id):
        return self.side_choices.get(team_id, "Non choisi")

class MapVetoCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.group(name='mapveto', invoke_without_command=True)
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def mapveto(self, ctx):
        """Affiche les options de gestion des templates de veto."""
        await ctx.send_help(ctx.command)

    @mapveto.command(name='create')
    @checks.has_permissions(PermissionLevel.MODERATOR)
    async def mapveto_create(self, ctx, name: str):
        """Crée un template de veto avec le nom donné."""
        if veto_config.create_veto(name):
            await ctx.send(f"Template de veto '{name}' créé avec succès.")
        else:
            await ctx.send(f"Un template de veto avec le nom '{name}' existe déjà.")

    @mapveto.command(name='add')
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def mapveto_add(self, ctx, name: str, *, maps: str):
        """Ajoute des cartes à un template de veto existant."""
        map_names = maps.split(',')
        if veto_config.add_maps(name, map_names):
            await ctx.send(f"Cartes ajoutées au template de veto '{name}'.")
        else:
            await ctx.send(f"Aucun template de veto trouvé avec le nom '{name}'.")

    @mapveto.command(name='rules')
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def mapveto_rules(self, ctx, name: str, *, rules: str):
        """Définit les règles pour un template de veto existant."""
        if veto_config.set_rules(name, rules):
            await ctx.send(f"Règles mises à jour pour le template de veto '{name}'.")
        else:
            await ctx.send(f"Aucun template de veto trouvé avec le nom '{name}'.")

    @mapveto.command(name='delete')
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def mapveto_delete(self, ctx, name: str):
        """Supprime un template de veto existant."""
        if veto_config.delete_veto(name):
            await ctx.send(f"Template de veto '{name}' supprimé.")
        else:
            await ctx.send(f"Aucun template de veto trouvé avec le nom '{name}'.")

    @mapveto.command(name='start')
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def start_mapveto(self, ctx, name: str, team_a_id: int, team_a_name: str, team_b_id: int, team_b_name: str):
        """Démarre un veto et envoie des messages en DM aux équipes spécifiées avec les noms des équipes."""
        if name not in veto_config.vetos:
            await ctx.send(f"Aucun template de veto trouvé avec le nom '{name}'.")
            return

        veto = MapVeto(name, veto_config.vetos[name]["maps"], team_a_id, team_b_id, veto_config.vetos[name]["rules"])
        veto.team_a_name = team_a_name
        veto.team_b_name = team_b_name
        vetos[name] = veto

        await send_ticket_message(self.bot, veto, ctx.channel)

def setup(bot):
    bot.add_cog(MapVetoCog(bot))
