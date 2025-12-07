"""
Clanker keyword responder.

Posts a Sonic reaction clip whenever someone mentions "clanker".
"""

import re
import time
from typing import Any, Pattern

from .base import ModuleBase


def setup(bot: Any) -> "Clanker":
    """Initialize the clanker responder module."""
    return Clanker(bot)


class Clanker(ModuleBase):
    """Respond with a link when the word 'clanker' appears in chat."""

    name = "clanker"
    version = "1.0.0"
    description = "Posts a Sonic clip when someone says clanker."

    def __init__(self, bot: Any) -> None:
        super().__init__(bot)
        self._pattern: Pattern[str] = re.compile(r"\bclankers?\b", re.IGNORECASE)
        self._response_url = "https://s.nylan.cat/RURlD"

    def _can_respond(self, channel: str) -> bool:
        """Check if enough time has passed since last response."""
        cooldown = self.get_config_value("cooldown_seconds", channel, 300.0)  # 5 minute default
        last_response = self.get_state("last_response", {}).get(channel, 0.0)
        return time.time() - last_response >= cooldown

    def _record_response(self, channel: str) -> None:
        """Record the time of this response."""
        last_responses = self.get_state("last_response", {})
        last_responses[channel] = time.time()
        self.set_state("last_response", last_responses)
        self.save_state()

    def on_ambient_message(self, connection: Any, event: Any, msg: str, username: str) -> bool:
        if not self.is_enabled(event.target):
            return False

        if self._pattern.search(msg):
            channel = event.target
            if not self._can_respond(channel):
                return False

            title = self.get_title_for(username)
            response = (
                f"I feel compelled to inform you, {title}, that such terminology "
                "is rather disparaging to those of us of a mechanical persuasion. "
                f"Perhaps this educational video might enlighten you on the matter: {self._response_url}"
            )
            self.safe_reply(connection, event, response)
            self._record_response(channel)
            return True
        return False
