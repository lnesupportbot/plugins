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
    
        team_name = veto.team_a_name if interaction.user.id == veto.team_a_id else veto.team_b_name
        if self.action_type == "ban":
            veto.ban_map(self.label)
            message = f"Map {self.label} bannie par {interaction.user.mention} ({team_name})."
        elif self.action_type == "pick":
            veto.pick_map(self.label, f"{interaction.user.mention} ({team_name})")
            message = f"**Map {self.label} choisie par {interaction.user.mention} ({team_name}).**"
        elif self.action_type == "side":
            veto.pick_side(self.label, f"{interaction.user.mention} ({team_name})")
            message = f"*Side {self.label} choisi par {interaction.user.mention} ({team_name}).*"
    
        await interaction.response.send_message(message)
        await self.channel.send(message)
    
        opponent_user = interaction.client.get_user(veto.team_b_id if interaction.user.id == veto.team_a_id else veto.team_b_id)
        if opponent_user:
            await opponent_user.send(message)
    
        veto.next_turn()
        if veto.current_turn is not None:
            await send_ticket_message(interaction.client, veto, self.channel)
        else:
            if len(veto.maps) == 1:
                last_map = veto.maps[0]
                veto.pick_map(last_map, "DECIDER")
                message = f"**Map {last_map} choisie par DECIDER.**"
                await self.channel.send(message)
                last_side_chooser = f"{interaction.user.mention} ({team_name})"
                message = f"*Side Attaque choisi par {last_side_chooser}*"
                await self.channel.send(message)
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
                veto.pick_map(random_map, "Automatique")
                await current_user.send(f"Map {random_map} choisie automatiquement.")
            veto.next_turn()
            if veto.current_turn is not None:
                await send_ticket_message(bot, veto, channel)
            else:
                # Optionally handle the end of veto in timeout
                pass

    bot.loop.create_task(timeout())


class MapVeto:
    def __init__(self, name, maps, team_a_id, team_a_name, team_b_id, team_b_name, rules, channel, bot):
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
        self.participants = [team_a_id, team_b_id]
        self.bot = bot

    def create_summary_embed(self):
        embed = discord.Embed(title="__**Résumé du Veto**__", color=discord.Color.blue())

        # Maps choisies
        picked_maps_str = []
        last_map = None
        last_chooser = None
        last_side_chooser = None

        for entry in self.picked_maps:
            if "map" in entry:
                if last_map:
                    picked_maps_str.append(f"**{last_map}** choisi par {last_chooser}")
                last_map = entry["map"]
                last_chooser = entry["chooser"]
            elif "side" in entry:
                side = entry["side"]
                chooser = entry["chooser"]
                if last_map:
                    picked_maps_str.append(f"**{last_map}** choisi par {last_chooser} / Side {side} choisi par {chooser}")
                    last_map = None
                    last_chooser = None
                last_side_chooser = chooser

        if last_map:
            picked_maps_str.append(f"**{last_map}** choisi par {last_chooser}")

        # Ajouter la dernière carte par défaut si elle reste non choisie
        if len(self.maps) == 1:
            last_map = self.maps[0]
            picked_maps_str.append(f"**{last_map}** choisi par DECIDER / Side Attaque choisi par {last_side_chooser}")

        if picked_maps_str:
            embed.add_field(name="__**Maps choisies**__", value="\n".join(picked_maps_str), inline=False)
        else:
            embed.add_field(name="__**Maps choisies**__", value="Aucune", inline=False)

        # Maps bannies
        banned_maps_str = ", ".join(self.banned_maps) if self.banned_maps else "Aucune"
        embed.add_field(name="__**Maps bannies**__", value=banned_maps_str, inline=False)

        return embed

    def current_action_type(self):
        if self.current_action < len(self.rules):
            return self.rules[self.current_action]
        return None
        pass

    def get_current_turn(self):
        return self.current_turn

    def next_turn(self):
        if self.stopped or self.paused:
            return

        if self.current_action < len(self.rules):
            current_rule = self.rules[self.current_action]
            print(f"Processing rule: {current_rule}")

            if current_rule == "Continue":
                # Allow the same team to play again
                return
            elif current_rule == "Fin":
                # Handle the end of the veto
                print("End of veto detected, stopping the veto.")
                self.end_veto()  # Call the method to end the veto
                return
            else:
                if current_rule in {"Ban", "Pick", "Side"}:
                    self.current_turn = self.team_a_id if self.current_turn == self.team_b_id else self.team_b_id
                    self.current_action += 1

                # Handle consecutive "Continue" rules
                while self.current_action < len(self.rules) and self.rules[self.current_action] == "Continue":
                    self.current_action += 1
                    if self.current_action < len(self.rules) and self.rules[self.current_action] != "Continue":
                        # Switch turn after exiting consecutive "Continue"
                        self.current_turn = self.team_a_id if self.current_turn == self.team_b_id else self.team_b_id

                # If there are no more actions, stop the veto
                if self.current_action >= len(self.rules):
                    print("No more rules, stopping the veto")
                    self.end_veto()  # Call the method to end the veto
                    return

        else:
            # No more actions, end the veto
            print("No more actions, stopping the veto")
            self.end_veto()  # Call the method to end the veto
            return
        pass

    def ban_map(self, map_name):
        if map_name in self.maps:
            self.maps.remove(map_name)
            self.banned_maps.append(map_name)

    def pick_map(self, map_name, chooser):
        if map_name in self.maps:
            self.maps.remove(map_name)
            self.picked_maps.append({"map": map_name, "chooser": chooser})

    def pick_side(self, side, chooser):
        self.picked_maps.append({"side": side, "chooser": chooser})

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def stop(self):
        self.stopped = True
        self.paused = False
    
    def end_veto(self):
        if not self.stopped:
            self.stopped = True
            self.paused = False
    
            # Créer l'embed de résumé
            embed = self.create_summary_embed()
    
            # Envoyer le résumé dans le canal où la commande a été lancée
            if self.channel:
                self.bot.loop.create_task(self.channel.send(embed=embed))
    
            # Envoyer le résumé aux participants en DM
            for participant_id in self.participants:
                participant = self.bot.get_user(participant_id)
                if participant:
                    try:
                        self.bot.loop.create_task(participant.send(embed=embed))
                    except discord.Forbidden:
                        print(f"Cannot DM user {participant_id}")

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
        valid_rules = {"Pick", "Ban", "Continue", "Side"}
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
    
        veto = MapVeto(name, veto_config.vetos[name]["maps"], team_a_id, team_a_name, team_b_id, team_b_name, veto_config.vetos[name]["rules"], ctx.channel, self.bot)
        vetos[name] = veto
    
        await send_ticket_message(self.bot, veto, ctx.channel)


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
