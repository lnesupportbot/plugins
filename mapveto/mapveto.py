import discord
from discord.ext import commands
import random

# Classe pour gérer les veto de cartes
class MapVeto:
    def __init__(self, name, maps, team_a_id, team_b_id, rules):
        self.name = name
        self.maps = maps
        self.rules = rules
        self.team_a_id = team_a_id
        self.team_b_id = team_b_id
        self.current_turn = team_a_id
        self.bans = []
        self.picks = []
        self.current_action_index = 0

    def current_action_type(self):
        if not self.rules:
            return None
        return self.rules[self.current_action_index]

    def ban_map(self, map_name):
        if map_name in self.maps:
            self.maps.remove(map_name)
            self.bans.append(map_name)

    def pick_map(self, map_name):
        if map_name in self.maps:
            self.maps.remove(map_name)
            self.picks.append(map_name)

    def next_turn(self):
        if not self.rules:
            return
        self.current_action_index = (self.current_action_index + 1) % len(self.rules)
        if self.current_action_type() == "ban":
            self.current_turn = self.team_b_id if self.current_turn == self.team_a_id else self.team_a_id
        elif self.current_action_type() == "pick":
            self.current_turn = self.team_b_id if self.current_turn == self.team_a_id else self.team_a_id

# Classe pour gérer la configuration des templates de veto
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

class MapVetoCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def mapveto(self, ctx, action: str, name: str, *args):
        """Commandes pour créer, ajouter des cartes, définir des règles et supprimer un template de veto"""
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
    async def list_mapvetos(self, ctx):
        """Liste tous les templates de veto disponibles"""
        if veto_config.vetos:
            await ctx.send(f"Templates de veto disponibles : {', '.join(veto_config.vetos.keys())}")
        else:
            await ctx.send("Aucun template de veto disponible.")

    @commands.command()
    async def start_mapveto(self, ctx, name: str, team_a_id: int, team_b_id: int):
        """Démarre un veto dans un thread avec les utilisateurs spécifiés."""
        if name not in veto_config.vetos:
            await ctx.send(f"Aucun veto de maps trouvé avec le nom {name}.")
            return

        veto = MapVeto(name, veto_config.vetos[name]["maps"], team_a_id, team_b_id, veto_config.vetos[name]["rules"])
        vetos[name] = veto

        # Crée un thread pour le veto
        thread = await ctx.channel.create_thread(name=f"Veto de {name}", type=discord.ChannelType.public_thread)

        await thread.send(f"Démarrage du veto '{name}' dans ce thread. Vous pouvez maintenant faire des choix.")

        await send_veto_message(thread, veto)

    @commands.command()
    async def help(self, ctx, command=None):
        """Affiche l'aide pour les commandes disponibles."""
        embed = discord.Embed(title="Aide des commandes")
        if command is None:
            embed.description = (
                "**?mapveto create <nom>** - Crée un nouveau template de veto.\n"
                "**?mapveto add <nom> <map>** - Ajoute une map au template de veto.\n"
                "**?mapveto rules <nom> <ordre>** - Définit les règles pour le veto.\n"
                "**?mapveto delete <nom>** - Supprime un template de veto.\n"
                "**?mapveto start <nom> <ID équipe A> <ID équipe B>** - Démarre un veto dans un thread.\n"
                "**?list_mapvetos** - Liste tous les templates de veto disponibles."
            )
        else:
            if command == "mapveto":
                embed.description = (
                    "**?mapveto create <nom>** - Crée un nouveau template de veto.\n"
                    "**?mapveto add <nom> <map>** - Ajoute une map au template de veto.\n"
                    "**?mapveto rules <nom> <ordre>** - Définit les règles pour le veto.\n"
                    "**?mapveto delete <nom>** - Supprime un template de veto.\n"
                    "**?mapveto start <nom> <ID équipe A> <ID équipe B>** - Démarre un veto dans un thread."
                )
            else:
                embed.description = "Commande inconnue. Utilisez `?help` pour voir la liste des commandes disponibles."

        await ctx.send(embed=embed)

def setup(bot):
    bot.add_cog(MapVetoCog(bot))
