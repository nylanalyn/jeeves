# modules/users.py
# A module to provide a persistent, canonical identity for users.
import uuid
from .base import SimpleCommandModule, admin_required

def setup(bot):
    """Initializes the Users module."""
    return Users(bot)

class Users(SimpleCommandModule):
    """Handles the mapping of nicknames to persistent user IDs."""
    name = "users"
    version = "2.1.0" # Added flavor text preference
    description = "Provides persistent user identity across nickname changes."

    # This module is a core service and does not require changes for the refactor,
    # as it has no user-facing commands or ambient triggers to be disabled.
    # It will always be active to ensure user identity is tracked correctly.

    def __init__(self, bot):
        """Initializes the module's state."""
        super().__init__(bot)
        self.set_state("user_map", self.get_state("user_map", {})) # Maps UUID -> user object
        self.set_state("nick_map", self.get_state("nick_map", {})) # Maps lower_nick -> UUID
        self.save_state()

    def _register_commands(self):
        """Register user preference commands."""
        self.register_command(r"^\s*!flavor\s+(on|off)$", self._cmd_flavor, name="flavor", description="Toggle flavor text on/off")

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

        # Check if the new nickname is already mapped to a DIFFERENT user
        existing_user_id = nick_map.get(lower_new)
        if existing_user_id and existing_user_id != user_id:
            # Don't overwrite someone else's nickname mapping
            self.log_debug(f"Nick change blocked: {old_nick} -> {new_nick}. '{new_nick}' already belongs to user {existing_user_id}")
            # Still add it to this user's seen_nicks, but don't update the mapping
            user_map = self.get_state("user_map", {})
            user_profile = user_map.get(user_id)
            if user_profile:
                if lower_new not in user_profile["seen_nicks"]:
                    user_profile["seen_nicks"].append(lower_new)
                user_map[user_id] = user_profile
                self.set_state("user_map", user_map)
                self.save_state()
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

    def _cmd_flavor(self, connection, event, msg, username, match):
        """Toggle flavor text preference for a user."""
        setting = match.group(1).lower()
        user_id = self.get_user_id(username)

        user_map = self.get_state("user_map", {})
        user_profile = user_map.get(user_id, {})

        user_profile["flavor_enabled"] = (setting == "on")
        user_map[user_id] = user_profile
        self.set_state("user_map", user_map)
        self.save_state()

        if setting == "on":
            self.safe_reply(connection, event, f"Very good, {self.bot.title_for(username)}. Flavor text has been re-enabled.")
        else:
            self.safe_reply(connection, event, "Flavor text disabled. Responses will be concise.")
        return True

    def get_user_nick(self, user_id: str) -> str:
        """Get the canonical nickname for a user ID."""
        user_map = self.get_state("user_map", {})
        profile = user_map.get(user_id)
        if profile:
            if profile.get("canonical_nick"):
                return profile["canonical_nick"]
            seen = profile.get("seen_nicks", [])
            if seen:
                return seen[-1]
        return user_id

    def has_flavor_enabled(self, username: str) -> bool:
        """Check if a user has flavor text enabled (default: True)."""
        user_id = self.get_user_id(username)
        user_map = self.get_state("user_map", {})
        user_profile = user_map.get(user_id, {})
        return user_profile.get("flavor_enabled", True)
