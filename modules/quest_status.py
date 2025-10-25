# modules/quest_status.py
# Injury and status effect system for quest module
import random
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Tuple, Optional

from .quest_state import QuestStateManager

UTC = timezone.utc


class QuestStatus:
    """Injury and status effect management for quest system."""

    def __init__(self, bot, state_manager: QuestStateManager):
        self.bot = bot
        self.state = state_manager
        self.config = state_manager.get_quest_config()

    def apply_injury(self, user_id: str, username: str, channel: str,
                    injury_reduction: float = 0.0) -> Optional[str]:
        """Apply a random injury to a player upon defeat. Returns injury message."""
        injury_config = self.config.get("injury_system", {})
        if not injury_config.get("enabled"):
            return None

        # Check injury chance
        injury_chance = injury_config.get("injury_chance_on_loss", 0.75)
        # Apply injury reduction from armor
        injury_chance = max(0.0, injury_chance * (1.0 - injury_reduction))

        if random.random() > injury_chance:
            return None

        possible_injuries = injury_config.get("injuries", [])
        if not possible_injuries:
            return None

        injury = random.choice(possible_injuries)
        player = self.state.get_player_data(user_id)

        # Migrate old single injury format to list
        if 'active_injury' in player:
            player['active_injuries'] = [player['active_injury']]
            del player['active_injury']

        # Initialize injuries list
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
        self.state.update_player_data(user_id, player)

        # Return appropriate message
        if injury_count == 1:
            return f"You have sustained another {injury['name']}! {injury['description']}"
        else:
            return f"You have sustained an injury: {injury['name']}! {injury['description']}"

    def heal_injuries(self, user_id: str, injury_name: Optional[str] = None,
                     all_injuries: bool = False) -> List[Dict[str, Any]]:
        """Heal injuries for a player. Returns list of healed injuries."""
        player = self.state.get_player_data(user_id)

        # Migrate old single injury format to list
        if 'active_injury' in player:
            player['active_injuries'] = [player['active_injury']]
            del player['active_injury']

        if 'active_injuries' not in player or not player['active_injuries']:
            return []

        healed_injuries = []

        if all_injuries:
            # Heal all injuries
            healed_injuries = player['active_injuries'].copy()
            player['active_injuries'] = []
        elif injury_name:
            # Heal specific injury
            remaining_injuries = []
            for injury in player['active_injuries']:
                if injury['name'].lower() == injury_name.lower():
                    healed_injuries.append(injury)
                else:
                    remaining_injuries.append(injury)
            player['active_injuries'] = remaining_injuries
        else:
            # Heal first injury
            if player['active_injuries']:
                healed_injuries.append(player['active_injuries'].pop(0))

        if healed_injuries:
            self.state.update_player_data(user_id, player)

        return healed_injuries

    def check_and_clear_expired_injuries(self, user_id: str) -> Tuple[Dict[str, Any], Optional[str]]:
        """Check for expired injuries and remove them. Returns (updated_player, recovery_message)."""
        player = self.state.get_player_data(user_id)

        # Migrate old single injury format to list
        if 'active_injury' in player:
            player['active_injuries'] = [player['active_injury']]
            del player['active_injury']

        if 'active_injuries' not in player or not player['active_injuries']:
            return player, None

        now = datetime.now(UTC)
        active_injuries = []
        expired_injuries = []

        for injury in player['active_injuries']:
            try:
                expires_at = datetime.fromisoformat(injury['expires_at'])
                if expires_at > now:
                    active_injuries.append(injury)
                else:
                    expired_injuries.append(injury['name'])
            except (ValueError, TypeError):
                # Invalid injury, remove it
                expired_injuries.append(injury.get('name', 'Unknown injury'))

        player['active_injuries'] = active_injuries
        self.state.update_player_data(user_id, player)

        # Return recovery message if any injuries expired
        if expired_injuries:
            if len(expired_injuries) == 1:
                return player, f"You have recovered from your {expired_injuries[0]}!"
            else:
                return player, f"You have recovered from: {', '.join(expired_injuries)}!"

        return player, None

    def get_injury_effects(self, user_id: str) -> Dict[str, float]:
        """Get total effects from all active injuries for a player."""
        player = self.state.get_player_data(user_id)

        effects = {
            "xp_multiplier": 1.0,
            "energy_regen_modifier": 0
        }

        # Migrate old single injury format to list
        if 'active_injury' in player:
            player['active_injuries'] = [player['active_injury']]
            del player['active_injury']

        if 'active_injuries' not in player:
            return effects

        # Apply all injury effects
        for injury in player['active_injuries']:
            injury_effects = injury.get('effects', {})
            xp_mult = injury_effects.get('xp_multiplier', 1.0)
            effects["xp_multiplier"] *= xp_mult

            regen_mod = injury_effects.get('energy_regen_modifier', 0)
            effects["energy_regen_modifier"] += regen_mod

        return effects

    def has_active_injuries(self, user_id: str) -> bool:
        """Check if player has any active injuries."""
        player = self.state.get_player_data(user_id)

        # Migrate old single injury format to list
        if 'active_injury' in player:
            player['active_injuries'] = [player['active_injury']]
            del player['active_injury']

        injuries = player.get('active_injuries', [])
        return bool(injuries)

    def get_injury_list(self, user_id: str) -> List[str]:
        """Get formatted list of active injuries for display."""
        player = self.state.get_player_data(user_id)

        # Migrate old single injury format to list
        if 'active_injury' in player:
            player['active_injuries'] = [player['active_injury']]
            del player['active_injury']

        if 'active_injuries' not in player or not player['active_injuries']:
            return []

        injury_strs = []
        now = datetime.now(UTC)

        for injury in player['active_injuries']:
            try:
                expires_at = datetime.fromisoformat(injury['expires_at'])
                if expires_at > now:
                    time_left = expires_at - now
                    hours = int(time_left.total_seconds() // 3600)
                    minutes = int((time_left.total_seconds() % 3600) // 60)
                    time_str = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"
                    injury_strs.append(f"{injury['name']} ({time_str})")
                else:
                    injury_strs.append(injury['name'])
            except (ValueError, TypeError):
                injury_strs.append(injury['name'])

        return injury_strs

    def get_injury_reduction(self, user_id: str) -> float:
        """Get total injury chance reduction from active effects."""
        player = self.state.get_player_data(user_id)
        reduction = 0.0

        for effect in player.get("active_effects", []):
            if effect["type"] == "armor_shard":
                reduction += effect.get("injury_reduction", 0.0)

        return reduction

    def apply_injury_from_search(self, user_id: str) -> Dict[str, Any]:
        """Apply injury from failed search attempt."""
        player = self.state.get_player_data(user_id)

        # Apply injury
        injury_config = self.config.get("injury_system", {})
        possible_injuries = injury_config.get("injuries", [])
        if possible_injuries:
            injury = random.choice(possible_injuries)
            duration = timedelta(hours=injury.get("duration_hours", 1))
            expires_at = datetime.now(UTC) + duration

            new_injury = {
                "name": injury['name'],
                "description": injury['description'],
                "expires_at": expires_at.isoformat(),
                "effects": injury.get('effects', {})
            }

            # Initialize injuries list
            if 'active_injuries' not in player:
                player['active_injuries'] = []

            # Migrate old single injury format to list
            if 'active_injury' in player:
                player['active_injuries'] = [player['active_injury']]
                del player['active_injury']

            player['active_injuries'].append(new_injury)
            self.state.update_player_data(user_id, player)

            return {
                "success": True,
                "type": "injury",
                "injury": new_injury,
                "message": f"INJURED! You sustained: {injury['name']}! {injury['description']}"
            }

        return {
            "success": False,
            "message": "You got hurt but managed to avoid serious injury."
        }

    def process_armor_effects(self, user_id: str) -> bool:
        """Process armor shard effects after combat. Returns True if armor was consumed."""
        player = self.state.get_player_data(user_id)
        armor_consumed = False

        active_effects = player.get("active_effects", [])
        remaining_effects = []

        for effect in active_effects:
            if effect["type"] == "armor_shard":
                remaining_fights = effect.get("remaining_fights", 0) - 1
                if remaining_fights > 0:
                    effect["remaining_fights"] = remaining_fights
                    remaining_effects.append(effect)
                else:
                    armor_consumed = True
            else:
                remaining_effects.append(effect)

        if armor_consumed:
            player["active_effects"] = remaining_effects
            self.state.update_player_data(user_id, player)

        return armor_consumed

    def format_injury_status(self, user_id: str) -> str:
        """Format injury status for display in profiles."""
        if not self.has_active_injuries(user_id):
            return ""

        injury_list = self.get_injury_list(user_id)
        if not injury_list:
            return ""

        if len(injury_list) == 1:
            return f"Status: Injured ({injury_list[0]})"
        else:
            return f"Status: Injured ({', '.join(injury_list)})"

    def get_available_injuries(self) -> List[Dict[str, Any]]:
        """Get list of possible injuries from configuration."""
        return self.config.get("injury_system", {}).get("injuries", [])