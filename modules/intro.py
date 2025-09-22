# modules/intro.py
# A module to provide a one-time introduction for new users.

from .base import SimpleCommandModule, admin_required

def setup(bot, config):
    """Initializes the Intro module."""
    return Intro(bot, config)

class Intro(SimpleCommandModule):
    """Handles the one-time !intro command."""
    name = "intro"
    version = "1.1.0"
    description = "Provides a one-time introduction for new users."

    def __init__(self, bot, config):
        """Initializes the module's state and registers commands."""
        super().__init__(bot)
        self.set_state("users_introduced", self.get_state("users_introduced", []))
        self.save_state()
        self._register_commands()

    def _register_commands(self):
        """Registers the !intro command."""
        self.register_command(
            r"^\s*!intro\s*$", self._cmd_intro, 
            name="intro", 
            description="Get a brief introduction to my services."
        )

    def _cmd_intro(self, connection, event, msg, username, match):
        """Handles the !intro command logic."""
        introduced_users = self.get_state("users_introduced", [])
        username_lower = username.lower()
        is_admin = self.bot.is_admin(event.source)

        if username_lower in introduced_users and not is_admin:
            self.safe_reply(connection, event, f"My apologies, {self.bot.title_for(username)}, but the introduction is intended for newcomers.")
            return True

        intro_lines = [
            "Greetings. I am Jeeves, the household's dutiful butler.",
            "My services are enhanced if you set your preferences with `!gender <identity>` and `!location <city, country>`.",
            "Common services include: `!weather`, `!time`, `!fortune`, and `!yt <query>`.",
            "For a full list of my capabilities, please use the `!help` command."
        ]
        
        if is_admin:
            # For admins, post publicly in the channel for demonstration.
            for line in intro_lines:
                self.safe_reply(connection, event, line)
        else:
            # For regular users, send the message privately.
            for line in intro_lines:
                self.safe_privmsg(username, line)
            # And send a confirmation to the channel.
            self.safe_reply(connection, event, f"{self.bot.title_for(username)}, I have sent you my introduction privately.")

        # Update state for non-admins to prevent reuse.
        if not is_admin and username_lower not in introduced_users:
            introduced_users.append(username_lower)
            self.set_state("users_introduced", introduced_users)
            self.save_state()

        return True

