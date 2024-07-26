import discord # type: ignore
from discord.errors import NotFound # type: ignore
from discord.ext import commands # type: ignore
from discord.ui import Modal, TextInput, View, Button, Select # type: ignore
import json
import os
import asyncio

from core import checks # type: ignore
from core.models import PermissionLevel # type: ignore

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

    def create_veto(self, name, maps, rules):
        if name not in self.vetos:
            self.vetos[name] = {
                "maps": maps,
                "rules": rules,
            }
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

    def update_veto(self, name, maps, rules):
        if name in self.vetos:
            self.vetos[name] = {
                "maps": maps,
                "rules": rules,
            }
            self.save_vetos()
            return True
        return False

veto_config = MapVetoConfig()
vetos = {}

class TournamentConfig:
    def __init__(self, filename="tourney.json"):
        self.filename = filename
        self.tournaments = self.load_tournaments()

    def load_tournaments(self):
        if os.path.exists(self.filename):
            with open(self.filename, "r") as file:
                return json.load(file)
        return {}

    def save_tournaments(self):
        with open(self.filename, "w") as file:
            json.dump(self.tournaments, file, indent=4)

    def create_tournament(self, name, template_name):
        if name not in self.tournaments:
            self.tournaments[name] = {"template": template_name}
            self.save_tournaments()
            return True
        return False

    def delete_tournament(self, name):
        if name in self.tournaments:
            del self.tournaments[name]
            self.save_tournaments()
            return True
        return False

    def get_tournament(self, name):
        return self.tournaments.get(name, None)

    def update_tournament(self, name, template_name):
        if name in self.tournaments:
            self.tournaments[name]["template"] = template_name
            self.save_tournaments()
            return True
        return False

tournament_config = TournamentConfig()

class TournamentCreateModal(Modal):
    def __init__(self, template_name):
        super().__init__(title="Créer un Tournoi")
        self.template_name = template_name
        self.name = TextInput(label="Nom du Tournoi", placeholder="Entrez le nom du tournoi")

        self.add_item(self.name)

    async def on_submit(self, interaction: discord.Interaction):
        tournament_name = self.name.value.strip()
        template_name = self.template_name

        # Enregistrer le tournoi avec le nom et le template sélectionné
        if tournament_config.create_tournament(tournament_name, template_name):
            await interaction.response.send_message(f"Tournoi '{tournament_name}' créé avec le template '{template_name}'.", ephemeral=True)
        else:
            await interaction.response.send_message(f"Un tournoi avec le nom '{tournament_name}' existe déjà.", ephemeral=True)

class TournamentEditModal(Modal):
    def __init__(self, tournament_name, tournament):
        super().__init__(title=f"Modifier le Tournoi '{tournament_name}'")
        self.tournament_name = tournament_name
        self.tournament = tournament
        self.name = TextInput(
            label="Nom du Tournoi",
            default=tournament_name,
            placeholder="Entrez le nom du tournoi"
        )
        self.template = TextInput(
            label="Template du Tournoi",
            default=tournament["template"],
            placeholder="Entrez le nom du template"
        )
        self.add_item(self.name)
        self.add_item(self.template)

    async def on_submit(self, interaction: discord.Interaction):
        new_name = self.name.value.strip()
        template = self.template.value.strip()

        if not new_name:
            await interaction.response.send_message("Le nom ne peut pas être vide.", ephemeral=True)
            return

        if new_name != self.tournament_name:
            if tournament_config.get_tournament(new_name):
                await interaction.response.send_message(f"Un tournoi avec le nom '{new_name}' existe déjà.", ephemeral=True)
                return
            else:
                tournament_config.tournaments[new_name] = tournament_config.tournaments.pop(self.tournament_name)
                self.tournament_name = new_name

        tournament_config.update_tournament(self.tournament_name, template)
        await interaction.response.send_message(f"Tournoi '{self.tournament_name}' mis à jour avec succès.", ephemeral=True)

