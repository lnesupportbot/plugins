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

    def refresh_teams(self):
        """Refresh the teams data from the file."""
        self.teams = self.load_teams()

team_config = TeamConfig()
tournament_config = TournamentConfig()

class TeamCreateModal(Modal):
    def __init__(self, bot, tournament_name):
        super().__init__(title="Créer une Équipe")
        self.bot = bot
        self.tournament_name = tournament_name
        self.name = TextInput(label="Nom de l'Équipe", placeholder="Entrez le nom de l'équipe")
        self.captain_discord_id = TextInput(label="Discord ID du Capitaine", placeholder="Entrez le Discord ID du capitaine")
        self.add_item(self.name)
        self.add_item(self.captain_discord_id)

    async def on_submit(self, interaction: discord.Interaction):
        team_name = self.name.value
        captain_discord_id = self.captain_discord_id.value

        try:
            # Fetch user object using the bot
            captain = await self.bot.fetch_user(int(captain_discord_id))
            if team_config.create_team(team_name, self.tournament_name, captain_discord_id):
                await interaction.response.send_message(
                    f"L'équipe **{team_name}** a été créée avec succès.\nTournoi: **{self.tournament_name}**\nCapitaine: **{captain.display_name}**",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(f"Une équipe avec le nom '{team_name}' existe déjà.", ephemeral=True)
        except discord.NotFound:
            await interaction.response.send_message("Le Discord ID du capitaine est invalide.", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("Veuillez entrer un ID Discord valide pour le capitaine.", ephemeral=True)

class TeamEditModal(Modal):
    def __init__(self, bot, team_name, team):
        super().__init__(title=f"Modifier l'Équipe '{team_name}'")
        self.bot = bot  # Stocker le bot
        self.team_name = team_name
        self.team = team
        self.name = TextInput(
            label="Nom de l'Équipe",
            default=team_name,
            placeholder="Entrez le nom de l'équipe"
        )
        self.captain_discord_id = TextInput(
            label="Discord ID du Capitaine",
            default=team["captain_discord_id"],
            placeholder="Entrez le Discord ID du capitaine"
        )
        self.add_item(self.name)
        self.add_item(self.captain_discord_id)

    async def on_submit(self, interaction: discord.Interaction):
        new_name = self.name.value.strip()
        captain_discord_id = self.captain_discord_id.value.strip()

        if not new_name:
            await interaction.response.send_message("Le nom ne peut pas être vide.", ephemeral=True)
            return

        try:
            # Fetch user object using the bot
            captain = await self.bot.fetch_user(int(captain_discord_id))
            if new_name != self.team_name:
                if team_config.get_team(new_name):
                    await interaction.response.send_message(f"Une équipe avec le nom '{new_name}' existe déjà.", ephemeral=True)
                    return
                else:
                    team_config.teams[new_name] = team_config.teams.pop(self.team_name)
                    self.team_name = new_name

            # Mise à jour des informations de l'équipe
            team_config.update_team(self.team_name, self.team["tournament"], captain_discord_id)
            await interaction.response.send_message(
                f"Équipe '{self.team_name}' mise à jour avec succès.\nTournoi: {self.team['tournament']}\nCapitaine: {captain.display_name}",
                ephemeral=True
            )
        except discord.NotFound:
            await interaction.response.send_message("Le Discord ID du capitaine est invalide.", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("Veuillez entrer un ID Discord valide pour le capitaine.", ephemeral=True)

class ChangeTournamentButton(Button):
    def __init__(self, bot, team_name):
        super().__init__(label="Changer le tournoi", style=discord.ButtonStyle.primary, custom_id=f"change_tournament_{team_name}")
        self.team_name = team_name
        self.bot = bot

    async def callback(self, interaction: discord.Interaction):
        tournament_names = list(tournament_config.tournaments.keys())
        if not tournament_names:
            await interaction.response.send_message("Aucun tournoi disponible pour la modification.", ephemeral=True)
            return

        class TournamentSelect(Select):
            def __init__(self, bot, team_name, options):
                super().__init__(placeholder="Choisissez un tournoi...", options=options)
                self.team_name = team_name
                self.bot = bot

            async def callback(self, interaction: discord.Interaction):
                selected_tournament = self.values[0]
                team = team_config.get_team(self.team_name)
                # Créer la fenêtre modale sans le champ "Tournoi"
                modal = TeamEditModal(self.bot, self.team_name, team)
                team_config.update_team(self.team_name, selected_tournament, team["captain_discord_id"])  # Mise à jour du tournoi ici
                await interaction.response.send_modal(modal)

        select = TournamentSelect(self.team_name, [discord.SelectOption(label=name, value=name) for name in tournament_names])
        view = View()
        view.add_item(select)
        await interaction.response.send_message("Choisissez un nouveau tournoi pour l'équipe :", view=view, ephemeral=True)

class NoChangeTournamentButton(Button):
    def __init__(self, bot, team_name):
        super().__init__(label="Ne pas changer le tournoi", style=discord.ButtonStyle.secondary, custom_id=f"no_change_tournament_{team_name}")
        self.team_name = team_name
        self.bot = bot

    async def callback(self, interaction: discord.Interaction):
        team = team_config.get_team(self.team_name)
        # Créer la fenêtre modale sans le champ "Tournoi"
        modal = TeamEditModal(self.team_name, team)
        # Passer le tournoi actuel à la méthode update_team
        team_config.update_team(self.team_name, team["tournament"], team["captain_discord_id"])  
        await interaction.response.send_modal(modal)


class TeamEditTournamentSelect(Select):
    def __init__(self, current_tournament, options):
        super().__init__(placeholder="Choisissez un tournoi...", options=options)
        self.current_tournament = current_tournament

    async def callback(self, interaction: discord.Interaction):
        selected_tournament = self.values[0]
        teams = team_config.get_teams_by_tournament(selected_tournament)
        
        if not teams:
            await interaction.response.send_message(f"Aucune équipe trouvée pour le tournoi '{selected_tournament}'.", ephemeral=True)
            return

        class TeamSelect(Select):
            def __init__(self, options):
                super().__init__(placeholder="Choisissez une équipe...", options=options)

            async def callback(self, interaction: discord.Interaction):
                selected_team = self.values[0]
                team = team_config.get_team(selected_team)
                
                if not team:
                    await interaction.response.send_message("Équipe introuvable.", ephemeral=True)
                    return
                
                # Demander si le tournoi doit être modifié
                view = View()
                view.add_item(ChangeTournamentButton(selected_team))
                view.add_item(NoChangeTournamentButton(selected_team))

                await interaction.response.send_message(
                    "Souhaitez-vous également changer le tournoi associé ?",
                    view=view,
                    ephemeral=True
                )

        select = TeamSelect([discord.SelectOption(label=name, value=name) for name in teams.keys()])
        view = View()
        view.add_item(select)
        await interaction.response.send_message("Sélectionnez une équipe à éditer :", view=view, ephemeral=True)

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

    def refresh_setup_message_id(self):
        """Refresh the message id from the file."""
        self.message_id = self.load_setup_message_id()

    async def update_setup_message(self, channel):
        self.refresh_setup_message_id()
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
        view.add_item(CreateTeamButton(self.bot))  # Passez le bot ici
        view.add_item(EditTeamButton(self.bot))
        view.add_item(DeleteTeamButton())
        return view

class ListTeamsButton(Button):
    def __init__(self):
        super().__init__(label="Liste des Équipes", style=discord.ButtonStyle.secondary, custom_id="list_teams")

    async def callback(self, interaction: discord.Interaction):
        tournament_config.refresh_tournaments()
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
    def __init__(self, bot):
        super().__init__(label="Créer une nouvelle équipe", style=discord.ButtonStyle.primary, custom_id="create_team")
        self.bot = bot

    async def callback(self, interaction: discord.Interaction):
        tournament_config.refresh_tournaments()
        tournament_names = list(tournament_config.tournaments.keys())
        if not tournament_names:
            await interaction.response.send_message("Aucun tournoi disponible.", ephemeral=True)
            return

        class TournamentSelect(Select):
            def __init__(self, bot, options):
                self.bot = bot
                super().__init__(placeholder="Choisissez un tournoi...", options=options)

            async def callback(self, interaction: discord.Interaction):
                selected_tournament = self.values[0]
                modal = TeamCreateModal(self.bot, selected_tournament)  # Passer le bot ici
                await interaction.response.send_modal(modal)

        select = TournamentSelect(self.bot, [discord.SelectOption(label=name, value=name) for name in tournament_names])
        view = View()
        view.add_item(select)
        await interaction.response.send_message("Sélectionnez un tournoi pour créer une équipe :", view=view, ephemeral=True)

class EditTeamButton(Button):
    def __init__(self, bot):
        super().__init__(label="Éditer une équipe", style=discord.ButtonStyle.primary, custom_id="edit_team")
        self.bot = bot

    async def callback(self, interaction: discord.Interaction):
        tournament_names = list(tournament_config.tournaments.keys())
        if not tournament_names:
            await interaction.response.send_message("Aucun tournoi disponible pour la modification.", ephemeral=True)
            return

        class TournamentSelect(Select):
            def __init__(self,  options):
                super().__init__(placeholder="Choisissez un tournoi...", options=options)

            async def callback(self, interaction: discord.Interaction):
                selected_tournament = self.values[0]
                teams = team_config.get_teams_by_tournament(selected_tournament)
                
                if not teams:
                    await interaction.response.send_message(f"Aucune équipe trouvée pour le tournoi '{selected_tournament}'.", ephemeral=True)
                    return

                class TeamSelect(Select):
                    def __init__(self, bot, options):
                        super().__init__(placeholder="Choisissez une équipe...", options=options)
                        self.bot = bot

                    async def callback(self, interaction: discord.Interaction):
                        selected_team = self.values[0]
                        team = team_config.get_team(selected_team)
                        
                        if not team:
                            await interaction.response.send_message("Équipe introuvable.", ephemeral=True)
                            return
                        
                        # Demander si le tournoi doit être modifié
                        view = View()
                        view.add_item(ChangeTournamentButton(self.bot, selected_team))
                        view.add_item(NoChangeTournamentButton(self.bot, selected_team))

                        await interaction.response.send_message(
                            "Souhaitez-vous également changer le tournoi associé ?",
                            view=view,
                            ephemeral=True
                        )

                select = TeamSelect([discord.SelectOption(label=name, value=name) for name in teams.keys()])
                view = View()
                view.add_item(select)
                await interaction.response.send_message("Sélectionnez une équipe à éditer :", view=view, ephemeral=True)

        select = TournamentSelect([discord.SelectOption(label=name, value=name) for name in tournament_names])
        view = View()
        view.add_item(select)
        await interaction.response.send_message("Choisissez un tournoi pour filtrer les équipes :", view=view, ephemeral=True)

class DeleteTeamButton(Button):
    def __init__(self):
        super().__init__(label="Supprimer une équipe", style=discord.ButtonStyle.danger, custom_id="delete_team")

    async def callback(self, interaction: discord.Interaction):
        tournament_names = list(tournament_config.tournaments.keys())
        if not tournament_names:
            await interaction.response.send_message("Aucun tournoi disponible pour la suppression.", ephemeral=True)
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

                class TeamSelect(Select):
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

                select = TeamSelect([discord.SelectOption(label=name, value=name) for name in teams.keys()])
                view = View()
                view.add_item(select)
                await interaction.response.send_message("Sélectionnez une équipe à supprimer :", view=view, ephemeral=True)

        select = TournamentSelect([discord.SelectOption(label=name, value=name) for name in tournament_names])
        view = View()
        view.add_item(select)
        await interaction.response.send_message("Choisissez un tournoi pour filtrer les équipes :", view=view, ephemeral=True)

class ConfirmTeamDeleteButton(Button):
    def __init__(self, team_name):
        super().__init__(label=f"Confirmer la suppression de {team_name}", style=discord.ButtonStyle.danger, custom_id=f"confirm_delete_team_{team_name}")
        self.team_name = team_name

    async def callback(self, interaction: discord.Interaction):
        if team_config.delete_team(self.team_name):
            await interaction.response.send_message(f"L'équipe '{self.team_name}' a été supprimée avec succès.", ephemeral=True)
        else:
            await interaction.response.send_message(f"Erreur lors de la suppression de l'équipe '{self.team_name}'.", ephemeral=True)
