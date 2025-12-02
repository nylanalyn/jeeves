# modules/quotes.py
# A module to randomly remember things people say and recall them later.
import re
import random
from datetime import datetime, timezone
from typing import Any
from .base import SimpleCommandModule

UTC = timezone.utc

def setup(bot: Any) -> 'Quotes':
    """Initializes the Quotes module."""
    return Quotes(bot)

class Quotes(SimpleCommandModule):
    """Randomly stores things people say and recalls them on demand."""
    name = "quotes"
    version = "1.0.0"
    description = "Remembers random things people say in the channel."

    def __init__(self, bot: Any) -> None:
        """Initializes the module's state."""
        super().__init__(bot)
        # State structure: { "quotes": [ { "message": str, "nick": str, "timestamp": ISO_STRING }, ... ] }
        self.set_state("quotes", self.get_state("quotes", []))
        self.save_state()

    def _register_commands(self) -> None:
        """Registers the !quote command."""
        self.register_command(r"^\s*!quote\s*$", self._cmd_quote,
                              name="quote", description="Recalls a random thing someone once said.")

    def _get_config(self, key: str, default: Any) -> Any:
        """Helper to get module config with defaults."""
        return self.bot.config.get(self.name, {}).get(key, default)

    def on_ambient_message(self, connection, event, msg: str, username: str) -> bool:
        """Randomly stores messages for later recall."""
        if not self.is_enabled(event.target):
            return False

        # Skip commands
        if msg.startswith('!') or re.match(r"^\s*s/", msg):
            return False

        # Skip bot's own messages
        if username.lower() == connection.get_nickname().lower():
            return False

        # Check minimum message length
        min_length = self._get_config("min_message_length", 3)
        if len(msg) < min_length:
            return False

        # Random chance to save this quote
        save_chance = self._get_config("save_chance", 0.005)  # 1 in 200 by default
        if random.random() > save_chance:
            return False

        # Save the quote
        quotes = self.get_state("quotes", [])
        quotes.append({
            "message": msg,
            "nick": username,
            "timestamp": datetime.now(UTC).isoformat()
        })

        self.set_state("quotes", quotes)
        self.save_state()
        self.log_debug(f"Saved quote from {username}: {msg[:50]}...")

        return False  # Don't stop other ambient handlers

    def _format_date(self, dt_obj: datetime) -> str:
        """Formats a date in a proper, Jeeves-like manner."""
        day = dt_obj.day
        # Add ordinal suffix (1st, 2nd, 3rd, 4th, etc.)
        if 10 <= day % 100 <= 20:
            suffix = "th"
        else:
            suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")

        month = dt_obj.strftime("%B")  # Full month name
        year = dt_obj.year

        return f"the {day}{suffix} of {month}, {year}"

    def _cmd_quote(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        """Handles the !quote command - recalls a random stored quote."""
        quotes = self.get_state("quotes", [])

        if not quotes:
            self.safe_reply(connection, event, f"My apologies, {self.bot.title_for(username)}, but I have not yet committed any remarks to memory.")
            return True

        # Select a random quote
        quote = random.choice(quotes)

        try:
            when_dt = datetime.fromisoformat(quote["timestamp"])
            date_str = self._format_date(when_dt)

            self.safe_reply(connection, event,
                f"Of course, {self.bot.title_for(username)}, do you remember on {date_str} {quote['nick']} said: \"{quote['message']}\"")
        except (ValueError, KeyError) as e:
            self.log_debug(f"Error formatting quote: {e}")
            self.safe_reply(connection, event, f"I seem to have a corrupted memory, {self.bot.title_for(username)}.")

        return True
