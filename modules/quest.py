# modules/quest.py
# A persistent RPG-style questing game for the channel.
import random
import time
import re
import schedule
import threading
import operator
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
                    schedule.every(remaining).seconds.do(self._close_mob_window).tag(f"{self.name}-mob_close")

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

                # Migrate old format
                if 'active_injury' in player_data:
                    player_data['active_injuries'] = [player_data['active_injury']]
                    del player_data['active_injury']

                # Sum all injury effects
                if 'active_injuries' in player_data:
                    for injury in player_data['active_injuries']:
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
        self.register_command(r"^\s*!mob\s+ping\s+(on|off)\s*$", self._cmd_mob_ping, name="mob_ping")
        self.register_command(r"^\s*!mob\s*$", self._cmd_mob_start, name="mob")
        self.register_command(r"^\s*!join\s*$", self._cmd_mob_join, name="join")
        self.register_command(r"^\s*!medkit(?:\s+(.+))?\s*$", self._cmd_medkit, name="medkit",
                              description="Use a medkit to heal yourself or another player")
        self.register_command(r"^\s*!inv(?:entory)?\s*$", self._cmd_inventory, name="inventory",
                              description="View your medkits and active injuries")

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
        """Checks if a player's injuries have expired and clears them if so."""
        # Migrate old single injury format to list
        if 'active_injury' in player_data:
            old_injury = player_data['active_injury']
            player_data['active_injuries'] = [old_injury]
            del player_data['active_injury']

        if 'active_injuries' in player_data and player_data['active_injuries']:
            now = datetime.now(UTC)
            expired_injuries = []
            active_injuries = []

            for injury in player_data['active_injuries']:
                try:
                    expires_at = datetime.fromisoformat(injury['expires_at'])
                    if now >= expires_at:
                        expired_injuries.append(injury['name'])
                    else:
                        active_injuries.append(injury)
                except (ValueError, TypeError):
                    # Invalid injury, skip it
                    pass

            player_data['active_injuries'] = active_injuries

            if expired_injuries:
                if len(expired_injuries) == 1:
                    return player_data, f"You have recovered from your {expired_injuries[0]}."
                else:
                    return player_data, f"You have recovered from: {', '.join(expired_injuries)}."

        return player_data, None
        
    def _apply_injury(self, user_id: str, username: str, channel: str, is_medic_quest: bool = False) -> Optional[str]:
        """Applies a random injury to a player upon defeat. Max 2 of each injury type."""
        injury_config = self.get_config_value("injury_system", channel, default={})
        if not injury_config.get("enabled"): return None

        # Don't apply injuries during medic quests
        if is_medic_quest:
            return None

        injury_chance = injury_config.get("injury_chance_on_loss", 0.75)
        if random.random() > injury_chance: return None

        possible_injuries = injury_config.get("injuries", [])
        if not possible_injuries: return None

        injury = random.choice(possible_injuries)

        players = self.get_state("players")
        player = self._get_player(user_id, username)

        # Migrate old format if needed
        if 'active_injury' in player:
            player['active_injuries'] = [player['active_injury']]
            del player['active_injury']

        # Initialize injuries list if not present
        if 'active_injuries' not in player:
            player['active_injuries'] = []

        # Check if player already has 2 of this injury type
        injury_count = sum(1 for inj in player['active_injuries'] if inj['name'] == injury['name'])
        if injury_count >= 2:
            return f"You narrowly avoid another {injury['name']}!"

        # Apply the injury
        duration = timedelta(hours=injury.get("duration_hours", 1))
        expires_at = datetime.now(UTC) + duration

        new_injury = {
            "name": injury['name'],
            "description": injury['description'],
            "expires_at": expires_at.isoformat(),
            "effects": injury.get('effects', {})
        }

        player['active_injuries'].append(new_injury)
        players[user_id] = player
        self.set_state("players", players)
        self.save_state()

        if injury_count == 1:
            return f"You have sustained another {injury['name']}! {injury['description']}"
        else:
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
            # Use safe calculation instead of eval
            result = self._safe_calculate(safe_expr)
            return int(result)
        except Exception as e:
            self.log_debug(f"Error calculating XP formula '{xp_formula}': {e}, using default")
            return level * 100

    def _safe_calculate(self, expr: str) -> float:
        """Safely evaluates a simple mathematical expression without eval()."""
        # Remove whitespace
        expr = expr.replace(" ", "")

        # Simple recursive descent parser for basic arithmetic
        def parse_expr(s, pos):
            left, pos = parse_term(s, pos)
            while pos < len(s) and s[pos] in ('+', '-'):
                op = s[pos]
                pos += 1
                right, pos = parse_term(s, pos)
                left = operator.add(left, right) if op == '+' else operator.sub(left, right)
            return left, pos

        def parse_term(s, pos):
            left, pos = parse_factor(s, pos)
            while pos < len(s) and s[pos] in ('*', '/'):
                op = s[pos]
                pos += 1
                right, pos = parse_factor(s, pos)
                left = operator.mul(left, right) if op == '*' else operator.truediv(left, right)
            return left, pos

        def parse_factor(s, pos):
            if pos < len(s) and s[pos] == '(':
                pos += 1
                result, pos = parse_expr(s, pos)
                if pos < len(s) and s[pos] == ')':
                    pos += 1
                return result, pos
            else:
                # Parse number
                start = pos
                while pos < len(s) and (s[pos].isdigit() or s[pos] == '.'):
                    pos += 1
                if start == pos:
                    raise ValueError("Expected number")
                return float(s[start:pos]), pos

        try:
            result, pos = parse_expr(expr, 0)
            if pos != len(expr):
                raise ValueError("Unexpected characters in expression")
            return result
        except Exception:
            raise ValueError("Invalid expression")

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
        player.setdefault("win_streak", 0)
        player.setdefault("medkits", 0)  # New: medkit inventory
        player["name"] = username

        return player

    def _grant_xp(self, user_id: str, username: str, amount: int, is_win: bool = False, is_crit: bool = False) -> List[str]:
        player, messages, total_xp_gain = self._get_player(user_id, username), [], int(amount)
        today = datetime.now(UTC).date().isoformat()

        # Critical hit bonus (2x XP)
        if is_crit:
            total_xp_gain *= 2
            messages.append("CRITICAL HIT! XP doubled!")

        # Win streak bonus (10% per streak, max 5 streaks = 50%)
        if is_win:
            current_streak = player.get("win_streak", 0)
            if current_streak > 0:
                max_streak_bonus = self.get_config_value("max_streak_bonus", default=5)
                streak_bonus_mult = 1 + (min(current_streak, max_streak_bonus) * 0.10)
                old_xp = total_xp_gain
                total_xp_gain = int(total_xp_gain * streak_bonus_mult)
                messages.append(f"{current_streak}-win streak bonus! (+{total_xp_gain - old_xp} XP)")

            # Increment streak
            player["win_streak"] = current_streak + 1

        first_win_bonus = self.get_config_value("first_win_bonus_xp", default=50)

        if is_win and player.get("last_win_date") != today:
            total_xp_gain += first_win_bonus
            player["last_win_date"] = today
            messages.append(f"You receive a 'First Victory of the Day' bonus of {first_win_bonus} XP!")

        # Migrate old format
        if 'active_injury' in player:
            player['active_injuries'] = [player['active_injury']]
            del player['active_injury']

        # Apply all injury XP multipliers
        if 'active_injuries' in player:
            total_xp_mult = 1.0
            for injury in player['active_injuries']:
                xp_mult = injury.get('effects', {}).get('xp_multiplier', 1.0)
                total_xp_mult *= xp_mult

            if total_xp_mult != 1.0:
                total_xp_gain = int(total_xp_gain * total_xp_mult)
                if total_xp_mult < 1.0:
                    messages.append(f"Your injuries reduce your XP gain...")

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
        # Reset win streak on loss
        player["win_streak"] = 0
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
        if subcommand == "medic":
            return self._handle_medic_quest(connection, event, username)
        elif subcommand == "profile":
            return self._handle_profile(connection, event, username, args[1:])
        elif subcommand == "story":
            return self._handle_story(connection, event, username)
        elif subcommand == "class":
            return self._handle_class(connection, event, username, args[1:])
        elif subcommand in ("top", "leaderboard"):
            return self._handle_leaderboard(connection, event)
        else:
            self.safe_reply(connection, event, f"Unknown quest command. Use '!quest', or '!quest <medic|profile|story|class|top>'.")
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

        # Show medkit count
        medkit_count = player.get("medkits", 0)
        if medkit_count > 0:
            profile_parts.append(f"Medkits: {medkit_count}")

        # Migrate old format
        if 'active_injury' in player:
            player['active_injuries'] = [player['active_injury']]
            del player['active_injury']

        if 'active_injuries' in player and player['active_injuries']:
            injury_strs = []
            for injury in player['active_injuries']:
                try:
                    expires_at = datetime.fromisoformat(injury['expires_at'])
                    time_left = self._format_timedelta(expires_at)
                    injury_strs.append(f"{injury['name']} ({time_left})")
                except (ValueError, TypeError):
                    injury_strs.append(injury['name'])

            if injury_strs:
                profile_parts.append(f"Status: Injured ({', '.join(injury_strs)})")

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

    def _handle_leaderboard(self, connection, event):
        """Display top 10 players by level and XP."""
        players = self.get_state("players", {})

        if not players:
            self.safe_reply(connection, event, "No players have embarked on quests yet.")
            return True

        # Sort by level (desc), then XP (desc)
        sorted_players = sorted(
            [(uid, p) for uid, p in players.items() if isinstance(p, dict)],
            key=lambda x: (x[1].get("level", 1), x[1].get("xp", 0)),
            reverse=True
        )[:10]

        self.safe_reply(connection, event, "Quest Leaderboard - Top 10 Adventurers:")
        for idx, (uid, player) in enumerate(sorted_players, 1):
            name = player.get("name", "Unknown")
            level = player.get("level", 1)
            xp = player.get("xp", 0)
            streak = player.get("win_streak", 0)
            streak_indicator = f" [Streak: {streak}]" if streak > 0 else ""
            self.safe_reply(connection, event, f"{idx}. {name} - Level {level} ({xp} XP){streak_indicator}")

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

        # Check for rare spawn
        rare_spawn_chance = self.get_config_value("rare_spawn_chance", event.target, default=0.10)
        is_rare = random.random() < rare_spawn_chance
        rare_xp_mult = self.get_config_value("rare_spawn_xp_multiplier", event.target, default=2.0)

        monster_prefix = "[RARE] " if is_rare else ""
        monster_name_with_level = f"{monster_prefix}Level {monster_level} {monster['name']}"
        action_text = self._get_action_text(user_id)

        story = f"{random.choice(story_beats.get('openers',[]))} {action_text}".format(user=username, monster=monster_name_with_level)
        self.safe_reply(connection, event, story)

        if is_rare:
            self.safe_say(f"A rare {monster['name']} has appeared! {username} engages in combat!", event.target)
        time.sleep(1.5)
        
        energy_xp_mult, energy_win_chance_mod = 1.0, 0.0
        applied_penalty_msgs = []
        if energy_enabled:
            energy_penalties = self.get_config_value("energy_system.penalties", event.target, default=[])
            # Check all penalties and apply the most severe (lowest threshold) that matches
            for penalty in sorted(energy_penalties, key=lambda x: x['threshold'], reverse=True):
                if player["energy"] <= penalty["threshold"]:
                    energy_xp_mult = penalty.get("xp_multiplier", 1.0)
                    energy_win_chance_mod = penalty.get("win_chance_modifier", 0.0)
                    # Don't break - let lower thresholds override

            # Generate message after finding final penalty values
            if energy_xp_mult < 1.0:
                applied_penalty_msgs.append("you will gain less experience")
            if energy_win_chance_mod < 0.0:
                applied_penalty_msgs.append("you are less effective in battle")

            if applied_penalty_msgs:
                self.safe_reply(connection, event, f"You feel fatigued... ({' and '.join(applied_penalty_msgs)}).")
        
        win_chance = self._calculate_win_chance(player_level, monster_level, energy_win_chance_mod)
        win = random.random() < win_chance
        player['last_fight'] = {"monster_name": monster['name'], "monster_level": monster_level, "win": win}
        
        xp_level_mult = self.get_config_value("xp_level_multiplier", event.target, default=2)
        base_xp = random.randint(monster.get('xp_win_min', 10), monster.get('xp_win_max', 20))
        total_xp = (base_xp + player_level * xp_level_mult) * diff_mod["xp_mult"] * energy_xp_mult

        # Apply rare spawn multiplier
        if is_rare:
            total_xp *= rare_xp_mult

        # Check for critical hit
        crit_chance = self.get_config_value("crit_chance", event.target, default=0.15)
        is_crit = win and random.random() < crit_chance

        if win:
            self.safe_reply(connection, event, f"Victory! (Win chance: {win_chance:.0%}) The {monster_name_with_level} is defeated! You gain {int(total_xp)} XP.")
            for m in self._grant_xp(user_id, username, total_xp, is_win=True, is_crit=is_crit): self.safe_reply(connection, event, m)
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

    def _cmd_mob_ping(self, connection, event, msg, username, match):
        """Toggle mob ping notifications for the user."""
        if not self.is_enabled(event.target):
            return False

        action = match.group(1).lower()  # "on" or "off"
        channel = event.target
        user_id = self.bot.get_user_id(username)

        # Get mob ping list per channel (store as dict with user_id -> username)
        mob_pings = self.get_state("mob_pings", {})
        if channel not in mob_pings:
            mob_pings[channel] = {}

        if action == "on":
            if user_id not in mob_pings[channel]:
                mob_pings[channel][user_id] = username
                self.set_state("mob_pings", mob_pings)
                self.save_state()
                self.safe_reply(connection, event, f"{username}, you will now be notified when mob encounters start.")
            else:
                # Update username in case it changed
                mob_pings[channel][user_id] = username
                self.set_state("mob_pings", mob_pings)
                self.save_state()
                self.safe_reply(connection, event, f"{username}, you are already receiving mob notifications.")
        else:  # off
            if user_id in mob_pings[channel]:
                del mob_pings[channel][user_id]
                self.set_state("mob_pings", mob_pings)
                self.save_state()
                self.safe_reply(connection, event, f"{username}, you will no longer be notified of mob encounters.")
            else:
                self.safe_reply(connection, event, f"{username}, you were not receiving mob notifications.")

        return True

    def _cmd_mob_start(self, connection, event, msg, username, match):
        """Start a mob encounter that others can join."""
        if not self.is_enabled(event.target):
            return False

        with self.mob_lock:
            # Check global cooldown for mob encounters (per channel)
            mob_cooldown = self.get_config_value("mob_cooldown_seconds", event.target, default=3600)  # 1 hour default
            if not self.check_rate_limit(f"mob_spawn_{event.target}", mob_cooldown):
                self.safe_reply(connection, event, "A mob encounter was recently completed. Please wait before summoning another.")
                return True
            active_mob = self.get_state("active_mob")
            if active_mob:
                self.safe_reply(connection, event, "A mob encounter is already active! Use !join to participate.")
                return True

            user_id = self.bot.get_user_id(username)
            player = self._get_player(user_id, username)

            # Check energy
            energy_enabled = self.get_config_value("energy_system.enabled", event.target, default=True)
            if energy_enabled and player["energy"] < 1:
                self.safe_reply(connection, event, f"You are too exhausted for a mob quest, {self.bot.title_for(username)}.")
                return True

            # Select a mob monster
            monsters = self.get_config_value("monsters", event.target, default=[])
            avg_level = player['level']
            possible_monsters = [m for m in monsters if isinstance(m, dict) and m['min_level'] <= avg_level + 5]

            if not possible_monsters:
                self.safe_reply(connection, event, "No suitable mob encounter found.")
                return True

            monster = random.choice(possible_monsters)
            monster_level = max(player['level'], avg_level + 3)

            # Check for rare spawn
            rare_spawn_chance = self.get_config_value("rare_spawn_chance", event.target, default=0.10)
            is_rare = random.random() < rare_spawn_chance

            join_window_seconds = self.get_config_value("mob_join_window_seconds", event.target, default=60)
            close_time = time.time() + join_window_seconds

            mob_data = {
                "channel": event.target,
                "monster": monster,
                "monster_level": monster_level,
                "is_rare": is_rare,
                "participants": [{"user_id": user_id, "username": username}],
                "initiator": username,
                "close_epoch": close_time
            }

            self.set_state("active_mob", mob_data)
            self.save_state()

            # Schedule mob window close
            schedule.every(join_window_seconds).seconds.do(self._close_mob_window).tag(f"{self.name}-mob_close")

            rare_prefix = "[RARE] " if is_rare else ""
            self.safe_reply(connection, event, f"{username} has summoned a {rare_prefix}Level {monster_level} {monster['name']}! Others can !join within {join_window_seconds} seconds!")

            if is_rare:
                self.safe_say(f"A rare mob encounter has appeared! Use !join to participate!", event.target)

            # Ping users who opted in for mob notifications
            mob_pings = self.get_state("mob_pings", {})
            if event.target in mob_pings and mob_pings[event.target]:
                ping_names = list(mob_pings[event.target].values())
                if ping_names:
                    self.safe_say(f"Mob alert: {', '.join(ping_names)}", event.target)

            return True

    def _cmd_mob_join(self, connection, event, msg, username, match):
        """Join an active mob encounter."""
        if not self.is_enabled(event.target):
            return False

        with self.mob_lock:
            active_mob = self.get_state("active_mob")
            if not active_mob:
                self.safe_reply(connection, event, "No active mob encounter to join.")
                return True

            if active_mob["channel"] != event.target:
                self.safe_reply(connection, event, "The mob encounter is in another channel.")
                return True

            user_id = self.bot.get_user_id(username)

            # Check if already in party
            if any(p["user_id"] == user_id for p in active_mob["participants"]):
                self.safe_reply(connection, event, "You are already in the party!")
                return True

            # Check energy
            player = self._get_player(user_id, username)
            energy_enabled = self.get_config_value("energy_system.enabled", event.target, default=True)
            if energy_enabled and player["energy"] < 1:
                self.safe_reply(connection, event, f"You are too exhausted to join, {self.bot.title_for(username)}.")
                return True

            # Add to party
            active_mob["participants"].append({"user_id": user_id, "username": username})
            self.set_state("active_mob", active_mob)
            self.save_state()

            party_size = len(active_mob["participants"])
            self.safe_reply(connection, event, f"{username} joins the party! ({party_size} adventurers ready)")
            return True

    def _close_mob_window(self):
        """Execute the mob encounter after the join window closes."""
        with self.mob_lock:
            active_mob = self.get_state("active_mob")
            if not active_mob:
                schedule.clear(self.name)
                return

            channel = active_mob["channel"]
            monster = active_mob["monster"]
            monster_level = active_mob["monster_level"]
            participants = active_mob["participants"]
            party_size = len(participants)

            # Clear the active mob and scheduled task
            self.set_state("active_mob", None)
            schedule.clear(self.name)

            # Calculate win chance based on party size
            # 1 person = 5%, 2 = 25%, 3 = 75%, 4+ = 95%
            win_chance_map = {1: 0.05, 2: 0.25, 3: 0.75}
            win_chance = win_chance_map.get(party_size, 0.95)  # 4+ people = 95%

            win = random.random() < win_chance

            # Check if rare spawn
            is_rare = active_mob.get("is_rare", False)
            rare_xp_mult = self.get_config_value("rare_spawn_xp_multiplier", channel, default=2.0)

            rare_prefix = "[RARE] " if is_rare else ""
            monster_name = f"{rare_prefix}Level {monster_level} {monster['name']}"

            # Deduct energy from all participants
            energy_enabled = self.get_config_value("energy_system.enabled", channel, default=True)
            players_state = self.get_state("players", {})

            for p in participants:
                player = self._get_player(p["user_id"], p["username"])
                if energy_enabled and player["energy"] > 0:
                    player["energy"] -= 1
                players_state[p["user_id"]] = player

            self.set_state("players", players_state)

            # Announce outcome
            party_names = ", ".join([p["username"] for p in participants])
            self.safe_say(f"The party ({party_names}) engages the {monster_name}!", channel)
            time.sleep(1.5)

            xp_level_mult = self.get_config_value("xp_level_multiplier", channel, default=2)
            base_xp = random.randint(monster.get('xp_win_min', 10), monster.get('xp_win_max', 20))

            if win:
                # Victory - distribute XP
                total_xp = (base_xp + monster_level * xp_level_mult) * 1.5  # Bonus for mob

                # Apply rare spawn multiplier
                if is_rare:
                    total_xp *= rare_xp_mult

                # Check for critical hit (shared for whole party)
                crit_chance = self.get_config_value("crit_chance", channel, default=0.15)
                is_crit = random.random() < crit_chance

                self.safe_say(f"Victory! (Win chance: {win_chance:.0%}) The {monster_name} falls! Each adventurer gains {int(total_xp)} XP!", channel)

                for p in participants:
                    xp_msgs = self._grant_xp(p["user_id"], p["username"], total_xp, is_win=True, is_crit=is_crit)
                    for m in xp_msgs:
                        self.safe_say(f"{p['username']}: {m}", channel)
            else:
                # Defeat - lose XP and potentially get injured
                xp_loss_perc = self.get_config_value("xp_loss_percentage", channel, default=0.25)
                xp_loss = (base_xp + monster_level * xp_level_mult) * xp_loss_perc
                self.safe_say(f"Defeat! (Win chance: {win_chance:.0%}) The party has been overwhelmed! Each member loses {int(xp_loss)} XP.", channel)

                for p in participants:
                    self._deduct_xp(p["user_id"], p["username"], xp_loss)
                    injury_msg = self._apply_injury(p["user_id"], p["username"], channel)
                    if injury_msg:
                        self.safe_say(f"{p['username']}: {injury_msg}", channel)

            self.save_state()

            self.set_state("active_mob", None)
            schedule.clear(self.name)

        return schedule.CancelJob

    # ===== MEDIC QUEST SYSTEM =====

    def _handle_medic_quest(self, connection, event, username):
        """Handle medic quests - fight for medkits instead of XP."""
        user_id = self.bot.get_user_id(username)
        player = self._get_player(user_id, username)

        # Check if medic quests are enabled
        if not self.get_config_value("medic_quests.enabled", event.target, default=True):
            self.safe_reply(connection, event, "Medic quests are not available at this time.")
            return True

        # Check energy
        energy_enabled = self.get_config_value("energy_system.enabled", event.target, default=True)
        if energy_enabled and player["energy"] < 1:
            self.safe_reply(connection, event, f"You are too exhausted for a quest, {self.bot.title_for(username)}.")
            return True

        # Check and clear expired injury
        player, recovery_msg = self._check_and_clear_injury(player)
        if recovery_msg:
            self.safe_reply(connection, event, recovery_msg)

        # Migrate old format
        if 'active_injury' in player:
            player['active_injuries'] = [player['active_injury']]
            del player['active_injury']

        # Check if player is injured
        if 'active_injuries' in player and player['active_injuries']:
            injury_names = [inj['name'] for inj in player['active_injuries']]
            if len(injury_names) == 1:
                self.safe_reply(connection, event, f"You are still recovering from your {injury_names[0]}. Rest or use a !medkit to heal.")
            else:
                self.safe_reply(connection, event, f"You are still recovering from: {', '.join(injury_names)}. Rest or use a !medkit to heal.")
            players_state = self.get_state("players", {})
            players_state[user_id] = player
            self.set_state("players", players_state)
            self.save_state()
            return True

        # Deduct energy
        if energy_enabled:
            player["energy"] = max(0, player["energy"] - 1)

        # Select monster
        monsters = self.get_config_value("monsters", event.target, default=[])
        suitable_monsters = [m for m in monsters if isinstance(m, dict) and m.get("min_level", 1) <= player["level"]]
        if not suitable_monsters:
            suitable_monsters = monsters

        if not suitable_monsters:
            self.safe_reply(connection, event, "No suitable monsters found for medic quest.")
            return True

        monster = random.choice(suitable_monsters)
        monster_level = max(1, player["level"] + random.randint(-2, 2))

        # Calculate combat with energy penalties
        energy_win_chance_mod = 0.0
        if energy_enabled:
            energy_penalties = self.get_config_value("energy_system.penalties", event.target, default=[])
            for penalty in sorted(energy_penalties, key=lambda x: x['threshold'], reverse=True):
                if player["energy"] <= penalty["threshold"]:
                    energy_win_chance_mod = penalty.get("win_chance_modifier", 0.0)

        win_chance = self._calculate_win_chance(player["level"], monster_level, energy_win_chance_mod)
        won = random.random() < win_chance

        # Get action text and format it with user and monster placeholders
        action_template = self._get_action_text(user_id)
        monster_name_with_level = f"Level {monster_level} {monster['name']}"
        action = action_template.format(user=username, monster=monster_name_with_level)

        if won:
            # Victory - check for medkit drop
            drop_chance = self.get_config_value("medic_quests.medkit_drop_chance", event.target, default=0.25)
            got_medkit = random.random() < drop_chance

            if got_medkit:
                player["medkits"] = player.get("medkits", 0) + 1
                result_msg = f"{action}. Victory! You found a MEDKIT! (Total: {player['medkits']})"
            else:
                result_msg = f"{action}. Victory! No medkit found this time."

        else:
            # Defeat - chance of injury
            result_msg = f"{action}. Defeat!"

            # Apply injury (injury_chance is already handled inside _apply_injury)
            injury_msg = self._apply_injury(user_id, username, event.target, is_medic_quest=True)
            if injury_msg:
                result_msg += f" {injury_msg}"

        # Save player state
        players_state = self.get_state("players", {})
        players_state[user_id] = player
        self.set_state("players", players_state)
        self.save_state()

        self.safe_reply(connection, event, result_msg)
        return True

    def _cmd_medkit(self, connection, event, msg, username, match):
        """Use a medkit to heal yourself or another player."""
        if not self.is_enabled(event.target):
            return False

        target_arg = (match.group(1) or "").strip() if match else ""
        user_id = self.bot.get_user_id(username)
        player = self._get_player(user_id, username)

        # Check if player has medkits
        if player.get("medkits", 0) < 1:
            self.safe_reply(connection, event, f"You don't have any medkits, {self.bot.title_for(username)}. Try !quest medic to earn one!")
            return True

        # Determine target
        if not target_arg:
            # Self-heal
            return self._medkit_self_heal(connection, event, username, user_id, player)
        else:
            # Heal another player
            return self._medkit_heal_other(connection, event, username, user_id, player, target_arg)

    def _medkit_self_heal(self, connection, event, username, user_id, player):
        """Use medkit on self."""
        # Migrate old format
        if 'active_injury' in player:
            player['active_injuries'] = [player['active_injury']]
            del player['active_injury']

        if 'active_injuries' not in player or not player['active_injuries']:
            self.safe_reply(connection, event, f"You're not injured, {self.bot.title_for(username)}!")
            return True

        injury_names = [inj['name'] for inj in player['active_injuries']]
        injury_count = len(injury_names)

        # Remove all injuries
        player['active_injuries'] = []

        # Deduct medkit
        player["medkits"] -= 1

        # Grant partial XP
        base_xp = self.get_config_value("base_xp_reward", event.target, default=50)
        self_heal_multiplier = self.get_config_value("medic_quests.self_heal_xp_multiplier", event.target, default=0.75)
        xp_reward = int(base_xp * self_heal_multiplier)

        xp_messages = self._grant_xp(user_id, username, xp_reward, is_win=False, is_crit=False)

        # Save state
        players_state = self.get_state("players", {})
        players_state[user_id] = player
        self.set_state("players", players_state)
        self.save_state()

        if injury_count == 1:
            response = f"{self.bot.title_for(username)} uses a medkit and recovers from {injury_names[0]}! (+{xp_reward} XP)"
        else:
            response = f"{self.bot.title_for(username)} uses a medkit and recovers from all injuries ({', '.join(injury_names)})! (+{xp_reward} XP)"

        if xp_messages:
            response += " " + " ".join(xp_messages)

        self.safe_reply(connection, event, response)
        return True

    def _medkit_heal_other(self, connection, event, username, user_id, player, target_nick):
        """Use medkit on another player."""
        target_id = self.bot.get_user_id(target_nick)
        target_player = self._get_player(target_id, target_nick)

        # Migrate old format
        if 'active_injury' in target_player:
            target_player['active_injuries'] = [target_player['active_injury']]
            del target_player['active_injury']

        # Check if target is injured
        if 'active_injuries' not in target_player or not target_player['active_injuries']:
            self.safe_reply(connection, event, f"{target_nick} is not injured!")
            return True

        injury_names = [inj['name'] for inj in target_player['active_injuries']]
        injury_count = len(injury_names)

        # Remove all target's injuries
        target_player['active_injuries'] = []

        # Deduct medkit from healer
        player["medkits"] -= 1

        # Grant MASSIVE XP to healer
        base_xp = self.get_config_value("base_xp_reward", event.target, default=50)
        altruistic_multiplier = self.get_config_value("medic_quests.altruistic_heal_xp_multiplier", event.target, default=3.0)
        xp_reward = int(base_xp * altruistic_multiplier)

        xp_messages = self._grant_xp(user_id, username, xp_reward, is_win=True, is_crit=False)

        # Save both players
        players_state = self.get_state("players", {})
        players_state[user_id] = player
        players_state[target_id] = target_player
        self.set_state("players", players_state)
        self.save_state()

        if injury_count == 1:
            response = f"{self.bot.title_for(username)} uses a medkit to heal {target_nick}'s {injury_names[0]}! Such selflessness is rewarded with +{xp_reward} XP!"
        else:
            response = f"{self.bot.title_for(username)} uses a medkit to heal all of {target_nick}'s injuries ({', '.join(injury_names)})! Such selflessness is rewarded with +{xp_reward} XP!"

        if xp_messages:
            response += " " + " ".join(xp_messages)

        self.safe_reply(connection, event, response)
        return True

    def _cmd_inventory(self, connection, event, msg, username, match):
        """Show player's medkits and injuries."""
        if not self.is_enabled(event.target):
            return False

        user_id = self.bot.get_user_id(username)
        player = self._get_player(user_id, username)

        # Check and clear expired injury
        player, recovery_msg = self._check_and_clear_injury(player)
        if recovery_msg:
            self.safe_reply(connection, event, recovery_msg)
            players_state = self.get_state("players", {})
            players_state[user_id] = player
            self.set_state("players", players_state)
            self.save_state()

        title = self.bot.title_for(username)
        medkit_count = player.get("medkits", 0)

        inv_parts = [f"{title}'s inventory:"]

        # Medkits
        if medkit_count > 0:
            inv_parts.append(f"Medkits: {medkit_count}")
        else:
            inv_parts.append("No medkits (try !quest medic)")

        # Migrate old format
        if 'active_injury' in player:
            player['active_injuries'] = [player['active_injury']]
            del player['active_injury']

        # Active injuries
        if 'active_injuries' in player and player['active_injuries']:
            injury_strs = []
            for injury in player['active_injuries']:
                try:
                    expires_at = datetime.fromisoformat(injury['expires_at'])
                    time_left = self._format_timedelta(expires_at)
                    injury_strs.append(f"{injury['name']} (recovers in {time_left})")
                except (ValueError, TypeError):
                    injury_strs.append(injury['name'])

            if len(injury_strs) == 1:
                inv_parts.append(f"Injury: {injury_strs[0]}")
            else:
                inv_parts.append(f"Injuries: {', '.join(injury_strs)}")
        else:
            inv_parts.append("Status: Healthy")

        self.safe_reply(connection, event, " | ".join(inv_parts))
        return True
