# modules/quest_core.py
# Core player management and XP system for quest module
import random
import operator
from typing import Dict, Any, List, Tuple, Optional

from .base import SimpleCommandModule, admin_required
from .quest_state import QuestStateManager


class QuestCore:
    """Core quest functionality for player management, XP, and progression."""

    def __init__(self, bot, state_manager: QuestStateManager):
        self.bot = bot
        self.state = state_manager
        self.config = state_manager.get_quest_config()

    def get_player(self, user_id: str) -> Dict:
        """Get or create player data."""
        player = self.state.get_player_data(user_id)
        if not player or "xp" not in player:
            player = self.state._get_default_player_data()
            self.state.update_player_data(user_id, player)
        return player

    def grant_xp(self, user_id: str, amount: int, multiplier: float = 1.0) -> Tuple[int, bool]:
        """Grant XP to a player and handle level ups. Returns (new_level, leveled_up)."""
        player = self.get_player(user_id)

        # Apply multipliers
        final_amount = int(amount * multiplier)

        # Apply prestige bonuses
        effective_prestige = player.get("effective_prestige", player.get("prestige", 0))
        if effective_prestige > 0:
            prestige_bonus = effective_prestige * 0.1  # 10% per effective prestige
            final_amount = int(final_amount * (1 + prestige_bonus))

        player["xp"] += final_amount
        old_level = player["level"]

        # Check for level up
        new_level = self.calculate_level_from_xp(player["xp"])
        leveled_up = new_level > old_level

        if leveled_up:
            player["level"] = new_level
            player["max_energy"] = self.config.get("energy_system", {}).get("max_energy", 10)
            player["energy"] = min(player["energy"], player["max_energy"])

        self.state.update_player_data(user_id, player)
        return new_level, leveled_up

    def deduct_xp(self, user_id: str, amount: int) -> int:
        """Deduct XP from a player, preventing level loss below current. Returns actual amount deducted."""
        player = self.get_player(user_id)

        xp_for_current_level = self.calculate_xp_for_level(player["level"])
        min_xp = xp_for_current_level

        # Can't go below minimum XP for current level
        max_deductable = player["xp"] - min_xp
        actual_amount = min(amount, max_deductable)

        player["xp"] -= actual_amount
        self.state.update_player_data(user_id, player)

        return actual_amount

    def calculate_level_from_xp(self, xp: int) -> int:
        """Calculate player level from total XP."""
        level = 1
        while xp >= self.calculate_xp_for_level(level + 1):
            level += 1
        return min(level, self.config.get("level_cap", 20))

    def calculate_xp_for_level(self, level: int) -> int:
        """Calculate XP required for a specific level using safe formula evaluation."""
        formula = self.config.get("xp_curve_formula", "level * 100")

        # Safe evaluation of mathematical expressions
        allowed_names = {
            "level": level,
            "abs": abs,
            "min": min,
            "max": max,
            "round": round,
            "pow": pow,
            "int": int,
            "float": float
        }

        try:
            # Only allow mathematical operations
            code = compile(formula, "<string>", "eval")
            for name in code.co_names:
                if name not in allowed_names:
                    raise ValueError(f"Unsafe name in formula: {name}")

            result = eval(code, {"__builtins__": {}}, allowed_names)
            return max(0, int(result))
        except Exception as e:
            self.bot.log_debug(f"Error calculating XP for level {level}: {e}")
            # Fallback to simple linear formula
            return level * 100

    def handle_prestige(self, user_id: str) -> Tuple[bool, str]:
        """Handle player prestige. Returns (success, message)."""
        player = self.get_player(user_id)

        if player["level"] < self.config.get("level_cap", 20):
            return False, "You must reach level 20 to prestige!"

        current_prestige = player.get("prestige", 0)
        max_prestige = self.config.get("max_prestige", 10)

        if current_prestige >= max_prestige:
            # Player has reached max prestige - offer transcendence option
            from .quest_legacy import QuestLegacy
            legacy = QuestLegacy(self.bot, self.state)

            can_transcend, message = legacy.can_transcend(user_id)
            if can_transcend:
                return False, f"You've reached the maximum prestige level of {max_prestige}! Use **!quest transcend** to become a Legacy Boss and reset your journey!"
            else:
                return False, f"You've reached the maximum prestige level of {max_prestige}! {message}"

        # Perform prestige
        player["prestige"] += 1
        player["xp"] = 0
        player["level"] = 1
        player["energy"] = player["max_energy"]
        player["wins"] = 0
        player["losses"] = 0
        player["streak"] = 0
        player["max_streak"] = 0
        player["injuries"] = []
        player["inventory"] = {
            "medkits": 0,
            "energy_potions": 0,
            "lucky_charms": 0,
            "armor_shards": 0,
            "xp_scrolls": 0
        }
        player["active_effects"] = []
        player["quest_cooldown"] = None
        player["search_cooldown"] = None

        # Store prestige bonus
        if "prestige_bonuses" not in player:
            player["prestige_bonuses"] = []

        prestige_bonus = f"+10% XP gain (Prestige {player['prestige']})"
        player["prestige_bonuses"].append(prestige_bonus)

        self.state.update_player_data(user_id, player)

        return True, f"🌟 **PRESTIGE COMPLETE!** You are now Prestige {player['prestige']}! All progress has been reset but you'll gain {player['prestige'] * 10}% more XP forever!"

    def get_leaderboard(self, limit: int = 10, sort_by: str = "prestige") -> List[Tuple[str, Dict]]:
        """Get leaderboard data sorted by specified criteria."""
        all_players = self.state.get_all_players()

        if not all_players:
            return []

        # Sort players based on criteria
        if sort_by == "prestige":
            sorted_players = sorted(
                all_players.items(),
                key=lambda x: (x[1].get("prestige", 0), x[1].get("level", 1), x[1].get("xp", 0)),
                reverse=True
            )
        elif sort_by == "level":
            sorted_players = sorted(
                all_players.items(),
                key=lambda x: (x[1].get("level", 1), x[1].get("xp", 0)),
                reverse=True
            )
        elif sort_by == "wins":
            sorted_players = sorted(
                all_players.items(),
                key=lambda x: (x[1].get("wins", 0), x[1].get("level", 1)),
                reverse=True
            )
        else:  # default to prestige
            sorted_players = sorted(
                all_players.items(),
                key=lambda x: (x[1].get("prestige", 0), x[1].get("level", 1), x[1].get("xp", 0)),
                reverse=True
            )

        return sorted_players[:limit]

    def format_player_profile(self, user_id: str) -> str:
        """Format player data into a readable profile."""
        player = self.get_player(user_id)
        nick = self.bot.get_user_nick(user_id)

        # Calculate progress to next level
        current_level = player["level"]
        current_xp = player["xp"]
        xp_for_current = self.calculate_xp_for_level(current_level)
        xp_for_next = self.calculate_xp_for_level(current_level + 1)
        xp_needed = xp_for_next - current_xp
        xp_total_needed = xp_for_next - xp_for_current

        progress = (current_xp - xp_for_current) / max(1, xp_total_needed) * 100
        progress_bar = "█" * int(progress / 10) + "░" * (10 - int(progress / 10))

        profile = f"👤 **{nick}**'s Profile\n"
        profile += f"📊 Level {current_level} (Prestige {player.get('prestige', 0)})\n"
        profile += f"⭐ XP: {current_xp} / {xp_for_next} ({progress:.1f}%)\n"
        profile += f"📈 Progress: [{progress_bar}] {xp_needed} XP to next level\n"
        profile += f"⚡ Energy: {player['energy']}/{player['max_energy']}\n"
        profile += f"🏆 Wins: {player['wins']} | Losses: {player['losses']}\n"
        profile += f"🔥 Current Streak: {player['streak']} | Best: {player['max_streak']}\n"

        # Show class if assigned
        if player.get("class"):
            profile += f"🎭 Class: {player['class']}\n"

        # Show injuries
        if player.get("injuries"):
            profile += f"🩹 Injuries: {len(player['injuries'])}\n"

        # Show prestige bonuses
        if player.get("prestige_bonuses"):
            profile += f"✨ Prestige Bonuses: {', '.join(player['prestige_bonuses'])}\n"

        # Show challenge path if active
        challenge_stats = player.get("challenge_stats", {})
        if challenge_stats.get("path"):
            profile += f"🎯 Challenge Path: {challenge_stats['path']}\n"

        return profile

    def assign_class(self, user_id: str, class_name: str) -> Tuple[bool, str]:
        """Assign a class to a player."""
        player = self.get_player(user_id)

        # Check if player meets requirements (if any)
        # For now, allow any class assignment

        player["class"] = class_name
        self.state.update_player_data(user_id, player)

        return True, f"🎭 You are now a {class_name}!"

    def get_available_classes(self) -> List[str]:
        """Get list of available classes."""
        # For now, return some basic classes
        # This could be expanded to load from config or content files
        return [
            "Warrior", "Mage", "Rogue", "Cleric", "Ranger",
            "Paladin", "Necromancer", "Bard", "Monk", "Druid"
        ]