# modules/turtle.py
# A simple command that displays random turtle activities
import random
import re
from typing import Any
from .base import SimpleCommandModule

def setup(bot: Any) -> 'Turtle':
    return Turtle(bot)

class Turtle(SimpleCommandModule):
    name = "turtle"
    version = "1.0.0"
    description = "Displays random silly turtle activities."

    TURTLE_ACTIVITIES = [
        "eating fish",
        "vibing",
        "committing tax fraud",
        "swimming peacefully",
        "napping on a rock",
        "judging you silently",
        "filing bankruptcy",
        "overthinking everything",
        "questioning existence",
        "doing yoga",
        "hacking the mainframe",
        "contemplating lettuce",
        "speedrunning life",
        "playing chess",
        "writing poetry",
        "investing in crypto",
        "avoiding responsibilities",
        "practicing meditation",
        "plotting world domination",
        "reading philosophy",
        "eating pizza",
        "doing taxes (incorrectly)",
        "learning quantum physics",
        "starting a podcast",
        "becoming sentient",
        "challenging the gods",
        "discovering fire",
        "inventing the wheel",
        "time traveling",
        "breakdancing",
    ]

    def __init__(self, bot: Any) -> None:
        super().__init__(bot)

    def _register_commands(self) -> None:
        self.register_command(r"^\s*!turtle\s*$", self._cmd_turtle,
                              name="turtle", description="Show what the turtle is doing.")

    def _cmd_turtle(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        activity = random.choice(self.TURTLE_ACTIVITIES)
        self.safe_reply(connection, event, f"🐢 Turtle {activity}")
        return True
