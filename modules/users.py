# modules/users.py
# A module to provide a persistent, canonical identity for users.
import uuid
from .base import SimpleCommandModule, admin_required

def setup(bot, config):
    """Initializes the Users module."""
    return Users(bot, config)

class Users(SimpleCommandModule):
    """Handles the mapping of nicknames to persistent user IDs."""
    name = "users"
    version = "2.0.0" # Dynamic configuration refactor
    description = "Provides persistent user identity across nickname changes."

    # This module is a core service and does not require changes for the refactor,
    # as it has no user-facing commands or ambient triggers to be disabled.
    # It will always be active to ensure user identity is tracked correctly.

    def __init__(self, bot, config):
        """Initializes the module's state."""
        super().__init__(bot)
        self.set_state("user_map", self.get_state("user_map", {})) # Maps UUID -> user object
        self.set_state("nick_map", self.get_state("nick_map", {})) # Maps lower_nick -> UUID
        self.save_state()

    def _register_commands(self):
        """This module has no user-facing commands."""
        pass

    def get_user_id(self, nick: str) -> str:
        """
        Gets the persistent UUID for a nickname.
        Creates a new user profile if the nick has never been seen before.
        """
        lower_nick = nick.lower()
        nick_map = self.get_state("nick_map", {})

        if lower_nick in nick_map:
            return nick_map[lower_nick]

        # New user detected
        user_id = str(uuid.uuid4())
        user_map = self.get_state("user_map", {})
        
        user_map[user_id] = {
            "id": user_id,
            "canonical_nick": nick,
            "seen_nicks": [lower_nick],
            "first_seen": self.bot.get_utc_time()
        }
        nick_map[lower_nick] = user_id

        self.set_state("user_map", user_map)
        self.set_state("nick_map", nick_map)
        self.save_state()
        
        return user_id

    def on_nick(self, connection, event, old_nick: str, new_nick: str):
        """Handles a user changing their nickname."""
        lower_old = old_nick.lower()
        lower_new = new_nick.lower()

        nick_map = self.get_state("nick_map", {})
        user_id = nick_map.get(lower_old)

        if not user_id:
            # If we didn't know the old nick, treat the new one as a new user.
            self.get_user_id(new_nick)
            return

        # Link the new nick to the existing user ID
        nick_map[lower_new] = user_id
        
        user_map = self.get_state("user_map", {})
        user_profile = user_map.get(user_id)
        if user_profile:
            user_profile["canonical_nick"] = new_nick # Update their "main" name
            if lower_new not in user_profile["seen_nicks"]:
                user_profile["seen_nicks"].append(lower_new)
            user_map[user_id] = user_profile
            self.set_state("user_map", user_map)

        self.set_state("nick_map", nick_map)
        self.save_state()
