# modules/intro.py
# A module to provide a one-time introduction for new users.

import re
from typing import Any, List
from .base import SimpleCommandModule, admin_required

def setup(bot: Any) -> 'Intro':
    """Initializes the Intro module."""
    return Intro(bot)

class Intro(SimpleCommandModule):
    """Handles the one-time !intro command."""
    name = "intro"
    version = "3.0.0" # Dynamic configuration refactor
    description = "Provides a one-time introduction for new users."

    def __init__(self, bot: Any) -> None:
        """Initializes the module's state and registers commands."""
        super().__init__(bot)
        self.set_state("users_introduced", self.get_state("users_introduced", [])) # List of user_ids
        self.save_state()

    def _register_commands(self) -> None:
        """Registers the !intro command."""
        self.register_command(
            r"^\s*!intro\s*$", self._cmd_intro,
            name="intro",
            description="Get a brief introduction to my services."
        )

    def _cmd_intro(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        """Handles the !intro command logic."""
        # The is_enabled check is handled by the base class's command dispatcher.
        user_id = self.bot.get_user_id(username)
        introduced_users = self.get_state("users_introduced", [])
        is_admin = self.bot.is_admin(event.source)

        if user_id in introduced_users and not is_admin:
            self.safe_reply(connection, event, f"I believe we've already completed the tour, {self.bot.title_for(username)}. I reserve the formal welcome for newly arrived guests.")
            return True

        intro_lines = [
            f"{self.bot.connection.get_nickname()} at your service—your Wodehouse-grade butler with a polishing cloth in one hand and an eye on the room's wellbeing.",
            "Tune the niceties with `!gender <identity>` and `!location <city, country>` so I may address you properly and keep the atmosphere agreeable.",
            "Need something fetched? Try `!weather`, `!time`, `!fortune`, or allow me to retrieve a clip with `!yt <query>`.",
            "If you want the full service card, ask `!help` and I'll present it neatly folded."
        ]
        
        if is_admin:
            for line in intro_lines:
                self.safe_reply(connection, event, line)
        else:
            for line in intro_lines:
                self.safe_privmsg(username, line)
            self.safe_reply(connection, event, f"You'll find the welcome notes in your private line, {self.bot.title_for(username)}—no need to clutter the drawing room.")

        if not is_admin and user_id not in introduced_users:
            introduced_users.append(user_id)
            self.set_state("users_introduced", introduced_users)
            self.save_state()

        return True
