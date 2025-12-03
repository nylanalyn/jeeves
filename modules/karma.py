# modules/karma.py
# A module to track user karma through ++ and -- voting
import re
import time
from typing import Any, Dict, Optional
from .base import SimpleCommandModule


def setup(bot: Any) -> 'Karma':
    """Initializes the Karma module."""
    return Karma(bot)


class Karma(SimpleCommandModule):
    """Tracks karma for users through ++ and -- voting."""
    name = "karma"
    version = "1.0.0"
    description = "Track user karma through ++ and -- voting"

    def __init__(self, bot: Any) -> None:
        """Initialize the module's state."""
        super().__init__(bot)

        # State structure:
        # karma_scores: {user_id: int}
        # cooldowns: {giver_id: {receiver_id: timestamp}}
        self.set_state("karma_scores", self.get_state("karma_scores", {}))
        self.set_state("cooldowns", self.get_state("cooldowns", {}))
        self.save_state()

    def _register_commands(self) -> None:
        """Register karma commands."""
        self.register_command(
            r"^\s*!karma(?:\s+(\S+))?\s*$",
            self._cmd_karma,
            name="karma",
            description="Check karma score for yourself or another user"
        )

    def on_ambient_message(self, connection: Any, event: Any, msg: str, username: str) -> bool:
        """Listen for karma modifications in channel messages."""
        if not self.is_enabled(event.target):
            return False

        # Look for karma patterns: username++ or username--
        # Pattern: word characters followed by ++ or --
        karma_pattern = r'\b(\w+)(\+\+|--)'

        for match in re.finditer(karma_pattern, msg):
            target_nick = match.group(1)
            operation = match.group(2)

            # Don't allow users to karma themselves
            if target_nick.lower() == username.lower():
                continue

            # Process the karma change
            if operation == "++":
                self._modify_karma(username, target_nick, 1)
            elif operation == "--":
                self._modify_karma(username, target_nick, -1)

        # Allow other ambient handlers to process the message
        return False

    def _modify_karma(self, giver_nick: str, receiver_nick: str, amount: int) -> bool:
        """
        Modify karma for a user.

        Args:
            giver_nick: Nickname of person giving karma
            receiver_nick: Nickname of person receiving karma
            amount: +1 or -1

        Returns:
            True if karma was modified, False if on cooldown or other issue
        """
        # Get user IDs
        giver_id = self.bot.get_user_id(giver_nick)
        receiver_id = self.bot.get_user_id(receiver_nick)

        # Check cooldown (5 minutes per person-to-person)
        cooldown_seconds = 300  # 5 minutes
        now = time.time()

        cooldowns = self.get_state("cooldowns", {})

        if giver_id not in cooldowns:
            cooldowns[giver_id] = {}

        last_karma_time = cooldowns[giver_id].get(receiver_id, 0)

        if now - last_karma_time < cooldown_seconds:
            # Still on cooldown, ignore silently
            return False

        # Update cooldown
        cooldowns[giver_id][receiver_id] = now
        self.set_state("cooldowns", cooldowns)

        # Update karma
        karma_scores = self.get_state("karma_scores", {})
        current_karma = karma_scores.get(receiver_id, 0)
        karma_scores[receiver_id] = current_karma + amount
        self.set_state("karma_scores", karma_scores)

        self.save_state()

        self.log_debug(f"Karma: {giver_nick} gave {amount} to {receiver_nick} (new total: {karma_scores[receiver_id]})")

        return True

    def _cmd_karma(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        """Show karma score for a user."""
        target_nick = match.group(1)

        if target_nick:
            # Show karma for specified user
            # Try to get their user ID
            # First check if this nick is known
            target_id = None

            # Try to find the user ID from nick_map
            users_module = self.bot.modules.get("users")
            if users_module:
                nick_map = users_module.get_state("nick_map", {})
                target_id = nick_map.get(target_nick.lower())

            if not target_id:
                # Unknown user
                self.safe_reply(
                    connection, event,
                    f"I haven't seen {target_nick} before. Karma: 0"
                )
                return True

            # Get their canonical nick from user_map
            display_nick = target_nick
            if users_module:
                user_map = users_module.get_state("user_map", {})
                user_profile = user_map.get(target_id)
                if user_profile:
                    display_nick = user_profile.get("canonical_nick", target_nick)

        else:
            # Show karma for requesting user
            target_id = self.bot.get_user_id(username)
            display_nick = username

        # Get karma score
        karma_scores = self.get_state("karma_scores", {})
        karma = karma_scores.get(target_id, 0)

        self.safe_reply(
            connection, event,
            f"{display_nick}'s karma: {karma}"
        )

        return True
