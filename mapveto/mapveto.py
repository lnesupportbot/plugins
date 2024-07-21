import discord
from discord.ext import commands
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

    bot.loop.create_task(timeout())

class MapVeto:
    def __init__(self, name, maps, team_a_id, team_a_name, team_b_id, team_b_name, rules, channel=None, bot=None):
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
        self.channel = channel
        self.bot = bot
        self.participants = [team_a_id, team_b_id]  # Assuming participants are teams

    def get_current_turn(self):
        return self.current_turn

    def current_action_type(self):
        """Retourne le type d'action actuelle (Pick, Ban, Side, etc.) basé sur la règle en cours."""
        if self.current_action < len(self.rules):
            return self.rules[self.current_action]
        return None
        
    def create_summary_embed(self):
        """Crée un embed résumant les résultats du veto."""
        embed = discord.Embed(title="__**Résumé du Veto**__", color=discord.Color.blue())
    
        # Ajouter les maps choisies
        embed.add_field(name="**Maps choisies**", value=self.format_chosen_maps(), inline=False)
        
        # Ajouter les maps bannies
        banned_maps_str = ", ".join(self.banned_maps)
        embed.add_field(name="**Maps bannies**", value=banned_maps_str, inline=False)
    
        return embed
    
    def format_chosen_maps(self):
        """Format les maps choisies pour l'embed."""
        chosen_maps_lines = []
        
        # Associe les maps choisies à leurs équipes ou à DECIDER
        for map_name in self.picked_maps:
            if "choisi" in map_name:
                # Determine quelle équipe a choisi le side
                if "Attaque" in map_name or "Défense" in map_name:
                    side = map_name.split()[0]
                    team_name = self.team_a_name if self.current_turn == self.team_a_id else self.team_b_name
                    chosen_maps_lines.append(f"{map_name} / {side} choisi par {team_name}")
                else:
                    # Dernière map choisie par DECIDER
                    chosen_maps_lines.append(f"{map_name} choisi par DECIDER")
            else:
                # Si c'est une map choisie sans mention spéciale
                team_name = self.team_a_name if self.current_turn == self.team_a_id else self.team_b_name
                chosen_maps_lines.append(f"{map_name} choisi par {team_name}")
        
        return "\n".join(chosen_maps_lines)

    def ban_map(self, map_name):
        """Ban un map."""
        if map_name not in self.banned_maps and map_name in self.maps:
            self.banned_maps.append(map_name)
            self.maps.remove(map_name)
            if map_name in self.picked_maps:
                self.picked_maps.remove(map_name)

    def pick_map(self, map_name):
        """Choisi un map."""
        if map_name not in self.picked_maps and map_name in self.maps:
            self.picked_maps.append(map_name)
            self.maps.remove(map_name)

    def pick_side(self, side):
        """Choisi un side (Attaque ou Défense)."""
        if side in ["Attaque", "Défense"]:
            self.picked_maps.append(side)

    def next_turn(self):
        """Détermine le tour suivant et met à jour l'état."""
        if self.current_action < len(self.rules):
            self.current_action += 1
            self.current_turn = self.team_b_id if self.current_turn == self.team_a_id else self.team_a_id
        else:
            self.stopped = True

@commands.group()
@commands.guild_only()
@commands.check(checks.has_permissions(PermissionLevel.ADMIN))
async def mapveto(ctx):
    if ctx.invoked_subcommand is None:
        await ctx.send("Command not recognized. Use `!mapveto create`, `!mapveto start`, etc.")

@mapveto.command(name="create")
async def mapveto_create(ctx, name: str):
    if veto_config.create_veto(name):
        await ctx.send(f"Veto {name} créé.")
    else:
        await ctx.send(f"Veto {name} existe déjà.")

@mapveto.command(name="add_maps")
async def mapveto_add_maps(ctx, name: str, *maps):
    if veto_config.add_maps(name, maps):
        await ctx.send(f"Maps ajoutées au veto {name}.")
    else:
        await ctx.send(f"Veto {name} non trouvé.")

@mapveto.command(name="set_rules")
async def mapveto_set_rules(ctx, name: str, *, rules: str):
    if veto_config.set_rules(name, rules):
        await ctx.send(f"Règles définies pour le veto {name}.")
    else:
        await ctx.send(f"Veto {name} non trouvé.")

@mapveto.command(name="delete")
async def mapveto_delete(ctx, name: str):
    if veto_config.delete_veto(name):
        await ctx.send(f"Veto {name} supprimé.")
    else:
        await ctx.send(f"Veto {name} non trouvé.")

@mapveto.command()
async def mapveto_start(ctx, name: str, team_a_id: int, team_a_name: str, team_b_id: int, team_b_name: str):
    veto_data = veto_config.get_veto(name)
    if veto_data:
        veto = MapVeto(
            name=name,
            maps=veto_data["maps"],
            team_a_id=team_a_id,
            team_a_name=team_a_name,
            team_b_id=team_b_id,
            team_b_name=team_b_name,
            rules=veto_data["rules"],
            channel=ctx.channel,
            bot=ctx.bot
        )
        vetos[name] = veto
        await ctx.send(f"Le veto {name} a commencé. Les équipes {team_a_name} et {team_b_name} sont en jeu.")
        await send_ticket_message(ctx.bot, veto, ctx.channel)
    else:
        await ctx.send(f"Veto {name} non trouvé.")

    @commands.command()
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def resume_mapveto(self, ctx, name: str):
        """Reprend le veto spécifié."""
        if name not in vetos:
            await ctx.send(f"Aucun veto en cours avec le nom '{name}'.")
            return

        veto = vetos[name]
        veto.resume()
        await ctx.send(f"Le veto '{name}' a repris.")

    @commands.command()
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def stop_mapveto(self, ctx, name: str):
        """Arrête complètement le veto spécifié mais ne supprime pas le template."""
        if name not in vetos:
            await ctx.send(f"Aucun veto en cours avec le nom '{name}'.")
            return

        veto = vetos[name]
        veto.stop()  # Call stop to end the veto

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
            name="start_mapveto <name> <team_a_id> <team_a_name> <team_b_id> <team_b_name>",
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
