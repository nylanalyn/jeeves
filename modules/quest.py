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
    version = "3.0.6" # Fixed UnboundLocalError in command handlers
    description = "An RPG-style questing game where users can fight monsters and level up."

    def __init__(self, bot, config):
        """Initializes the Quest module's state and configuration."""
        self._is_loaded = False
        self.on_config_reload(config)
        super().__init__(bot)
        
        self.set_state("players", self.get_state("players", {}))
        self.set_state("active_mob", self.get_state("active_mob", None)) # For group content
        self.save_state()

    def on_config_reload(self, config):
        """Handles reloading the module's configuration."""
        self.ALLOWED_CHANNELS = config.get("allowed_channels", [])
        self.COOLDOWN = config.get("cooldown_seconds", 300)
        self.XP_CURVE_FORMULA = config.get("xp_curve_formula", "level * 100")
        self.MONSTER_SPAWN_CHANCE = config.get("monster_spawn_chance", 0.8)
        self.MONSTERS = config.get("monsters", [])
        self.STORY_BEATS = config.get("story_beats", {})
        self.WORLD_LORE = config.get("world_lore", [])
        
        difficulty_settings = config.get("difficulty", {})
        self.DIFFICULTY_MODS = {
            "easy": difficulty_settings.get("easy", {"level_mod": -2, "xp_mult": 0.7}),
            "normal": difficulty_settings.get("normal", {"level_mod": 1, "xp_mult": 1.0}),
            "hard": difficulty_settings.get("hard", {"level_mod": 3, "xp_mult": 1.5}),
        }
        
        combat_settings = config.get("combat", {})
        self.BASE_WIN_CHANCE = combat_settings.get("base_win_chance", 0.5)
        self.WIN_CHANCE_MOD_PER_LEVEL = combat_settings.get("win_chance_level_modifier", 0.1)
        self.MIN_WIN_CHANCE = combat_settings.get("min_win_chance", 0.05)
        self.MAX_WIN_CHANCE = combat_settings.get("max_win_chance", 0.95)
        
        self.XP_LOSS_PERCENTAGE = config.get("xp_loss_percentage", 0.25)
        self.DAILY_BONUS_XP = config.get("first_win_bonus_xp", 50)
        self.XP_LEVEL_MULTIPLIER = config.get("xp_level_multiplier", 2)

        energy_settings = config.get("energy_system", {})
        self.ENERGY_ENABLED = energy_settings.get("enabled", True)
        self.MAX_ENERGY = energy_settings.get("max_energy", 10)
        self.ENERGY_REGEN_MINUTES = energy_settings.get("regen_minutes", 10)
        self.ENERGY_PENALTIES = energy_settings.get("penalties", [])

        # --- Group Content Config ---
        group_config = config.get("group_content", {})
        self.MOB_JOIN_WINDOW = group_config.get("join_window_seconds", 90)
        self.MOB_WIN_CHANCE_MODS = group_config.get("win_chance_modifiers", [])
        self.MOB_XP_SCALING = group_config.get("xp_scaling", [])
        self.BOSS_MONSTERS = config.get("boss_monsters", [])

        if self._is_loaded:
            self._schedule_energy_regen()

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
                schedule.every(remaining).seconds.do(self._close_mob_window).tag(self.name, "mob_close")

        self._is_loaded = True

    def on_unload(self):
        super().on_unload()
        schedule.clear(self.name)

    def _schedule_energy_regen(self):
        if not self.ENERGY_ENABLED: return
        schedule.clear("energy_regen")
        schedule.every(self.ENERGY_REGEN_MINUTES).minutes.do(self._regenerate_energy).tag(self.name, "energy_regen")

    def _regenerate_energy(self):
        if not self.ENERGY_ENABLED: return
        players, updated = self.get_state("players", {}), False
        for user_id, player_data in players.items():
            if isinstance(player_data, dict) and player_data.get("energy", self.MAX_ENERGY) < self.MAX_ENERGY:
                player_data["energy"] += 1
                updated = True
        if updated:
            self.set_state("players", players)
            self.save_state()

    def _register_commands(self):
        self.register_command(r"^\s*!quest\s+profile(?:\s+(\S+))?\s*$", self._cmd_profile, name="quest profile")
        self.register_command(r"^\s*!quest\s+story\s*$", self._cmd_story, name="quest story")
        self.register_command(r"^\s*!quest(?:\s+(easy|normal|hard))?\s*$", self._cmd_quest, name="quest", cooldown=self.COOLDOWN)
        self.register_command(r"^\s*!mob\s*$", self._cmd_mob_start, name="mob", cooldown=self.COOLDOWN)
        self.register_command(r"^\s*!join\s*$", self._cmd_mob_join, name="join")
        self.register_command(r"^\s*!quest\s+admin\s+addxp\s+(\S+)\s+(\d+)\s*$", self._cmd_admin_add_xp, name="quest admin addxp", admin_only=True)

    def _get_player(self, user_id: str, username: str) -> Dict[str, Any]:
        players = self.get_state("players", {})
        player = players.get(user_id)
        if not isinstance(player, dict): player = {"name": username, "level": 1, "xp": 0}
        player.setdefault("xp_to_next_level", self._calculate_xp_for_level(player.get("level", 1)))
        player.setdefault("last_fight", None)
        player.setdefault("last_win_date", None)
        player.setdefault("energy", self.MAX_ENERGY)
        player["name"] = username
        return player

    def _calculate_xp_for_level(self, level: int) -> int:
        try: return int(eval(self.XP_CURVE_FORMULA, {"__builtins__": {}}, {"level": level}))
        except: return level * 100

    def _grant_xp(self, user_id: str, username: str, amount: int, is_win: bool = False) -> List[str]:
        player, messages, total_xp_gain = self._get_player(user_id, username), [], int(amount)
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
        if leveled_up:
            messages.append(f"Congratulations, you have reached Level {player['level']}!")
        return messages

    def _deduct_xp(self, user_id: str, username: str, amount: int):
        player = self._get_player(user_id, username)
        player["xp"] = max(0, player["xp"] - int(amount))
        players = self.get_state("players")
        players[user_id] = player
        self.set_state("players", players)

    def _calculate_win_chance(self, player_level: float, monster_level: int, energy_modifier: float = 0.0, group_modifier: float = 0.0) -> float:
        level_diff = player_level - monster_level
        chance = self.BASE_WIN_CHANCE + (level_diff * self.WIN_CHANCE_MOD_PER_LEVEL) + energy_modifier + group_modifier
        return max(self.MIN_WIN_CHANCE, min(self.MAX_WIN_CHANCE, chance))

    def _cmd_profile(self, connection, event, msg, username, match):
        target_user_nick = match.group(1) or username
        user_id = self.bot.get_user_id(target_user_nick)
        player = self._get_player(user_id, target_user_nick)
        title = self.bot.title_for(player["name"])
        profile_parts = [f"Profile for {title}: Level {player['level']}", f"XP: {player['xp']}/{player['xp_to_next_level']}"]
        if self.ENERGY_ENABLED:
            profile_parts.append(f"Energy: {player['energy']}/{self.MAX_ENERGY}")
        self.safe_reply(connection, event, " | ".join(profile_parts))
        return True

    def _cmd_story(self, connection, event, msg, username, match):
        user_id = self.bot.get_user_id(username)
        player = self._get_player(user_id, username)
        lore = random.choice(self.WORLD_LORE) if self.WORLD_LORE else "The world is vast."
        history = ""
        if (last_fight := player.get("last_fight")):
            outcome = "victorious against" if last_fight['win'] else "defeated by"
            history = f" You last remember being {outcome} a Level {last_fight['monster_level']} {last_fight['monster_name']}."
        self.safe_reply(connection, event, f"{lore}{history}")
        return True

    def _cmd_quest(self, connection, event, msg, username, match):
        if self.ALLOWED_CHANNELS and event.target not in self.ALLOWED_CHANNELS: return False
        user_id = self.bot.get_user_id(username)
        player = self._get_player(user_id, username)
        if self.ENERGY_ENABLED and player["energy"] < 1:
            self.safe_reply(connection, event, f"You are too exhausted to go on a quest, {self.bot.title_for(username)}. You must rest.")
            return True
        
        difficulty = (match.group(1) or "normal").lower()
        diff_mod = self.DIFFICULTY_MODS.get(difficulty)
        player_level = player['level']

        if random.random() > self.MONSTER_SPAWN_CHANCE:
            self.safe_reply(connection, event, "The lands are quiet. You gain 10 XP for your diligence. (No energy was spent).")
            for m in self._grant_xp(user_id, username, 10): self.safe_reply(connection, event, m)
            self.save_state()
            return True
        if self.ENERGY_ENABLED: player["energy"] -= 1
        target_monster_level = player_level + diff_mod["level_mod"]
        possible_monsters = [m for m in self.MONSTERS if isinstance(m, dict) and m['min_level'] <= target_monster_level <= m['max_level']]
        if not possible_monsters:
            self.safe_reply(connection, event, "The lands are eerily quiet... no suitable monsters could be found.")
            return True
        monster = random.choice(possible_monsters)
        monster_level = max(1, random.randint(min(player_level - 1, player_level + diff_mod["level_mod"]), max(player_level - 1, player_level + diff_mod["level_mod"])))
        monster_name_with_level = f"Level {monster_level} {monster['name']}"
        action_text = random.choice(self.STORY_BEATS.get('actions', ["..."]))
        story = f"{random.choice(self.STORY_BEATS.get('openers',[]))} {action_text}".format(user=username, monster=monster_name_with_level)
        self.safe_reply(connection, event, story)
        time.sleep(1.5)
        energy_xp_mult, energy_win_chance_mod = 1.0, 0.0
        if self.ENERGY_ENABLED:
            for penalty in sorted(self.ENERGY_PENALTIES, key=lambda x: x['threshold'], reverse=True):
                if player["energy"] <= penalty["threshold"]:
                    energy_xp_mult, energy_win_chance_mod = penalty["xp_multiplier"], penalty["win_chance_modifier"]
                    self.safe_reply(connection, event, f"You feel fatigued... (Energy penalties are in effect!)")
                    break
        win_chance = self._calculate_win_chance(player_level, monster_level, energy_win_chance_mod)
        win = random.random() < win_chance
        player['last_fight'] = {"monster_name": monster['name'], "monster_level": monster_level, "win": win}
        base_xp = random.randint(monster.get('xp_win_min', 10), monster.get('xp_win_max', 20))
        total_xp = (base_xp + player_level * self.XP_LEVEL_MULTIPLIER) * diff_mod["xp_mult"] * energy_xp_mult
        if win:
            self.safe_reply(connection, event, f"Victory! (Win chance: {win_chance:.0%}) The {monster_name_with_level} is defeated! You gain {int(total_xp)} XP.")
            for m in self._grant_xp(user_id, username, total_xp, is_win=True): self.safe_reply(connection, event, m)
        else:
            xp_loss = total_xp * self.XP_LOSS_PERCENTAGE
            self.safe_reply(connection, event, f"Defeat! (Win chance: {win_chance:.0%}) You have been bested! You lose {int(xp_loss)} XP.")
            self._deduct_xp(user_id, username, xp_loss)
        players = self.get_state("players")
        players[user_id] = player
        self.set_state("players", players)
        self.save_state()
        return True

    def _cmd_mob_start(self, connection, event, msg, username, match):
        if self.ALLOWED_CHANNELS and event.target not in self.ALLOWED_CHANNELS: return False
        if self.get_state("active_mob"):
            self.safe_reply(connection, event, "A mob is already forming!")
            return True
        user_id = self.bot.get_user_id(username)
        player = self._get_player(user_id, username)
        if self.ENERGY_ENABLED and player["energy"] < 1:
            self.safe_reply(connection, event, f"You are too exhausted to start a mob, {self.bot.title_for(username)}.")
            return True
        boss = random.choice(self.BOSS_MONSTERS)
        self.set_state("active_mob", {"starter": username, "participants": {user_id: username}, "boss": boss, "room": event.target, "close_epoch": time.time() + self.MOB_JOIN_WINDOW})
        self.safe_reply(connection, event, f"{self.bot.title_for(username)} is gathering a party to hunt a {boss['name']}! Type !join in the next {self.MOB_JOIN_WINDOW} seconds to join the hunt!")
        schedule.every(self.MOB_JOIN_WINDOW).seconds.do(self._close_mob_window).tag(self.name, "mob_close")
        self.save_state()
        return True

    def _cmd_mob_join(self, connection, event, msg, username, match):
        active_mob = self.get_state("active_mob")
        if not active_mob or active_mob.get("room") != event.target: return False
        user_id = self.bot.get_user_id(username)
        player = self._get_player(user_id, username)
        if self.ENERGY_ENABLED and player["energy"] < 1:
            self.safe_reply(connection, event, f"You are too exhausted to join the mob, {self.bot.title_for(username)}.")
            return True
        if user_id in active_mob["participants"]:
            self.safe_reply(connection, event, f"You are already in the party, {self.bot.title_for(username)}.")
            return True
        active_mob["participants"][user_id] = username
        self.set_state("active_mob", active_mob)
        self.save_state()
        self.safe_reply(connection, event, f"{self.bot.title_for(username)} has joined the hunt! Party size: {len(active_mob['participants'])}.")
        return True

    def _close_mob_window(self):
        schedule.clear("mob_close")
        active_mob = self.get_state("active_mob")
        if not active_mob: return
        self.set_state("active_mob", None)
        party = active_mob["participants"]
        if not party: return
        if self.ENERGY_ENABLED:
            players = self.get_state("players")
            for user_id in party.keys():
                if user_id in players:
                    players[user_id]["energy"] = max(0, players[user_id].get("energy", 0) - 1)
            self.set_state("players", players)
        avg_level = sum(self._get_player(uid, name).get("level", 1) for uid, name in party.items()) / len(party)
        boss, boss_level = active_mob["boss"], max(boss['min_level'], min(boss['max_level'], int(avg_level)))
        party_size_mod = 0.0
        for mod in sorted(self.MOB_WIN_CHANCE_MODS, key=lambda x: x['players']):
            if len(party) >= mod['players']:
                party_size_mod = mod['modifier']
        win_chance = self._calculate_win_chance(avg_level, boss_level, group_modifier=party_size_mod)
        win = random.random() < win_chance
        boss_name_with_level = f"Level {boss_level} {boss['name']}"
        party_names = ", ".join(party.values())
        action_text = random.choice(self.STORY_BEATS.get('actions', ["..."]))
        story = f"The party of {party_names} confronts the {boss_name_with_level}! {action_text.format(user='', monster='')}"
        self.safe_say(f"{story} (Win Chance: {win_chance:.0%})", active_mob["room"])
        time.sleep(2)
        if win:
            base_xp = random.randint(boss.get('xp_win_min', 100), boss.get('xp_win_max', 200))
            xp_scaling_mult = 1.0
            for scale in sorted(self.MOB_XP_SCALING, key=lambda x: x['players']):
                if len(party) >= scale['players']:
                    xp_scaling_mult = scale['multiplier']
            total_xp_gain = int(base_xp * xp_scaling_mult)
            self.safe_say(f"Victory! The party has defeated the {boss_name_with_level} and gains {total_xp_gain} XP each!", active_mob["room"])
            for user_id, username in party.items():
                for m in self._grant_xp(user_id, username, total_xp_gain, is_win=True): self.safe_say(m, active_mob["room"])
        else:
            self.safe_say(f"Defeat! The {boss_name_with_level} has bested the party!", active_mob["room"])
        self.save_state()
        return schedule.CancelJob

    @admin_required
    def _cmd_admin_add_xp(self, connection, event, msg, username, match):
        target_user, amount_str = match.groups()
        user_id, amount = self.bot.get_user_id(target_user), int(amount_str)
        self.safe_reply(connection, event, f"Granted {amount} XP to {target_user}.")
        messages = self._grant_xp(user_id, target_user, amount)
        if messages:
             for message in messages:
                self.safe_reply(connection, event, f"{target_user}: {message}")
        self.save_state()
        return True