class TournamentDeleteButton(Button):
    def __init__(self, tournament_name):
        super().__init__(label=f"Supprimer {tournament_name}", style=discord.ButtonStyle.danger, custom_id=f"delete_{tournament_name}")
        self.tournament_name = tournament_name

    async def callback(self, interaction: discord.Interaction):
        if tournament_config.delete_tournament(self.tournament_name):
            await interaction.response.send_message(f"Le tournoi '{self.tournament_name}' a été supprimé avec succès.", ephemeral=True)
        else:
            await interaction.response.send_message(f"Erreur lors de la suppression du tournoi '{self.tournament_name}'.", ephemeral=True)


class VetoCreateModal(Modal):
    def __init__(self):
        super().__init__(title="Créer un template de veto")

        self.name = TextInput(label="Nom du Template", placeholder="Entrez le nom du template")
        self.maps = TextInput(label="Noms des Maps (séparés par des espaces)", placeholder="Entrez les noms des maps séparés par des espaces")
        self.rules = TextInput(
            label="Règles (séparées par des espaces)",
            placeholder="Ban, Pick, Side, Continue (Respectez les majuscules)"
        )

        self.add_item(self.name)
        self.add_item(self.maps)
        self.add_item(self.rules)

    async def on_submit(self, interaction: discord.Interaction):
        name = self.name.value
        maps = self.maps.value.split()
        rules = self.rules.value.split()

        if veto_config.create_veto(name, maps, rules):
            await interaction.response.send_message(f"Template de veto '{name}' créé avec succès.", ephemeral=True)
        else:
            await interaction.response.send_message(f"Un template de veto avec le nom '{name}' existe déjà.", ephemeral=True)

class VetoEditModal(Modal):
    def __init__(self, template_name, veto):
        super().__init__(title=f"Modifier le template '{template_name}'")
        self.template_name = template_name
        self.veto = veto

        # Champs pour le nom, les maps et les règles
        self.name = TextInput(
            label="Nom du Template",
            default=template_name,
            placeholder="Entrez le nom du template"
        )
        self.maps = TextInput(
            label="Noms des Maps",
            default=" ".join(veto["maps"]),
            placeholder="Entrez les noms des maps séparés par des espaces"
        )
        self.rules = TextInput(
            label="Règles",
            default=" ".join(veto["rules"]),
            placeholder="Ban, Pick, Side, Continue (Respectez les majuscules, séparées par des espaces)"
        )

        self.add_item(self.name)
        self.add_item(self.maps)
        self.add_item(self.rules)

    async def on_submit(self, interaction: discord.Interaction):
        new_name = self.name.value.strip()
        maps = self.maps.value.strip().split()
        rules = self.rules.value.strip().split()

        if not new_name:
            await interaction.response.send_message("Le nom ne peut pas être vide.", ephemeral=True)
            return

        if new_name != self.template_name:
            if veto_config.get_veto(new_name):
                await interaction.response.send_message(f"Un template avec le nom '{new_name}' existe déjà.", ephemeral=True)
                return
            else:
                veto_config.vetos[new_name] = veto_config.vetos.pop(self.template_name)
                self.template_name = new_name

        veto_config.update_veto(self.template_name, maps, rules)
        await interaction.response.send_message(f"Template de veto '{self.template_name}' mis à jour avec succès.", ephemeral=True)

tournament_config = TournamentConfig()

class TeamCreateModal(Modal):
    def __init__(self, tournament_name):
        super().__init__(title="Ajouter une Équipe")
        self.tournament_name = tournament_name
        self.team_name = TextInput(label="Nom de l'Équipe", placeholder="Entrez le nom de l'équipe")
        self.add_item(self.team_name)

    async def on_submit(self, interaction: discord.Interaction):
        team_name = self.team_name.value.strip()
        if team_config.add_team(self.tournament_name, team_name):
            await interaction.response.send_message(f"Équipe '{team_name}' ajoutée au tournoi '{self.tournament_name}'.", ephemeral=True)
        else:
            await interaction.response.send_message(f"L'équipe '{team_name}' existe déjà dans le tournoi '{self.tournament_name}'.", ephemeral=True)

