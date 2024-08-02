import json
import os
import discord # type: ignore
from discord.ui import Modal, TextInput, Button, Select, View # type: ignore
from discord.ext import commands # type: ignore

from .tournament import TournamentConfig, tournament_config

class TeamConfig:
    def __init__(self, filename="teams.json"):
        self.filename = os.path.join(os.path.dirname(__file__), '..', filename)
        self.teams = self.load_teams()
        self.tournaments = TournamentConfig.load_tournaments()

    def load_teams(self):
        if os.path.exists(self.filename):
            with open(self.filename, "r") as file:
                return json.load(file)
        return {}

    def save_teams(self):
        with open(self.filename, "w") as file:
            json.dump(self.teams, file, indent=4)

    def create_team(self, name, tournament_name, captain_discord_id):
        if name not in self.teams:
            self.teams[name] = {
                "tournament": tournament_name,
                "captain_discord_id": captain_discord_id
            }
            self.save_teams()
            return True
        return False

    def delete_team(self, name):
        if name in self.teams:
            del self.teams[name]
            self.save_teams()
            return True
        return False

    def get_team(self, name):
        return self.teams.get(name, None)

    def update_team(self, name, tournament_name, captain_discord_id):
        if name in self.teams:
            self.teams[name]["tournament"] = tournament_name
            self.teams[name]["captain_discord_id"] = captain_discord_id
            self.save_teams()
            return True
        return False
        
    def get_teams_by_tournament(self, tournament_name):
        teams = {}
        for name, data in self.teams.items():
            if "tournament" in data and data["tournament"] == tournament_name:
                teams[name] = data
        return teams

team_config = TeamConfig()
tournament_config = TournamentConfig()

class TeamCreateModal(Modal):
    def __init__(self, tournament_name):
        super().__init__(title="Créer une Équipe")
        self.tournament_name = tournament_name
        self.name = TextInput(label="Nom de l'Équipe", placeholder="Entrez le nom de l'équipe")
        self.captain_discord_id = TextInput(label="Discord ID du Capitaine", placeholder="Entrez le Discord ID du capitaine")
        self.add_item(self.name)
        self.add_item(self.captain_discord_id)

    async def on_submit(self, interaction: discord.Interaction):
        team_name = self.name.value
        captain_discord_id = self.captain_discord_id.value
        if team_config.create_team(team_name, self.tournament_name, captain_discord_id):
            await interaction.response.send_message(f"L'équipe '{team_name}' a été créée avec succès.", ephemeral=True)
        else:
            await interaction.response.send_message(f"Une équipe avec le nom '{team_name}' existe déjà.", ephemeral=True)

class TeamEditModal(Modal):
    def __init__(self, team_name, team):
        super().__init__(title=f"Modifier l'Équipe '{team_name}'")
        self.team_name = team_name
        self.team = team
        self.name = TextInput(
            label="Nom de l'Équipe",
            default=team_name,
            placeholder="Entrez le nom de l'équipe"
        )
        self.template = TextInput(
            label="Tournoi rattaché à l'Équipe",
            default=team["tournament"],
            placeholder="Entrez le nom du tournoi"
        )
        self.add_item(self.name)
        self.add_item(self.template)

    async def on_submit(self, interaction: discord.Interaction):
        new_name = self.name.value.strip()
        template = self.template.value.strip()

        if not new_name:
            await interaction.response.send_message("Le nom ne peut pas être vide.", ephemeral=True)
            return

        if new_name != self.team_name:
            if team_config.get_team(new_name):
                await interaction.response.send_message(f"Une équipe avec le nom '{new_name}' existe déjà.", ephemeral=True)
                return
            else:
                team_config.teams[new_name] = team_config.teams.pop(self.team_name)
                self.team_name = new_name

        team_config.update_team(self.team_name, template)
        await interaction.response.send_message(f"Équipe '{self.team_name}' mise à jour avec succès.", ephemeral=True)

class TeamDeleteButton(Button):
    def __init__(self, team_name):
        super().__init__(label=f"Supprimer {team_name}", style=discord.ButtonStyle.danger, custom_id=f"delete_{team_name}")
        self.team_name = team_name

    async def callback(self, interaction: discord.Interaction):
        if team_config.delete_team(self.team_name):
            await interaction.response.send_message(f"L'équipe '{self.team_name}' a été supprimée avec succès.", ephemeral=True)
        else:
            await interaction.response.send_message(f"Erreur lors de la suppression de l'équipe '{self.team_name}'.", ephemeral=True)

class TeamManager:
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
        tournament_config.load_tournaments()
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
            title="Configuration des Équipes",
            description="Utilisez les boutons ci-dessous pour gérer les équipes.",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="Créer une Équipe",
            value="Cliquez sur le bouton pour créer une nouvelle équipe.",
            inline=False
        )
        embed.add_field(
            name="Éditer une Équipe",
            value="Cliquez sur le bouton pour éditer une équipe existante.",
            inline=False
        )
        embed.add_field(
            name="Supprimer une Équipe",
            value="Cliquez sur le bouton pour supprimer une équipe existante.",
            inline=False
        )
        embed.add_field(
            name="Liste des Équipes",
            value="Cliquez sur le bouton pour voir la liste des équipes enregistrées.",
            inline=False
        )
        return embed

    def create_setup_view(self):
        view = discord.ui.View(timeout=None)
        view.add_item(ListTeamsButton())
        view.add_item(CreateTeamButton())
        view.add_item(EditTeamButton())
        view.add_item(DeleteTeamButton())
        return view

