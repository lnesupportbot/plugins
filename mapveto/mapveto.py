import discord
from discord.ext import commands
import random

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

async def setup(bot_instance):
    global bot
    bot = bot_instance
    bot.add_command(create_mapveto)
    bot.add_command(show_mapveto)
    bot.add_command(mapveto)
    bot.add_command(list_mapvetos)

@commands.command()
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

@commands.command()
async def show_mapveto(ctx, name: str):
    if name not in vetos:
        await ctx.send(f"Aucun veto de maps trouvé avec le nom {name}.")
        return

    veto = vetos[name]
    await ctx.send(f"Veto '{name}':\nMaps: {', '.join(veto.maps)}\nPicks: {', '.join(veto.picks)}\nBans: {', '.join(veto.bans)}\nTour actuel: {veto.current_turn}\nAction actuelle: {veto.current_action_type()}")

@commands.command(name="mapveto", usage="<option>", invoke_without_command=True)
@checks.has_permissions(PermissionLevel.MODERATOR))
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

@commands.command()
async def list_mapvetos(ctx):
    if veto_config.vetos:
        await ctx.send(f"Templates de veto disponibles : {', '.join(veto_config.vetos.keys())}")
    else:
        await ctx.send("Aucun template de veto disponible.")


@commands.command()
async def help(ctx, command: str = None):
    """Affiche l'aide pour les commandes disponibles."""
    embed = discord.Embed(title="Commandes Map Veto", color=discord.Color.blue())
    
    if command is None:
        embed.description = (
            "Voici les commandes disponibles pour gérer les veto de cartes :\n"
            "**?mapveto create <nom> <ID équipe A> <ID équipe B> <nom template>** - Crée un veto de carte.\n"
            "**?show_mapveto <nom>** - Affiche les détails d'un veto de carte.\n"
            "**?mapveto <action> <nom> [arguments...]** - Gère les templates de veto (create, add, rules, delete).\n"
            "**?list_mapvetos** - Liste tous les templates de veto disponibles."
        )
        embed.add_field(name="Commandes pour gérer les templates", value="`?mapveto create`, `?mapveto add`, `?mapveto rules`, `?mapveto delete`", inline=False)
        embed.add_field(name="Autres commandes", value="`?show_mapveto`, `?list_mapvetos`", inline=False)
    else:
        if command == "mapveto":
            embed.description = (
                "**?mapveto create <nom> <ID équipe A> <ID équipe B> <nom template>** - Crée un nouveau veto de carte.\n"
                "**?mapveto add <nom> <nom_carte>** - Ajoute une carte à un template.\n"
                "**?mapveto rules <nom> <ordre>** - Définit les règles pour un template.\n"
                "**?mapveto delete <nom>** - Supprime un template de veto."
            )
        elif command == "show_mapveto":
            embed.description = "**?show_mapveto <nom>** - Affiche les détails d'un veto de carte."
        elif command == "list_mapvetos":
            embed.description = "**?list_mapvetos** - Liste tous les templates de veto disponibles."
        else:
            embed.description = "Commande inconnue. Utilisez `?help` pour voir la liste des commandes disponibles."

    await ctx.send(embed=embed)
