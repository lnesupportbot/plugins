import json
import os
import discord
from discord.ui import Modal, TextInput, View, Button, Select

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

        if new_name != self.template_name:
            veto_config.delete_veto(self.template_name)
            veto_config.create_veto(new_name, maps, rules)
        else:
            veto_config.update_veto(new_name, maps, rules)

        await interaction.response.send_message(f"Template de veto '{new_name}' mis à jour avec succès.", ephemeral=True)

class MapButton(Button):
    def __init__(self, label, map_name, veto, team):
        super().__init__(label=label, style=discord.ButtonStyle.primary)
        self.map_name = map_name
        self.veto = veto
        self.team = team

    async def callback(self, interaction: discord.Interaction):
        await self.veto.process_map_selection(interaction, self.map_name, self.team)

async def send_ticket_message(bot, veto, channel):
    team_a = await bot.fetch_user(veto.team_a_id)
    team_b = await bot.fetch_user(veto.team_b_id)

    view_a = View()
    view_b = View()
    for map_name in veto.maps:
        view_a.add_item(MapButton(f"Ban {map_name}", map_name, veto, veto.team_a_id))
        view_b.add_item(MapButton(f"Ban {map_name}", map_name, veto, veto.team_b_id))

    await team_a.send("Veuillez sélectionner une map à bannir:", view=view_a)
    await team_b.send("Veuillez sélectionner une map à bannir:", view=view_b)

class MapVeto:
    def __init__(self, name, maps, team_a_id, team_a_name, team_b_id, team_b_name, rules, channel, bot):
        self.name = name
        self.maps = maps
        self.team_a_id = team_a_id
        self.team_a_name = team_a_name
        self.team_b_id = team_b_id
        self.team_b_name = team_b_name
        self.rules = rules
        self.channel = channel
        self.bot = bot
        self.current_step = 0
        self.paused = False

    async def process_map_selection(self, interaction, map_name, team_id):
        current_rule = self.rules[self.current_step]

        if current_rule == "Ban":
            self.maps.remove(map_name)
            await interaction.response.send_message(f"La carte {map_name} a été bannie par {interaction.user.name}.")
        # Ajoutez ici d'autres règles de traitement comme "Pick" et "Side".

        self.current_step += 1
        if self.current_step >= len(self.rules):
            await self.channel.send("Le veto est terminé.")
        else:
            await self.send_next_step_message()

    async def send_next_step_message(self):
        current_rule = self.rules[self.current_step]
        team = self.team_a_id if self.current_step % 2 == 0 else self.team_b_id

        view = View()
        for map_name in self.maps:
            view.add_item(MapButton(f"{current_rule} {map_name}", map_name, self, team))

        user = await self.bot.fetch_user(team)
        await user.send(f"Veuillez sélectionner une carte à {current_rule.lower()}:", view=view)

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def stop(self):
        del vetos[self.name]

class ListButton(Button):
    def __init__(self):
        super().__init__(label="Liste des Templates", style=discord.ButtonStyle.primary)

    async def callback(self, interaction: discord.Interaction):
        if not veto_config.vetos:
            await interaction.response.send_message("Aucun template de veto n'est enregistré.", ephemeral=True)
        else:
            message = "Templates de veto enregistrés :\n"
            for name, details in veto_config.vetos.items():
                message += f"- {name} : {', '.join(details['maps'])}\n"
            await interaction.response.send_message(message, ephemeral=True)

class CreateButton(Button):
    def __init__(self):
        super().__init__(label="Créer un Template", style=discord.ButtonStyle.success)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(VetoCreateModal())

class EditButton(Select):
    def __init__(self):
        options = [discord.SelectOption(label=name, description="Modifier ce template") for name in veto_config.vetos]
        super().__init__(placeholder="Choisissez un template à modifier", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        template_name = self.values[0]
        veto = veto_config.get_veto(template_name)
        await interaction.response.send_modal(VetoEditModal(template_name, veto))

class DeleteButton(Select):
    def __init__(self):
        options = [discord.SelectOption(label=name, description="Supprimer ce template") for name in veto_config.vetos]
        super().__init__(placeholder="Choisissez un template à supprimer", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        template_name = self.values[0]
        confirmation_view = View()
        confirmation_view.add_item(ConfirmDeleteButton(template_name))
        await interaction.response.send_message(f"Êtes-vous sûr de vouloir supprimer le template '{template_name}'?", view=confirmation_view, ephemeral=True)

class ConfirmDeleteButton(Button):
    def __init__(self, template_name):
        super().__init__(label="Confirmer la Suppression", style=discord.ButtonStyle.danger)
        self.template_name = template_name

    async def callback(self, interaction: discord.Interaction):
        if veto_config.delete_veto(self.template_name):
            await interaction.response.send_message(f"Template de veto '{self.template_name}' supprimé avec succès.", ephemeral=True)
        else:
            await interaction.response.send_message(f"Erreur lors de la suppression du template '{self.template_name}'.", ephemeral=True)
