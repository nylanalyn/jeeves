# modules/quest.py
# A persistent RPG-style questing game for the channel.
import random
import time
import re
import schedule
import threading
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List

from .base import SimpleCommandModule, admin_required

UTC = timezone.utc

def setup(bot, config):
    """Initializes the Quest module."""
    return Quest(bot, config)

class Quest(SimpleCommandModule):
    """A module for a persistent RPG-style questing game."""
    name = "quest"
    version = "4.0.0" # Dynamic configuration refactor
    description = "An RPG-style questing game where users can fight monsters and level up."

    def __init__(self, bot, config):
        """Initializes the Quest module's state and configuration."""
        super().__init__(bot)
        
        self.static_keys = [
            "monsters", "story_beats", "world_lore", "classes", "boss_monsters",
            "difficulty", "combat", "energy_system", "group_content"
        ]
        
        self.set_state("players", self.get_state("players", {}))
        self.set_state("active_mob", self.get_state("active_mob", None))
        self.set_state("player_classes", self.get_state("player_classes", {}))
        self.mob_lock = threading.Lock()
        self.save_state()
        self._is_loaded = False # Defer scheduling until on_load

    def on_load(self):
        super().on_load()
        self._schedule_energy_regen()
        active_mob = self.get_state("active_mob")
        if active_mob:
            close_time = active_mob.get("close_epoch", 0)
            now = time.time()
            if now >= close_time:
                self._close_mob_window()
            else:
                remaining = close_time - now
                if remaining > 0:
                    schedule.every(remaining).seconds.do(self._close_mob_window).tag(self.name, "mob_close")
        self._is_loaded = True

    def on_unload(self):
        super().on_unload()
        schedule.clear(self.name)

    def _schedule_energy_regen(self):
        energy_enabled = self.get_config_value("energy_system", default={}).get("enabled", True)
        if not energy_enabled: return
        
        schedule.clear("energy_regen")
        regen_minutes = self.get_config_value("energy_system", default={}).get("regen_minutes", 10)
        if regen_minutes > 0:
            schedule.every(regen_minutes).minutes.do(self._regenerate_energy).tag(self.name, "energy_regen")

    def _regenerate_energy(self):
        energy_system_config = self.get_config_value("energy_system", default={})
        if not energy_system_config.get("enabled", True): return

        max_energy = energy_system_config.get("max_energy", 10)
        players, updated = self.get_state("players", {}), False
        for user_id, player_data in players.items():
            if isinstance(player_data, dict) and player_data.get("energy", max_energy) < max_energy:
                player_data["energy"] += 1
                updated = True
        if updated:
            self.set_state("players", players)
            self.save_state()

    def _register_commands(self):
        self.register_command(r"^\s*!quest(?:\s+(.*))?$", self._cmd_quest_master, name="quest")
        self.register_command(r"^\s*!mob\s*$", self._cmd_mob_start, name="mob", cooldown=300.0)
        self.register_command(r"^\s*!join\s*$", self._cmd_mob_join, name="join")
        
    def _get_player(self, user_id: str, username: str, channel: str) -> Dict[str, Any]:
        players = self.get_state("players", {})
        player = players.get(user_id)
        if not isinstance(player, dict): player = {"name": username, "level": 1, "xp": 0}
        
        energy_system = self.get_config_value("energy_system", channel, default={})
        max_energy = energy_system.get("max_energy", 10)
        
        player.setdefault("xp_to_next_level", self._calculate_xp_for_level(player.get("level", 1), channel))
        player.setdefault("last_fight", None)
        player.setdefault("last_win_date", None)
        player.setdefault("energy", max_energy)
        player["name"] = username
        return player

    def _calculate_xp_for_level(self, level: int, channel: str) -> int:
        formula = self.get_config_value("xp_curve_formula", channel, "level * 100")
        try: return int(eval(formula, {"__builtins__": {}}, {"level": level}))
        except: return level * 100

    def _grant_xp(self, user_id: str, username: str, amount: int, channel: str, is_win: bool = False) -> List[str]:
        player = self._get_player(user_id, username, channel)
        messages, total_xp_gain = [], int(amount)
        today = datetime.now(UTC).date().isoformat()
        
        daily_bonus_xp = self.get_config_value("first_win_bonus_xp", channel, 50)
        if is_win and player.get("last_win_date") != today:
            total_xp_gain += daily_bonus_xp
            player["last_win_date"] = today
            messages.append(f"You receive a 'First Victory' bonus of {daily_bonus_xp} XP!")
        
        player["xp"] += total_xp_gain
        leveled_up = False
        while player["xp"] >= player["xp_to_next_level"]:
            player["xp"] -= player["xp_to_next_level"]
            player["level"] += 1
            player["xp_to_next_level"] = self._calculate_xp_for_level(player["level"], channel)
            leveled_up = True
            
        players = self.get_state("players")
        players[user_id] = player
        self.set_state("players", players)
        
        if leveled_up:
            messages.append(f"Congratulations, you have reached Level {player['level']}!")
        return messages

    def _deduct_xp(self, user_id: str, username: str, amount: int, channel: str):
        player = self._get_player(user_id, username, channel)
        player["xp"] = max(0, player["xp"] - int(amount))
        players = self.get_state("players")
        players[user_id] = player
        self.set_state("players", players)

    # ... Master Command Handler and Sub-handlers (profile, story, class, admin) are unchanged ...
    def _cmd_quest_master(self, connection, event, msg, username, match):
        args_str = (match.group(1) or "").strip()
        args = args_str.split()
        
        difficulty_mods = self.get_config_value("difficulty", event.target, {})
        if not args_str or args[0].lower() in difficulty_mods:
            return self._handle_solo_quest(connection, event, username, args[0] if args else "normal")

        subcommand = args[0].lower()
        if subcommand == "profile":
            return self._handle_profile(connection, event, username, args[1:])
        elif subcommand == "story":
            return self._handle_story(connection, event, username)
        elif subcommand == "class":
            return self._handle_class(connection, event, username, args[1:])
        elif subcommand == "admin":
            return self._handle_admin(connection, event, username, args[1:])
        else:
            self.safe_reply(connection, event, f"Unknown quest command '{subcommand}'. Use '!quest' to start.")
            return True

    def _handle_profile(self, connection, event, username, args):
        target_user_nick = args[0] if args else username
        user_id = self.bot.get_user_id(target_user_nick)
        player = self._get_player(user_id, target_user_nick, event.target)
        title = self.bot.title_for(player["name"])
        player_class = self.get_state("player_classes", {}).get(user_id, "None")
        
        parts = [f"Profile for {title}: Level {player['level']}", f"XP: {player['xp']}/{player['xp_to_next_level']}", f"Class: {player_class.capitalize()}"]
        
        energy_system = self.get_config_value("energy_system", event.target, {})
        if energy_system.get("enabled", True):
            max_energy = energy_system.get("max_energy", 10)
            parts.append(f"Energy: {player['energy']}/{max_energy}")
            
        self.safe_reply(connection, event, " | ".join(parts))
        return True

    def _handle_story(self, connection, event, username):
        user_id = self.bot.get_user_id(username)
        player = self._get_player(user_id, username, event.target)
        world_lore = self.get_config_value("world_lore", event.target, [])
        lore = random.choice(world_lore) if world_lore else "The world is vast."
        history = ""
        if (last_fight := player.get("last_fight")):
            outcome = "victorious against" if last_fight['win'] else "defeated by"
            history = f" You last remember being {outcome} a Level {last_fight['monster_level']} {last_fight['monster_name']}."
        self.safe_reply(connection, event, f"{lore}{history}")
        return True
        
    def _handle_class(self, connection, event, username, args):
        user_id = self.bot.get_user_id(username)
        chosen_class = args[0].lower() if args else ""
        player_classes = self.get_state("player_classes", {})
        available_classes_dict = self.get_config_value("classes", event.target, {})
        
        if not chosen_class:
            current_class = player_classes.get(user_id, "no class")
            available_str = ", ".join(available_classes_dict.keys())
            self.safe_reply(connection, event, f"{self.bot.title_for(username)}, your class: {current_class}. Available: {available_str}.")
            return True
            
        if chosen_class not in available_classes_dict:
            self.safe_reply(connection, event, f"My apologies, that is not a recognized class.")
            return True
            
        player_classes[user_id] = chosen_class
        self.set_state("player_classes", player_classes)
        self.save_state()
        self.safe_reply(connection, event, f"Very good, {self.bot.title_for(username)}. You are now a {chosen_class.capitalize()}.")
        return True

    @admin_required
    def _handle_admin(self, connection, event, username, args):
        if not args: return self._usage(connection, event, "admin addxp <user> <amount>")
        if args[0].lower() == "addxp" and len(args) == 3:
            return self._cmd_admin_add_xp(connection, event, "", username, args[1:])
        return self._usage(connection, event, "unknown admin command.")

    def _usage(self, connection, event, text):
        self.safe_reply(connection, event, f"Usage: !quest {text}")
        return True

    def _handle_solo_quest(self, connection, event, username, difficulty):
        channel = event.target
        cooldown = self.get_config_value("cooldown_seconds", channel, 300)
        if not self.check_user_cooldown(username, "quest_solo", cooldown):
            self.safe_reply(connection, event, f"You are recovering, {self.bot.title_for(username)}. Please wait.")
            return True

        user_id = self.bot.get_user_id(username)
        player = self._get_player(user_id, username, channel)
        energy_system = self.get_config_value("energy_system", channel, {})
        
        if energy_system.get("enabled", True) and player["energy"] < 1:
            self.safe_reply(connection, event, f"You are too exhausted for a quest, {self.bot.title_for(username)}.")
            return True
        
        # --- Fetch all configs dynamically ---
        difficulty_mods = self.get_config_value("difficulty", channel, {})
        monsters = self.get_config_value("monsters", channel, [])
        story_beats = self.get_config_value("story_beats", channel, {})
        combat_config = self.get_config_value("combat", channel, {})
        
        diff_mod = difficulty_mods.get(difficulty, {"level_mod": 1, "xp_mult": 1.0})
        
        if random.random() > self.get_config_value("monster_spawn_chance", channel, 0.8):
            self.safe_reply(connection, event, "The lands are quiet. You gain 10 XP. (No energy spent).")
            for m in self._grant_xp(user_id, username, 10, channel): self.safe_reply(connection, event, m)
            self.save_state()
            return True
            
        if energy_system.get("enabled", True): player["energy"] -= 1
        
        target_level = player['level'] + diff_mod["level_mod"]
        possible_monsters = [m for m in monsters if m['min_level'] <= target_level <= m['max_level']]
        if not possible_monsters:
            self.safe_reply(connection, event, "The lands are eerily quiet... no suitable monsters could be found.")
            return True
            
        monster = random.choice(possible_monsters)
        monster_level = max(1, random.randint(min(player['level'] - 1, target_level), max(player['level'] - 1, target_level)))
        monster_name = f"Level {monster_level} {monster['name']}"
        action_text = self._get_action_text(user_id, channel)
        story = f"{random.choice(story_beats.get('openers',[]))} {action_text}".format(user=username, monster=monster_name)
        self.safe_reply(connection, event, story)
        time.sleep(1.5)
        
        # Calculate win chance with dynamic values
        energy_xp_mult, energy_win_mod = 1.0, 0.0
        if energy_system.get("enabled", True):
            for penalty in sorted(energy_system.get("penalties", []), key=lambda x: x['threshold'], reverse=True):
                if player["energy"] <= penalty["threshold"]:
                    energy_xp_mult, energy_win_mod = penalty["xp_multiplier"], penalty["win_chance_modifier"]
                    self.safe_reply(connection, event, f"You feel fatigued... (Energy penalties are in effect!)")
                    break
        
        base_win = combat_config.get("base_win_chance", 0.5)
        level_mod = combat_config.get("win_chance_level_modifier", 0.1)
        min_win, max_win = combat_config.get("min_win_chance", 0.05), combat_config.get("max_win_chance", 0.95)
        
        level_diff = player['level'] - monster_level
        win_chance = max(min_win, min(max_win, base_win + (level_diff * level_mod) + energy_win_mod))
        win = random.random() < win_chance
        
        player['last_fight'] = {"monster_name": monster['name'], "monster_level": monster_level, "win": win}
        
        base_xp = random.randint(monster.get('xp_win_min', 10), monster.get('xp_win_max', 20))
        xp_level_mult = self.get_config_value("xp_level_multiplier", channel, 2)
        total_xp = (base_xp + player['level'] * xp_level_mult) * diff_mod["xp_mult"] * energy_xp_mult
        
        if win:
            self.safe_reply(connection, event, f"Victory! ({win_chance:.0%}) The {monster_name} is defeated! You gain {int(total_xp)} XP.")
            for m in self._grant_xp(user_id, username, total_xp, channel, is_win=True): self.safe_reply(connection, event, m)
        else:
            xp_loss_pct = self.get_config_value("xp_loss_percentage", channel, 0.25)
            xp_loss = total_xp * xp_loss_pct
            self.safe_reply(connection, event, f"Defeat! ({win_chance:.0%}) You have been bested! You lose {int(xp_loss)} XP.")
            self._deduct_xp(user_id, username, xp_loss, channel)
            
        players = self.get_state("players")
        players[user_id] = player
        self.set_state("players", players)
        self.save_state()
        return True

    def _get_action_text(self, user_id: str, channel: str) -> str:
        player_class = self.get_state("player_classes", {}).get(user_id)
        classes_dict = self.get_config_value("classes", channel, {})
        if player_class and player_class in classes_dict:
            return random.choice(classes_dict[player_class].get("actions", ["..."]))
        return random.choice(self.get_config_value("story_beats", channel, {}).get('actions', ["..."]))

    # --- Mob/Group Logic ---
    def _cmd_mob_start(self, connection, event, msg, username, match):
        channel = event.target
        with self.mob_lock:
            if self.get_state("active_mob"):
                self.safe_reply(connection, event, "A mob is already forming!")
                return True
            user_id = self.bot.get_user_id(username)
            player = self._get_player(user_id, username, channel)
            
            energy_system = self.get_config_value("energy_system", channel, {})
            if energy_system.get("enabled", True) and player["energy"] < 1:
                self.safe_reply(connection, event, f"You are too exhausted to start a mob, {self.bot.title_for(username)}.")
                return True
                
            boss_monsters = self.get_config_value("boss_monsters", channel, [])
            if not boss_monsters:
                self.safe_reply(connection, event, "There are no great beasts to hunt in these lands.")
                return True
            boss = random.choice(boss_monsters)
            
            join_window = self.get_config_value("group_content", channel, {}).get("join_window_seconds", 90)
            
            self.set_state("active_mob", {"starter": username, "participants": {user_id: username}, "boss": boss, "room": channel, "close_epoch": time.time() + join_window})
            self.safe_reply(connection, event, f"{self.bot.title_for(username)} is gathering a party for a {boss['name']}! !join in the next {join_window}s!")
            schedule.every(join_window).seconds.do(self._close_mob_window).tag(self.name, "mob_close")
            self.save_state()
        return True

    def _cmd_mob_join(self, connection, event, msg, username, match):
        active_mob = self.get_state("active_mob")
        if not active_mob or active_mob.get("room") != event.target: return False
        
        user_id = self.bot.get_user_id(username)
        player = self._get_player(user_id, username, event.target)
        
        energy_system = self.get_config_value("energy_system", event.target, {})
        if energy_system.get("enabled", True) and player["energy"] < 1:
            self.safe_reply(connection, event, f"You are too exhausted to join, {self.bot.title_for(username)}.")
            return True
            
        if user_id in active_mob["participants"]:
            self.safe_reply(connection, event, f"You are already in the party, {self.bot.title_for(username)}.")
            return True
            
        active_mob["participants"][user_id] = username
        self.set_state("active_mob", active_mob)
        self.save_state()
        self.safe_reply(connection, event, f"{self.bot.title_for(username)} has joined! Party size: {len(active_mob['participants'])}.")
        return True

    def _close_mob_window(self):
        schedule.clear("mob_close")
        active_mob = self.get_state("active_mob")
        if not active_mob: return
        self.set_state("active_mob", None)
        
        party, channel = active_mob["participants"], active_mob["room"]
        if not party: return
        
        energy_system = self.get_config_value("energy_system", channel, {})
        if energy_system.get("enabled", True):
            players = self.get_state("players")
            for uid in party:
                if uid in players: players[uid]["energy"] = max(0, players[uid].get("energy", 0) - 1)
            self.set_state("players", players)
            
        avg_level = sum(self._get_player(uid, name, channel).get("level", 1) for uid, name in party.items()) / len(party)
        
        boss = active_mob["boss"]
        boss_level = max(boss['min_level'], min(boss['max_level'], int(avg_level)))
        
        group_config = self.get_config_value("group_content", channel, {})
        win_mods = group_config.get("win_chance_modifiers", [])
        
        party_size_mod = 0.0
        for mod in sorted(win_mods, key=lambda x: x['players']):
            if len(party) >= mod['players']: party_size_mod = mod['modifier']
        
        # We need combat config for this channel to calculate win chance
        combat_config = self.get_config_value("combat", channel, {})
        base_win = combat_config.get("base_win_chance", 0.5)
        level_mod = combat_config.get("win_chance_level_modifier", 0.1)
        min_win, max_win = combat_config.get("min_win_chance", 0.05), combat_config.get("max_win_chance", 0.95)
        
        win_chance = max(min_win, min(max_win, base_win + ((avg_level - boss_level) * level_mod) + party_size_mod))
        win = random.random() < win_chance
        
        boss_name = f"Level {boss_level} {boss['name']}"
        party_names = ", ".join(party.values())
        starter_id = self.bot.get_user_id(active_mob["starter"])
        action_text = self._get_action_text(starter_id, channel)
        
        self.safe_say(f"The party of {party_names} confronts {boss_name}! {action_text.format(user='', monster='')} (Win Chance: {win_chance:.0%})", channel)
        time.sleep(2)
        
        if win:
            base_xp = random.randint(boss.get('xp_win_min', 100), boss.get('xp_win_max', 200))
            xp_scaling = group_config.get("xp_scaling", [])
            xp_mult = 1.0
            for scale in sorted(xp_scaling, key=lambda x: x['players']):
                if len(party) >= scale['players']: xp_mult = scale['multiplier']
            
            total_xp = int(base_xp * xp_mult)
            self.safe_say(f"Victory! The party defeated {boss_name} and gains {total_xp} XP each!", channel)
            for uid, name in party.items():
                for m in self._grant_xp(uid, name, total_xp, channel, is_win=True): self.safe_say(m, channel)
        else:
            self.safe_say(f"Defeat! The {boss_name} has bested the party!", channel)
            
        self.save_state()
        return schedule.CancelJob

    @admin_required
    def _cmd_admin_add_xp(self, connection, event, msg, username, args):
        target_user, amount_str = args
        user_id, amount = self.bot.get_user_id(target_user), int(amount_str)
        messages = self._grant_xp(user_id, target_user, amount, event.target)
        self.safe_reply(connection, event, f"Granted {amount} XP to {target_user}.")
        for message in messages:
            self.safe_reply(connection, event, f"{target_user}: {message}")
        self.save_state()
        return True
