# modules/courtesy.py
# Courtesy ledger for user profiles, pronouns, and ignore list management.
import re
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from .base import SimpleCommandModule, admin_required

UTC = timezone.utc

def setup(bot, config):
    return Courtesy(bot, config)

class Courtesy(SimpleCommandModule):
    name = "courtesy"
    version = "5.0.1" # Added missing is_enabled check
    description = "User courtesy, pronoun, and ignore list management"

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
        super().__init__(bot)
        
        self.set_state("profiles", self.get_state("profiles", {}))
        self.set_state("ignored_users", self.get_state("ignored_users", []))
        self.set_state("admin_hostnames", self.get_state("admin_hostnames", {}))
        self.save_state()

        name_pat = self.bot.JEEVES_NAME_RE
        self.RE_GENDER_SET = re.compile(
            rf"\b{name_pat}[,!\s]*\s*(?:i\s*am|i'?m)\s*(?:a\s+)?({self._gender_pattern()})\b", re.IGNORECASE)
        self.RE_PRONOUNS_SET = re.compile(
            rf"\b{name_pat}[,!\s]*\s*(?:my\s+pronouns\s+are|pronouns[:\s]+)\s*([a-zA-Z/\- ]{{2,40}})\b", re.IGNORECASE)
        self.RE_NO_ASSUME = re.compile(
            rf"\b{name_pat}[,!\s]*\s*(?:don't\s+assume\s+my\s+gender|use\s+neutral)\b", re.IGNORECASE)

    def _register_commands(self):
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
        if not self.is_enabled(event.target):
            return False
            
        user_id = self.bot.get_user_id(username)

        gender_match = self.RE_GENDER_SET.search(msg)
        if gender_match:
            gender = gender_match.group(1).strip()
            title = self._normalize_gender_to_title(gender)
            self._set_user_profile(user_id, title=title)
            self.safe_reply(connection, event, f"Very good, {username}. I shall address you as {self.bot.title_for(username)} henceforth.")
            return True

        pronoun_match = self.RE_PRONOUNS_SET.search(msg)
        if pronoun_match:
            pronouns_str = pronoun_match.group(1).strip()
            if len(pronouns_str.split()) > 4: return False
            pronouns = self._normalize_pronouns(pronouns_str)
            self._set_user_profile(user_id, pronouns=pronouns)
            self.safe_reply(connection, event, f"Noted, {username}. Your pronouns are set to {pronouns}.")
            return True
            
        if self.RE_NO_ASSUME.search(msg):
            self._set_user_profile(user_id, title="neutral")
            self.safe_reply(connection, event, f"My apologies, {username}. I shall use neutral address for you.")
            return True
        return False

    def is_user_ignored(self, user_id: str) -> bool:
        return user_id in self.get_state("ignored_users", [])

    def _cmd_ignore(self, connection, event, msg, username, match):
        target_nick = match.group(1)
        if target_nick and not self.bot.is_admin(event.source):
            self.safe_reply(connection, event, f"{username}, you do not have permission to ignore other users.")
            return True
        
        victim_nick = target_nick or username
        victim_id = self.bot.get_user_id(victim_nick)
        
        ignored_list = self.get_state("ignored_users", [])
        if victim_id not in ignored_list:
            ignored_list.append(victim_id)
            self.set_state("ignored_users", ignored_list)
            self.save_state()
            self.safe_reply(connection, event, f"Very good. I shall henceforth ignore {victim_nick}.")
        else:
            self.safe_reply(connection, event, f"{victim_nick} is already on the ignore list.")
        return True

    def _cmd_unignore(self, connection, event, msg, username, match):
        target_nick = match.group(1)
        if target_nick and not self.bot.is_admin(event.source):
            self.safe_reply(connection, event, f"{username}, you do not have permission to unignore other users.")
            return True
            
        victim_nick = target_nick or username
        victim_id = self.bot.get_user_id(victim_nick)
        
        ignored_list = self.get_state("ignored_users", [])
        if victim_id in ignored_list:
            ignored_list.remove(victim_id)
            self.set_state("ignored_users", ignored_list)
            self.save_state()
            self.safe_reply(connection, event, f"As you wish. I will no longer ignore {victim_nick}.")
        else:
            self.safe_reply(connection, event, f"{victim_nick} was not on the ignore list.")
        return True
        
    def _cmd_gender(self, connection, event, msg, username, match):
        user_id = self.bot.get_user_id(username)
        gender = match.group(1).strip()
        title = self._normalize_gender_to_title(gender)
        self._set_user_profile(user_id, title=title)
        self.safe_reply(connection, event, f"{username}, recorded: {self.bot.title_for(username)}.")
        return True

    def _cmd_pronouns(self, connection, event, msg, username, match):
        user_id = self.bot.get_user_id(username)
        pronouns = self._normalize_pronouns(match.group(1))
        self._set_user_profile(user_id, pronouns=pronouns)
        self.safe_reply(connection, event, f"{username}, recorded: {pronouns}.")
        return True

    @admin_required
    def _cmd_set_gender(self, connection, event, msg, username, match):
        target_user, gender_str = match.groups()
        user_id = self.bot.get_user_id(target_user)
        title = self._normalize_gender_to_title(gender_str.strip())
        self._set_user_profile(user_id, title=title)
        self.safe_reply(connection, event, f"Very good. {target_user}'s title has been set to {self.bot.title_for(target_user)}.")
        return True

    @admin_required
    def _cmd_set_pronouns(self, connection, event, msg, username, match):
        target_user, pronouns_str = match.groups()
        user_id = self.bot.get_user_id(target_user)
        pronouns = self._normalize_pronouns(pronouns_str.strip())
        self._set_user_profile(user_id, pronouns=pronouns)
        self.safe_reply(connection, event, f"Noted. {target_user}'s pronouns have been set to {pronouns}.")
        return True

    def _cmd_whoami(self, connection, event, msg, username, match):
        user_id = self.bot.get_user_id(username)
        self._display_profile(connection, event, username, user_id)
        return True

    def _cmd_profile(self, connection, event, msg, username, match):
        target_user = match.group(1)
        user_id = self.bot.get_user_id(target_user)
        self._display_profile(connection, event, target_user, user_id)
        return True
        
    def _display_profile(self, connection, event, nick, user_id):
        profile = self._get_user_profile(user_id)
        if profile:
            profile_title_raw = profile.get("title")
            title_display = "Not set"
            if profile_title_raw == "sir": title_display = "Sir"
            elif profile_title_raw == "madam": title_display = "Madam"
            
            pronouns = profile.get("pronouns", "Not set")
            self.safe_reply(connection, event, f"Preferences for {nick}: title={title_display}, pronouns={pronouns}.")
        else:
            self.safe_reply(connection, event, f"I have no preferences on file for {nick}.")

    def _cmd_forget(self, connection, event, msg, username, match):
        user_id = self.bot.get_user_id(username)
        profiles = self.get_state("profiles", {})
        if profiles.pop(user_id, None) is not None:
            self.set_state("profiles", profiles)
            self.save_state()
            self.safe_reply(connection, event, f"{username}, your preferences have been removed.")
        else:
            self.safe_reply(connection, event, f"{username}, there were no preferences on file to remove.")
        return True

    # --- Helper Methods ---
    def _gender_pattern(self) -> str:
        return "|".join(re.escape(g) for g in self.GENDER_MAP.keys())
        
    def _normalize_pronouns(self, s: str) -> str:
        spaceless = s.strip().lower().replace(" ", "").replace("/", "")
        if spaceless in self.PRONOUN_MAP:
            return self.PRONOUN_MAP[spaceless]
        if len(s) <= 40 and re.match(r"^[a-zA-Z/\s]+$", s):
            return s.strip().lower()
        return "they/them"

    def _normalize_gender_to_title(self, gender: str) -> str:
        return self.GENDER_MAP.get(gender.lower().strip(), "neutral")
        
    def _get_user_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        return self.get_state("profiles", {}).get(user_id)

    def _set_user_profile(self, user_id: str, *, title: Optional[str] = None, pronouns: Optional[str] = None):
        profiles = self.get_state("profiles", {})
        profile = profiles.get(user_id, {})
        
        if pronouns is not None:
            profile["pronouns"] = pronouns
            if pronouns == "he/him" and profile.get("title") != "madam":
                profile["title"] = "sir"
            elif pronouns == "she/her" and profile.get("title") != "sir":
                profile["title"] = "madam"

        if title is not None:
            profile["title"] = title

        profile["updated_at"] = self.bot.get_utc_time()
        profiles[user_id] = profile
        self.set_state("profiles", profiles)
        self.save_state()
