# modules/quest.py
# A persistent RPG-style questing game for the channel.
import random
import time
import re
import schedule
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
    version = "2.6.0" # Energy and Rested XP Systems
    description = "An RPG-style questing game where users can fight monsters and level up."

    def __init__(self, bot, config):
        """Initializes the Quest module's state and configuration."""
        self._is_loaded = False
        self.on_config_reload(config)
        super().__init__(bot)
        
        self.set_state("players", self.get_state("players", {}))
        self.save_state()

    def on_config_reload(self, config):
        """Handles reloading the module's configuration."""
        quest_config = config.get(self.name, config)
        self.ALLOWED_CHANNELS = quest_config.get("allowed_channels", [])
        self.COOLDOWN = quest_config.get("cooldown_seconds", 300)
        self.XP_CURVE_FORMULA = quest_config.get("xp_curve_formula", "level * 100")
        self.MONSTER_SPAWN_CHANCE = quest_config.get("monster_spawn_chance", 0.8)
        self.MONSTERS = quest_config.get("monsters", [])
        self.STORY_BEATS = quest_config.get("story_beats", {})
        self.WORLD_LORE = quest_config.get("world_lore", [])
        
        difficulty_settings = quest_config.get("difficulty", {})
        self.DIFFICULTY_MODS = {
            "easy": difficulty_settings.get("easy", {"level_mod": -2, "xp_mult": 0.7}),
            "normal": difficulty_settings.get("normal", {"level_mod": 1, "xp_mult": 1.0}),
            "hard": difficulty_settings.get("hard", {"level_mod": 3, "xp_mult": 1.5}),
        }
        
        combat_settings = quest_config.get("combat", {})
        self.BASE_WIN_CHANCE = combat_settings.get("base_win_chance", 0.5)
        self.WIN_CHANCE_MOD_PER_LEVEL = combat_settings.get("win_chance_level_modifier", 0.1)
        self.MIN_WIN_CHANCE = combat_settings.get("min_win_chance", 0.05)
        self.MAX_WIN_CHANCE = combat_settings.get("max_win_chance", 0.95)
        
        self.XP_LOSS_PERCENTAGE = quest_config.get("xp_loss_percentage", 0.25)
        self.DAILY_BONUS_XP = quest_config.get("first_win_bonus_xp", 50)
        self.XP_LEVEL_MULTIPLIER = quest_config.get("xp_level_multiplier", 2)

        # --- New Energy System Config ---
        energy_settings = quest_config.get("energy_system", {})
        self.ENERGY_ENABLED = energy_settings.get("enabled", True)
        self.MAX_ENERGY = energy_settings.get("max_energy", 10)
        self.ENERGY_REGEN_MINUTES = energy_settings.get("regen_minutes", 10)
        self.ENERGY_PENALTIES = energy_settings.get("penalties", [
            {"threshold": 5, "xp_multiplier": 0.5, "win_chance_modifier": 0},
            {"threshold": 2, "xp_multiplier": 0.5, "win_chance_modifier": -0.15}
        ])

        # --- New Rested XP Config ---
        rested_settings = quest_config.get("rested_xp_system", {})
        self.RESTED_XP_ENABLED = rested_settings.get("enabled", True)
        self.RESTED_XP_CAP_MULTIPLIER = rested_settings.get("cap_level_multiplier", 2)
        self.RESTED_XP_PER_HOUR = rested_settings.get("xp_per_hour", 50)
        self.RESTED_XP_MESSAGES = rested_settings.get("messages", ["You feel well-rested."])

        # Reschedule energy regen if the interval changed
        if self._is_loaded:
            self._schedule_energy_regen()

    def on_load(self):
        super().on_load()
        self._schedule_energy_regen()
        self._is_loaded = True

    def _schedule_energy_regen(self):
        """Schedules the recurring energy regeneration task."""
        if not self.ENERGY_ENABLED:
            return
        schedule.clear(self.name)
        schedule.every(self.ENERGY_REGEN_MINUTES).minutes.do(self._regenerate_energy).tag(self.name, "energy_regen")

    def _regenerate_energy(self):
        """The scheduled task that passively regenerates energy for all players."""
        if not self.ENERGY_ENABLED:
            return
        
        players = self.get_state("players", {})
        updated = False
        for user_id, player_data in players.items():
            if isinstance(player_data, dict):
                current_energy = player_data.get("energy", self.MAX_ENERGY)
                if current_energy < self.MAX_ENERGY:
                    player_data["energy"] = current_energy + 1
                    updated = True
        
        if updated:
            self.set_state("players", players)
            self.save_state()

    def _register_commands(self):
        """Registers all the commands for the quest module."""
        # Commands remain the same as previous versions
        self.register_command(r"^\s*!quest\s+profile(?:\s+(\S+))?\s*$", self._cmd_profile, name="quest profile")
        self.register_command(r"^\s*!quest\s+story\s*$", self._cmd_story, name="quest story")
        self.register_command(r"^\s*!quest(?:\s+(easy|normal|hard))?\s*$", self._cmd_quest, name="quest", cooldown=self.COOLDOWN)
        self.register_command(r"^\s*!quest\s+admin\s+addxp\s+(\S+)\s+(\d+)\s*$", self._cmd_admin_add_xp, name="quest admin addxp", admin_only=True)

    def _get_player(self, user_id: str, username: str) -> Dict[str, Any]:
        """Retrieves a player's profile, creating and back-filling new fields as needed."""
        players = self.get_state("players", {})
        player = players.get(user_id)
        
        if not isinstance(player, dict): player = None
            
        if not player:
            player = {"name": username, "level": 1, "xp": 0}
        
        # Back-fill missing fields for existing players
        player.setdefault("xp_to_next_level", self._calculate_xp_for_level(player.get("level", 1)))
        player.setdefault("last_fight", None)
        player.setdefault("last_win_date", None)
        player.setdefault("energy", self.MAX_ENERGY)
        player.setdefault("rested_xp_pool", 0)
        player.setdefault("last_quest_timestamp", 0)
        player["name"] = username
        
        return player

    def _calculate_xp_for_level(self, level: int) -> int:
        try: return int(eval(self.XP_CURVE_FORMULA, {"__builtins__": {}}, {"level": level}))
        except: return level * 100

    def _grant_xp(self, user_id: str, username: str, amount: int, is_win: bool = False) -> List[str]:
        """Grants XP to a player, handles leveling up and rested XP bonus."""
        player = self._get_player(user_id, username)
        messages = []
        
        # --- Apply Rested XP Bonus ---
        rested_bonus = 0
        if is_win and self.RESTED_XP_ENABLED and player.get("rested_xp_pool", 0) > 0:
            rested_bonus = min(player["rested_xp_pool"], int(amount))
            player["rested_xp_pool"] -= rested_bonus
            messages.append(f"{random.choice(self.RESTED_XP_MESSAGES)} You gain a rested bonus of {rested_bonus} XP!")
        
        total_xp_gain = int(amount) + rested_bonus

        today = datetime.now(UTC).date().isoformat()
        if is_win and player.get("last_win_date") != today:
            total_xp_gain += self.DAILY_BONUS_XP
            player["last_win_date"] = today
            messages.append(f"You receive a 'First Victory of the Day' bonus of {self.DAILY_BONUS_XP} XP!")

        player["xp"] += total_xp_gain
        
        leveled_up = False
        while player["xp"] >= player["xp_to_next_level"]:
            player["xp"] -= player["xp_to_next_level"]
            player["level"] += 1
            player["xp_to_next_level"] = self._calculate_xp_for_level(player["level"])
            leveled_up = True
            
        players = self.get_state("players")
        players[user_id] = player
        self.set_state("players", players)
        self.save_state()

        if leveled_up:
            messages.append(f"Congratulations, you have reached Level {player['level']}!")
        return messages
        
    def _deduct_xp(self, user_id: str, username: str, amount: int):
        player = self._get_player(user_id, username)
        player["xp"] = max(0, player["xp"] - int(amount))
        players = self.get_state("players")
        players[user_id] = player
        self.set_state("players", players)
        self.save_state()

    def _calculate_win_chance(self, player_level: int, monster_level: int, energy_modifier: float = 0.0) -> float:
        """Calculates win chance, including energy penalties."""
        level_diff = player_level - monster_level
        chance = self.BASE_WIN_CHANCE + (level_diff * self.WIN_CHANCE_MOD_PER_LEVEL) + energy_modifier
        return max(self.MIN_WIN_CHANCE, min(self.MAX_WIN_CHANCE, chance))

    def _cmd_profile(self, connection, event, msg, username, match):
        target_user_nick = match.group(1) or username
        user_id = self.bot.get_user_id(target_user_nick)
        player = self._get_player(user_id, target_user_nick)
        
        title = self.bot.title_for(player["name"])
        profile_parts = [
            f"Profile for {title}: Level {player['level']}",
            f"XP: {player['xp']}/{player['xp_to_next_level']}"
        ]
        if self.ENERGY_ENABLED:
            profile_parts.append(f"Energy: {player['energy']}/{self.MAX_ENERGY}")
        if self.RESTED_XP_ENABLED:
             profile_parts.append(f"Rested XP Bonus: {player['rested_xp_pool']}")

        self.safe_reply(connection, event, " | ".join(profile_parts))
        return True

    def _cmd_story(self, connection, event, msg, username, match):
        user_id = self.bot.get_user_id(username)
        player = self._get_player(user_id, username)
        lore = random.choice(self.WORLD_LORE) if self.WORLD_LORE else "The world is vast."
        last_fight = player.get("last_fight")
        history = ""
        if last_fight:
            outcome = "victorious against" if last_fight['win'] else "defeated by"
            history = f" You last remember being {outcome} a Level {last_fight['monster_level']} {last_fight['monster_name']}."
        self.safe_reply(connection, event, f"{lore}{history}")
        return True

    def _cmd_quest(self, connection, event, msg, username, match):
        if self.ALLOWED_CHANNELS and event.target not in self.ALLOWED_CHANNELS:
            return False

        user_id = self.bot.get_user_id(username)
        player = self._get_player(user_id, username)

        # --- Energy Check ---
        if self.ENERGY_ENABLED:
            if player["energy"] < 1:
                self.safe_reply(connection, event, f"You are too exhausted to go on a quest, {self.bot.title_for(username)}. You must rest.")
                return True
            player["energy"] -= 1

        # --- Rested XP Accrual ---
        if self.RESTED_XP_ENABLED:
            now = time.time()
            time_since_last_quest = now - player.get("last_quest_timestamp", now)
            hours_rested = time_since_last_quest / 3600
            xp_to_add = int(hours_rested * self.RESTED_XP_PER_HOUR)
            
            cap = self._calculate_xp_for_level(player['level']) * self.RESTED_XP_CAP_MULTIPLIER
            
            if xp_to_add > 0:
                current_pool = player.get("rested_xp_pool", 0)
                player["rested_xp_pool"] = min(cap, current_pool + xp_to_add)

        player["last_quest_timestamp"] = time.time()

        difficulty = (match.group(1) or "normal").lower()
        diff_mod = self.DIFFICULTY_MODS.get(difficulty)
        player_level = player['level']

        if random.random() > self.MONSTER_SPAWN_CHANCE:
            xp_gain = 10
            self.safe_reply(connection, event, f"The lands are quiet. You gain {xp_gain} XP for your diligence.")
            messages = self._grant_xp(user_id, username, xp_gain)
            for m in messages: self.safe_reply(connection, event, m)
            return True

        target_monster_level = player_level + diff_mod["level_mod"]
        possible_monsters = [m for m in self.MONSTERS if isinstance(m, dict) and m['min_level'] <= target_monster_level <= m['max_level']]
        if not possible_monsters:
            self.safe_reply(connection, event, "The lands are eerily quiet... no suitable monsters could be found.")
            return True
        
        monster = random.choice(possible_monsters)
        bound1, bound2 = player_level - 1, player_level + diff_mod["level_mod"]
        monster_level = max(1, random.randint(min(bound1, bound2), max(bound1, bound2)))

        story = f"{random.choice(self.STORY_BEATS.get('openers',[]))} {random.choice(self.STORY_BEATS.get('actions',[]))}".format(user=username, monster=monster['name'])
        self.safe_reply(connection, event, story)
        time.sleep(1.5)
        
        # --- Energy Penalties ---
        energy_xp_mult = 1.0
        energy_win_chance_mod = 0.0
        if self.ENERGY_ENABLED:
            for penalty in sorted(self.ENERGY_PENALTIES, key=lambda x: x['threshold'], reverse=True):
                if player["energy"] <= penalty["threshold"]:
                    energy_xp_mult = penalty["xp_multiplier"]
                    energy_win_chance_mod = penalty["win_chance_modifier"]
                    self.safe_reply(connection, event, f"You feel fatigued... (Energy penalties are in effect!)")
                    break

        win_chance = self._calculate_win_chance(player_level, monster_level, energy_win_chance_mod)
        win = random.random() < win_chance
        
        last_fight_data = {"monster_name": monster['name'], "monster_level": monster_level, "win": win}
        player['last_fight'] = last_fight_data
        
        base_xp_gain = random.randint(monster.get('xp_win_min', 10), monster.get('xp_win_max', 20))
        level_bonus = player_level * self.XP_LEVEL_MULTIPLIER
        difficulty_bonus = diff_mod["xp_mult"]
        total_xp_gain = (base_xp_gain + level_bonus) * difficulty_bonus * energy_xp_mult

        if win:
            self.safe_reply(connection, event, f"Victory! (Win chance: {win_chance:.0%}) The Level {monster_level} {monster['name']} is defeated! You gain {int(total_xp_gain)} XP.")
            messages = self._grant_xp(user_id, username, total_xp_gain, is_win=True)
            for m in messages: self.safe_reply(connection, event, m)
        else:
            xp_loss = total_xp_gain * self.XP_LOSS_PERCENTAGE
            self.safe_reply(connection, event, f"Defeat! (Win chance: {win_chance:.0%}) You have been bested! You lose {int(xp_loss)} XP.")
            self._deduct_xp(user_id, username, xp_loss)
            
        players = self.get_state("players")
        players[user_id] = player
        self.set_state("players", players)
        self.save_state()
        return True
        
    @admin_required
    def _cmd_admin_add_xp(self, connection, event, msg, username, match):
        target_user, amount_str = match.groups()
        user_id = self.bot.get_user_id(target_user)
        amount = int(amount_str)
        
        self.safe_reply(connection, event, f"Granted {amount} XP to {target_user}.")
        messages = self._grant_xp(user_id, target_user, amount)
        if messages:
             for message in messages:
                self.safe_reply(connection, event, f"{target_user} leveled up! {message}")
        return True

