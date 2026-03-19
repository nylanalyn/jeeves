# modules/dead.py
# A module for reassuring everyone that things are fine
import random
import re
from typing import Any, List
from .base import SimpleCommandModule

def setup(bot: Any) -> 'Dead':
    return Dead(bot)

class Dead(SimpleCommandModule):
    name = "dead"
    version = "1.0.0"
    description = "Reassures everyone that things are completely under control."

    REASSURANCES: List[str] = [
        "Don't panic.",
        "Everything is under control.",
        "We are safe.",
        "Nothing to worry about. Absolutely nothing.",
        "This is fine.",
        "All systems nominal.",
        "Situation under control. Resume normal activities.",
        "There is no cause for alarm.",
        "Please remain calm. Everything is fine.",
        "We are totally in control of the situation.",
        "Stand by. All is well.",
        "No reason to panic. None whatsoever.",
        "Do not adjust your set. This is not a test.",
        "Everything is proceeding exactly as planned.",
        "We have the situation well in hand.",
    ]

    def _register_commands(self) -> None:
        self.register_command(
            r"^\s*!dead\s*$",
            self._cmd_dead,
            name="dead",
            cooldown=5.0,
            description="Reassures everyone that everything is fine."
        )

    def _cmd_dead(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        self.safe_reply(connection, event, random.choice(self.REASSURANCES))
        return True
