import discord
from discord.ext import commands, tasks
import random
import json
import os
from core import checks
from core.models import PermissionLevel

class MapVetoConfig:
    def __init__(self, filename="vetos.json"):
        self.filename = filename
        self.vetos = self.load_vetos()

    def load_vetos(self):
        if os.path.exists(self.filename):
            with open(self.filename, "r") as file:
                return json.load(file)
        return {}

    def save_vetos(self):
        with open(self.filename, "w") as file:
            json.dump(self.vetos, file, indent=4)

    def create_veto(self, name):
        if name not in self.vetos:
            self.vetos[name] = {
                "maps": [],
                "rules": [],
            }
            self.save_vetos()
            return True
        return False

    def add_maps(self, name, map_names):
        if name in self.vetos:
            self.vetos[name]["maps"].extend(map_names)
            self.save_vetos()
            return True
        return False

    def set_rules(self, name, rules):
        if name in self.vetos:
            self.vetos[name]["rules"] = rules.split()
            self.save_vetos()
            return True
        return False

    def delete_veto(self, name):
        if name in self.vetos:
            del self.vetos[name]
            self.save_vetos()
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
            message = f"Map {self.label} bannie par {interaction.user.mention} (Équipe {veto.team_a_name if interaction.user.id == veto.team_a_id else veto.team_b_name})."
        elif self.action_type == "pick":
            veto.pick_map(self.label)
            message = f"**Map {self.label} choisie par {interaction.user.mention} (Équipe {veto.team_a_name if interaction.user.id == veto.team_a_id else veto.team_b_name}).**"
        elif self.action_type == "side":
            veto.pick_side(self.label)
            message = f"*Side {self.label} choisi par {interaction.user.mention} (Équipe {veto.team_a_name if interaction.user.id == veto.team_a_id else veto.team_b_name}).*"

        await interaction.response.send_message(message)
        await self.channel.send(message)

        opponent_user = interaction.client.get_user(veto.team_b_id if interaction.user.id == veto.team_a_id else veto.team_a_id)
        if opponent_user:
            await opponent_user.send(message)

        veto.next_turn()
        if veto.current_turn is not None:
            await send_ticket_message(interaction.client, veto, self.channel)
        else:
            await self.channel.send("Le veto est terminé!")
            embed = veto.create_summary_embed()
            await self.channel.send(embed=embed)

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

    team_name = veto.team_a_name if veto.get_current_turn() == veto.team_a_id else veto.team_b_name

    try:
        await current_user.send(f"{current_user.mention}, c'est votre tour de {action} une map.", view=view)
    except discord.Forbidden:
        print(f"Cannot DM user {current_user.id}")

    # Start the countdown
    countdown_task = CountdownTask(60, current_user, veto, action, bot, channel)
    countdown_task.start()

class CountdownTask:
    def __init__(self, duration, current_user, veto, action, bot, channel):
        self.duration = duration
        self.current_user = current_user
        self.veto = veto
        self.action = action
        self.bot = bot
        self.channel = channel

    async def update_timer_message(self):
        timer_message = await self.current_user.send(f"Il vous reste {self.duration} secondes pour {self.action.lower()} une map.")
        for i in range(self.duration, 0, -1):
            await timer_message.edit(content=f"Il vous reste {i} secondes pour {self.action.lower()} une map.")
            await asyncio.sleep(1)
        
        if self.duration == 0:
            random_map = random.choice(self.veto.maps)
            if self.action == "ban":
                self.veto.ban_map(random_map)
                await self.current_user.send(f"Map {random_map} bannie automatiquement.")
            elif self.action == "pick":
                self.veto.pick_map(random_map)
                await self.current_user.send(f"Map {random_map} choisie automatiquement.")
            self.veto.next_turn()
            if self.veto.current_turn is not None:
                await send_ticket_message(self.bot, self.veto, self.channel)

    def start(self):
        self.bot.loop.create_task(self.update_timer_message())