class ListTeamsButton(Button):
    def __init__(self):
        super().__init__(label="Liste des Équipes", style=discord.ButtonStyle.secondary, custom_id="list_teams")

    async def callback(self, interaction: discord.Interaction):
        tournament_names = list(tournament_config.tournaments.keys())  # Liste des tournois
        if not tournament_names:
            await interaction.response.send_message("Aucun tournoi trouvé.", ephemeral=True)
            return

        class TournamentSelect(Select):
            def __init__(self, options):
                super().__init__(placeholder="Choisissez un tournoi...", options=options)

            async def callback(self, interaction: discord.Interaction):
                selected_tournament = self.values[0]
                teams = team_config.get_teams_by_tournament(selected_tournament)
                if not teams:
                    await interaction.response.send_message(f"Aucune équipe trouvée pour le tournoi '{selected_tournament}'.", ephemeral=True)
                    return

                embed = discord.Embed(
                    title=f"Équipes pour le Tournoi '{selected_tournament}'",
                    description="\n".join(f"- {name}" for name in teams.keys()),
                    color=discord.Color.green()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)

        select = TournamentSelect([discord.SelectOption(label=name, value=name) for name in tournament_names])
        view = discord.ui.View()
        view.add_item(select)
        await interaction.response.send_message("Veuillez choisir un tournoi pour afficher les équipes :", view=view, ephemeral=True)

class CreateTeamButton(Button):
    def __init__(self):
        super().__init__(label="Créer une nouvelle équipe", style=discord.ButtonStyle.primary, custom_id="create_team")

    async def callback(self, interaction: discord.Interaction):
        tournament_names = list(tournament_config.tournaments.keys())
        if not tournament_names:
            await interaction.response.send_message("Aucun tournoi disponible.", ephemeral=True)
            return

        class TournamentSelect(Select):
            def __init__(self, options):
                super().__init__(placeholder="Choisissez un tournoi...", options=options)

            async def callback(self, interaction: discord.Interaction):
                selected_tournament = self.values[0]
                modal = TeamCreateModal(selected_tournament)
                await interaction.response.send_modal(modal)

        select = TournamentSelect([discord.SelectOption(label=name, value=name) for name in tournament_names])
        view = View()
        view.add_item(select)
        await interaction.response.send_message("Sélectionnez un tournoi pour créer une équipe :", view=view, ephemeral=True)

class EditTeamButton(Button):
    def __init__(self):
        super().__init__(label="Éditer une équipe", style=discord.ButtonStyle.primary, custom_id="edit_team")

    async def callback(self, interaction: discord.Interaction):
        team_names = list(team_config.teams.keys())
        if not team_names:
            await interaction.response.send_message("Aucune équipe disponible pour modification.", ephemeral=True)
            return

        class TeamEditSelect(Select):
            def __init__(self, options):
                super().__init__(placeholder="Choisissez une équipe à éditer...", options=options)

            async def callback(self, interaction: discord.Interaction):
                selected_team = self.values[0]
                team = team_config.get_team(selected_team)

                if not team:
                    await interaction.response.send_message("Équipe introuvable.", ephemeral=True)
                    return

                modal = TeamEditModal(selected_team, team)
                await interaction.response.send_modal(modal)

        select = TeamEditSelect([discord.SelectOption(label=name, value=name) for name in team_names])
        view = View()
        view.add_item(select)
        await interaction.response.send_message("Sélectionnez une équipe à éditer :", view=view, ephemeral=True)

class DeleteTeamButton(Button):
    def __init__(self):
        super().__init__(label="Supprimer une équipe", style=discord.ButtonStyle.danger, custom_id="delete_team")

    async def callback(self, interaction: discord.Interaction):
        team_names = list(team_config.teams.keys())
        if not team_names:
            await interaction.response.send_message("Aucune équipe disponible pour suppression.", ephemeral=True)
            return

        class TeamDeleteSelect(Select):
            def __init__(self, options):
                super().__init__(placeholder="Choisissez une équipe à supprimer...", options=options)

            async def callback(self, interaction: discord.Interaction):
                selected_team = self.values[0]
                confirm_view = View()
                confirm_view.add_item(ConfirmTeamDeleteButton(selected_team))

                await interaction.response.send_message(
                    f"Êtes-vous sûr de vouloir supprimer l'équipe '{selected_team}' ?",
                    view=confirm_view,
                    ephemeral=True
                )

        select = TeamDeleteSelect([discord.SelectOption(label=name, value=name) for name in team_names])
        view = View()
        view.add_item(select)
        await interaction.response.send_message("Sélectionnez une équipe à supprimer :", view=view, ephemeral=True)

class ConfirmTeamDeleteButton(Button):
    def __init__(self, team_name):
        super().__init__(label=f"Confirmer la suppression de {team_name}", style=discord.ButtonStyle.danger, custom_id=f"confirm_delete_team_{team_name}")
        self.team_name = team_name

    async def callback(self, interaction: discord.Interaction):
        if team_config.delete_team(self.team_name):
            await interaction.response.send_message(f"L'équipe '{self.team_name}' a été supprimée avec succès.", ephemeral=True)
        else:
            await interaction.response.send_message(f"Erreur lors de la suppression de l'équipe '{self.team_name}'.", ephemeral=True)
