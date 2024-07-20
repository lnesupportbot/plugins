import discord
from discord.ext import commands
import random

class MapVetoConfig(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.vetos = {}

    def create_veto(self, name):
        if name not in self.vetos:
            self.vetos[name] = {
                "maps": [],
                "rules": [],
            }
            return True
        return False

    def add_map(self, name, map_name):
        if name in self.vetos:
            self.vetos[name]["maps"].append(map_name)
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

class MapVeto:
    def __init__(self, name, maps, team_a_id, team_b_id, rules):
        self.name = name
        self.maps = list(maps)
        self.team_a_id = team_a_id
        self.team_b_id = team_b_id
        self.current_turn = team_a_id
        self.actions = rules
        self.current_action = 0
        self.picks = []
        self.bans = []

    def next_turn(self):
        self.current_action += 1
        if self.current_action < len(self.actions):
            self.current_turn = self.team_a_id if self.current_turn == self.team_b_id else self.team_b_id
        else:
            self.current_turn = None  # Veto terminé

    def current_action_type(self):
        if self.current_action < len(self.actions):
            return self.actions[self.current_action]
        return None

    def pick_map(self, map_name):
        if map_name in self.maps and map_name not in self.picks and map_name not in self.bans:
            self.picks.append(map_name)
            self.maps.remove(map_name)
            return True
        return False

    def ban_map(self, map_name):
        if map_name in self.maps and map_name not in self.picks and map_name not in self.bans:
            self.bans.append(map_name)
            self.maps.remove(map_name)
            return True
        return False

vetos = {}

class MapButton(discord.ui.Button):
    def __init__(self, label, veto_name):
        super().__init__(label=label, style=discord.ButtonStyle.primary)
        self.veto_name = veto_name

    async def callback(self, interaction: discord.Interaction):
        if self.veto_name not in vetos:
            await interaction.response.send_message("Veto non trouvé.", ephemeral=True)
            return
        
        veto = vetos[self.veto_name]
        if interaction.user.id != veto.current_turn:
            await interaction.response.send_message("Ce n'est pas votre tour.", ephemeral=True)
            return

        if veto.current_action_type() == "ban":
            veto.ban_map(self.label)
            await interaction.response.send_message(f"Map {self.label} bannie par {interaction.user.mention}.")
        elif veto.current_action_type() == "pick":
            veto.pick_map(self.label)
            await interaction.response.send_message(f"Map {self.label} choisie par {interaction.user.mention}.")

        veto.next_turn()
        if veto.current_turn is not None:
            await send_veto_message(interaction.channel, veto)
        else:
            await interaction.channel.send("Le veto est terminé!")

async def send_veto_message(channel, veto):
    action = veto.current_action_type()
    if action is None:
        return

    components = []
    for map_name in veto.maps:
        components.append(MapButton(label=map_name, veto_name=veto.name))

    view = discord.ui.View(timeout=60)
    for component in components:
        view.add_item(component)

    current_team = bot.get_user(veto.current_turn)
    message = await channel.send(f"{current_team.mention}, c'est votre tour de {action} une map.", view=view)

    async def timeout():
        await view.wait()
        if not view.is_finished():
            random_map = random.choice(veto.maps)
            if action == "ban":
                veto.ban_map(random_map)
                await channel.send(f"Map {random_map} bannie automatiquement.")
            elif action == "pick":
                veto.pick_map(random_map)
                await channel.send(f"Map {random_map} choisie automatiquement.")
            veto.next_turn()
            if veto.current_turn is not None:
                await send_veto_message(channel, veto)
            else:
                await channel.send("Le veto est terminé!")

    bot.loop.create_task(timeout())

@bot.command()
async def create_mapveto(ctx, name: str, team_a_id: int, team_b_id: int, template_name: str):
    template = veto_config.get_veto(template_name)
    if not template:
        await ctx.send(f"Aucun template de veto trouvé avec le nom {template_name}.")
        return

    if name in vetos:
        await ctx.send(f"Un veto avec le nom {name} existe déjà.")
        return

    vetos[name] = MapVeto(name, template["maps"], team_a_id, team_b_id, template["rules"])
    await ctx.send(f"Veto de maps '{name}' créé avec succès entre les équipes {team_a_id} et {team_b_id}.")
    await send_veto_message(ctx.channel, vetos[name])

@bot.command()
async def show_mapveto(ctx, name: str):
    if name not in vetos:
        await ctx.send(f"Aucun veto de maps trouvé avec le nom {name}.")
        return

    veto = vetos[name]
    await ctx.send(f"Veto '{name}':\nMaps: {', '.join(veto.maps)}\nPicks: {', '.join(veto.picks)}\nBans: {', '.join(veto.bans)}\nTour actuel: {veto.current_turn}\nAction actuelle: {veto.current_action_type()}")

@bot.command()
async def mapveto(ctx, action: str, name: str, *args):
    if action == "create":
        if veto_config.create_veto(name):
            await ctx.send(f"Template de veto '{name}' créé avec succès.")
        else:
            await ctx.send(f"Un template de veto avec le nom '{name}' existe déjà.")
    elif action == "add":
        map_name = args[0]
        if veto_config.add_map(name, map_name):
            await ctx.send(f"Map '{map_name}' ajoutée au template de veto '{name}'.")
        else:
            await ctx.send(f"Aucun template de veto trouvé avec le nom '{name}'.")
    elif action == "rules":
        rules = ' '.join(args)
        if veto_config.set_rules(name, rules):
            await ctx.send(f"Règles '{rules}' définies pour le template de veto '{name}'.")
        else:
            await ctx.send(f"Aucun template de veto trouvé avec le nom '{name}'.")
    elif action == "delete":
        if veto_config.delete_veto(name):
            await ctx.send(f"Template de veto '{name}' supprimé avec succès.")
        else:
            await ctx.send(f"Aucun template de veto trouvé avec le nom '{name}'.")

@bot.command()
async def list_mapvetos(ctx):
    if veto_config.vetos:
        await ctx.send(f"Templates de veto disponibles : {', '.join(veto_config.vetos.keys())}")
    else:
        await ctx.send("Aucun template de veto disponible.")

def setup(bot):
    bot.add_command(create_mapveto)
    bot.add_command(show_mapveto)
    bot.add_command(mapveto)
    bot.add_command(list_mapvetos)

