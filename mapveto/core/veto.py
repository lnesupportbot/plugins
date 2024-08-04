import json
import os
import asyncio
import random
import discord # type: ignore
from discord.ui import Modal, TextInput, Button, Select, View # type: ignore
from discord.ext import commands # type: ignore

from .templateveto import MapVetoConfig, TemplateManager, veto_config
from .tournament import TournamentManager, TournamentConfig, tournament_config
from .teams import TeamManager, TeamConfig, team_config

from cogs import modmail

# Charger les configurations
veto_config = MapVetoConfig()
vetos = veto_config.load_vetos()
tournament_config = TournamentConfig()
tournaments = tournament_config.load_tournaments()
team_config = TeamConfig()
teams = team_config.load_teams()

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
        self.channel = channel

    async def send_ticket_message(self, channel):
        action = self.current_action_type()
        if action is None:
            return

        current_user = self.bot.get_user(self.get_current_turn())
        if not current_user:
            return

        components = []
        if action == "Side":
            components.append(MapButton(label="Attaque", veto_name=self.name, action_type="side", channel=channel, veto=self))
            components.append(MapButton(label="Défense", veto_name=self.name, action_type="side", channel=channel, veto=self))
        else:
            for map_name in self.listmaps:
                button = MapButton(label=map_name, veto_name=self.name, action_type=action.lower(), channel=channel, veto=self)
                if map_name in self.banned_maps or map_name in self.picked_maps_only:
                    button.disabled = True
                components.append(button)

        view = discord.ui.View(timeout=None)
        for component in components:
            view.add_item(component)

        if action == "Side":
            if len(self.maps) == 1:
                last_picked_map = self.maps[0]
                message = f"{current_user.mention}, vous devez choisir votre Side sur **{last_picked_map}**."
            else:
                # Include the last picked map in the message
                last_picked_map = self.picked_maps[-1]["map"] if self.picked_maps else "Unknown"
                message = f"{current_user.mention}, vous devez choisir votre Side sur **{last_picked_map}**."
        else:
            message = f"{current_user.mention}, c'est votre tour de {action} une map."

        try:
            await current_user.send(message, view=view)
        except discord.Forbidden:
            print(f"Cannot DM user {current_user.id}")

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

class VetoManager:
    def __init__(self, bot, filename="message_id.json"):
        self.filename = os.path.join(os.path.dirname(__file__), '..', filename)
        self.bot = bot
        self.setup_message_id = None
        self.load_veto_setup_message_id()

    def save_veto_setup_message_id(self, message_id):
        data = {}
        # Load existing data
        if os.path.exists(self.filename):
            with open(self.filename, 'r') as f:
                data = json.load(f)
        
        # Update setup_message_id while preserving existing keys
        data['setup_veto_message_id'] = message_id
        
        with open(self.filename, 'w') as f:
            json.dump(data, f, indent=4)

    def load_veto_setup_message_id(self):
        if os.path.exists(self.filename):
            with open(self.filename, 'r') as f:
                data = json.load(f)
                self.setup_message_id = data.get('setup_veto_message_id')

    def refresh_veto_setup_message_id(self):
        """Refresh the message id from the file."""
        self.message_id = self.load_veto_setup_message_id()

    async def update_veto_setup_message(self, channel):
        self.refresh_veto_setup_message_id()
        if self.setup_message_id:
            try:
                message = await channel.fetch_message(self.setup_message_id)
                await message.edit(embed=self.create_veto_setup_embed(), view=self.create_veto_setup_view())
            except discord.NotFound:
                await self.send_veto_setup_message(channel)
        else:
            await self.send_veto_setup_message(channel)

    def create_veto_setup_embed(self):
        embed = discord.Embed(
            title="Lancer un MapVeto",
            description="Cliquez sur le bouton ci-dessous pour lancer un MapVeto.",
            color=discord.Color.blue()
        )
        return embed

    def create_veto_setup_view(self):
        view = discord.ui.View(timeout=None)
        view.add_item(MapVetoButton())
        return view

    async def send_veto_setup_message(self, channel):
        message = await channel.send(embed=self.create_veto_setup_embed(), view=self.create_veto_setup_view())
        self.setup_message_id = message.id
        self.save_veto_setup_message_id(message.id)

class MapVetoButton(Button):
    def __init__(self):
        super().__init__(label="Lancer un MapVeto", style=discord.ButtonStyle.primary)

    async def callback(self, interaction: discord.Interaction):
        vetos = veto_config.vetos
        if not vetos:
            await interaction.response.send_message("Le MapVeto ne peut pas être lancé car aucun template de veto n'a été créé.", ephemeral=True)
            return

        select = TemplateSelect(interaction.client)
        view = View()
        view.add_item(select)
        await interaction.response.send_message("Choisissez un template de veto:", view=view, ephemeral=True) 

