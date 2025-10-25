# modules/quest_state.py
# Shared state management for quest system modules
import threading
from typing import Dict, Any, Optional
import json


class QuestStateManager:
    """Centralized state manager for all quest modules."""

    def __init__(self, bot):
        self.bot = bot
        self._lock = threading.RLock()

    def get_player_data(self, user_id: str, default: Optional[Dict] = None) -> Dict:
        """Get player data from state."""
        if default is None:
            default = self._get_default_player_data()

        with self._lock:
            players = self.bot.state_manager.get_module_state("quest", {}).get("players", {})
            return players.get(user_id, default.copy())

    def update_player_data(self, user_id: str, data: Dict) -> None:
        """Update player data in state."""
        with self._lock:
            quest_state = self.bot.state_manager.get_module_state("quest", {})
            if "players" not in quest_state:
                quest_state["players"] = {}
            quest_state["players"][user_id] = data
            self.bot.state_manager.update_module_state("quest", quest_state)

    def get_all_players(self) -> Dict[str, Dict]:
        """Get all players data."""
        with self._lock:
            return self.bot.state_manager.get_module_state("quest", {}).get("players", {})

    def get_active_mob(self) -> Optional[Dict]:
        """Get active mob data."""
        with self._lock:
            return self.bot.state_manager.get_module_state("quest", {}).get("active_mob")

    def update_active_mob(self, mob_data: Optional[Dict]) -> None:
        """Update active mob data."""
        with self._lock:
            quest_state = self.bot.state_manager.get_module_state("quest", {})
            quest_state["active_mob"] = mob_data
            self.bot.state_manager.update_module_state("quest", quest_state)

    def get_player_classes(self) -> Dict:
        """Get player classes mapping."""
        with self._lock:
            return self.bot.state_manager.get_module_state("quest", {}).get("player_classes", {})

    def update_player_classes(self, classes: Dict) -> None:
        """Update player classes mapping."""
        with self._lock:
            quest_state = self.bot.state_manager.get_module_state("quest", {})
            quest_state["player_classes"] = classes
            self.bot.state_manager.update_module_state("quest", quest_state)

    def get_challenge_paths(self) -> Dict:
        """Get challenge paths configuration."""
        with self._lock:
            return self.bot.state_manager.get_module_state("quest", {}).get("challenge_paths", {})

    def update_challenge_paths(self, paths: Dict) -> None:
        """Update challenge paths configuration."""
        with self._lock:
            quest_state = self.bot.state_manager.get_module_state("quest", {})
            quest_state["challenge_paths"] = paths
            self.bot.state_manager.update_module_state("quest", quest_state)

    def get_content(self) -> Dict:
        """Get quest content."""
        with self._lock:
            return self.bot.state_manager.get_module_state("quest", {}).get("content", {})

    def update_content(self, content: Dict) -> None:
        """Update quest content."""
        with self._lock:
            quest_state = self.bot.state_manager.get_module_state("quest", {})
            quest_state["content"] = content
            self.bot.state_manager.update_module_state("quest", quest_state)

    def get_quest_config(self) -> Dict:
        """Get quest module configuration."""
        return self.bot.config.get("quest", {})

    def _get_default_player_data(self) -> Dict:
        """Get default player data structure."""
        return {
            "xp": 0,
            "level": 1,
            "prestige": 0,
            "energy": 10,
            "max_energy": 10,
            "last_energy_regen": None,
            "wins": 0,
            "losses": 0,
            "streak": 0,
            "max_streak": 0,
            "injuries": [],
            "inventory": {
                "medkits": 0,
                "energy_potions": 0,
                "lucky_charms": 0,
                "armor_shards": 0,
                "xp_scrolls": 0
            },
            "active_effects": [],
            "quest_cooldown": None,
            "search_cooldown": None,
            "class": None,
            "prestige_bonuses": [],
            "challenge_stats": {},
            "medkit_usage": {}
        }