class TeamEditModal(Modal):
    def __init__(self, tournament_name, old_team_name):
        super().__init__(title=f"Modifier l'Équipe '{old_team_name}'")
        self.tournament_name = tournament_name
        self.old_team_name = old_team_name
        self.new_team_name = TextInput(
            label="Nouveau Nom de l'Équipe",
            default=old_team_name,
            placeholder="Entrez le nouveau nom de l'équipe"
        )
        self.add_item(self.new_team_name)

    async def on_submit(self, interaction: discord.Interaction):
        new_team_name = self.new_team_name.value.strip()
        if not new_team_name:
            await interaction.response.send_message("Le nom de l'équipe ne peut pas être vide.", ephemeral=True)
            return

        if team_config.update_team(self.tournament_name, self.old_team_name, new_team_name):
            await interaction.response.send_message(f"Équipe '{self.old_team_name}' mise à jour en '{new_team_name}'.", ephemeral=True)
        else:
            await interaction.response.send_message(f"Échec de la mise à jour de l'équipe '{self.old_team_name}'.", ephemeral=True)

class TeamDeleteButton(Button):
    def __init__(self, tournament_name, team_name):
        super().__init__(label=f"Supprimer {team_name}", style=discord.ButtonStyle.danger, custom_id=f"delete_{team_name}")
        self.tournament_name = tournament_name
        self.team_name = team_name

    async def callback(self, interaction: discord.Interaction):
        if team_config.delete_team(self.tournament_name, self.team_name):
            await interaction.response.send_message(f"Équipe '{self.team_name}' supprimée du tournoi '{self.tournament_name}'.", ephemeral=True)
        else:
            await interaction.response.send_message(f"Erreur lors de la suppression de l'équipe '{self.team_name}'.", ephemeral=True)

class TeamConfig:
    def __init__(self, filename="teams.json"):
        self.filename = filename
        self.teams = self.load_teams()

    def load_teams(self):
        if os.path.exists(self.filename):
            with open(self.filename, "r") as file:
                return json.load(file)
        return {}

    def save_teams(self):
        with open(self.filename, "w") as file:
            json.dump(self.teams, file, indent=4)

    def add_team(self, tournament, team_name):
        if tournament not in self.teams:
            self.teams[tournament] = []
        if team_name not in self.teams[tournament]:
            self.teams[tournament].append(team_name)
            self.save_teams()
            return True
        return False

    def delete_team(self, tournament, team_name):
        if tournament in self.teams and team_name in self.teams[tournament]:
            self.teams[tournament].remove(team_name)
            if not self.teams[tournament]:
                del self.teams[tournament]
            self.save_teams()
            return True
        return False

    def update_team(self, tournament, old_name, new_name):
        if tournament in self.teams and old_name in self.teams[tournament]:
            index = self.teams[tournament].index(old_name)
            self.teams[tournament][index] = new_name
            self.save_teams()
            return True
        return False

    def get_teams(self, tournament):
        return self.teams.get(tournament, [])

team_config = TeamConfig()

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
        opponent_user = interaction.client.get_user(veto.team_b_id if interaction.user.id == veto.team_a_id else veto.team_a_id)
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
        view = discord.ui.View()
        for item in interaction.message.components[0].children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
                view.add_item(item)
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
        for map_name in veto.listmaps:
            button = MapButton(label=map_name, veto_name=veto.name, action_type=action.lower(), channel=channel)
            if map_name in veto.banned_maps or map_name in veto.picked_maps_only:
                button.disabled = True
            components.append(button)

    view = discord.ui.View()
    for component in components:
        view.add_item(component)

    team_name = veto.team_a_name if veto.get_current_turn() == veto.team_a_id else veto.team_b_name

    if action == "Side":
        if len(veto.maps) == 1:
            last_picked_map = veto.maps[0]
            message = f"{current_user.mention}, vous devez choisir votre Side sur **{last_picked_map}**."
        else:
            # Include the last picked map in the message
            last_picked_map = veto.picked_maps[-1]["map"] if veto.picked_maps else "Unknown"
            message = f"{current_user.mention}, vous devez choisir votre Side sur **{last_picked_map}**."
    else:
        message = f"{current_user.mention}, c'est votre tour de {action} une map."

    try:
        await current_user.send(message, view=view)
    except discord.Forbidden:
        print(f"Cannot DM user {current_user.id}")

