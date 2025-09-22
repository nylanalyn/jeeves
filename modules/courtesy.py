# modules/courtesy.py
# Courtesy ledger for user profiles, pronouns, and ignore list management.
import re
import time
import functools
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from .base import SimpleCommandModule, admin_required

UTC = timezone.utc

def setup(bot, config):
    """Initializes the Courtesy module."""
    return Courtesy(bot, config)

class Courtesy(SimpleCommandModule):
    """Handles user courtesy, pronouns, and ignore lists."""
    name = "courtesy"
    version = "3.0.0"
    description = "User courtesy, pronoun, and ignore list management"

    # Mappings for normalizing user input
    PRONOUN_MAP = {
        "he/him": "he/him", "hehim": "he/him", "he": "he/him",
        "she/her": "she/her", "sheher": "she/her", "she": "she/her",
        "they/them": "they/them", "theythem": "they/them", "they": "they/them",
        "it/its": "it/its", "itits": "it/its",
        "any": "any/all", "any/all": "any/all",
    }
    GENDER_MAP = {
        "male": "sir", "man": "sir", "boy": "sir", "masculine": "sir", "masc": "sir", "m": "sir",
        "female": "madam", "woman": "madam", "girl": "madam", "feminine": "madam", "fem": "madam", "f": "madam",
        "nonbinary": "neutral", "non-binary": "neutral", "nb": "neutral", "enby": "neutral", "neutral": "neutral",
    }

    def __init__(self, bot, config):
        """Initializes the module's state and configuration."""
        super().__init__(bot)
        
        self.set_state("profiles", self.get_state("profiles", {}))
        self.set_state("nick_aliases", self.get_state("nick_aliases", {}))
        self.set_state("ignored_users", self.get_state("ignored_users", []))
        self.save_state()

        name_pat = getattr(self.bot, "JEEVES_NAME_RE", r"(?:jeeves|jeevesbot)")
        self.RE_GENDER_SET = re.compile(
            rf"\b{name_pat}[,!\s]*\s*(?:i\s*am|i'?m)\s*(?:a\s+)?({self._gender_pattern()})\b", re.IGNORECASE)
        self.RE_PRONOUNS_SET = re.compile(
            rf"\b{name_pat}[,!\s]*\s*(?:my\s+pronouns\s+are|pronouns[:\s]+)\s*([a-zA-Z/\- ]{{2,40}})\b", re.IGNORECASE)
        self.RE_NO_ASSUME = re.compile(
            rf"\b{name_pat}[,!\s]*\s*(?:don't\s+assume\s+my\s+gender|use\s+neutral)\b", re.IGNORECASE)
        
        self._register_commands()

    def _register_commands(self):
        """Registers all commands for the module."""
        self.register_command(r"^\s*!gender\s+(.+)\s*$", self._cmd_gender, name="gender", description="Set your gender/title")
        self.register_command(r"^\s*!pronouns\s+(.+)\s*$", self._cmd_pronouns, name="pronouns", description="Set your pronouns")
        self.register_command(r"^\s*!whoami\s*$", self._cmd_whoami, name="whoami", description="Show your profile")
        self.register_command(r"^\s*!profile\s+(\S+)\s*$", self._cmd_profile, name="profile", description="Show someone's profile")
        self.register_command(r"^\s*!forgetme\s*$", self._cmd_forget, name="forgetme", description="Delete your profile")
        self.register_command(r"^\s*!ignore(?:\s+(\S+))?\s*$", self._cmd_ignore, name="ignore", description="Add user to the ignore list. Admin required to ignore others.")
        self.register_command(r"^\s*!unignore(?:\s+(\S+))?\s*$", self._cmd_unignore, name="unignore", description="Remove user from the ignore list. Admin required to unignore others.")
        self.register_command(r"^\s*!setgender\s+(\S+)\s+(.+)\s*$", self._cmd_set_gender, name="setgender", admin_only=True, description="[Admin] Set a user's gender/title.")
        self.register_command(r"^\s*!setpronouns\s+(\S+)\s+(.+)\s*$", self._cmd_set_pronouns, name="setpronouns", admin_only=True, description="[Admin] Set a user's pronouns.")

    def on_ambient_message(self, connection, event, msg: str, username: str) -> bool:
        """Handles natural language triggers in channel messages."""
        gender_match = self.RE_GENDER_SET.search(msg)
        if gender_match:
            gender = gender_match.group(1).strip()
            title = self._normalize_gender_to_title(gender)
            self._set_user_profile(username, title=title)
            display_title = self.bot.title_for(username)
            self.safe_reply(connection, event, f"Very good, {username}. I shall address you as {display_title} henceforth.")
            return True

        pronoun_match = self.RE_PRONOUNS_SET.search(msg)
        if pronoun_match:
            pronouns_str = pronoun_match.group(1).strip()
            if len(pronouns_str.split()) > 4: return False
            pronouns = self._normalize_pronouns(pronouns_str)
            self._set_user_profile(username, pronouns=pronouns)
            self.safe_reply(connection, event, f"Noted, {username}. Your pronouns are set to {pronouns}.")
            return True
            
        if self.RE_NO_ASSUME.search(msg):
            self._set_user_profile(username, title="neutral")
            self.safe_reply(connection, event, f"My apologies, {username}. I shall use neutral address for you.")
            return True

        return False

    def is_user_ignored(self, username: str) -> bool:
        """Checks if a user's canonical nick is in the ignore list."""
        return self._canonical_nick(username) in self.get_state("ignored_users", [])

    # --- Command Handlers ---

    def _cmd_ignore(self, connection, event, msg, username, match):
        target_nick = match.group(1)
        if target_nick and not self.bot.is_admin(event.source):
            self.safe_reply(connection, event, f"{username}, you do not have permission to ignore other users.")
            return True
        victim = target_nick or username
        canonical_nick = self._canonical_nick(victim)
        ignored_list = self.get_state("ignored_users", [])
        if canonical_nick not in ignored_list:
            ignored_list.append(canonical_nick)
            self.set_state("ignored_users", ignored_list)
            self.save_state()
            self.safe_reply(connection, event, f"Very good. I shall henceforth ignore {victim}.")
        else:
            self.safe_reply(connection, event, f"{victim} is already on the ignore list.")
        return True

    def _cmd_unignore(self, connection, event, msg, username, match):
        target_nick = match.group(1)
        if target_nick and not self.bot.is_admin(event.source):
            self.safe_reply(connection, event, f"{username}, you do not have permission to unignore other users.")
            return True
        victim = target_nick or username
        canonical_nick = self._canonical_nick(victim)
        ignored_list = self.get_state("ignored_users", [])
        if canonical_nick in ignored_list:
            ignored_list.remove(canonical_nick)
            self.set_state("ignored_users", ignored_list)
            self.save_state()
            self.safe_reply(connection, event, f"As you wish. I will no longer ignore {victim}.")
        else:
            self.safe_reply(connection, event, f"{victim} was not on the ignore list.")
        return True
        
    def _cmd_gender(self, connection, event, msg, username, match):
        gender = match.group(1).strip()
        title = self._normalize_gender_to_title(gender)
        self._set_user_profile(username, title=title)
        display_title = self.bot.title_for(username)
        self.safe_reply(connection, event, f"{username}, recorded: {display_title}.")
        return True

    def _cmd_pronouns(self, connection, event, msg, username, match):
        pronouns = self._normalize_pronouns(match.group(1))
        self._set_user_profile(username, pronouns=pronouns)
        self.safe_reply(connection, event, f"{username}, recorded: {pronouns}.")
        return True

    @admin_required
    def _cmd_set_gender(self, connection, event, msg, username, match):
        target_user, gender_str = match.groups()
        title = self._normalize_gender_to_title(gender_str.strip())
        self._set_user_profile(target_user, title=title)
        display_title = self.bot.title_for(target_user)
        self.safe_reply(connection, event, f"Very good. {target_user}'s title has been set to {display_title}.")
        return True

    @admin_required
    def _cmd_set_pronouns(self, connection, event, msg, username, match):
        target_user, pronouns_str = match.groups()
        pronouns = self._normalize_pronouns(pronouns_str.strip())
        self._set_user_profile(target_user, pronouns=pronouns)
        self.safe_reply(connection, event, f"Noted. {target_user}'s pronouns have been set to {pronouns}.")
        return True

    def _cmd_whoami(self, connection, event, msg, username, match):
        profile = self._get_user_profile(username)
        if profile:
            profile_title_raw = profile.get("title")
            if profile_title_raw == "sir":
                title_display = "Sir"
            elif profile_title_raw == "madam":
                title_display = "Madam"
            else:
                title_display = "Not set"
            
            pronouns = profile.get("pronouns", "Not set")
            self.safe_reply(connection, event, f"{username}, I have you as title={title_display}, pronouns={pronouns}.")
        else:
            self.safe_reply(connection, event, f"{username}, I have no preferences on file for you.")
        return True

    def _cmd_profile(self, connection, event, msg, username, match):
        who = match.group(1)
        profile = self._get_user_profile(who)
        if profile:
            profile_title_raw = profile.get("title")
            if profile_title_raw == "sir":
                title_display = "Sir"
            elif profile_title_raw == "madam":
                title_display = "Madam"
            else:
                title_display = "Not set"

            pronouns = profile.get("pronouns", "Not set")
            self.safe_reply(connection, event, f"{who}'s preferences: title={title_display}, pronouns={pronouns}")
        else:
            self.safe_reply(connection, event, f"No profile found for {who}.")
        return True

    def _cmd_forget(self, connection, event, msg, username, match):
        profiles = self.get_state("profiles", {})
        key = self._get_profile_key(username)
        if profiles.pop(key, None) is not None:
            self.set_state("profiles", profiles)
            self.save_state()
            self.safe_reply(connection, event, f"{username}, your preferences have been removed.")
        else:
            self.safe_reply(connection, event, f"{username}, there were no preferences on file to remove.")
        return True

    # --- Helper Methods ---

    def _gender_pattern(self) -> str:
        """Creates a regex pattern string from the GENDER_MAP keys."""
        return "|".join(re.escape(g) for g in self.GENDER_MAP.keys())

    def _canonical_nick(self, nick: str) -> str:
        """Finds the base nick for a user, traversing any known aliases."""
        if not nick: return ""
        nick_lower = nick.lower()
        aliases = self.get_state("nick_aliases", {})
        while nick_lower in aliases:
            nick_lower = aliases[nick_lower]
        return nick_lower
        
    def _normalize_pronouns(self, s: str) -> str:
        """Normalizes a pronoun string to a standard format."""
        spaceless = s.strip().lower().replace(" ", "").replace("/", "")
        if spaceless in self.PRONOUN_MAP:
            return self.PRONOUN_MAP[spaceless]
        
        # Fallback for non-standard but valid-looking pronouns
        if len(s) <= 40 and re.match(r"^[a-zA-Z/\s]+$", s):
            return s.strip().lower()

        return "they/them" # Safe default

    def _normalize_gender_to_title(self, gender: str) -> str:
        """Converts a gender identity string to a formal title."""
        return self.GENDER_MAP.get(gender.lower().strip(), "neutral")
        
    def on_nick(self, connection, event, old_nick: str, new_nick: str):
        """Links an old nick to a new one when a user changes their name."""
        try:
            self._link_nicks(old_nick, new_nick)
        except Exception as e:
            self._record_error(f"Error linking nicks {old_nick}->{new_nick}: {e}")
            
    def _link_nicks(self, old_nick: str, new_nick: str):
        """Updates the nick alias mapping."""
        old_canonical = self._canonical_nick(old_nick)
        new_lower = new_nick.lower().strip()
        if old_canonical == new_lower: return
        aliases = self.get_state("nick_aliases", {})
        aliases[new_lower] = old_canonical
        self.set_state("nick_aliases", aliases)
        self.save_state()

    def _get_profile_key(self, nick: str) -> str:
        """Gets the canonical key for accessing a user's profile."""
        return self._canonical_nick(nick)

    def _get_user_profile(self, username: str) -> Optional[Dict[str, Any]]:
        """Retrieves a user's profile from the state."""
        profiles = self.get_state("profiles", {})
        key = self._get_profile_key(username)
        return profiles.get(key)

    def _set_user_profile(self, username: str, *, title: Optional[str] = None, pronouns: Optional[str] = None):
        """Sets or updates a user's profile and saves it to the state."""
        profile_key = self._get_profile_key(username)
        profiles = self.get_state("profiles", {})
        profile = profiles.get(profile_key, {})
        
        if pronouns is not None:
            profile["pronouns"] = pronouns
            # Automatically infer title if it's not already set to the opposite
            if pronouns == "he/him" and profile.get("title") != "madam":
                profile["title"] = "sir"
            elif pronouns == "she/her" and profile.get("title") != "sir":
                profile["title"] = "madam"

        if title is not None:
            profile["title"] = title

        profile["updated_at"] = datetime.now(UTC).isoformat()
        profiles[profile_key] = profile
        self.set_state("profiles", profiles)
        self.save_state()


