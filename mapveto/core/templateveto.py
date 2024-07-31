import json
import os
import discord # type: ignore
from discord.ui import Modal, TextInput, View, Button, Select # type: ignore
from discord.ext import commands # type: ignore

class MapVetoConfig:
    def __init__(self, filename="vetos.json"):
        self.filename = os.path.join(os.path.dirname(__file__), '..', filename)
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

class TemplateManager:
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
        message = await channel.send(embed=self.create_setup_embed(), view=self.create_setup_view(), timeout=None)
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
