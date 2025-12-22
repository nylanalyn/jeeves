# modules/scare.py
# A module that tells short spooky horror stories
import random
import re
from typing import Any, List
from .base import SimpleCommandModule
from . import achievement_hooks

def setup(bot: Any) -> 'Scare':
    return Scare(bot)

class Scare(SimpleCommandModule):
    name = "scare"
    version = "1.0.0"
    description = "Tells short spooky horror stories to give you a fright."

    SPOOKY_STORIES: List[str] = [
        "You hear a child's laughter echo through your empty house at 3 AM. You live alone, and you have no children.",

        "Every night, you lock all the doors and windows before bed. Every morning, you wake to find one window open, and muddy footprints leading to your bedside.",

        "You finally answer the phone that's been ringing for hours. A voice identical to yours says 'Let me in.' You hear scratching at your front door.",

        "The old photograph shows your family gathering from 1952. But there, in the background behind grandmother, is you - wearing the clothes you have on right now.",

        "You've been home alone all evening when you hear footsteps upstairs. Then you remember: you don't have an upstairs.",

        "The thing that's been living in your walls has learned to mimic your voice perfectly. Your family can't tell which one of you is real anymore.",

        "You wake to find your bedroom door wide open. You always sleep with it closed, and the lock can only be opened from the inside.",

        "For weeks, you've been finding notes in your own handwriting warning you to leave. You don't remember writing any of them.",
    ]

    def _register_commands(self) -> None:
        self.register_command(
            r"^\s*!scare\s*$",
            self._cmd_scare,
            name="scare",
            cooldown=30.0,
            description="Hear a frightening tale, if you dare."
        )

    def _cmd_scare(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        story = random.choice(self.SPOOKY_STORIES)
        self.safe_reply(connection, event, f"{self.bot.title_for(username)}, steel yourself... {story}")
        achievement_hooks.record_scare(self.bot, username)
        return True
