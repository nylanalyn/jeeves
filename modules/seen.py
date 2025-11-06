# modules/seen.py
# A module to track user activity and provide a !seen command.
import re
from datetime import datetime, timezone
from typing import Any
from .base import SimpleCommandModule

UTC = timezone.utc

def setup(bot: Any) -> 'Seen':
    """Initializes the Seen module."""
    return Seen(bot)

class Seen(SimpleCommandModule):
    """Handles tracking and reporting the last time a user was seen speaking."""
    name = "seen"
    version = "1.0.0"
    description = "Tracks user activity to report when they were last seen."

    def __init__(self, bot: Any) -> None:
        """Initializes the module's state."""
        super().__init__(bot)
        # State structure: { "#channel": { "user_id": { "when": ISO_STRING, "message": "text" } } }
        self.set_state("last_seen", self.get_state("last_seen", {}))
        self.save_state()

    def _register_commands(self) -> None:
        """Registers the !seen command."""
        self.register_command(r"^\s*!seen\s+(\S+)\s*$", self._cmd_seen,
                              name="seen", description="Reports when a user was last seen speaking in this channel.")

    def on_ambient_message(self, connection, event, msg: str, username: str) -> bool:
        """Records the last message from a user in a channel."""
        if not self.is_enabled(event.target):
            return False
            
        # Do not track commands
        if msg.startswith('!') or re.match(r"^\s*s/", msg):
            return False

        user_id = self.bot.get_user_id(username)
        channel = event.target
        
        last_seen_data = self.get_state("last_seen", {})
        channel_data = last_seen_data.setdefault(channel, {})
        
        channel_data[user_id] = {
            "when": datetime.now(UTC).isoformat(),
            "message": msg
        }
        
        self.set_state("last_seen", last_seen_data)
        self.save_state()
        return False # This module should not stop other ambient handlers

    def _format_timedelta(self, dt_obj: datetime) -> str:
        """Formats the time difference into a human-readable string."""
        delta = datetime.now(UTC) - dt_obj
        seconds = int(delta.total_seconds())
        
        if seconds < 60:
            return f"{seconds} second{'s' if seconds != 1 else ''} ago"
        minutes, seconds = divmod(seconds, 60)
        if minutes < 60:
            return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
        hours, minutes = divmod(minutes, 60)
        if hours < 24:
            return f"{hours} hour{'s' if hours != 1 else ''} ago"
        days, hours = divmod(hours, 24)
        return f"{days} day{'s' if days != 1 else ''} ago"

    def _cmd_seen(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        """Handles the !seen command."""
        target_user_nick = match.group(1)
        target_user_id = self.bot.get_user_id(target_user_nick)
        channel = event.target

        last_seen_data = self.get_state("last_seen", {}).get(channel, {})
        user_data = last_seen_data.get(target_user_id)

        if not user_data:
            self.safe_reply(connection, event, f"My apologies, {self.bot.title_for(username)}, but I have not seen {target_user_nick} speak in this channel.")
            return True

        try:
            when_dt = datetime.fromisoformat(user_data["when"])
            time_ago = self._format_timedelta(when_dt)
            last_message = user_data["message"]

            self.safe_reply(connection, event, f"{self.bot.title_for(username)}, I last saw {target_user_nick} here {time_ago}, saying: \"{last_message}\"")
        except (ValueError, KeyError):
            self.safe_reply(connection, event, f"I seem to have faulty records for {target_user_nick}.")

        return True