class MapVeto:
    def __init__(self, name, maps, team_a_id, team_a_name, team_b_id, team_b_name, rules, channel, bot):
        self.name = name
        self.maps = maps[:]
        self.listmaps = maps[:]
        self.team_a_id = team_a_id
        self.team_a_name = team_a_name
        self.team_b_id = team_b_id
        self.team_b_name = team_b_name
        self.rules = rules
        self.current_turn = team_a_id
        self.current_action = 0
        self.picked_maps = []
        self.picked_maps_only = []
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
            self.picked_maps_only.append(map_name)
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
        self.setup_message_id = None
        self.load_setup_message_id()

    def save_setup_message_id(self, message_id):
        with open('setup_message_id.json', 'w') as f:
            json.dump({'setup_message_id': message_id}, f)

    def load_setup_message_id(self):
        if os.path.exists('setup_message_id.json'):
            with open('setup_message_id.json', 'r') as f:
                data = json.load(f)
                self.setup_message_id = data.get('setup_message_id')

    async def update_setup_message(self, channel):
        if self.setup_message_id:
            try:
                message = await channel.fetch_message(self.setup_message_id)
                await message.edit(embed=self.create_setup_embed(), view=self.create_setup_view())
            except discord.NotFound:
                await self.send_setup_message(channel)
        else:
            await self.send_setup_message(channel)

    async def send_setup_message(self, channel):
        message = await channel.send(embed=self.create_setup_embed(), view=self.create_setup_view())
        self.setup_message_id = message.id
        self.save_setup_message_id(message.id)

    def create_setup_embed(self):
        embed = discord.Embed(
            title="Configuration des Templates de Veto",
            description="Utilisez les boutons ci-dessous pour gérer les templates de veto.",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="Créer un Template",
            value="Cliquez sur le bouton pour créer un nouveau template de veto.",
            inline=False
        )
        embed.add_field(
            name="Éditer un Template",
            value="Cliquez sur le bouton pour éditer un template de veto existant.",
            inline=False
        )
        embed.add_field(
            name="Supprimer un Template",
            value="Cliquez sur le bouton pour supprimer un template de veto existant.",
            inline=False
        )
        embed.add_field(
            name="Liste des Templates",
            value="Cliquez sur le bouton pour voir la liste des templates enregistrés.",
            inline=False
        )
        return embed

    def create_setup_view(self):
        view = discord.ui.View()
        view.add_item(ListButton())
        view.add_item(CreateButton())
        view.add_item(EditButton())
        view.add_item(DeleteButton())
        return view

    @commands.command(name='mapveto_setup')
    @commands.has_permissions(administrator=True)
    async def mapveto_setup(self, ctx):
        """Crée ou met à jour le message avec les boutons pour gérer les templates de veto."""
        await self.update_setup_message(ctx.channel)

