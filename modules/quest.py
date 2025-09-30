# modules/quest.py
# A persistent RPG-style questing game for the channel.
import random
import time
import re
import schedule
import threading
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List, Tuple

from .base import SimpleCommandModule, admin_required

UTC = timezone.utc

def setup(bot):
    """Initializes the Quest module."""
    return Quest(bot)

class Quest(SimpleCommandModule):
    """A module for a persistent RPG-style questing game."""
    name = "quest"
    version = "3.3.2" # Restored specific low-energy announcements
    description = "An RPG-style questing game where users can fight monsters and level up."

    def __init__(self, bot):
        """Initializes the Quest module's state and configuration."""
        super().__init__(bot)
        
        self.set_state("players", self.get_state("players", {}))
        self.set_state("active_mob", self.get_state("active_mob", None))
        self.set_state("player_classes", self.get_state("player_classes", {}))
        self.mob_lock = threading.Lock()
        self.save_state()
        self._is_loaded = False

    def on_load(self):
        super().on_load()
        self._is_loaded = True
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

    def on_unload(self):
        super().on_unload()
        schedule.clear(self.name)

    def _schedule_energy_regen(self):
        energy_enabled = self.get_config_value("energy_system.enabled", default=True)
        if not energy_enabled: return

        regen_minutes = self.get_config_value("energy_system.regen_minutes", default=10)
        schedule.clear(f"{self.name}-energy_regen")
        schedule.every(regen_minutes).minutes.do(self._regenerate_energy).tag(f"{self.name}-energy_regen")

    def _regenerate_energy(self):
        energy_enabled = self.get_config_value("energy_system.enabled", default=True)
        if not energy_enabled: return
        
        players, updated = self.get_state("players", {}), False
        max_energy = self.get_config_value("energy_system.max_energy", default=10)

        for user_id, player_data in players.items():
            if isinstance(player_data, dict):
                # Check for and apply injury effects on regeneration
                regen_amount = 1
                if 'active_injury' in player_data:
                    injury = player_data['active_injury']
                    regen_mod = injury.get('effects', {}).get('energy_regen_modifier', 0)
                    regen_amount += regen_mod

                if regen_amount > 0 and player_data.get("energy", max_energy) < max_energy:
                    player_data["energy"] = min(max_energy, player_data.get("energy", 0) + regen_amount)
                    updated = True
        if updated:
            self.set_state("players", players)
            self.save_state()

    def _register_commands(self):
        self.register_command(r"^\s*!quest(?:\s+(.*))?$", self._cmd_quest_master, name="quest")
        self.register_command(r"^\s*!mob\s*$", self._cmd_mob_start, name="mob")
        self.register_command(r"^\s*!join\s*$", self._cmd_mob_join, name="join")

    def _format_timedelta(self, future_datetime: datetime) -> str:
        """Formats the time remaining until a future datetime."""
        delta = future_datetime - datetime.now(UTC)
        seconds = int(delta.total_seconds())
        if seconds < 0: return "recovered"
        
        hours, remainder = divmod(seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        
        parts = []
        if hours > 0: parts.append(f"{hours}h")
        if minutes > 0: parts.append(f"{minutes}m")
        return " ".join(parts) if parts else "less than a minute"


    def _check_and_clear_injury(self, player_data: Dict[str, Any]) -> Tuple[Dict[str, Any], Optional[str]]:
        """Checks if a player's injury has expired and clears it if so."""
        if 'active_injury' in player_data:
            injury = player_data['active_injury']
            try:
                expires_at = datetime.fromisoformat(injury['expires_at'])
                if datetime.now(UTC) >= expires_at:
                    recovery_message = f"You have recovered from your {injury['name']}."
                    del player_data['active_injury']
                    return player_data, recovery_message
            except (ValueError, TypeError):
                del player_data['active_injury']
        return player_data, None
        
    def _apply_injury(self, user_id: str, username: str, channel: str) -> Optional[str]:
        """Applies a random injury to a player upon defeat."""
        injury_config = self.get_config_value("injury_system", channel, default={})
        if not injury_config.get("enabled"): return None

        injury_chance = injury_config.get("injury_chance_on_loss", 0.75)
        if random.random() > injury_chance: return None

        possible_injuries = injury_config.get("injuries", [])
        if not possible_injuries: return None

        injury = random.choice(possible_injuries)
        duration = timedelta(hours=injury.get("duration_hours", 1))
        expires_at = datetime.now(UTC) + duration
        
        players = self.get_state("players")
        player = self._get_player(user_id, username)
        player['active_injury'] = {
            "name": injury['name'],
            "description": injury['description'],
            "expires_at": expires_at.isoformat(),
            "effects": injury.get('effects', {})
        }
        players[user_id] = player
        self.set_state("players", players)
        self.save_state()
        
        return f"You have sustained an injury: {injury['name']}! {injury['description']}"


    def _calculate_xp_for_level(self, level: int) -> int:
        """Safely calculates XP required for a level using the configured formula."""
        xp_formula = self.get_config_value("xp_curve_formula", default="level * 100")

        # Safe formula parser: only allow level variable and basic arithmetic
        # Supports: level * N, level + N, or combinations with parentheses
        try:
            # Replace 'level' with the actual value in a safe way
            safe_expr = xp_formula.replace('level', str(level))
            # Only allow numbers, operators, spaces, and parentheses
            if not re.match(r'^[0-9\s\+\-\*/\.\(\)]+$', safe_expr):
                self.log_debug(f"Invalid XP formula: {xp_formula}, using default")
                return level * 100
            # Evaluate with no builtins for safety
            return int(eval(safe_expr, {'__builtins__': {}}, {}))
        except Exception as e:
            self.log_debug(f"Error calculating XP formula '{xp_formula}': {e}, using default")
            return level * 100

    def _get_player(self, user_id: str, username: str) -> Dict[str, Any]:
        players = self.get_state("players", {})
        player = players.get(user_id)

        if not isinstance(player, dict):
            player = {"name": username, "level": 1, "xp": 0}

        max_energy = self.get_config_value("energy_system.max_energy", default=10)

        player.setdefault("xp_to_next_level", self._calculate_xp_for_level(player.get("level", 1)))
        player.setdefault("last_fight", None)
        player.setdefault("last_win_date", None)
        player.setdefault("energy", max_energy)
        player["name"] = username

        return player

    def _grant_xp(self, user_id: str, username: str, amount: int, is_win: bool = False) -> List[str]:
        player, messages, total_xp_gain = self._get_player(user_id, username), [], int(amount)
        today = datetime.now(UTC).date().isoformat()
        
        first_win_bonus = self.get_config_value("first_win_bonus_xp", default=50)

        if is_win and player.get("last_win_date") != today:
            total_xp_gain += first_win_bonus
            player["last_win_date"] = today
            messages.append(f"You receive a 'First Victory of the Day' bonus of {first_win_bonus} XP!")
            
        if 'active_injury' in player:
            xp_mult = player['active_injury'].get('effects', {}).get('xp_multiplier', 1.0)
            if xp_mult != 1.0:
                total_xp_gain = int(total_xp_gain * xp_mult)
                messages.append(f"Your injury reduces your XP gain...")

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
        base_win = self.get_config_value("combat.base_win_chance", default=0.5)
        level_mod = self.get_config_value("combat.win_chance_level_modifier", default=0.1)
        min_win = self.get_config_value("combat.min_win_chance", default=0.05)
        max_win = self.get_config_value("combat.max_win_chance", default=0.95)
        
        level_diff = player_level - monster_level
        chance = base_win + (level_diff * level_mod) + energy_modifier + group_modifier
        return max(min_win, min(max_win, chance))

    def _get_action_text(self, user_id: str) -> str:
        player_classes = self.get_state("player_classes", {})
        player_class = player_classes.get(user_id)
        classes_config = self.get_config_value("classes", default={})

        if player_class and player_class in classes_config:
            return random.choice(classes_config[player_class].get("actions", ["..."]))
        
        story_beats = self.get_config_value("story_beats", default={})
        return random.choice(story_beats.get('actions', ["..."]))

    def _cmd_quest_master(self, connection, event, msg, username, match):
        if not self.is_enabled(event.target): return False
        
        args_str = (match.group(1) or "").strip()
        args = args_str.split()
        
        difficulty_mods = self.get_config_value("difficulty", default={})
        if not args_str or args[0].lower() in difficulty_mods:
            return self._handle_solo_quest(connection, event, username, args[0] if args else "normal")

        subcommand = args[0].lower()
        if subcommand == "profile":
            return self._handle_profile(connection, event, username, args[1:])
        elif subcommand == "story":
            return self._handle_story(connection, event, username)
        elif subcommand == "class":
            return self._handle_class(connection, event, username, args[1:])
        else:
            self.safe_reply(connection, event, f"Unknown quest command. Use '!quest', or '!quest <profile|story|class>'.")
            return True

    def _handle_profile(self, connection, event, username, args):
        target_user_nick = args[0] if args else username
        user_id = self.bot.get_user_id(target_user_nick)
        player = self._get_player(user_id, target_user_nick)
        
        player, recovery_msg = self._check_and_clear_injury(player)
        if recovery_msg:
            self.safe_reply(connection, event, recovery_msg)
            players_state = self.get_state("players")
            players_state[user_id] = player
            self.set_state("players", players_state)
            self.save_state()

        title = self.bot.title_for(player["name"])
        player_class = self.get_state("player_classes", {}).get(user_id, "None")
        max_energy = self.get_config_value("energy_system.max_energy", event.target, default=10)
        
        profile_parts = [f"Profile for {title}: Level {player['level']}", f"XP: {player['xp']}/{player['xp_to_next_level']}", f"Class: {player_class.capitalize()}"]
        
        if self.get_config_value("energy_system.enabled", event.target, default=True):
            profile_parts.append(f"Energy: {player['energy']}/{max_energy}")
            
        if 'active_injury' in player:
            injury = player['active_injury']
            try:
                expires_at = datetime.fromisoformat(injury['expires_at'])
                time_left = self._format_timedelta(expires_at)
                profile_parts.append(f"Status: Injured ({injury['name']}, recovers in {time_left})")
            except (ValueError, TypeError): pass

        self.safe_reply(connection, event, " | ".join(profile_parts))
        return True

    def _handle_story(self, connection, event, username):
        user_id = self.bot.get_user_id(username)
        player = self._get_player(user_id, username)
        world_lore = self.get_config_value("world_lore", default=[])
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
        classes_config = self.get_config_value("classes", default={})

        if not chosen_class:
            current_class = player_classes.get(user_id, "no class")
            available_classes = ", ".join(classes_config.keys())
            self.safe_reply(connection, event, f"{self.bot.title_for(username)}, your current class is: {current_class}. Available: {available_classes}.")
            return True
        if chosen_class not in classes_config:
            self.safe_reply(connection, event, f"My apologies, that is not a recognized class.")
            return True
        
        player_classes[user_id] = chosen_class
        self.set_state("player_classes", player_classes)
        self.save_state()
        self.safe_reply(connection, event, f"Very good, {self.bot.title_for(username)}. You are now a {chosen_class.capitalize()}.")
        return True

    def _handle_solo_quest(self, connection, event, username, difficulty):
        cooldown = self.get_config_value("cooldown_seconds", event.target, default=300)
        if not self.check_user_cooldown(username, "quest_solo", cooldown):
            self.safe_reply(connection, event, f"You are still recovering, {self.bot.title_for(username)}.")
            return True

        user_id = self.bot.get_user_id(username)
        player = self._get_player(user_id, username)

        player, recovery_msg = self._check_and_clear_injury(player)
        if recovery_msg:
            self.safe_reply(connection, event, recovery_msg)
        
        energy_enabled = self.get_config_value("energy_system.enabled", event.target, default=True)
        if energy_enabled and player["energy"] < 1:
            self.safe_reply(connection, event, f"You are too exhausted for a quest, {self.bot.title_for(username)}. You must rest.")
            return True
            
        difficulty_mods = self.get_config_value("difficulty", event.target, default={})
        diff_mod = difficulty_mods.get(difficulty, {"level_mod": 1, "xp_mult": 1.0})
        player_level = player['level']

        monster_spawn_chance = self.get_config_value("monster_spawn_chance", event.target, default=0.8)
        monsters = self.get_config_value("monsters", event.target, default=[])
        story_beats = self.get_config_value("story_beats", event.target, default={})

        if random.random() > monster_spawn_chance:
            self.safe_reply(connection, event, "The lands are quiet. You gain 10 XP for your diligence.")
            for m in self._grant_xp(user_id, username, 10): self.safe_reply(connection, event, m)
            return True
            
        if energy_enabled: player["energy"] -= 1
        
        target_monster_level = player_level + diff_mod["level_mod"]
        possible_monsters = [m for m in monsters if isinstance(m, dict) and m['min_level'] <= target_monster_level <= m['max_level']]
        if not possible_monsters:
            self.safe_reply(connection, event, "The lands are eerily quiet... no suitable monsters could be found.")
            if energy_enabled: player["energy"] += 1
            return True
            
        monster = random.choice(possible_monsters)
        monster_level = max(1, random.randint(min(player_level - 1, player_level + diff_mod["level_mod"]), max(player_level - 1, player_level + diff_mod["level_mod"])))
        monster_name_with_level = f"Level {monster_level} {monster['name']}"
        action_text = self._get_action_text(user_id)
        
        story = f"{random.choice(story_beats.get('openers',[]))} {action_text}".format(user=username, monster=monster_name_with_level)
        self.safe_reply(connection, event, story)
        time.sleep(1.5)
        
        energy_xp_mult, energy_win_chance_mod = 1.0, 0.0
        if energy_enabled:
            energy_penalties = self.get_config_value("energy_system.penalties", event.target, default=[])
            for penalty in sorted(energy_penalties, key=lambda x: x['threshold'], reverse=True):
                if player["energy"] <= penalty["threshold"]:
                    energy_xp_mult = penalty.get("xp_multiplier", 1.0)
                    energy_win_chance_mod = penalty.get("win_chance_modifier", 0.0)
                    
                    penalty_msgs = []
                    if energy_xp_mult < 1.0:
                        penalty_msgs.append("you will gain less experience")
                    if energy_win_chance_mod < 0.0:
                        penalty_msgs.append("you are less effective in battle")

                    if penalty_msgs:
                        self.safe_reply(connection, event, f"You feel fatigued... ({' and '.join(penalty_msgs)}).")
                    break
        
        win_chance = self._calculate_win_chance(player_level, monster_level, energy_win_chance_mod)
        win = random.random() < win_chance
        player['last_fight'] = {"monster_name": monster['name'], "monster_level": monster_level, "win": win}
        
        xp_level_mult = self.get_config_value("xp_level_multiplier", event.target, default=2)
        base_xp = random.randint(monster.get('xp_win_min', 10), monster.get('xp_win_max', 20))
        total_xp = (base_xp + player_level * xp_level_mult) * diff_mod["xp_mult"] * energy_xp_mult

        if win:
            self.safe_reply(connection, event, f"Victory! (Win chance: {win_chance:.0%}) The {monster_name_with_level} is defeated! You gain {int(total_xp)} XP.")
            for m in self._grant_xp(user_id, username, total_xp, is_win=True): self.safe_reply(connection, event, m)
        else:
            xp_loss_perc = self.get_config_value("xp_loss_percentage", event.target, default=0.25)
            xp_loss = total_xp * xp_loss_perc
            self.safe_reply(connection, event, f"Defeat! (Win chance: {win_chance:.0%}) You have been bested! You lose {int(xp_loss)} XP.")
            self._deduct_xp(user_id, username, xp_loss)
            
            injury_msg = self._apply_injury(user_id, username, event.target)
            if injury_msg:
                self.safe_reply(connection, event, injury_msg)

        players = self.get_state("players")
        players[user_id] = player
        self.set_state("players", players)
        self.save_state()
        return True

    def _cmd_mob_start(self, connection, event, msg, username, match):
        self.safe_reply(connection, event, "Mob quests are not yet implemented.")
        return True

    def _cmd_mob_join(self, connection, event, msg, username, match):
        self.safe_reply(connection, event, "Mob quests are not yet implemented.")
        return True

