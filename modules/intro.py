# modules/intro.py
# A module to provide a one-time introduction for new users.

from .base import SimpleCommandModule, admin_required

def setup(bot, config):
    """Initializes the Intro module."""
    return Intro(bot, config)

class Intro(SimpleCommandModule):
    """Handles the one-time !intro command."""
    name = "intro"
    version = "2.0.0" # UUID Refactor
    description = "Provides a one-time introduction for new users."

    def __init__(self, bot, config):
        """Initializes the module's state and registers commands."""
        super().__init__(bot)
        self.set_state("users_introduced", self.get_state("users_introduced", [])) # List of user_ids
        self.save_state()

    def _register_commands(self):
        """Registers the !intro command."""
        self.register_command(
            r"^\s*!intro\s*$", self._cmd_intro, 
            name="intro", 
            description="Get a brief introduction to my services."
        )

    def _cmd_intro(self, connection, event, msg, username, match):
        """Handles the !intro command logic."""
        user_id = self.bot.get_user_id(username)
        introduced_users = self.get_state("users_introduced", [])
        is_admin = self.bot.is_admin(event.source)

        if user_id in introduced_users and not is_admin:
            self.safe_reply(connection, event, f"My apologies, {self.bot.title_for(username)}, but the introduction is for newcomers.")
            return True

        intro_lines = [
            "Greetings. I am Jeeves, the household's dutiful butler.",
            "My services are enhanced if you set your preferences with `!gender <identity>` and `!location <city, country>`.",
            "Common services include: `!weather`, `!time`, `!fortune`, and `!yt <query>`.",
            "For a full list of my capabilities, please use the `!help` command."
        ]
        
        if is_admin:
            for line in intro_lines:
                self.safe_reply(connection, event, line)
        else:
            for line in intro_lines:
                self.safe_privmsg(username, line)
            self.safe_reply(connection, event, f"{self.bot.title_for(username)}, I have sent you my introduction privately.")

        if not is_admin and user_id not in introduced_users:
            introduced_users.append(user_id)
            self.set_state("users_introduced", introduced_users)
            self.save_state()

        return True

