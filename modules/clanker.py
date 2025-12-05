"""
Clanker keyword responder.

Posts a Sonic reaction clip whenever someone mentions "clanker".
"""

import re
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

    def on_ambient_message(self, connection: Any, event: Any, msg: str, username: str) -> bool:
        if not self.is_enabled(event.target):
            return False

        if self._pattern.search(msg):
            self.safe_reply(connection, event, self._response_url)
            return True
        return False