class TemplateSelect(Select):
    def __init__(self, bot):
        self.bot = bot
        self.vetos = veto_config.load_vetos()
        options = [
            discord.SelectOption(
                label=template, 
                description=f"Règles: {self.vetos[template]['rules']}",
                value=template
            )
            for template in self.vetos.keys()
        ]
        super().__init__(placeholder="Choisir un template de veto...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        template_name = self.values[0]
        tournaments = tournament_config.tournaments

        if not tournaments:
            await interaction.response.send_message("Le MapVeto ne peut pas être lancé car aucun tournoi n'a trouvé.", ephemeral=True)
            return
        
        select = TournamentSelect(template_name, self.bot)
        view = View()
        view.add_item(select)
        await interaction.response.send_message(f"Template choisi: {template_name}", view=view, ephemeral=True)

class TournamentSelect(Select):
    def __init__(self, template_name, bot):
        self.template_name = template_name
        self.bot = bot
        self.tournaments = tournament_config.load_tournaments()

        options = [
            discord.SelectOption(label=name, value=name)
            for name in self.tournaments
        ]

        super().__init__(placeholder="Choisir un tournoi...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        tournament_name = self.values[0]
        teams = team_config.get_teams_by_tournament(tournament_name)

        if not teams:
            await interaction.response.send_message(
            f"Le Mapveto ne peut pas être lancé car il n'y a pas d'équipes dans le tournoi selectionné : {tournament_name} ",
            ephemeral=True,
            )
            return
        
        select = TeamSelect(tournament_name, self.template_name, self.bot)
        view = View()
        view.add_item(select)
        await interaction.response.send_message(f"Tournament choisi: {tournament_name}", view=view, ephemeral=True)

class TeamSelect(Select):
    def __init__(self, tournament_name, template_name, bot):
        self.template_name = template_name
        self.tournament_name = tournament_name
        self.bot = bot
        self.teams = team_config.refresh_teams()

        # Filtrer les équipes pour le tournoi spécifié
        teams = team_config.get_teams_by_tournament(tournament_name)

        # Préparer les options avec les descriptions des capitaines
        options = []
        for team in teams:
            captain_id = int(teams[team]["captain_discord_id"])
            captain_user = self.bot.get_user(captain_id)
            if captain_user:
                description = f"Capitaine : {captain_user.name}"
            else:
                description = "Capitaine non trouvé"
            options.append(discord.SelectOption(label=team, description=description, value=team))

        super().__init__(placeholder="Choisir deux équipes...", min_values=2, max_values=2, options=options)

    async def callback(self, interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)       
            team_a_name, team_b_name = self.values
            team_a_id = int(teams[team_a_name]["captain_discord_id"])
            team_b_id = int(teams[team_b_name]["captain_discord_id"])

            if not team_a_id or not team_b_id:
                await interaction.followup.send("Un ou les deux capitaines ne sont pas trouvés sur le serveur.", ephemeral=True)
                return

            # Récupérer les objets utilisateur à partir des IDs
            team_a_user = await self.bot.fetch_user(team_a_id)
            team_b_user = await self.bot.fetch_user(team_b_id)

            if not team_a_user or not team_b_user:
                await interaction.followup.send("Un ou les deux capitaines ne sont pas trouvés sur le serveur.", ephemeral=True)
                return

            # Vérifier si des threads existent déjà pour les utilisateurs
            errors = []
            modmail_cog = self.bot.get_cog("Modmail")
            if modmail_cog is None:
                await interaction.followup.send("Le cog Modmail n'est pas chargé.", ephemeral=True)
                return

            existing_thread_a = await self.bot.threads.find(recipient=team_a_user)
            existing_thread_b = await self.bot.threads.find(recipient=team_b_user)

            if existing_thread_a:
                errors.append(f"Un thread pour **{team_a_user.display_name}** existe déjà.")
            if existing_thread_b:
                errors.append(f"Un thread pour **{team_b_user.display_name}** existe déjà.")

            if errors:
                await interaction.followup.send("\n".join(errors), ephemeral=True)
                return

            # Crée le ticket avec les capitaines d'équipe
            category = None  # Vous pouvez spécifier une catégorie si besoin
            users = [team_a_user, team_b_user]

            # Créez un contexte factice pour appeler la commande `contact`
            fake_context = await self.bot.get_context(interaction.message)

            # Créer le thread
            await modmail_cog.contact(
                fake_context,  # passez le contexte de commande factice
                users,
                category=category,
                manual_trigger=False
            )

            # Pause explicite pour attendre la création complète du thread
            await asyncio.sleep(2)

            # Trouver le thread pour s'assurer qu'il est prêt
            thread = await self.bot.threads.find(recipient=team_a_user)

            if not thread or not thread.channel:
                await interaction.followup.send("Erreur lors de la création du thread.", ephemeral=True)
                return

            ticket_channel = thread.channel  # Obtenir le canal du thread créé

            # Envoyer l'embed avec la liste déroulante et le bouton dans le thread
            embed = discord.Embed(
                title="Sélection de l'équipe qui commence le MapVeto",
                description=(
                    "\n__Sélectionner dans la liste ci-dessous l'équipe commencera le MapVeto :__\n\n"
                    "*Si vous devez relancer le MapVeto et que la liste ci-dessous n'est plus fonctionnelle, vous pouvez lancer le MapVeto avec la commande :*\n"
                    f"- `?start_mapveto {self.template_name} {team_a_id} {team_a_name} {team_b_id} {team_b_name}`\n*(Si l'équipe **{team_a_name}** doit démarrer le veto)*\n"
                    f"- `?start_mapveto {self.template_name} {team_b_id} {team_b_name} {team_a_id} {team_a_name}`\n*(Si l'équipe **{team_b_name}** doit démarrer le veto)*\n"
                ),
                color=discord.Color.blue()
            )

            select = SelectTeamForMapVeto(team_a_name, team_b_name, self.template_name, self.bot)
            view = View(timeout = None)
            view.add_item(CoinFlipMessage(team_a_id, team_b_id, self.bot))
            view.add_item(CoinFlipButton(team_a_name, team_b_name, team_a_id, team_b_id, self.bot))
            view.add_item(VetoRdyMessage(team_a_id, team_b_id, self.bot))
            view.add_item(select)
            view.add_item(CloseMapVetoButton(team_a_id, team_b_id, thread ,self.bot))
            await ticket_channel.send(embed=embed, view=view)

            await interaction.followup.send(
                f"Le ticket a été créé avec succès pour le MapVeto du match : **{team_a_name}**(Capitaine : {team_a_user.display_name}) VS **{team_b_name}**(Capitaine : {team_b_user.display_name}).\n\n"
                f"Accédez au thread ici : <#{ticket_channel.id}>",
                ephemeral=True
            )

class SelectTeamForMapVeto(Select):
    def __init__(self, team_a_name, team_b_name, template_name, bot):
        self.template_name = template_name
        self.team_a_name = team_a_name
        self.team_b_name = team_b_name
        self.bot = bot

        self.teams = team_config.load_teams()

        options = [
            discord.SelectOption(label=team_a_name, description=f"{team_a_name} commence", value=team_a_name),
            discord.SelectOption(label=team_b_name, description=f"{team_b_name} commence", value=team_b_name),
        ]

        super().__init__(placeholder="Choisir l'équipe qui commence...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        teams = team_config.load_teams()
        starting_team = self.values[0]
        other_team = self.team_b_name if starting_team == self.team_a_name else self.team_a_name

        # Obtenir les IDs des capitaines des équipes
        starting_team_id = int(teams[starting_team]["captain_discord_id"])
        other_team_id = int(teams[other_team]["captain_discord_id"])

        maps = veto_config.vetos[self.template_name]["maps"]
        rules = veto_config.vetos[self.template_name]["rules"]
        ticket_channel = interaction.channel

        veto = MapVeto(self.template_name, maps, starting_team_id, starting_team, other_team_id, other_team, rules, ticket_channel, self.bot)
        vetos[self.template_name] = veto

        await interaction.response.send_message(f"Le Map Veto commence avec {starting_team} contre {other_team}.", ephemeral=True)
        await veto.send_ticket_message(ticket_channel)

class CoinFlipButton(Button):
    def __init__(self, team_a_name, team_b_name, team_a_id, team_b_id, bot):
        super().__init__(label="Lancer le coinflip", style=discord.ButtonStyle.green, custom_id="coinflip")
        self.team_a_name = team_a_name
        self.team_b_name = team_b_name
        self.team_a_id = team_a_id
        self.team_b_id = team_b_id
        self.bot = bot

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.team_a_id and interaction.user.id != self.team_b_id:
            await interaction.response.send_message("Ce n'est pas votre tour.", ephemeral=True)
            return

        result = random.choice([self.team_a_name, self.team_b_name])
        result_message = f"Le CoinFlip a donné l'équipe **{result}** comme gagnant !"
        await interaction.response.send_message(result_message)
        
        team_a_user = self.bot.get_user(self.team_a_id)
        team_b_user = self.bot.get_user(self.team_b_id)
        
        if team_a_user and team_b_user:
            await team_a_user.send(result_message)
            await team_b_user.send(result_message)
        else:
            await interaction.followup.send("Un ou les deux capitaines ne sont pas trouvés pour envoyer le résultat.", ephemeral=True)

class CoinFlipMessage(Button):
    def __init__(self, team_a_id, team_b_id, bot):
        super().__init__(label="Prêt pour le CoinFlip?", style=discord.ButtonStyle.grey, custom_id="rdy_coinflip")
        self.team_a_id = team_a_id
        self.team_b_id = team_b_id
        self.bot = bot

    async def callback(self, interaction: discord.Interaction):
        team_a_user = self.bot.get_user(self.team_a_id)
        team_b_user = self.bot.get_user(self.team_b_id)
        
        if team_a_user and team_b_user:
            await team_a_user.send(f"{team_a_user.mention}, êtes-vous prêt pour lancer le CoinFlip ?")
            await team_b_user.send(f"{team_b_user.mention}, êtes-vous prêt pour lancer le CoinFlip ?")
            await interaction.response.send_message("Les capitaines ont été notifiés pour se préparer au CoinFlip.", ephemeral=True)
        else:
            await interaction.response.send_message("Un ou les deux capitaines ne sont pas trouvés.", ephemeral=True)

class VetoRdyMessage(Button):
    def __init__(self, team_a_id, team_b_id, bot):
        super().__init__(label="Prêt pour le MapVeto?", style=discord.ButtonStyle.grey, custom_id="rdy_mapveto")
        self.team_a_id = team_a_id
        self.team_b_id = team_b_id
        self.bot = bot

    async def callback(self, interaction: discord.Interaction):
        team_a_user = self.bot.get_user(self.team_a_id)
        team_b_user = self.bot.get_user(self.team_b_id)
        
        if team_a_user and team_b_user:
            await team_a_user.send(f"{team_a_user.mention}, êtes-vous prêt pour lancer le MapVeto ?")
            await team_b_user.send(f"{team_b_user.mention}, êtes-vous prêt pour lancer le MapVeto ?")
            await interaction.response.send_message("Les capitaines ont été notifiés pour se préparer au MapVeto.", ephemeral=True)
        else:
            await interaction.response.send_message("Un ou les deux capitaines ne sont pas trouvés.", ephemeral=True)

class CloseMapVetoButton(Button):
    def __init__(self, team_a_id, team_b_id, thread, bot, ctx):
        super().__init__(label="Fermer le Map Veto", style=discord.ButtonStyle.danger, custom_id="close_mapveto")
        self.team_a_id = team_a_id
        self.team_b_id = team_b_id
        self.thread = thread
        self.bot = bot
        self.ctx = ctx
        
    async def callback(self, interaction: discord.Interaction):
        modmail_cog = modmail.Modmail(self.bot)
        team_a_user = self.bot.get_user(self.team_a_id)
        team_b_user = self.bot.get_user(self.team_b_id)
        
        if team_a_user and team_b_user:
            await team_a_user.send(f"{team_a_user.mention}, le MapVeto est fini. Bonne chance pour votre match! Ce ticket va être fermé. Si vous avez des questions, merci de nous contacter en passant par #teddy.")
            await team_b_user.send(f"{team_b_user.mention}, le MapVeto est fini. Bonne chance pour votre match! Ce ticket va être fermé. Si vous avez des questions, merci de nous contacter en passant par #teddy")
            await interaction.response.send_message("Les capitaines ont été notifiés de la fermeture du ticket de MapVeto.", ephemeral=True)
        else:
            await interaction.response.send_message("Un ou les deux capitaines ne sont pas trouvés.", ephemeral=True)

        # Fermer le ticket de manière silencieuse
        # Assurez-vous que le bot a la permission de supprimer le channel
        await modmail_cog.close(        
            self,
            self.ctx,
            option = "silent",
        )

class MapButton(discord.ui.Button):
    def __init__(self, label, veto_name, action_type, channel, veto):
        super().__init__(label=label, style=discord.ButtonStyle.primary, custom_id=f"{veto_name}_{label}_{action_type}")
        self.veto_name = veto_name
        self.action_type = action_type
        self.channel = channel
        self.veto = veto  # Add the veto object reference
        self.current_action = 0
        self.paused = False
        self.stopped = False

    async def callback(self, interaction: discord.Interaction):
        veto = self.veto  # Use the passed veto object
        if not veto:
            await interaction.response.send_message("Veto non trouvé.", ephemeral=True)
            return

        if self.paused or self.stopped:
            await interaction.response.send_message("Le veto est actuellement en pause ou a été arrêté.", ephemeral=True)
            return

        if interaction.user.id != veto.current_turn:  # Access current_turn from veto
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
            await veto.send_ticket_message(self.channel)  # Correct method call
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
