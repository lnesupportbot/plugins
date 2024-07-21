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
    def __init__(self, label, veto_name, action_type, channel, ctx):
        super().__init__(label=label, style=discord.ButtonStyle.primary, custom_id=f"{veto_name}_{label}_{action_type}")
        self.veto_name = veto_name
        self.action_type = action_type
        self.channel = channel
        self.ctx = ctx

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

        await veto.next_turn(self.ctx)  # Await the next turn call

        if veto.current_turn is not None:
            await send_ticket_message(interaction.client, veto, self.channel, self.ctx)
        else:
            await self.channel.send("Le veto est terminé!")
            embed = veto.create_summary_embed()
            await self.channel.send(embed=embed)

        # Disable the button and update the message
        view = interaction.message.view
        for item in view.children:
            if isinstance(item, discord.ui.Button) and item.custom_id == self.custom_id:
                item.disabled = True

        # Update the message with the modified view
        await interaction.message.edit(view=view)

async def send_ticket_message(bot, veto, channel, ctx):
    action = veto.current_action_type()
    if action is None:
        return

    current_user = bot.get_user(veto.get_current_turn())
    if not current_user:
        return

    components = []
    if action == "Side":
        components.append(MapButton(label="Attaque", veto_name=veto.name, action_type="side", channel=channel, ctx=ctx))
        components.append(MapButton(label="Défense", veto_name=veto.name, action_type="side", channel=channel, ctx=ctx))
    else:
        for map_name in veto.maps:
            # Disable buttons for banned or picked maps
            button = MapButton(label=map_name, veto_name=veto.name, action_type=action.lower(), channel=channel, ctx=ctx)
            if map_name in veto.banned_maps or map_name in veto.picked_maps:
                button.disabled = True
            components.append(button)
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
            random_button = random.choice(view.children)
            if isinstance(random_button, discord.ui.Button):
                await random_button.callback(None)

    bot.loop.create_task(timeout())

class MapVeto:
    def __init__(self, name, maps, team_a_id, team_a_name, team_b_id, team_b_name, rules):
        self.name = name
        self.maps = maps
        self.initial_maps = maps.copy()  # Save initial maps
        self.team_a_id = team_a_id
        self.team_a_name = team_a_name
        self.team_b_id = team_b_id
        self.team_b_name = team_b_name
        self.rules = rules
        self.initial_rules = rules.copy()  # Save initial rules
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
    
        # Check if there are more rules to process
        if self.current_action < len(self.rules):
            current_rule = self.rules[self.current_action]
            print(f"Processing rule: {current_rule}")
    
            # Process the current rule
            if current_rule in {"Ban", "Pick", "Side"}:
                # Switch turn between teams
                self.current_turn = self.team_a_id if self.current_turn == self.team_b_id else self.team_b_id
                # Move to the next action
                self.current_action += 1
    
            # Handle consecutive "Continue" rules
            while self.current_action < len(self.rules) and self.rules[self.current_action] == "Continue":
                self.current_action += 1
                if self.current_action < len(self.rules) and self.rules[self.current_action] != "Continue":
                    # Switch turn after exiting consecutive "Continue"
                    self.current_turn = self.team_a_id if self.current_turn == self.team_b_id else self.team_b_id
    
            # Check if we need to stop the veto
            if self.current_action >= len(self.rules):
                print("No more actions, stopping the veto")
                return self.end_veto()  # Call the method to end the veto
        else:
            # No more actions, end the veto
            print("No more actions, stopping the veto")
            return self.end_veto()  # Call the method to end the veto

    def create_summary_embed(self):
        embed = discord.Embed(title=f"Map Veto {self.team_a_name} - {self.team_b_name} terminé!", color=discord.Color.green())
        for i, map_name in enumerate(self.picked_maps):
            side = "Non défini"
            if i < len(self.picked_maps):
                side = self.picked_maps[i].split(" ")[0] if " choisi" in self.picked_maps[i] else "Non défini"
            embed.add_field(
                name=f"Map {i + 1}",
                value=f"**Map :** {map_name} choisie par {self.team_a_name if i % 2 == 0 else self.team_b_name} ({side})",
                inline=False
            )
        return embed
    
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
        self.current_action = 0
        self.picked_maps = []
        self.banned_maps = []
        self.stopped = True
        self.paused = False
        self.maps = self.initial_maps.copy()  # Restore initial maps
        self.rules = self.initial_rules.copy()  # Restore initial rules
        self.current_turn = self.team_a_id  # Reset to the initial team turn

    async def end_veto(self, ctx):
        self.stop()  # Call stop to end the veto
        embed = self.create_summary_embed()  # Get the summary embed
        await ctx.send(embed=embed)  # Send the summary embed

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
    @checks.has_permissions(PermissionLevel.MODERATOR)
    async def mapveto_add(self, ctx, name: str, *, maps: str):
        """Ajoute plusieurs maps au template de veto spécifié."""
        map_names = maps.split()
        if veto_config.add_maps(name, map_names):
            await ctx.send(f"Maps ajoutées au template de veto '{name}' : {', '.join(map_names)}.")
        else:
            await ctx.send(f"Aucun template de veto trouvé avec le nom '{name}'.")

    @mapveto.command(name='rules')
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def mapveto_rules(self, ctx, name: str, *, rules: str):
        """Définit les règles pour le template de veto spécifié."""
        valid_rules = {"Pick", "Ban", "Continue", "Side", "Fin"}
        rules_list = rules.split()
        if all(rule in valid_rules for rule in rules_list):
            if veto_config.set_rules(name, rules):
                await ctx.send(f"Règles définies pour le template de veto '{name}' : {rules}.")
            else:
                await ctx.send(f"Aucun template de veto trouvé avec le nom '{name}'.")
        else:
            await ctx.send(f"Règles invalides. Les règles valides sont : {', '.join(valid_rules)}.")

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
    async def start_mapveto(self, ctx, name: str, team_a_id: int, team_a_name: str, team_b_id: int, team_b_name: str):
        """Démarre un veto et envoie des messages en DM aux équipes spécifiées."""
        if name not in veto_config.vetos:
            await ctx.send(f"Aucun template de veto trouvé avec le nom '{name}'.")
            return

        veto = MapVeto(name, veto_config.vetos[name]["maps"], team_a_id, team_a_name, team_b_id, team_b_name, veto_config.vetos[name]["rules"])
        vetos[name] = veto

        await send_ticket_message(bot, veto, ctx.channel, ctx)

    @commands.command()
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def pause_mapveto(self, ctx, name: str):
        """Met en pause le veto spécifié."""
        if name not in vetos:
            await ctx.send(f"Aucun veto en cours avec le nom '{name}'.")
            return

        veto = vetos[name]
        veto.pause()
        await ctx.send(f"Le veto '{name}' a été mis en pause.")

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
        embed = veto.create_summary_embed()  # Get the summary embed
        del vetos[name]  # Remove the veto from memory
        await ctx.send(embed=embed)  # Send the summary embed

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
