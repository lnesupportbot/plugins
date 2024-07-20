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
        allowed_rules = {"Ban", "Pick", "Side", "Continue"}
        split_rules = rules.split()
        if name in self.vetos and all(rule in allowed_rules for rule in split_rules):
            self.vetos[name]["rules"] = split_rules
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

class MapVeto:
    def __init__(self, name, maps, team_a_id, team_b_id, rules):
        self.name = name
        self.maps = maps
        self.rules = rules
        self.current_turn = team_a_id  # L'équipe qui commence
        self.team_a_id = team_a_id
        self.team_b_id = team_b_id
        self.current_action_index = 0

    def current_action_type(self):
        if self.rules:
            if self.current_action_index < len(self.rules):
                return self.rules[self.current_action_index]
        return None

    def next_turn(self):
        action = self.current_action_type()
        if action == "Continue":
            # Continue avec la même équipe si la règle est "Continue"
            pass
        else:
            # Passer au tour suivant
            self.current_turn = self.team_a_id if self.current_turn == self.team_b_id else self.team_b_id
        self.current_action_index += 1

    def ban_map(self, map_name):
        if map_name in self.maps:
            self.maps.remove(map_name)

    def pick_map(self, map_name):
        if map_name in self.maps:
            self.maps.remove(map_name)

    def get_current_turn(self):
        return self.current_turn

class SideButton(discord.ui.Button):
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

        veto.pick_map(self.label)
        await interaction.response.send_message(f"Map {self.label} choisie comme '{self.label}' par {interaction.user.mention}.")
        veto.next_turn()

        if veto.current_turn is not None:
            await send_veto_message(interaction.channel, veto)
        else:
            await interaction.channel.send("Le veto est terminé!")

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
    if action == "Side":
        components.append(SideButton(label="Attaque", veto_name=veto.name))
        components.append(SideButton(label="Défense", veto_name=veto.name))
    else:
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
            elif action == "Side":
                # Choix automatique entre "Attaque" ou "Défense"
                side_choice = random.choice(["Attaque", "Défense"])
                veto.pick_map(side_choice)
                await channel.send(f"Choix automatique : '{side_choice}'.")
            veto.next_turn()
            if veto.current_turn is not None:
                await send_veto_message(channel, veto)
            else:
                await channel.send("Le veto est terminé!")

    bot.loop.create_task(timeout())

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
    async def add_map(self, ctx, name: str, *map_names):
        """Ajoute plusieurs maps au template de veto spécifié."""
        if veto_config.add_maps(name, map_names):
            await ctx.send(f"Maps ajoutées au template de veto '{name}' : {', '.join(map_names)}.")
        else:
            await ctx.send(f"Aucun template de veto trouvé avec le nom '{name}'.")

    @mapveto.command(name='rules')
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def mapveto_rules(self, ctx, name: str, *, rules: str):
        """Définit les règles pour le template de veto spécifié."""
        if veto_config.set_rules(name, rules):
            await ctx.send(f"Règles '{rules}' définies pour le template de veto '{name}'.")
        else:
            await ctx.send(f"Aucun template de veto trouvé avec le nom '{name}'.")

    @mapveto.command(name='delete')
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def mapveto_delete(self, ctx, name: str):
        """Supprime le template de veto spécifié."""
        if veto_config.delete_veto(name):
            await ctx.send(f"Template de veto '{name}' supprimé avec succès.")
        else:
            await ctx.send(f"Aucun template de veto trouvé avec le nom '{name}'.")

    @mapveto.command(name='list')
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def mapveto_list(self, ctx):
        """Liste tous les templates de veto disponibles."""
        if veto_config.vetos:
            await ctx.send(f"Templates de veto disponibles : {', '.join(veto_config.vetos.keys())}")
        else:
            await ctx.send("Aucun template de veto disponible.")

    @commands.command()
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def start_mapveto(self, ctx, name: str, team_a_id: int, team_b_id: int):
        """Démarre un veto dans un thread spécifique avec les équipes spécifiées."""
        if name not in veto_config.vetos:
            await ctx.send(f"Aucun template de veto trouvé avec le nom {name}.")
            return

        veto = MapVeto(name, veto_config.vetos[name]["maps"], team_a_id, team_b_id, veto_config.vetos[name]["rules"])
        vetos[name] = veto

        await send_veto_message(ctx.channel, veto)

    @commands.command()
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def help_veto(self, ctx):
        """Affiche les commandes disponibles pour la gestion des veto de cartes."""
        embed = discord.Embed(title="Aide pour les Commandes MapVeto", description="Voici un résumé des commandes disponibles pour la gestion des veto de cartes.")

        embed.add_field(
            name="`mapveto create <name>`",
            value="Crée un template de veto avec le nom donné.",
            inline=False
        )
        embed.add_field(
            name="`mapveto add <name> <map_name>`",
            value="Ajoute une ou plusieurs maps au template de veto spécifié.",
            inline=False
        )
        embed.add_field(
            name="`mapveto rules <name> <rules>`",
            value="Définit les règles pour le template de veto spécifié. Les règles doivent être 'Ban', 'Pick', 'Side', ou 'Continue'.",
            inline=False
        )
        embed.add_field(
            name="`mapveto delete <name>`",
            value="Supprime le template de veto spécifié.",
            inline=False
        )
        embed.add_field(
            name="`mapveto list`",
            value="Liste tous les templates de veto disponibles.",
            inline=False
        )
        embed.add_field(
            name="`start_mapveto <name> <team_a_id> <team_b_id>`",
            value="Démarre un veto dans un thread spécifique avec les équipes spécifiées.",
            inline=False
        )

        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(MapVetoCog(bot))
