import discord
from discord.ext import commands, tasks
import random
import json
import os
import time
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

        veto.next_turn()
        if veto.current_turn is not None:
            await send_ticket_message(interaction.client, veto, self.channel)
        else:
            await self.channel.send("Le veto est terminé!")
            embed = veto.create_summary_embed()
            await self.channel.send(embed=embed)

            # Send the embed to the users
            team_a_user = interaction.client.get_user(veto.team_a_id)
            team_b_user = interaction.client.get_user(veto.team_b_id)
            if team_a_user:
                await team_a_user.send(embed=embed)
            if team_b_user:
                await team_b_user.send(embed=embed)

        # Disable the button and update the message
        view = interaction.message.view
        for item in view.children:
            if isinstance(item, discord.ui.Button) and item.custom_id == self.custom_id:
                item.disabled = True
        await interaction.message.edit(view=view)

class MapVeto:
    TURN_DURATION = 30  # durée d'un tour en secondes (à ajuster selon vos besoins)

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
        self.turn_start_time = time.time()  # Ajout de l'heure de début du tour

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
                return
            elif current_rule == "Fin":
                print("End of veto detected, stopping the veto.")
                self.end_veto()
                return
            else:
                if current_rule in {"Ban", "Pick", "Side"}:
                    self.current_turn = self.team_a_id if self.current_turn == self.team_b_id else self.team_b_id
                    self.current_action += 1

                while self.current_action < len(self.rules) and self.rules[self.current_action] == "Continue":
                    self.current_action += 1
                    if self.current_action < len(self.rules) and self.rules[self.current_action] != "Continue":
                        self.current_turn = self.team_a_id if self.current_turn == self.team_b_id else self.team_b_id

                if self.current_action >= len(self.rules):
                    print("No more rules, stopping the veto")
                    self.end_veto()
                    return

                self.turn_start_time = time.time()  # Réinitialisation de l'heure de début du tour

        else:
            print("No more actions, stopping the veto")
            self.end_veto()
            return

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
        self.stopped = True
        self.paused = False
        self.end_veto()

    def end_veto(self):
        self.stopped = True
        self.paused = False

        embed = discord.Embed(title=f"Résumé du veto '{self.name}'")
        embed.add_field(name="Maps bannies", value=", ".join(self.banned_maps) if self.banned_maps else "Aucune", inline=False)
        embed.add_field(name="Maps choisies", value=", ".join(self.picked_maps) if self.picked_maps else "Aucune", inline=False)

        team_a_user = self.bot.get_user(self.team_a_id)
        team_b_user = self.bot.get_user(self.team_b_id)
        if team_a_user:
            self.bot.loop.create_task(team_a_user.send(embed=embed))
        if team_b_user:
            self.bot.loop.create_task(team_b_user.send(embed=embed))

        self.picked_maps.clear()
        self.banned_maps.clear()
        self.current_action = 0
        self.current_turn = self.team_a_id
        self.paused = False
        self.stopped = False

    def get_remaining_time(self):
        elapsed_time = time.time() - self.turn_start_time
        remaining_time = self.TURN_DURATION - elapsed_time
        return max(0, int(remaining_time))

class MapVetoCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @checks.has_permissions(PermissionLevel.ADMIN)
    async def create_veto(self, ctx, name):
        if veto_config.create_veto(name):
            await ctx.send(f"Veto '{name}' créé.")
        else:
            await ctx.send(f"Le veto '{name}' existe déjà.")

    @commands.command()
    @checks.has_permissions(PermissionLevel.ADMIN)
    async def add_maps(self, ctx, name, *maps):
        if veto_config.add_maps(name, maps):
            await ctx.send(f"Maps ajoutées au veto '{name}': {', '.join(maps)}.")
        else:
            await ctx.send(f"Le veto '{name}' n'existe pas.")

    @commands.command()
    @checks.has_permissions(PermissionLevel.ADMIN)
    async def set_rules(self, ctx, name, *, rules):
        if veto_config.set_rules(name, rules):
            await ctx.send(f"Règles définies pour le veto '{name}': {rules}.")
        else:
            await ctx.send(f"Le veto '{name}' n'existe pas.")

    @commands.command()
    @checks.has_permissions(PermissionLevel.ADMIN)
    async def delete_veto(self, ctx, name):
        if veto_config.delete_veto(name):
            await ctx.send(f"Veto '{name}' supprimé.")
        else:
            await ctx.send(f"Le veto '{name}' n'existe pas.")

    @commands.command()
    async def start_veto(self, ctx, name, team_a: discord.Member, team_b: discord.Member):
        veto_data = veto_config.get_veto(name)
        if not veto_data:
            await ctx.send(f"Le veto '{name}' n'existe pas.")
            return

        maps = veto_data["maps"]
        rules = veto_data["rules"]

        if not maps or not rules:
            await ctx.send("Les maps ou les règles ne sont pas définies pour ce veto.")
            return

        veto = MapVeto(name, maps, team_a.id, team_a.display_name, team_b.id, team_b.display_name, rules)
        vetos[name] = veto

        await ctx.send(f"Veto '{name}' commencé entre {team_a.mention} et {team_b.mention}.")

        await send_ticket_message(self.bot, veto, ctx.channel)

    @commands.command()
    async def pause_veto(self, ctx, name):
        veto = vetos.get(name)
        if veto:
            veto.pause()
            await ctx.send(f"Veto '{name}' mis en pause.")
        else:
            await ctx.send(f"Le veto '{name}' n'existe pas ou n'est pas en cours.")

    @commands.command()
    async def resume_veto(self, ctx, name):
        veto = vetos.get(name)
        if veto:
            veto.resume()
            await ctx.send(f"Veto '{name}' repris.")
            await send_ticket_message(self.bot, veto, ctx.channel)
        else:
            await ctx.send(f"Le veto '{name}' n'existe pas ou n'est pas en cours.")

    @commands.command()
    async def stop_veto(self, ctx, name):
        veto = vetos.get(name)
        if veto:
            veto.stop()
            await ctx.send(f"Veto '{name}' arrêté.")
        else:
            await ctx.send(f"Le veto '{name}' n'existe pas ou n'est pas en cours.")

    @commands.command()
    async def end_veto(self, ctx, name):
        veto = vetos.get(name)
        if veto:
            veto.end_veto()
            await ctx.send(f"Veto '{name}' terminé.")
        else:
            await ctx.send(f"Le veto '{name}' n'existe pas ou n'est pas en cours.")

async def send_ticket_message(bot, veto, channel):
    action_type = veto.current_action_type()
    if not action_type:
        await channel.send("Le veto est terminé!")
        return

    current_turn = veto.get_current_turn()
    team_name = veto.team_a_name if current_turn == veto.team_a_id else veto.team_b_name

    embed = discord.Embed(title=f"Veto '{veto.name}'")
    embed.add_field(name="Tour actuel", value=f"{team_name} ({'Ban' if action_type == 'ban' else 'Pick' if action_type == 'pick' else 'Side'})", inline=False)
    embed.add_field(name="Maps disponibles", value=", ".join(veto.maps) if veto.maps else "Aucune", inline=False)
    embed.add_field(name="Maps bannies", value=", ".join(veto.banned_maps) if veto.banned_maps else "Aucune", inline=False)
    embed.add_field(name="Maps choisies", value=", ".join(veto.picked_maps) if veto.picked_maps else "Aucune", inline=False)
    embed.set_footer(text=f"Temps restant: {veto.get_remaining_time()} secondes")  # Affiche le temps restant

    view = discord.ui.View()
    for map_name in veto.maps:
        button = MapButton(map_name, veto.name, action_type, channel)
        view.add_item(button)

    await channel.send(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(MapVetoCog(bot))