class ListButton(Button):
    def __init__(self):
        super().__init__(label="Liste des Templates", style=discord.ButtonStyle.secondary, custom_id="list_templates")

    async def callback(self, interaction: discord.Interaction):
        veto_names = list(veto_config.vetos.keys())
        if not veto_names:
            await interaction.response.send_message("Aucun template de veto enregistré.", ephemeral=True)
            return

        # Créer l'embed pour la liste des templates
        embed = discord.Embed(
            title="Liste des Templates de Veto",
            description="Voici la liste des templates enregistrés :",
            color=discord.Color.green()
        )
        
        for name in veto_names:
            veto = veto_config.get_veto(name)
            embed.add_field(
                name=name,
                value=f"Maps: {veto['maps']}\nRules: {veto['rules']}",
                inline=False
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

class CreateButton(Button):
    def __init__(self):
        super().__init__(label="Créer un template", style=discord.ButtonStyle.primary, custom_id="create_template")

    async def callback(self, interaction: discord.Interaction):
        modal = VetoCreateModal()
        await interaction.response.send_modal(modal)

class EditButton(Button):
    def __init__(self):
        super().__init__(label="Éditer un template", style=discord.ButtonStyle.primary, custom_id="edit_template")

    async def callback(self, interaction: discord.Interaction):
        veto_names = list(veto_config.vetos.keys())
        if not veto_names:
            await interaction.response.send_message("Aucun template de veto disponible pour modification.", ephemeral=True)
            return

        class VetoEditSelect(Select):
            def __init__(self, options):
                super().__init__(placeholder="Choisissez un template à éditer...", options=options)
        
            async def callback(self, interaction: discord.Interaction):
                selected_template = self.values[0]
                veto = veto_config.get_veto(selected_template)
                
                if not veto:
                    await interaction.response.send_message("Template de veto introuvable.", ephemeral=True)
                    return
                
                edit_modal = VetoEditModal(selected_template, veto)
                await interaction.response.send_modal(edit_modal)

        select = VetoEditSelect([discord.SelectOption(label=name, value=name) for name in veto_names])
        view = View()
        view.add_item(select)
        await interaction.response.send_message("Sélectionnez un template à éditer :", view=view, ephemeral=True)

class DeleteButton(Button):
    def __init__(self):
        super().__init__(label="Supprimer un template", style=discord.ButtonStyle.danger, custom_id="delete_template")

    async def callback(self, interaction: discord.Interaction):
        veto_names = list(veto_config.vetos.keys())
        if not veto_names:
            await interaction.response.send_message("Aucun template de veto disponible pour suppression.", ephemeral=True)
            return

        class VetoDeleteSelect(Select):
            def __init__(self, options):
                super().__init__(placeholder="Choisissez un template à supprimer...", options=options)
            
            async def callback(self, interaction: discord.Interaction):
                selected_template = self.values[0]
                confirm_view = View()
                confirm_view.add_item(ConfirmDeleteButton(selected_template))
                
                await interaction.response.send_message(
                    f"Êtes-vous sûr de vouloir supprimer le template '{selected_template}' ?",
                    view=confirm_view,
                    ephemeral=True
                )

        select = VetoDeleteSelect([discord.SelectOption(label=name, value=name) for name in veto_names])
        view = View()
        view.add_item(select)
        await interaction.response.send_message("Sélectionnez un template à supprimer :", view=view, ephemeral=True)

class ConfirmDeleteButton(Button):
    def __init__(self, template_name):
        super().__init__(label=f"Confirmer la suppression de {template_name}", style=discord.ButtonStyle.danger, custom_id=f"confirm_delete_{template_name}")
        self.template_name = template_name

    async def callback(self, interaction: discord.Interaction):
        if veto_config.delete_veto(self.template_name):
            await interaction.response.send_message(f"Le template '{self.template_name}' a été supprimé avec succès.", ephemeral=True)
        else:
            await interaction.response.send_message(f"Erreur lors de la suppression du template '{self.template_name}'.", ephemeral=True)

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

        await ctx.send(embed=embed)
    
class TournamentCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.setup_message_id = None
        self.load_setup_message_id()

    def save_setup_message_id(self, message_id):
        with open('setup_message_id.json', 'w') as f:
            json.dump({'setup_message_id': message_id}, f)

    def load_setup_message_id(self):
        if os.path.exists('setup_message_id.json'):
            with open('setup_message_id.json', 'r') as f:
                data = json.load(f)
                self.setup_message_id = data.get('setup_message_id')

    async def update_setup_message(self, channel):
        if self.setup_message_id:
            try:
                message = await channel.fetch_message(self.setup_message_id)
                await message.edit(embed=self.create_setup_embed(), view=self.create_setup_view())
            except discord.NotFound:
                await self.send_setup_message(channel)
        else:
            await self.send_setup_message(channel)

    async def send_setup_message(self, channel):
        message = await channel.send(embed=self.create_setup_embed(), view=self.create_setup_view())
        self.setup_message_id = message.id
        self.save_setup_message_id(message.id)

    def create_setup_embed(self):
        embed = discord.Embed(
            title="Configuration des Tournois",
            description="Utilisez les boutons ci-dessous pour gérer les tournois.",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="Créer un Tournoi",
            value="Cliquez sur le bouton pour créer un nouveau tournoi.",
            inline=False
        )
        embed.add_field(
            name="Éditer un Tournoi",
            value="Cliquez sur le bouton pour éditer un tournoi existant.",
            inline=False
        )
        embed.add_field(
            name="Supprimer un Tournoi",
            value="Cliquez sur le bouton pour supprimer un tournoi existant.",
            inline=False
        )
        embed.add_field(
            name="Liste des Tournois",
            value="Cliquez sur le bouton pour voir la liste des tournois enregistrés.",
            inline=False
        )
        return embed

    def create_setup_view(self):
        view = discord.ui.View()
        view.add_item(ListTournamentsButton())
        view.add_item(CreateTournamentButton())
        view.add_item(EditTournamentButton())
        view.add_item(DeleteTournamentButton())
        return view

    @commands.command(name='tournament_setup')
    @commands.has_permissions(administrator=True)
    async def tournament_setup(self, ctx):
        """Crée ou met à jour le message avec les boutons pour gérer les tournois."""
        await self.update_setup_message(ctx.channel)

class ListTournamentsButton(Button):
    def __init__(self):
        super().__init__(label="Liste des Tournois", style=discord.ButtonStyle.secondary, custom_id="list_tournaments")

    async def callback(self, interaction: discord.Interaction):
        tournament_names = list(tournament_config.tournaments.keys())
        if not tournament_names:
            await interaction.response.send_message("Aucun tournoi enregistré.", ephemeral=True)
            return

        embed = discord.Embed(
            title="Liste des Tournois",
            description="Voici la liste des tournois enregistrés :",
            color=discord.Color.green()
        )

        for name in tournament_names:
            tournament = tournament_config.get_tournament(name)
            embed.add_field(
                name=name,
                value=f"Template: {tournament['template']}",
                inline=False
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

class CreateTournamentButton(Button):
    def __init__(self):
        super().__init__(label="Créer un tournoi", style=discord.ButtonStyle.primary, custom_id="create_tournament")

    async def callback(self, interaction: discord.Interaction):
        # Récupérer la liste des templates disponibles
        templates = list(veto_config.vetos.keys())
        if not templates:
            await interaction.response.send_message("Aucun template disponible pour création de tournoi.", ephemeral=True)
            return

        class TemplateSelect(Select):
            def __init__(self, options):
                super().__init__(placeholder="Choisissez un template pour le tournoi...", options=options)

            async def callback(self, interaction: discord.Interaction):
                selected_template = self.values[0]
                # Ouvrir une fenêtre modale pour entrer le nom du tournoi
                modal = TournamentCreateModal(selected_template)
                await interaction.response.send_modal(modal)

        select = TemplateSelect([discord.SelectOption(label=name, value=name) for name in templates])
        view = discord.ui.View()
        view.add_item(select)
        await interaction.response.send_message("Veuillez choisir un template pour le tournoi :", view=view, ephemeral=True)

class EditTournamentButton(Button):
    def __init__(self):
        super().__init__(label="Éditer un tournoi", style=discord.ButtonStyle.primary, custom_id="edit_tournament")

    async def callback(self, interaction: discord.Interaction):
        tournament_names = list(tournament_config.tournaments.keys())
        if not tournament_names:
            await interaction.response.send_message("Aucun tournoi disponible pour modification.", ephemeral=True)
            return

        class TournamentEditSelect(Select):
            def __init__(self, options):
                super().__init__(placeholder="Choisissez un tournoi à éditer...", options=options)

            async def callback(self, interaction: discord.Interaction):
                selected_tournament = self.values[0]
                tournament = tournament_config.get_tournament(selected_tournament)

                if not tournament:
                    await interaction.response.send_message("Tournoi introuvable.", ephemeral=True)
                    return

                modal = TournamentEditModal(selected_tournament, tournament)
                await interaction.response.send_modal(modal)

        select = TournamentEditSelect([discord.SelectOption(label=name, value=name) for name in tournament_names])
        view = View()
        view.add_item(select)
        await interaction.response.send_message("Sélectionnez un tournoi à éditer :", view=view, ephemeral=True)

class DeleteTournamentButton(Button):
    def __init__(self):
        super().__init__(label="Supprimer un tournoi", style=discord.ButtonStyle.danger, custom_id="delete_tournament")

    async def callback(self, interaction: discord.Interaction):
        tournament_names = list(tournament_config.tournaments.keys())
        if not tournament_names:
            await interaction.response.send_message("Aucun tournoi disponible pour suppression.", ephemeral=True)
            return

        class TournamentDeleteSelect(Select):
            def __init__(self, options):
                super().__init__(placeholder="Choisissez un tournoi à supprimer...", options=options)

            async def callback(self, interaction: discord.Interaction):
                selected_tournament = self.values[0]
                confirm_view = View()
                confirm_view.add_item(ConfirmTournamentDeleteButton(selected_tournament))

                await interaction.response.send_message(
                    f"Êtes-vous sûr de vouloir supprimer le tournoi '{selected_tournament}' ?",
                    view=confirm_view,
                    ephemeral=True
                )

        select = TournamentDeleteSelect([discord.SelectOption(label=name, value=name) for name in tournament_names])
        view = View()
        view.add_item(select)
        await interaction.response.send_message("Sélectionnez un tournoi à supprimer :", view=view, ephemeral=True)

class ConfirmTournamentDeleteButton(Button):
    def __init__(self, tournament_name):
        super().__init__(label=f"Confirmer la suppression de {tournament_name}", style=discord.ButtonStyle.danger, custom_id=f"confirm_delete_tournament_{tournament_name}")
        self.tournament_name = tournament_name

    async def callback(self, interaction: discord.Interaction):
        if tournament_config.delete_tournament(self.tournament_name):
            await interaction.response.send_message(f"Le tournoi '{self.tournament_name}' a été supprimé avec succès.", ephemeral=True)
        else:
            await interaction.response.send_message(f"Erreur lors de la suppression du tournoi '{self.tournament_name}'.", ephemeral=True)

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='list_teams')
    async def list_teams(self, ctx, tournament_name: str):
        """Liste les équipes pour un tournoi donné."""
        teams = team_config.get_teams(tournament_name)
        if not teams:
            await ctx.send(f"Aucune équipe trouvée pour le tournoi '{tournament_name}'.")
        else:
            embed = discord.Embed(
                title=f"Équipes pour le tournoi '{tournament_name}'",
                description="\n".join(teams),
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)

    @commands.command(name='add_team')
    async def add_team(self, ctx, tournament_name: str):
        """Ajoute une équipe à un tournoi donné."""
        modal = TeamCreateModal(tournament_name)
        await ctx.send_modal(modal)

    @commands.command(name='edit_team')
    async def edit_team(self, ctx, tournament_name: str, old_team_name: str):
        """Édite le nom d'une équipe existante."""
        modal = TeamEditModal(tournament_name, old_team_name)
        await ctx.send_modal(modal)

    @commands.command(name='delete_team')
    async def delete_team(self, ctx, tournament_name: str, team_name: str):
        """Supprime une équipe d'un tournoi donné."""
        if team_config.delete_team(tournament_name, team_name):
            await ctx.send(f"Équipe '{team_name}' supprimée du tournoi '{tournament_name}'.")
        else:
            await ctx.send(f"Erreur lors de la suppression de l'équipe '{team_name}'.")

async def setup(bot):
    await bot.add_cog(MapVetoCog(bot))
    await bot.add_cog(TournamentCog(bot))
    await bot.add_cog(TournamentCog(bot))
