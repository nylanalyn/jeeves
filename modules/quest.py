# modules/quest.py
# A persistent RPG-style questing game for the channel.
import random
import time
import re
import schedule
import threading
import operator
import json
import os
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
    version = "4.0.0" # Added search system with items (energy potions, lucky charms, armor shards, XP scrolls)
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

        # Load quest content from JSON file
        self.content = self._load_content()

    def _load_content(self) -> Dict[str, Any]:
        """Load quest content from quest_content.json file."""
        content_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "quest_content.json")

        try:
            with open(content_file, 'r') as f:
                content = json.load(f)
                self.log_debug(f"Loaded quest content from {content_file}")
                return content
        except FileNotFoundError:
            self.log_debug(f"Quest content file not found at {content_file}, using config fallback")
            return {}
        except json.JSONDecodeError as e:
            self.log_debug(f"Error parsing quest content JSON: {e}, using config fallback")
            return {}

    def _get_content(self, key: str, channel: str = None, default: Any = None) -> Any:
        """Get content from JSON file, falling back to config if not found."""
        # Try to get from content file first
        if key in self.content:
            return self.content[key]
        # Fall back to config
        return self.get_config_value(key, channel, default=default)

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
        # Register more specific patterns first
        self.register_command(r"^\s*!quest\s+reload\s*$", self._cmd_quest_reload, name="quest_reload",
                              admin_only=True, description="Reload quest content from quest_content.json")
        self.register_command(r"^\s*!quest\s+mob\s+ping\s+(on|off)\s*$", self._cmd_mob_ping, name="mob_ping")
        self.register_command(r"^\s*!quest\s+mob\s*$", self._cmd_mob_start, name="mob")
        self.register_command(r"^\s*!quest\s+join\s*$", self._cmd_mob_join, name="join")
        self.register_command(r"^\s*!quest\s+medkit(?:\s+(.+))?\s*$", self._cmd_medkit, name="medkit",
                              description="Use a medkit to heal yourself or another player")
        self.register_command(r"^\s*!quest\s+inv(?:entory)?\s*$", self._cmd_inventory, name="inventory",
                              description="View your medkits and active injuries")
        self.register_command(r"^\s*!quest(?:\s+(.*))?$", self._cmd_quest_master, name="quest")

        # Short aliases for frequently-used quest commands
        self.register_command(r"^\s*!q(?:\s+(.*))?$", self._cmd_quest_master, name="quest_alias")
        self.register_command(r"^\s*!qe\s*$", self._cmd_quest_easy, name="quest_easy_alias")
        self.register_command(r"^\s*!qh\s*$", self._cmd_quest_hard, name="quest_hard_alias")
        self.register_command(r"^\s*!qp(?:\s+(.*))?\s*$", self._cmd_quest_profile_alias, name="quest_profile_alias")
        self.register_command(r"^\s*!qi\s*$", self._cmd_inventory, name="quest_inventory_alias")
        self.register_command(r"^\s*!qs(?:\s+(.*))?\s*$", self._cmd_quest_search_alias, name="quest_search_alias")
        self.register_command(r"^\s*!qm\s*$", self._cmd_quest_medic_alias, name="quest_medic_alias")
        self.register_command(r"^\s*!qu(?:\s+(.*))?\s*$", self._cmd_quest_use_alias, name="quest_use_alias")
        self.register_command(r"^\s*!qt\s*$", self._cmd_quest_leaderboard_alias, name="quest_leaderboard_alias")
        self.register_command(r"^\s*!qc(?:\s+(.*))?\s*$", self._cmd_quest_class_alias, name="quest_class_alias")

        # Legacy aliases for backwards compatibility
        self.register_command(r"^\s*!mob\s+ping\s+(on|off)\s*$", self._cmd_mob_ping, name="mob_ping_legacy")
        self.register_command(r"^\s*!mob\s*$", self._cmd_mob_start, name="mob_legacy")
        self.register_command(r"^\s*!join\s*$", self._cmd_mob_join, name="join_legacy")
        self.register_command(r"^\s*!medkit(?:\s+(.+))?\s*$", self._cmd_medkit, name="medkit_legacy")
        self.register_command(r"^\s*!inv(?:entory)?\s*$", self._cmd_inventory, name="inventory_legacy")

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
        
    def _apply_injury(self, user_id: str, username: str, channel: str, is_medic_quest: bool = False, injury_reduction: float = 0.0) -> Optional[str]:
        """Applies a random injury to a player upon defeat. Max 2 of each injury type."""
        injury_config = self.get_config_value("injury_system", channel, default={})
        if not injury_config.get("enabled"): return None

        # Don't apply injuries during medic quests
        if is_medic_quest:
            return None

        injury_chance = injury_config.get("injury_chance_on_loss", 0.75)
        # Apply injury reduction from armor
        injury_chance = max(0.0, injury_chance * (1.0 - injury_reduction))
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

    def _get_prestige_win_bonus(self, prestige: int) -> float:
        """Calculate win chance bonus from prestige level."""
        if prestige == 0:
            return 0.0
        elif prestige <= 3:
            return 0.05  # Prestige 1-3: +5%
        elif prestige <= 6:
            return 0.10  # Prestige 4-6: +10%
        elif prestige <= 9:
            return 0.15  # Prestige 7-9: +15%
        else:  # prestige == 10
            return 0.20  # Prestige 10: +20%

    def _get_prestige_xp_bonus(self, prestige: int) -> float:
        """Calculate XP multiplier from prestige level."""
        if prestige < 2:
            return 1.0  # No bonus for prestige 0-1
        elif prestige < 5:
            return 1.25  # Prestige 2-4: +25%
        elif prestige < 8:
            return 1.50  # Prestige 5-7: +50%
        elif prestige < 10:
            return 1.75  # Prestige 8-9: +75%
        else:  # prestige == 10
            return 2.0  # Prestige 10: +100% (double XP)

    def _get_prestige_energy_bonus(self, prestige: int) -> int:
        """Calculate max energy bonus from prestige level."""
        if prestige < 3:
            return 0  # No bonus for prestige 0-2
        elif prestige < 6:
            return 1  # Prestige 3-5: +1 energy
        elif prestige < 9:
            return 2  # Prestige 6-8: +2 energy
        else:  # prestige >= 9
            return 3  # Prestige 9-10: +3 energy

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

        # Add prestige bonus to max energy
        prestige_level = player.get("prestige", 0)
        prestige_energy_bonus = self._get_prestige_energy_bonus(prestige_level)
        max_energy += prestige_energy_bonus

        player.setdefault("xp_to_next_level", self._calculate_xp_for_level(player.get("level", 1)))
        player.setdefault("last_fight", None)
        player.setdefault("last_win_date", None)
        player.setdefault("energy", max_energy)
        player.setdefault("win_streak", 0)
        player.setdefault("prestige", 0)  # Prestige level

        # Inventory system
        player.setdefault("inventory", {
            "medkits": 0,
            "energy_potions": 0,
            "lucky_charms": 0,
            "armor_shards": 0,
            "xp_scrolls": 0
        })

        # Migrate old medkits format
        if "medkits" in player and isinstance(player["medkits"], int):
            player["inventory"]["medkits"] = player["medkits"]
            del player["medkits"]

        # Active effects (buffs/debuffs with expiry)
        player.setdefault("active_effects", [])

        player["name"] = username

        return player

    def _grant_xp(self, user_id: str, username: str, amount: int, is_win: bool = False, is_crit: bool = False) -> List[str]:
        player, messages, total_xp_gain = self._get_player(user_id, username), [], int(amount)
        today = datetime.now(UTC).date().isoformat()

        # Check if player is at level cap
        level_cap = self.get_config_value("level_cap", default=20)
        if player.get("level", 1) >= level_cap:
            messages.append(f"You are at the level cap ({level_cap}). Use !quest prestige to reset and gain permanent bonuses!")
            return messages

        # Apply prestige XP bonus
        prestige_xp_mult = self._get_prestige_xp_bonus(player.get("prestige", 0))
        if prestige_xp_mult > 1.0:
            total_xp_gain = int(total_xp_gain * prestige_xp_mult)

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

        while player["xp"] >= player["xp_to_next_level"] and player["level"] < level_cap:
            player["xp"] -= player["xp_to_next_level"]
            player["level"] += 1
            player["xp_to_next_level"] = self._calculate_xp_for_level(player["level"])
            leveled_up = True

        # Cap XP at level cap
        if player["level"] >= level_cap:
            player["xp"] = 0
            player["xp_to_next_level"] = 0

        players = self.get_state("players")
        players[user_id] = player
        self.set_state("players", players)

        if leveled_up:
            if player["level"] >= level_cap:
                messages.append(f"*** LEVEL {player['level']} ACHIEVED - MAXIMUM POWER! ***")
                messages.append(f"You have reached the peak of mortal strength. Use !quest prestige to transcend your limits and be reborn with permanent bonuses!")
            else:
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

    def _calculate_win_chance(self, player_level: float, monster_level: int, energy_modifier: float = 0.0, group_modifier: float = 0.0, prestige_level: int = 0) -> float:
        base_win = self.get_config_value("combat.base_win_chance", default=0.5)
        level_mod = self.get_config_value("combat.win_chance_level_modifier", default=0.1)
        min_win = self.get_config_value("combat.min_win_chance", default=0.05)
        max_win = self.get_config_value("combat.max_win_chance", default=0.95)

        # Add prestige bonus
        prestige_modifier = self._get_prestige_win_bonus(prestige_level)

        level_diff = player_level - monster_level
        chance = base_win + (level_diff * level_mod) + energy_modifier + group_modifier + prestige_modifier
        return max(min_win, min(max_win, chance))

    def _get_action_text(self, user_id: str) -> str:
        player_classes = self.get_state("player_classes", {})
        player_class = player_classes.get(user_id)
        classes_config = self._get_content("classes", default={})

        if player_class and player_class in classes_config:
            return random.choice(classes_config[player_class].get("actions", ["..."]))

        story_beats = self._get_content("story_beats", default={})
        return random.choice(story_beats.get('actions', ["..."]))

    def _cmd_quest_master(self, connection, event, msg, username, match):
        if not self.is_enabled(event.target): return False

        args_str = (match.group(1) or "").strip()
        args = args_str.split()

        difficulty_mods = self.get_config_value("difficulty", default={})
        if not args_str or args[0].lower() in difficulty_mods:
            return self._handle_solo_quest(connection, event, username, args[0] if args else "normal")

        subcommand = args[0].lower()
        if subcommand == "search":
            return self._handle_search(connection, event, username, args[1:])
        elif subcommand == "medic":
            return self._handle_medic_quest(connection, event, username)
        elif subcommand == "profile":
            return self._handle_profile(connection, event, username, args[1:])
        elif subcommand == "story":
            return self._handle_story(connection, event, username)
        elif subcommand == "class":
            return self._handle_class(connection, event, username, args[1:])
        elif subcommand in ("top", "leaderboard"):
            return self._handle_leaderboard(connection, event)
        elif subcommand == "prestige":
            return self._handle_prestige(connection, event, username)
        elif subcommand == "use":
            return self._handle_use_item(connection, event, username, args[1:])
        else:
            self.safe_reply(connection, event, f"Unknown quest command. Use '!quest', or '!quest <search|use|medic|profile|story|class|top|prestige>'.")
            return True

    def _cmd_quest_easy(self, connection, event, msg, username, match):
        if not self.is_enabled(event.target):
            return False
        return self._handle_solo_quest(connection, event, username, "easy")

    def _cmd_quest_hard(self, connection, event, msg, username, match):
        if not self.is_enabled(event.target):
            return False
        return self._handle_solo_quest(connection, event, username, "hard")

    def _cmd_quest_profile_alias(self, connection, event, msg, username, match):
        if not self.is_enabled(event.target):
            return False
        args_str = (match.group(1) or "").strip() if match and match.lastindex else ""
        args = args_str.split() if args_str else []
        return self._handle_profile(connection, event, username, args)

    def _cmd_quest_search_alias(self, connection, event, msg, username, match):
        if not self.is_enabled(event.target):
            return False
        args_str = (match.group(1) or "").strip() if match and match.lastindex else ""
        args = args_str.split() if args_str else []
        return self._handle_search(connection, event, username, args)

    def _cmd_quest_medic_alias(self, connection, event, msg, username, match):
        if not self.is_enabled(event.target):
            return False
        return self._handle_medic_quest(connection, event, username)

    def _cmd_quest_use_alias(self, connection, event, msg, username, match):
        if not self.is_enabled(event.target):
            return False
        args_str = (match.group(1) or "").strip() if match and match.lastindex else ""
        args = args_str.split() if args_str else []
        return self._handle_use_item(connection, event, username, args)

    def _cmd_quest_leaderboard_alias(self, connection, event, msg, username, match):
        if not self.is_enabled(event.target):
            return False
        return self._handle_leaderboard(connection, event)

    def _cmd_quest_class_alias(self, connection, event, msg, username, match):
        if not self.is_enabled(event.target):
            return False
        args_str = (match.group(1) or "").strip() if match and match.lastindex else ""
        args = args_str.split() if args_str else []
        return self._handle_class(connection, event, username, args)

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

        # Add prestige to max energy display
        prestige_level = player.get("prestige", 0)
        prestige_energy_bonus = self._get_prestige_energy_bonus(prestige_level)
        max_energy += prestige_energy_bonus

        # Build profile header with prestige
        if prestige_level > 0:
            profile_parts = [f"Profile for {title}: Level {player['level']} (Prestige {prestige_level})"]
        else:
            profile_parts = [f"Profile for {title}: Level {player['level']}"]

        # Add XP (unless at level cap)
        level_cap = self.get_config_value("level_cap", event.target, default=20)
        if player['level'] < level_cap:
            profile_parts.append(f"XP: {player['xp']}/{player['xp_to_next_level']}")
        else:
            profile_parts.append(f"XP: MAX (use !quest prestige to ascend)")

        profile_parts.append(f"Class: {player_class.capitalize()}")

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
        world_lore = self._get_content("world_lore", default=[])
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
        classes_config = self._get_content("classes", default={})

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

    def _handle_prestige(self, connection, event, username):
        """Handle prestige - reset to level 1 with permanent bonuses."""
        user_id = self.bot.get_user_id(username)
        player = self._get_player(user_id, username)

        # Check if player is at level cap
        level_cap = self.get_config_value("level_cap", default=20)
        if player.get("level", 1) < level_cap:
            self.safe_reply(connection, event, f"You must reach level {level_cap} before you can prestige. Current level: {player['level']}")
            return True

        # Check if already at max prestige
        max_prestige = self.get_config_value("max_prestige", default=10)
        current_prestige = player.get("prestige", 0)
        if current_prestige >= max_prestige:
            self.safe_reply(connection, event, f"You are already at maximum prestige ({max_prestige})! You are a legend!")
            return True

        # Calculate new prestige level
        new_prestige = current_prestige + 1

        # Reset player to level 1 (but keep medkits!)
        player["level"] = 1
        player["xp"] = 0
        player["xp_to_next_level"] = self._calculate_xp_for_level(1)
        player["prestige"] = new_prestige
        player["win_streak"] = 0
        # medkits are preserved through prestige
        player["active_injuries"] = []
        if "active_injury" in player:
            del player["active_injury"]

        # Save player state
        players = self.get_state("players")
        players[user_id] = player
        self.set_state("players", players)
        self.save_state()

        # Build prestige announcement
        win_bonus = self._get_prestige_win_bonus(new_prestige)
        xp_bonus = self._get_prestige_xp_bonus(new_prestige)
        energy_bonus = self._get_prestige_energy_bonus(new_prestige)

        bonus_parts = []
        if win_bonus > 0:
            bonus_parts.append(f"+{int(win_bonus * 100)}% win chance")
        if xp_bonus > 1.0:
            bonus_parts.append(f"{int((xp_bonus - 1.0) * 100)}% bonus XP")
        if energy_bonus > 0:
            bonus_parts.append(f"+{energy_bonus} max energy")

        bonus_text = ", ".join(bonus_parts) if bonus_parts else "preparing for future bonuses"

        self.safe_reply(connection, event, f"*** {self.bot.title_for(username)} HAS ASCENDED TO PRESTIGE {new_prestige}! ***")
        self.safe_reply(connection, event, f"Reborn at Level 1 with permanent bonuses: {bonus_text}")
        self.safe_reply(connection, event, f"The cycle begins anew, but you are forever changed...")

        return True

    def _handle_leaderboard(self, connection, event):
        """Display top 10 players by prestige, level, and XP."""
        players = self.get_state("players", {})

        if not players:
            self.safe_reply(connection, event, "No players have embarked on quests yet.")
            return True

        # Sort by prestige (desc), then level (desc), then XP (desc)
        sorted_players = sorted(
            [(uid, p) for uid, p in players.items() if isinstance(p, dict)],
            key=lambda x: (x[1].get("prestige", 0), x[1].get("level", 1), x[1].get("xp", 0)),
            reverse=True
        )[:10]

        self.safe_reply(connection, event, "Quest Leaderboard - Top 10 Adventurers:")
        for idx, (uid, player) in enumerate(sorted_players, 1):
            name = player.get("name", "Unknown")
            level = player.get("level", 1)
            xp = player.get("xp", 0)
            prestige = player.get("prestige", 0)
            streak = player.get("win_streak", 0)

            # Format prestige indicator
            prestige_str = f"P{prestige} " if prestige > 0 else ""
            streak_indicator = f" [Streak: {streak}]" if streak > 0 else ""

            self.safe_reply(connection, event, f"{idx}. {name} - {prestige_str}Level {level} ({xp} XP){streak_indicator}")

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
        monsters = self._get_content("monsters", event.target, default=[])
        story_beats = self._get_content("story_beats", event.target, default={})

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

        base_win_chance = self._calculate_win_chance(player_level, monster_level, energy_win_chance_mod, prestige_level=player.get("prestige", 0))

        # Calculate base XP
        xp_level_mult = self.get_config_value("xp_level_multiplier", event.target, default=2)
        base_xp = random.randint(monster.get('xp_win_min', 10), monster.get('xp_win_max', 20))
        total_xp = (base_xp + player_level * xp_level_mult) * diff_mod["xp_mult"] * energy_xp_mult

        # Apply rare spawn multiplier
        if is_rare:
            total_xp *= rare_xp_mult

        # Apply active effects (lucky charm, xp scroll) - pass placeholder for is_win
        win_chance_modified, xp_modified, effect_msgs = self._apply_active_effects_to_combat(player, base_win_chance, total_xp, is_win=False)

        # Show effect messages before combat
        for msg in effect_msgs:
            if "lucky charm" in msg.lower():  # Only show lucky charm pre-combat
                self.safe_reply(connection, event, msg)

        # Determine combat result
        win = random.random() < win_chance_modified
        player['last_fight'] = {"monster_name": monster['name'], "monster_level": monster_level, "win": win}

        # Re-apply effects now that we know the outcome (for XP scroll)
        _, total_xp, xp_effect_msgs = self._apply_active_effects_to_combat(player, base_win_chance, total_xp, is_win=win)

        # Check for critical hit
        crit_chance = self.get_config_value("crit_chance", event.target, default=0.15)
        is_crit = win and random.random() < crit_chance

        if win:
            self.safe_reply(connection, event, f"Victory! (Win chance: {win_chance_modified:.0%}) The {monster_name_with_level} is defeated! You gain {int(total_xp)} XP.")
            # Show XP scroll message if it activated
            for msg in xp_effect_msgs:
                if "scroll" in msg.lower():
                    self.safe_reply(connection, event, msg)
            for m in self._grant_xp(user_id, username, total_xp, is_win=True, is_crit=is_crit): self.safe_reply(connection, event, m)
        else:
            xp_loss_perc = self.get_config_value("xp_loss_percentage", event.target, default=0.25)
            xp_loss = total_xp * xp_loss_perc
            self.safe_reply(connection, event, f"Defeat! (Win chance: {win_chance_modified:.0%}) You have been bested! You lose {int(xp_loss)} XP.")
            self._deduct_xp(user_id, username, xp_loss)

            # Apply injury with armor reduction
            injury_reduction = self._get_injury_reduction(player)
            injury_msg = self._apply_injury(user_id, username, event.target, injury_reduction=injury_reduction)
            if injury_msg:
                self.safe_reply(connection, event, injury_msg)

        # Consume active effects after combat
        self._consume_combat_effects(player, is_win=win)

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
                self.safe_reply(connection, event, "A mob encounter is already active! Use !quest join (or !join) to participate.")
                return True

            user_id = self.bot.get_user_id(username)
            player = self._get_player(user_id, username)

            # Check energy
            energy_enabled = self.get_config_value("energy_system.enabled", event.target, default=True)
            if energy_enabled and player["energy"] < 1:
                self.safe_reply(connection, event, f"You are too exhausted for a mob quest, {self.bot.title_for(username)}.")
                return True

            # Select a mob monster
            monsters = self._get_content("monsters", event.target, default=[])
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
            self.safe_reply(connection, event, f"{username} has summoned a {rare_prefix}Level {monster_level} {monster['name']}! Others can !quest join (or !join) within {join_window_seconds} seconds!")

            if is_rare:
                self.safe_say(f"A rare mob encounter has appeared! Use !quest join (or !join) to participate!", event.target)

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

    # ===== ACTIVE EFFECTS SYSTEM =====

    def _apply_active_effects_to_combat(self, player: Dict[str, Any], base_win_chance: float, base_xp: int, is_win: bool) -> Tuple[float, int, List[str]]:
        """
        Apply active effects to combat, return (modified_win_chance, modified_xp, messages).
        """
        messages = []
        win_chance = base_win_chance
        xp = base_xp

        # Lucky charm - boost win chance
        for effect in player.get("active_effects", []):
            if effect["type"] == "lucky_charm" and effect.get("expires") == "next_fight":
                win_bonus = effect.get("win_bonus", 0) / 100.0
                win_chance += win_bonus
                messages.append(f"Your lucky charm glows! (+{effect.get('win_bonus', 0)}% win chance)")

        # XP scroll - boost XP on wins
        if is_win:
            for effect in player.get("active_effects", []):
                if effect["type"] == "xp_scroll" and effect.get("expires") == "next_win":
                    xp_mult = effect.get("xp_multiplier", 1.0)
                    xp = int(xp * xp_mult)
                    messages.append(f"The XP scroll activates! ({xp_mult}x XP)")

        return (win_chance, xp, messages)

    def _consume_combat_effects(self, player: Dict[str, Any], is_win: bool):
        """Remove expired combat effects after a fight."""
        effects_to_remove = []

        for i, effect in enumerate(player.get("active_effects", [])):
            # Remove effects that expire on any fight
            if effect.get("expires") == "next_fight":
                effects_to_remove.append(i)
            # Remove effects that expire on win
            elif is_win and effect.get("expires") == "next_win":
                effects_to_remove.append(i)
            # Decrement fight-based effects
            elif effect["type"] == "armor_shard" and "remaining_fights" in effect:
                effect["remaining_fights"] -= 1
                if effect["remaining_fights"] <= 0:
                    effects_to_remove.append(i)

        # Remove in reverse order to avoid index issues
        for i in sorted(effects_to_remove, reverse=True):
            player["active_effects"].pop(i)

    def _get_injury_reduction(self, player: Dict[str, Any]) -> float:
        """Get total injury chance reduction from active effects."""
        reduction = 0.0
        for effect in player.get("active_effects", []):
            if effect["type"] == "armor_shard":
                reduction += effect.get("injury_reduction", 0.0)
        return min(reduction, 0.90)  # Cap at 90% reduction

    # ===== SEARCH SYSTEM =====

    def _perform_single_search(self, player: Dict[str, Any], event) -> Dict[str, Any]:
        """
        Perform a single search and return the result.
        Returns: {"type": str, "item": str, "message": str, "xp_change": int}
        """
        roll = random.random()
        result = {"type": "nothing", "item": None, "message": "", "xp_change": 0}

        # Get search probabilities from config
        medkit_chance = self.get_config_value("search_system.medkit_chance", event.target, default=0.25)
        energy_potion_chance = self.get_config_value("search_system.energy_potion_chance", event.target, default=0.15)
        lucky_charm_chance = self.get_config_value("search_system.lucky_charm_chance", event.target, default=0.15)
        armor_shard_chance = self.get_config_value("search_system.armor_shard_chance", event.target, default=0.10)
        xp_scroll_chance = self.get_config_value("search_system.xp_scroll_chance", event.target, default=0.10)
        injury_chance = self.get_config_value("search_system.injury_chance", event.target, default=0.05)
        # Remaining probability is "nothing"

        cumulative = 0.0

        # Medkit
        cumulative += medkit_chance
        if roll < cumulative:
            player["inventory"]["medkits"] += 1
            result = {"type": "item", "item": "medkit", "message": "a MEDKIT", "xp_change": 0}
            return result

        # Energy Potion
        cumulative += energy_potion_chance
        if roll < cumulative:
            player["inventory"]["energy_potions"] += 1
            result = {"type": "item", "item": "energy_potion", "message": "an ENERGY POTION", "xp_change": 0}
            return result

        # Lucky Charm
        cumulative += lucky_charm_chance
        if roll < cumulative:
            player["inventory"]["lucky_charms"] += 1
            result = {"type": "item", "item": "lucky_charm", "message": "a LUCKY CHARM", "xp_change": 0}
            return result

        # Armor Shard
        cumulative += armor_shard_chance
        if roll < cumulative:
            player["inventory"]["armor_shards"] += 1
            result = {"type": "item", "item": "armor_shard", "message": "an ARMOR SHARD", "xp_change": 0}
            return result

        # XP Scroll
        cumulative += xp_scroll_chance
        if roll < cumulative:
            player["inventory"]["xp_scrolls"] += 1
            result = {"type": "item", "item": "xp_scroll", "message": "an XP SCROLL", "xp_change": 0}
            return result

        # Minor Injury
        cumulative += injury_chance
        if roll < cumulative:
            # Lose 1 energy and small XP
            player["energy"] = max(0, player["energy"] - 1)
            xp_loss = random.randint(5, 15)
            result = {"type": "injury", "item": None, "message": "INJURED! Lost 1 energy", "xp_change": -xp_loss}
            return result

        # Nothing found (default)
        result = {"type": "nothing", "item": None, "message": "nothing of value", "xp_change": 0}
        return result

    def _handle_search(self, connection, event, username, args):
        """Handle search command - search for items using energy."""
        user_id = self.bot.get_user_id(username)
        player = self._get_player(user_id, username)

        # Check if search is enabled
        if not self.get_config_value("search_system.enabled", event.target, default=True):
            self.safe_reply(connection, event, "Searching is not available at this time.")
            return True

        # Parse number of searches
        num_searches = 1
        if args:
            try:
                num_searches = int(args[0])
                if num_searches < 1:
                    self.safe_reply(connection, event, "You must search at least once!")
                    return True
                if num_searches > 20:
                    self.safe_reply(connection, event, "You can search at most 20 times at once!")
                    return True
            except ValueError:
                self.safe_reply(connection, event, "Please provide a valid number of searches (e.g., !quest search 5)")
                return True

        # Check energy
        energy_cost_per_search = self.get_config_value("search_system.energy_cost", event.target, default=1)
        total_energy_cost = energy_cost_per_search * num_searches

        if player["energy"] < total_energy_cost:
            self.safe_reply(connection, event, f"You need {total_energy_cost} energy to search {num_searches} time(s). You have {player['energy']}.")
            return True

        # Check and clear expired injury
        player, recovery_msg = self._check_and_clear_injury(player)
        if recovery_msg:
            self.safe_reply(connection, event, recovery_msg)

        # Migrate old injury format
        if 'active_injury' in player:
            player['active_injuries'] = [player['active_injury']]
            del player['active_injury']

        # Check if player is injured
        if 'active_injuries' in player and player['active_injuries']:
            injury_names = [inj['name'] for inj in player['active_injuries']]
            if len(injury_names) == 1:
                self.safe_reply(connection, event, f"You are still recovering from your {injury_names[0]}. Rest or use a medkit to heal.")
            else:
                self.safe_reply(connection, event, f"You are still recovering from: {', '.join(injury_names)}. Rest or use a medkit to heal.")
            players_state = self.get_state("players", {})
            players_state[user_id] = player
            self.set_state("players", players_state)
            self.save_state()
            return True

        # Deduct energy upfront
        player["energy"] -= total_energy_cost

        # Perform searches
        results = []
        total_xp_change = 0
        for _ in range(num_searches):
            search_result = self._perform_single_search(player, event)
            results.append(search_result)
            total_xp_change += search_result["xp_change"]

        # Apply XP change if any
        if total_xp_change < 0:
            self._deduct_xp(user_id, username, abs(total_xp_change))

        # Save player state
        players_state = self.get_state("players", {})
        players_state[user_id] = player
        self.set_state("players", players_state)
        self.save_state()

        # Build result message
        if num_searches == 1:
            result = results[0]
            msg = f"You search the area and find {result['message']}!"
            if result["xp_change"] < 0:
                msg += f" (Lost {abs(result['xp_change'])} XP)"
            self.safe_reply(connection, event, msg)
        else:
            # Summarize multiple searches
            item_counts = {
                "medkit": 0,
                "energy_potion": 0,
                "lucky_charm": 0,
                "armor_shard": 0,
                "xp_scroll": 0,
                "nothing": 0,
                "injury": 0
            }

            for result in results:
                if result["type"] == "item":
                    item_counts[result["item"]] += 1
                elif result["type"] == "nothing":
                    item_counts["nothing"] += 1
                elif result["type"] == "injury":
                    item_counts["injury"] += 1

            # Build summary
            found_items = []
            if item_counts["medkit"] > 0:
                found_items.append(f"{item_counts['medkit']} medkit(s)")
            if item_counts["energy_potion"] > 0:
                found_items.append(f"{item_counts['energy_potion']} energy potion(s)")
            if item_counts["lucky_charm"] > 0:
                found_items.append(f"{item_counts['lucky_charm']} lucky charm(s)")
            if item_counts["armor_shard"] > 0:
                found_items.append(f"{item_counts['armor_shard']} armor shard(s)")
            if item_counts["xp_scroll"] > 0:
                found_items.append(f"{item_counts['xp_scroll']} XP scroll(s)")

            msg = f"After {num_searches} searches, you found: "
            if found_items:
                msg += ", ".join(found_items)
            else:
                msg += "nothing of value"

            if item_counts["nothing"] > 0:
                msg += f" ({item_counts['nothing']} empty search(es))"
            if item_counts["injury"] > 0:
                msg += f" (Injured {item_counts['injury']} time(s), lost {abs(total_xp_change)} XP)"

            self.safe_reply(connection, event, msg)

        return True

    def _handle_use_item(self, connection, event, username, args):
        """Handle using items from inventory."""
        if not args:
            self.safe_reply(connection, event, "Usage: !quest use <item> - Available items: medkit, energy_potion, lucky_charm, armor_shard, xp_scroll")
            return True

        item_name = args[0].lower()
        user_id = self.bot.get_user_id(username)
        player = self._get_player(user_id, username)

        # Map user-friendly names to inventory keys
        item_map = {
            "medkit": "medkits",
            "energy_potion": "energy_potions",
            "potion": "energy_potions",
            "lucky_charm": "lucky_charms",
            "charm": "lucky_charms",
            "armor_shard": "armor_shards",
            "armor": "armor_shards",
            "xp_scroll": "xp_scrolls",
            "scroll": "xp_scrolls"
        }

        if item_name not in item_map:
            self.safe_reply(connection, event, f"Unknown item: {item_name}. Available: medkit, energy_potion, lucky_charm, armor_shard, xp_scroll")
            return True

        inventory_key = item_map[item_name]

        # Check if player has the item
        if player["inventory"][inventory_key] < 1:
            self.safe_reply(connection, event, f"You don't have any {item_name.replace('_', ' ')}s!")
            return True

        # Use the item
        if inventory_key == "medkits":
            # Medkit - heal injuries
            # Migrate old format
            if 'active_injury' in player:
                player['active_injuries'] = [player['active_injury']]
                del player['active_injury']

            if not player.get('active_injuries') or len(player['active_injuries']) == 0:
                self.safe_reply(connection, event, "You are not injured! Save your medkit for when you need it.")
                return True

            player["inventory"]["medkits"] -= 1
            injury_healed = player['active_injuries'].pop(0)
            self.safe_reply(connection, event, f"You use a medkit to heal your {injury_healed['name']}. You feel much better! ({player['inventory']['medkits']} medkits remaining)")

        elif inventory_key == "energy_potions":
            # Energy potion - restore 2-4 energy
            max_energy = self.get_config_value("energy_system.max_energy", event.target, default=10)
            prestige_level = player.get("prestige", 0)
            prestige_energy_bonus = self._get_prestige_energy_bonus(prestige_level)
            max_energy += prestige_energy_bonus

            if player["energy"] >= max_energy:
                self.safe_reply(connection, event, "Your energy is already full! Save the potion for later.")
                return True

            energy_restore = random.randint(2, 4)
            player["inventory"]["energy_potions"] -= 1
            old_energy = player["energy"]
            player["energy"] = min(max_energy, player["energy"] + energy_restore)
            actual_restore = player["energy"] - old_energy
            self.safe_reply(connection, event, f"You drink the energy potion and feel refreshed! +{actual_restore} energy ({player['energy']}/{max_energy}). ({player['inventory']['energy_potions']} potions remaining)")

        elif inventory_key == "lucky_charms":
            # Lucky charm - add active effect for next fight
            player["inventory"]["lucky_charms"] -= 1
            # Check if already has lucky charm effect
            has_charm = any(eff["type"] == "lucky_charm" for eff in player["active_effects"])
            if has_charm:
                self.safe_reply(connection, event, "You already have a lucky charm active! The effects don't stack.")
                player["inventory"]["lucky_charms"] += 1  # Refund
                return True

            win_bonus = random.randint(10, 20)
            player["active_effects"].append({
                "type": "lucky_charm",
                "win_bonus": win_bonus,
                "expires": "next_fight"
            })
            self.safe_reply(connection, event, f"You activate the lucky charm! Your next fight will have +{win_bonus}% win chance. ({player['inventory']['lucky_charms']} charms remaining)")

        elif inventory_key == "armor_shards":
            # Armor shard - reduce injury chance for 3 fights
            player["inventory"]["armor_shards"] -= 1
            has_armor = any(eff["type"] == "armor_shard" for eff in player["active_effects"])
            if has_armor:
                self.safe_reply(connection, event, "You already have armor protection active! The effects don't stack.")
                player["inventory"]["armor_shards"] += 1  # Refund
                return True

            player["active_effects"].append({
                "type": "armor_shard",
                "injury_reduction": 0.30,
                "remaining_fights": 3
            })
            self.safe_reply(connection, event, f"You equip the armor shard! Injury chance reduced by 30% for the next 3 fights. ({player['inventory']['armor_shards']} shards remaining)")

        elif inventory_key == "xp_scrolls":
            # XP scroll - 1.5x XP on next win
            player["inventory"]["xp_scrolls"] -= 1
            has_scroll = any(eff["type"] == "xp_scroll" for eff in player["active_effects"])
            if has_scroll:
                self.safe_reply(connection, event, "You already have an XP scroll active! The effects don't stack.")
                player["inventory"]["xp_scrolls"] += 1  # Refund
                return True

            player["active_effects"].append({
                "type": "xp_scroll",
                "xp_multiplier": 1.5,
                "expires": "next_win"
            })
            self.safe_reply(connection, event, f"You read the XP scroll! Your next victory will grant 1.5x XP. ({player['inventory']['xp_scrolls']} scrolls remaining)")

        # Save player state
        players_state = self.get_state("players", {})
        players_state[user_id] = player
        self.set_state("players", players_state)
        self.save_state()

        return True

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
                self.safe_reply(connection, event, f"You are still recovering from your {injury_names[0]}. Rest or use !quest medkit (or !medkit) to heal.")
            else:
                self.safe_reply(connection, event, f"You are still recovering from: {', '.join(injury_names)}. Rest or use !quest medkit (or !medkit) to heal.")
            players_state = self.get_state("players", {})
            players_state[user_id] = player
            self.set_state("players", players_state)
            self.save_state()
            return True

        # Deduct energy
        if energy_enabled:
            player["energy"] = max(0, player["energy"] - 1)

        # Select monster
        monsters = self._get_content("monsters", event.target, default=[])
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

        win_chance = self._calculate_win_chance(player["level"], monster_level, energy_win_chance_mod, prestige_level=player.get("prestige", 0))
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

        # Check if player has medkits (check both old and new format)
        medkit_count = player.get("inventory", {}).get("medkits", 0) or player.get("medkits", 0)
        if medkit_count < 1:
            self.safe_reply(connection, event, f"You don't have any medkits, {self.bot.title_for(username)}. Try !quest search to find one!")
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

        # Deduct medkit (use new inventory system)
        player["inventory"]["medkits"] -= 1

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

        # Deduct medkit from healer (use new inventory system)
        player["inventory"]["medkits"] -= 1

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
        inventory = player.get("inventory", {})

        # Build inventory display
        items = []
        if inventory.get("medkits", 0) > 0:
            items.append(f"Medkits: {inventory['medkits']}")
        if inventory.get("energy_potions", 0) > 0:
            items.append(f"Energy Potions: {inventory['energy_potions']}")
        if inventory.get("lucky_charms", 0) > 0:
            items.append(f"Lucky Charms: {inventory['lucky_charms']}")
        if inventory.get("armor_shards", 0) > 0:
            items.append(f"Armor Shards: {inventory['armor_shards']}")
        if inventory.get("xp_scrolls", 0) > 0:
            items.append(f"XP Scrolls: {inventory['xp_scrolls']}")

        if not items:
            items_msg = "No items (try !quest search)"
        else:
            items_msg = ", ".join(items)

        # Active effects
        effects = []
        for effect in player.get("active_effects", []):
            if effect["type"] == "lucky_charm":
                effects.append(f"Lucky Charm (+{effect.get('win_bonus', 0)}% win)")
            elif effect["type"] == "armor_shard":
                effects.append(f"Armor ({effect.get('remaining_fights', 0)} fights)")
            elif effect["type"] == "xp_scroll":
                effects.append("XP Scroll (next win)")

        # Migrate old format
        if 'active_injury' in player:
            player['active_injuries'] = [player['active_injury']]
            del player['active_injury']

        # Active injuries
        injuries = []
        if 'active_injuries' in player and player['active_injuries']:
            for injury in player['active_injuries']:
                try:
                    expires_at = datetime.fromisoformat(injury['expires_at'])
                    time_left = self._format_timedelta(expires_at)
                    injuries.append(f"{injury['name']} ({time_left})")
                except (ValueError, TypeError):
                    injuries.append(injury['name'])

        # Build final message
        self.safe_reply(connection, event, f"{title}'s Inventory: {items_msg}")
        if effects:
            self.safe_reply(connection, event, f"Active Effects: {', '.join(effects)}")
        if injuries:
            self.safe_reply(connection, event, f"Injuries: {', '.join(injuries)}")
        elif not effects:
            self.safe_reply(connection, event, "Status: Healthy")

        return True

    def _cmd_quest_reload(self, connection, event, msg, username, match):
        """Reload quest content from quest_content.json file."""
        if not self.is_enabled(event.target):
            return False

        old_monster_count = len(self.content.get("monsters", []))
        old_story_count = len(self.content.get("story_beats", {}).get("openers", []))

        # Reload content
        self.content = self._load_content()

        new_monster_count = len(self.content.get("monsters", []))
        new_story_count = len(self.content.get("story_beats", {}).get("openers", []))

        self.safe_reply(connection, event, f"Quest content reloaded from quest_content.json")
        self.safe_reply(connection, event, f"Monsters: {old_monster_count} -> {new_monster_count} | Story openers: {old_story_count} -> {new_story_count}")
        return True