class MapVeto:
    def __init__(self, name, maps, team_a_id, team_a_name, team_b_id, team_b_name, rules):
        self.name = name
        self.maps = maps
        self.team_a_id = team_a_id
        self.team_a_name = team_a_name
        self.team_b_id = team_b_id
        self.team_b_name = team_b_name
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
            print(f"Processing rule: {current_rule}")

            if current_rule == "Continue":
                return
            elif current_rule == "Fin":
                self.end_veto()
                return
            else:
                if current_rule in {"Ban", "Pick", "Side"}:
                    self.current_turn = self.team_a_id if self.current_turn == self.team_b_id else self.team_b_id
                    self.current_action += 1

                while self.current_action < len(self.rules) and self.rules[self.current_action] == "Continue":
                    self.current_action += 1
                    if self.current_action < len(self.rules) and self.rules[self.current_action] != "Continue":
                        self.current_turn = self.team_a_id if self.current_turn == self.team_b_id else self.team_b_id

                if self.current_action >= len(self.rules):
                    print("No more rules, stopping the veto")
                    self.end_veto()
                    return
        else:
            print("No more actions, stopping the veto")
            self.end_veto()
            return

    def end_veto(self):
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
        self.picked_maps.append(side)

    def create_summary_embed(self):
        embed = discord.Embed(title="Résumé du Veto", description=f"Résumé du veto pour {self.name}")
        embed.add_field(name="Maps bannies", value=", ".join(self.banned_maps) if self.banned_maps else "Aucune", inline=False)
        embed.add_field(name="Maps choisies", value=", ".join(self.picked_maps) if self.picked_maps else "Aucune", inline=False)
        return embed

@commands.guild_only()
class VetoManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @checks.has_permissions(PermissionLevel.ADMIN)
    async def createveto(self, ctx, name):
        if veto_config.create_veto(name):
            await ctx.send(f"Veto '{name}' créé.")
        else:
            await ctx.send(f"Un veto avec le nom '{name}' existe déjà.")

    @commands.command()
    @checks.has_permissions(PermissionLevel.ADMIN)
    async def addmaps(self, ctx, name, *, maps):
        map_list = [map_name.strip() for map_name in maps.split(',')]
        if veto_config.add_maps(name, map_list):
            await ctx.send(f"Maps ajoutées au veto '{name}': {', '.join(map_list)}")
        else:
            await ctx.send(f"Veto '{name}' non trouvé.")

    @commands.command()
    @checks.has_permissions(PermissionLevel.ADMIN)
    async def setrules(self, ctx, name, *, rules):
        if veto_config.set_rules(name, rules):
            await ctx.send(f"Règles définies pour le veto '{name}': {rules}")
        else:
            await ctx.send(f"Veto '{name}' non trouvé.")

    @commands.command()
    @checks.has_permissions(PermissionLevel.ADMIN)
    async def startveto(self, ctx, name, team_a: discord.Member, team_b: discord.Member):
        veto_data = veto_config.get_veto(name)
        if not veto_data:
            await ctx.send(f"Veto '{name}' non trouvé.")
            return

        veto = MapVeto(name, veto_data["maps"], team_a.id, team_a.display_name, team_b.id, team_b.display_name, veto_data["rules"])
        vetos[name] = veto

        await ctx.send(f"Veto '{name}' commencé entre {team_a.mention} et {team_b.mention}.")
        await send_ticket_message(self.bot, veto, ctx.channel)

    @commands.command()
    @checks.has_permissions(PermissionLevel.ADMIN)
    async def stopveto(self, ctx, name):
        if name in vetos:
            vetos[name].stopped = True
            del vetos[name]
            await ctx.send(f"Veto '{name}' arrêté.")
        else:
            await ctx.send(f"Veto '{name}' non trouvé.")

    @commands.command()
    @checks.has_permissions(PermissionLevel.ADMIN)
    async def pauseveto(self, ctx, name):
        if name in vetos:
            vetos[name].paused = True
            await ctx.send(f"Veto '{name}' en pause.")
        else:
            await ctx.send(f"Veto '{name}' non trouvé.")

    @commands.command()
    @checks.has_permissions(PermissionLevel.ADMIN)
    async def resumeveto(self, ctx, name):
        if name in vetos:
            vetos[name].paused = False
            await ctx.send(f"Veto '{name}' repris.")
            await send_ticket_message(self.bot, vetos[name], ctx.channel)
        else:
            await ctx.send(f"Veto '{name}' non trouvé.")

def setup(bot):
    bot.add_cog(VetoManager(bot))
