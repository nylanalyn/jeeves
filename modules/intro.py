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
            self.safe_reply(connection, event, f"Already gave you the rundown, {self.bot.title_for(username)}. This brief is reserved for fresh faces.")
            return True

        intro_lines = [
            "Name's Jeeves. I keep the lights on and the secrets filed in locked cabinets.",
            "Tune the experience with `!gender <identity>` and `!location <city, country>` so I can tailor the briefing.",
            "Need intel? Try `!weather`, `!time`, `!fortune`, or shake down the wires with `!yt <query>`.",
            "If you want the full case file, ask `!help` and I'll slide it across the desk."
        ]
        
        if is_admin:
            for line in intro_lines:
                self.safe_reply(connection, event, line)
        else:
            for line in intro_lines:
                self.safe_privmsg(username, line)
            self.safe_reply(connection, event, f"Check your private line, {self.bot.title_for(username)}—the dossier's waiting there.")

        if not is_admin and user_id not in introduced_users:
            introduced_users.append(user_id)
            self.set_state("users_introduced", introduced_users)
            self.save_state()

        return True
