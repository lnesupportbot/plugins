import json
import os
import discord # type: ignore
from discord.ui import Modal, TextInput, Button, Select, View # type: ignore
from discord.ext import commands # type: ignore

from .templateveto import MapVetoConfig, veto_config

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
veto_config = MapVetoConfig()

class TournamentCreateModal(Modal):
    def __init__(self, template_name):
        super().__init__(title="Créer un Tournoi")
        self.template_name = template_name
        self.name = TextInput(label="Nom du Tournoi", placeholder="Entrez le nom du tournoi")

        self.add_item(self.name)

    async def on_submit(self, interaction: discord.Interaction):
        tournament_name = self.name.value.strip()
        template_name = self.template_name

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

class Tournament:
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

class ListTournamentsButton(Button):
    def __init__(self):
        super().__init__(label="Liste des Tournois", style=discord.ButtonStyle.primary, custom_id="list_tournaments")

    async def callback(self, interaction: discord.Interaction):
        tournaments = tournament_config.tournaments
        if not tournaments:
            await interaction.response.send_message("Aucun tournoi trouvé.", ephemeral=True)
            return

        embed = discord.Embed(
            title="Liste des Tournois",
            description="\n".join(f"- {name} (Template: {data['template']})" for name, data in tournaments.items()),
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

class CreateTournamentButton(Button):
    def __init__(self):
        super().__init__(label="Créer un tournoi", style=discord.ButtonStyle.primary, custom_id="create_tournament")

    async def callback(self, interaction: discord.Interaction):
        templates = list(veto_config.vetos.keys())
        if not templates:
            await interaction.response.send_message("Aucun template disponible pour création de tournoi.", ephemeral=True)
            return
        
        class TemplateSelect(Select):
            def __init__(self, options):
                super().__init__(placeholder="Choisissez un template pour le tournoi...", options=options)

            async def callback(self, interaction: discord.Interaction):
                selected_template = self.values[0]
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
