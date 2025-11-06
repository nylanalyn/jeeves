"""
Ambient response module.
Occasionally responds to certain phrases with emoji.
"""

import random
import re
from typing import Any, List, Pattern
from .base import ModuleBase


def setup(bot: Any) -> 'AmbientModule':
    """Module setup function."""
    return AmbientModule(bot)


class AmbientModule(ModuleBase):
    """Provides ambient responses to certain phrases."""

    name = "ambient"
    version = "1.0.0"
    description = "Occasionally responds to certain phrases"

    def __init__(self, bot: Any) -> None:
        super().__init__(bot)

        # Compile patterns for common dog whistles
        self.patterns: List[Pattern[str]] = [
            re.compile(r'\b(states?\s+rights?)\b', re.IGNORECASE),
            re.compile(r'\b(cultural\s+marxis[mt])\b', re.IGNORECASE),
            re.compile(r'\b(virtue\s+signal(?:ing|s)?)\b', re.IGNORECASE),
            re.compile(r'\b(globalist[s]?)\b', re.IGNORECASE),
            re.compile(r'\b(urban\s+(?:crime|violence|thugs?))\b', re.IGNORECASE),
            re.compile(r'\b(inner\s+cit(?:y|ies))\b', re.IGNORECASE),
            re.compile(r'\b(welfare\s+queen[s]?)\b', re.IGNORECASE),
            re.compile(r'\b(great\s+replacement)\b', re.IGNORECASE),
            re.compile(r'\b(western\s+(?:civilization|culture|values))\b', re.IGNORECASE),
            re.compile(r'\b(traditional\s+values)\b', re.IGNORECASE),
            re.compile(r'\b(judeo-christian)\b', re.IGNORECASE),
            re.compile(r'\b(identity\s+politics)\b', re.IGNORECASE),
            re.compile(r'\b(low\s+information\s+voter[s]?)\b', re.IGNORECASE),
            re.compile(r'\b(thugs?)\b', re.IGNORECASE),
            re.compile(r'\b(law\s+and\s+order)\b', re.IGNORECASE),
            re.compile(r'\b(silent\s+majority)\b', re.IGNORECASE),
            re.compile(r'\b(real\s+americ(?:a|ans?))\b', re.IGNORECASE),
            re.compile(r'\b(heritage\s+not\s+hate)\b', re.IGNORECASE),
            re.compile(r'\b(economic\s+anxiety)\b', re.IGNORECASE),
            re.compile(r'\b(woke\s+(?:mob|agenda|culture))\b', re.IGNORECASE),
        ]

    def on_ambient_message(self, connection: Any, event: Any, msg: str, username: str) -> bool:
        """Check messages for dog whistle patterns."""
        if not self.is_enabled(event.target):
            return False

        # Check if any pattern matches
        for pattern in self.patterns:
            if pattern.search(msg):
                # Only respond occasionally (default 15% of the time)
                response_rate = self.get_config_value('response_rate', event.target, 0.15)
                if random.random() < response_rate:
                    # Dog head + whistle emoji
                    self.safe_reply(connection, event, "🐕💨")
                    return True
                break

        return False
