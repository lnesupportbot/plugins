class MapButton(discord.ui.Button):
    def __init__(self, label, veto_name, action_type, channel):
        super().__init__(label=label, style=discord.ButtonStyle.primary, custom_id=f"{veto_name}_{label}_{action_type}")
        self.veto_name = veto_name
        self.action_type = action_type
        self.channel = channel

    async def callback(self, interaction: discord.Interaction):
        veto = vetos.get(self.veto_name)
        if not veto:
            await interaction.response.send_message("Veto non trouv�.", ephemeral=True)
            return
        
        if veto.paused or veto.stopped:
            await interaction.response.send_message("Le veto est actuellement en pause ou a �t� arr�t�.", ephemeral=True)
            return
        
        if interaction.user.id != veto.get_current_turn():
            await interaction.response.send_message("Ce n'est pas votre tour.", ephemeral=True)
            return

        if self.action_type == "ban":
            veto.ban_map(self.label)
            message = f"Map {self.label} bannie par {interaction.user.mention} (�quipe {veto.team_a_name if interaction.user.id == veto.team_a_id else veto.team_b_name})."
        elif self.action_type == "pick":
            veto.pick_map(self.label)
            message = f"**Map {self.label} choisie par {interaction.user.mention} (�quipe {veto.team_a_name if interaction.user.id == veto.team_a_id else veto.team_b_name}).**"
        elif self.action_type == "side":
            veto.pick_side(self.label)
            message = f"*Side {self.label} choisi par {interaction.user.mention} (�quipe {veto.team_a_name if interaction.user.id == veto.team_a_id else veto.team_b_name}).*"

        await interaction.response.send_message(message)
        await self.channel.send(message)

        opponent_user = interaction.client.get_user(veto.team_b_id if interaction.user.id == veto.team_a_id else veto.team_b_id)
        if opponent_user:
            await opponent_user.send(message)

        veto.next_turn()
        if veto.current_turn is not None:
            await send_ticket_message(interaction.client, veto, self.channel)
        else:
            await self.channel.send("Le veto est termin�!")
            embed = veto.create_summary_embed()
            await self.channel.send(embed=embed)

        # Disable the button and update the message
        view = interaction.message.view
        for item in view.children:
            if isinstance(item, discord.ui.Button) and item.custom_id == self.custom_id:
                item.disabled = True

        # Update the message with the modified view
        await interaction.message.edit(view=view)

async def send_ticket_message(bot, veto, channel):
    action = veto.current_action_type()
    if action is None:
        return

    components = []
    if action == "Side":
        components.append(MapButton(label="Attaque", veto_name=veto.name, action_type="side", channel=channel))
        components.append(MapButton(label="D�fense", veto_name=veto.name, action_type="side", channel=channel))
    else:
        for map_name in veto.maps:
            # Disable buttons for banned or picked maps
            button = MapButton(label=map_name, veto_name=veto.name, action_type=action.lower(), channel=channel)
            if map_name in veto.banned_maps or map_name in veto.picked_maps:
                button.disabled = True
            components.append(button)

    view = discord.ui.View(timeout=60)
    for component in components:
        view.add_item(component)

    team_name = veto.team_a_name if veto.get_current_turn() == veto.team_a_id else veto.team_b_name

    try:
        await bot.get_user(veto.get_current_turn()).send(f"{bot.get_user(veto.get_current_turn()).mention}, c'est votre tour de {action} une map.", view=view)
    except discord.Forbidden:
        print(f"Cannot DM user {veto.get_current_turn()}")

    async def timeout():
        await view.wait()
        if not view.is_finished():
            random_map = random.choice(veto.maps)
            if action == "ban":
                veto.ban_map(random_map)
                await bot.get_user(veto.get_current_turn()).send(f"Map {random_map} bannie automatiquement.")
            elif action == "pick":
                veto.pick_map(random_map)
                await bot.get_user(veto.get_current_turn()).send(f"Map {random_map} choisie automatiquement.")
            veto.next_turn()
            if veto.current_turn is not None:
                await send_ticket_message(bot, veto, channel)
            else:
                await channel.send("Le veto est termin�!")
                embed = veto.create_summary_embed()
                await channel.send(embed=embed)

    bot.loop.create_task(timeout())

class MapVeto:
    def __init__(self, name, maps, team_a_id, team_a_name, team_b_id, team_b_name, rules):
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
            if current_rule == "Continue":
                # Allow the same team to play again
                return
            elif current_rule == "Fin":
                # End the veto and send summary
                self.stopped = True
                return self.create_summary_embed()
            else:
                # Normal action, switch turn
                self.current_turn = self.team_a_id if self.current_turn == self.team_b_id else self.team_b_id
                self.current_action += 1

                # Handle consecutive "Continue" rules
                while self.current_action < len(self.rules) and self.rules[self.current_action] == "Continue":
                    self.current_action += 1
                    if self.current_action < len(self.rules) and self.rules[self.current_action] != "Continue":
                        # Switch turn after exiting consecutive "Continue"
                        self.current_turn = self.team_a_id if self.current_turn == self.team_b_id else self.team_b_id
        else:
            # No more actions, end the veto
            self.stopped = True
            return self.create_summary_embed()
