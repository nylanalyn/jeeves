# modules/quest.py
# A persistent RPG-style questing game for the channel.
import random
import time
import re
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
    version = "1.0.0"
    description = "An RPG-style questing game where users can fight monsters and level up."

    def __init__(self, bot, config):
        """Initializes the Quest module's state and configuration."""
        # --- Pre-super() setup ---
        # This is where we define attributes needed by _register_commands
        self.on_config_reload(config)

        # --- super() call ---
        # This will call _register_commands, so all needed attributes must be set above
        super().__init__(bot)

        # --- Post-super() setup ---
        # Initialize state for player profiles
        self.set_state("players", self.get_state("players", {}))
        self.save_state()
        self.is_loaded = True

    def on_config_reload(self, config):
        """Handles reloading the module's configuration."""
        quest_config = config.get(self.name, {})
        self.ALLOWED_CHANNELS = quest_config.get("allowed_channels", [])
        self.COOLDOWN = quest_config.get("cooldown_seconds", 300)
        self.XP_CURVE_FORMULA = quest_config.get("xp_curve_formula", "level * 100")

    def _register_commands(self):
        """Registers all the commands for the quest module."""
        self.register_command(
            r"^\s*!quest\s+profile(?:\s+(\S+))?\s*$",
            self._cmd_profile,
            name="quest profile",
            description="View your or another player's quest profile."
        )
        self.register_command(
            r"^\s*!quest\s*$",
            self._cmd_quest,
            name="quest",
            cooldown=self.COOLDOWN,
            description="Embark on a new quest."
        )
        # Admin command for testing
        self.register_command(
            r"^\s*!quest\s+admin\s+addxp\s+(\S+)\s+(\d+)\s*$",
            self._cmd_admin_add_xp,
            name="quest admin addxp",
            admin_only=True,
            description="[Admin] Give a player XP."
        )

    def _get_player(self, username: str) -> Dict[str, Any]:
        """
        Retrieves a player's profile from the state, creating it if it doesn't exist.
        """
        players = self.get_state("players", {})
        player_key = username.lower()
        
        if player_key not in players:
            players[player_key] = {
                "name": username,
                "level": 1,
                "xp": 0,
                "xp_to_next_level": self._calculate_xp_for_level(1),
                "last_quest_time": 0
            }
        
        # Ensure existing players have the latest data structure
        if "xp_to_next_level" not in players[player_key]:
            level = players[player_key].get("level", 1)
            players[player_key]["xp_to_next_level"] = self._calculate_xp_for_level(level)

        return players[player_key]

    def _calculate_xp_for_level(self, level: int) -> int:
        """Calculates the XP needed to advance to the next level based on the config formula."""
        try:
            # A safe way to evaluate the formula
            return int(eval(self.XP_CURVE_FORMULA, {"__builtins__": {}}, {"level": level}))
        except Exception as e:
            self._record_error(f"Error evaluating XP curve formula: {e}")
            return level * 100 # Fallback to a simple formula

    def _grant_xp(self, username: str, amount: int) -> Optional[str]:
        """Grants XP to a player and handles leveling up."""
        player = self._get_player(username)
        player_key = username.lower()
        
        player["xp"] += amount
        
        leveled_up = False
        while player["xp"] >= player["xp_to_next_level"]:
            player["xp"] -= player["xp_to_next_level"]
            player["level"] += 1
            player["xp_to_next_level"] = self._calculate_xp_for_level(player["level"])
            leveled_up = True
            
        players = self.get_state("players")
        players[player_key] = player
        self.set_state("players", players)
        self.save_state()

        if leveled_up:
            return f"Congratulations, you have reached Level {player['level']}!"
        return None

    def on_ambient_message(self, connection, event, msg: str, username: str) -> bool:
        """This module does not handle ambient messages."""
        return False

    # --- Command Handlers ---

    def _cmd_profile(self, connection, event, msg, username, match):
        """Handles the !quest profile command."""
        target_user = match.group(1) or username
        player = self._get_player(target_user)
        
        title = self.bot.title_for(player["name"])
        
        response = (
            f"Profile for {title} {player['name']}: "
            f"Level {player['level']} | "
            f"XP: {player['xp']}/{player['xp_to_next_level']}"
        )
        
        self.safe_reply(connection, event, response)
        return True

    def _cmd_quest(self, connection, event, msg, username, match):
        """Handles the !quest command."""
        # Check if the command is being used in an allowed channel
        if self.ALLOWED_CHANNELS and event.target not in self.ALLOWED_CHANNELS:
            return False # Silently ignore if not in the right channel

        # For V1, we will just grant a small amount of XP
        # In the future, this will trigger a story and combat
        xp_gain = random.randint(10, 25)
        
        self.safe_reply(connection, event, f"You embark on a simple quest and gain {xp_gain} XP.")
        
        level_up_message = self._grant_xp(username, xp_gain)
        if level_up_message:
            self.safe_reply(connection, event, level_up_message)
            
        return True
        
    @admin_required
    def _cmd_admin_add_xp(self, connection, event, msg, username, match):
        """Admin command to grant XP to a player."""
        target_user, amount_str = match.groups()
        amount = int(amount_str)
        
        self.safe_reply(connection, event, f"Granted {amount} XP to {target_user}.")
        
        level_up_message = self._grant_xp(target_user, amount)
        if level_up_message:
            self.safe_reply(connection, event, f"{target_user} leveled up! {level_up_message}")
            
        return True
