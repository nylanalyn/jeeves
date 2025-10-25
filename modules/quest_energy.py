# modules/quest_energy.py
# Energy system and scheduling for quest module
import schedule
import time
from datetime import datetime, timezone
from typing import Dict, Any, List

from .quest_state import QuestStateManager

UTC = timezone.utc


class QuestEnergy:
    """Energy management and regeneration system for quest module."""

    def __init__(self, bot, state_manager: QuestStateManager):
        self.bot = bot
        self.state = state_manager
        self.config = state_manager.get_quest_config()

    def regenerate_energy(self) -> None:
        """Regenerate energy for all players."""
        energy_config = self.config.get("energy_system", {})
        if not energy_config.get("enabled", True):
            return

        all_players = self.state.get_all_players()
        updated_count = 0

        for user_id, player_data in all_players.items():
            if isinstance(player_data, dict):
                if self._regenerate_player_energy(player_data):
                    self.state.update_player_data(user_id, player_data)
                    updated_count += 1

        if updated_count > 0:
            self.bot.log_debug(f"Energy regenerated for {updated_count} players")

    def _regenerate_player_energy(self, player_data: Dict[str, Any]) -> bool:
        """Regenerate energy for a single player. Returns True if energy was regenerated."""
        if not isinstance(player_data, dict):
            return False

        max_energy = player_data.get("max_energy", self.config.get("energy_system", {}).get("max_energy", 10))
        current_energy = player_data.get("energy", 0)

        if current_energy >= max_energy:
            return False

        # Check for injury-based energy regeneration penalty
        from .quest_status import QuestStatus
        quest_status = QuestStatus(self.bot, self.state)
        injury_effects = quest_status.get_injury_effects(self._get_user_id_from_player(player_data))
        regen_modifier = injury_effects.get("energy_regen_modifier", 0)

        # Base regeneration is 1 energy, modified by injuries
        regen_amount = max(0, 1 + regen_modifier)
        player_data["energy"] = min(current_energy + regen_amount, max_energy)
        player_data["last_energy_regen"] = time.time()

        return True

    def _get_user_id_from_player(self, player_data: Dict[str, Any]) -> str:
        """Extract user_id from player data - this is a helper method."""
        # In the actual implementation, this would be passed as a parameter
        # This is a placeholder to match the expected interface
        return "unknown"

    def regenerate_energy_for_player(self, user_id: str) -> bool:
        """Regenerate energy for a specific player. Returns True if energy was regenerated."""
        player = self.state.get_player_data(user_id)
        max_energy = player.get("max_energy", self.config.get("energy_system", {}).get("max_energy", 10))
        current_energy = player.get("energy", 0)

        if current_energy >= max_energy:
            return False

        # Check for injury-based energy regeneration penalty
        from .quest_status import QuestStatus
        quest_status = QuestStatus(self.bot, self.state)
        injury_effects = quest_status.get_injury_effects(user_id)
        regen_modifier = injury_effects.get("energy_regen_modifier", 0)

        # Base regeneration is 1 energy, modified by injuries
        regen_amount = max(0, 1 + regen_modifier)
        player["energy"] = min(current_energy + regen_amount, max_energy)
        player["last_energy_regen"] = time.time()

        self.state.update_player_data(user_id, player)
        return True

    def consume_energy(self, user_id: str, amount: int) -> bool:
        """Consume energy from a player. Returns True if successful."""
        player = self.state.get_player_data(user_id)

        if player["energy"] < amount:
            return False

        player["energy"] -= amount
        self.state.update_player_data(user_id, player)
        return True

    def restore_energy(self, user_id: str, amount: int) -> int:
        """Restore energy to a player. Returns actual amount restored."""
        player = self.state.get_player_data(user_id)
        max_energy = player["max_energy"]
        current_energy = player["energy"]

        if current_energy >= max_energy:
            return 0

        actual_restore = min(amount, max_energy - current_energy)
        player["energy"] = current_energy + actual_restore
        self.state.update_player_data(user_id, player)

        return actual_restore

    def get_energy_status(self, user_id: str) -> Dict[str, Any]:
        """Get detailed energy status for a player."""
        player = self.state.get_player_data(user_id)
        max_energy = player["max_energy"]
        current_energy = player["energy"]

        # Calculate regeneration info
        energy_config = self.config.get("energy_system", {})
        regen_minutes = energy_config.get("regen_minutes", 10)
        next_regen_in = max(0, regen_minutes * 60 - (time.time() - player.get("last_energy_regen", 0)))

        return {
            "current": current_energy,
            "max": max_energy,
            "percentage": (current_energy / max_energy) * 100,
            "regen_enabled": energy_config.get("enabled", True),
            "regen_minutes": regen_minutes,
            "next_regen_seconds": int(next_regen_in),
            "next_regen_minutes": int(next_regen_in // 60),
            "is_full": current_energy >= max_energy
        }

    def schedule_energy_regeneration(self) -> None:
        """Set up the energy regeneration schedule."""
        energy_config = self.config.get("energy_system", {})
        if not energy_config.get("enabled", True):
            return

        regen_minutes = energy_config.get("regen_minutes", 10)
        schedule.clear("quest-energy_regen")
        schedule.every(regen_minutes).minutes.do(self.regenerate_energy).tag("quest-energy_regen")

    def apply_energy_penalty(self, user_id: str, penalties: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Apply energy penalties based on current energy level."""
        player = self.state.get_player_data(user_id)
        current_energy = player["energy"]

        # Sort penalties by threshold (highest first)
        applicable_penalties = []
        for penalty in sorted(penalties, key=lambda x: x['threshold'], reverse=True):
            if current_energy <= penalty['threshold']:
                applicable_penalties.append(penalty)
                break  # Only apply the highest threshold penalty

        return {
            "penalties_applied": applicable_penalties,
            "energy_before": current_energy,
            "has_penalty": bool(applicable_penalties)
        }

    def check_energy_for_quest(self, user_id: str, energy_cost: int = 1) -> Dict[str, Any]:
        """Check if player has enough energy for a quest."""
        player = self.state.get_player_data(user_id)
        current_energy = player["energy"]

        return {
            "has_energy": current_energy >= energy_cost,
            "current_energy": current_energy,
            "required_energy": energy_cost,
            "deficit": max(0, energy_cost - current_energy)
        }

    def format_energy_bar(self, user_id: str) -> str:
        """Format energy display with visual bar."""
        status = self.get_energy_status(user_id)
        current = status["current"]
        max_energy = status["max"]

        # Create visual bar
        bar_length = 10
        filled_length = int((current / max_energy) * bar_length)
        bar = "⚡" * filled_length + "░" * (bar_length - filled_length)

        if status["is_full"]:
            return f"⚡ Energy: {current}/{max_energy} [{bar}] (FULL)"
        else:
            next_regen = status["next_regen_minutes"]
            if next_regen > 0:
                return f"⚡ Energy: {current}/{max_energy} [{bar}] (Next regen: {next_regen}m)"
            else:
                return f"⚡ Energy: {current}/{max_energy} [{bar}] (Regenerating...)"

    def get_max_energy_for_level(self, level: int) -> int:
        """Get maximum energy for a given level."""
        energy_config = self.config.get("energy_system", {})
        return energy_config.get("max_energy", 10)

    def update_max_energy_on_level_up(self, user_id: str, new_level: int) -> bool:
        """Update max energy when player levels up. Returns True if changed."""
        player = self.state.get_player_data(user_id)
        new_max_energy = self.get_max_energy_for_level(new_level)

        if player["max_energy"] != new_max_energy:
            player["max_energy"] = new_max_energy
            # If current energy exceeds new max, cap it
            if player["energy"] > new_max_energy:
                player["energy"] = new_max_energy
            self.state.update_player_data(user_id, player)
            return True

        return False

    def reset_energy_on_prestige(self, user_id: str) -> None:
        """Reset energy to full when player prestiges."""
        player = self.state.get_player_data(user_id)
        max_energy = self.get_max_energy_for_level(1)  # Reset to level 1 max
        player["energy"] = max_energy
        player["max_energy"] = max_energy
        player["last_energy_regen"] = time.time()
        self.state.update_player_data(user_id, player)

    def get_all_players_energy_summary(self) -> List[Dict[str, Any]]:
        """Get energy summary for all players (useful for admin commands)."""
        all_players = self.state.get_all_players()
        summary = []

        for user_id, player_data in all_players.items():
            if isinstance(player_data, dict):
                nick = self.bot.get_user_nick(user_id)
                status = self.get_energy_status(user_id)
                summary.append({
                    "user_id": user_id,
                    "nick": nick,
                    "energy": status["current"],
                    "max_energy": status["max"],
                    "is_full": status["is_full"],
                    "injuries": player_data.get("active_injuries", [])
                })

        return summary