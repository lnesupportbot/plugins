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

@commands.command()
@checks.has_permissions(PermissionLevel.ADMINISTRATOR)
@checks.thread_only()
async def create_mapveto(ctx, name: str):
    if veto_config.create_veto(name):
        await ctx.send(f"Template de veto '{name}' créé avec succès.")
    else:
        await ctx.send(f"Un template de veto avec le nom '{name}' existe déjà.")

@commands.command()
@checks.has_permissions(PermissionLevel.ADMINISTRATOR)
@checks.thread_only()
async def add_map(ctx, name: str, *map_names):
    if veto_config.add_maps(name, map_names):
        await ctx.send(f"Maps ajoutées au template de veto '{name}': {', '.join(map_names)}.")
    else:
        await ctx.send(f"Aucun template de veto trouvé avec le nom '{name}'.")

@commands.command()
@checks.has_permissions(PermissionLevel.ADMINISTRATOR)
@checks.thread_only()
async def set_rules(ctx, name: str, *, rules: str):
    if veto_config.set_rules(name, rules):
        await ctx.send(f"Règles '{rules}' définies pour le template de veto '{name}'.")
    else:
        await ctx.send(f"Aucun template de veto trouvé avec le nom '{name}'.")

@commands.command()
@checks.has_permissions(PermissionLevel.ADMINISTRATOR)
@checks.thread_only()
async def delete_mapveto(ctx, name: str):
    if veto_config.delete_veto(name):
        await ctx.send(f"Template de veto '{name}' supprimé avec succès.")
    else:
        await ctx.send(f"Aucun template de veto trouvé avec le nom '{name}'.")

@commands.command()
@checks.has_permissions(PermissionLevel.ADMINISTRATOR)
@checks.thread_only()
async def list_mapvetos(ctx):
    if veto_config.vetos:
        await ctx.send(f"Templates de veto disponibles : {', '.join(veto_config.vetos.keys())}")
    else:
        await ctx.send("Aucun template de veto disponible.")

@commands.command()
@checks.has_permissions(PermissionLevel.ADMINISTRATOR)
@checks.thread_only()
async def start_mapveto(ctx, name: str):
    # Assure que la commande est exécutée dans un thread
    if ctx.channel.type != discord.ChannelType.public_thread:
        await ctx.send("Cette commande ne peut être exécutée que dans un thread.")
        return

    if name not in vetos:
        await ctx.send(f"Aucun veto de cartes trouvé avec le nom '{name}'.")
        return

    veto = vetos[name]
    await send_veto_message(ctx.channel, veto)

@commands.command()
@checks.has_permissions(PermissionLevel.ADMINISTRATOR)
async def help_veto(ctx):
    embed = discord.Embed(title="Commandes Map Veto", description="Voici un résumé des commandes disponibles pour la gestion des veto de cartes.", color=discord.Color.blue())
    embed.add_field(name="`mapveto create <name>`", value="Crée un template de veto avec le nom spécifié.", inline=False)
    embed.add_field(name="`mapveto add <name> <map_names>`", value="Ajoute plusieurs maps au template de veto spécifié. Séparez les noms de maps par des espaces.", inline=False)
    embed.add_field(name="`mapveto rules <name> <rules>`", value="Définit les règles pour le template de veto spécifié.", inline=False)
    embed.add_field(name="`mapveto delete <name>`", value="Supprime le template de veto spécifié.", inline=False)
    embed.add_field(name="`mapveto list`", value="Liste tous les templates de veto disponibles.", inline=False)
    embed.add_field(name="`start_mapveto <name>`", value="Démarre un veto de carte dans un thread avec le template de veto nommé.", inline=False)
    await ctx.send(embed=embed)

async def setup(bot_instance):
    global bot
    bot = bot_instance
    bot.add_command(create_mapveto)
    bot.add_command(add_map)
    bot.add_command(set_rules)
    bot.add_command(delete_mapveto)
    bot.add_command(list_mapvetos)
    bot.add_command(start_mapveto)
    bot.add_command(help)
