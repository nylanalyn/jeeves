# modules/courtesy.py
# Enhanced courtesy ledger with proper nick tracking and base class usage
import re
import time
import random
import sys
import functools
from typing import Optional, Dict, Any, List, Callable, Union
from datetime import datetime, timezone
from .base import SimpleCommandModule, ResponseModule, admin_required

UTC = timezone.utc

def setup(bot, config):
    return Courtesy(bot, config)

class Courtesy(SimpleCommandModule):
    name = "courtesy"
    version = "2.3.0" 
    description = "User courtesy, pronoun, and ignore list management"

    PRONOUN_MAP = {"he/him":"he/him","hehim":"he/him","he":"he/him", "she/her":"she/her","sheher":"she/her","she":"she/her", "they/them":"they/them","theythem":"they/them","they":"they/them", "xe/xem":"xe/xem","xexem":"xe/xem", "ze/zir":"ze/zir","zezir":"ze/zir", "fae/faer":"fae/faer","faefer":"fae/faer", "e/em":"e/em","eem":"e/em", "per/per":"per/per","perper":"per/per", "ve/ver":"ve/ver","vever":"ve/ver", "it/its":"it/its","itits":"it/its", "they/xe":"they/xe","she/they":"she/they","he/they":"he/they", "any":"any","any/all":"any/all", }
    GENDER_MAP = {"male":"sir","man":"sir","boy":"sir","masculine":"sir","masc":"sir","m":"sir", "female":"madam","woman":"madam","girl":"madam","feminine":"madam","fem":"madam","f":"madam", "nonbinary":"neutral","non-binary":"neutral","nb":"neutral","enby":"neutral", "neutral":"neutral","agender":"neutral","genderfluid":"neutral","genderqueer":"neutral", "demiboy":"neutral","demigirl":"neutral","bigender":"neutral","pangender":"neutral", "questioning":"neutral", }

    def __init__(self, bot, config):
        super().__init__(bot)
        
        self.set_state("profiles", self.get_state("profiles", {}))
        self.set_state("nick_aliases", self.get_state("nick_aliases", {}))
        self.set_state("prompted_users", self.get_state("prompted_users", {}))
        self.set_state("ignored_users", self.get_state("ignored_users", []))
        self.set_state("admin_hostnames", self.get_state("admin_hostnames", {})) # NEW
        
        for key in ["profiles_created", "profiles_updated", "profiles_deleted", "natural_language_uses", "command_uses"]:
            self.set_state(key, self.get_state(key, 0))
        for key in ["most_common_pronouns", "most_common_titles", "users_who_set_profiles"]:
            self.set_state(key, self.get_state(key, {}))
        self.save_state()

        name_pat = getattr(self.bot, "JEEVES_NAME_RE", r"(?:jeeves|jeevesbot)")
        self.RE_GENDER_SET = re.compile(rf"\b{name_pat}[,!\s]*\s*(?:i\s*am|i'?m)\s*(?:a\s+)?({self._gender_pattern()})\b", re.IGNORECASE)
        self.RE_PRONOUNS_SET = re.compile(r"\b(?:my\s+pronouns\s+are|pronouns[:\s]+)\s*([a-zA-Z/\- ]{2,40})\b", re.IGNORECASE)
        self.RE_NO_ASSUME = re.compile(rf"\b{name_pat}[,!\s]*\s*(?:don't\s+assume\s+my\s+gender|use\s+neutral)\b", re.IGNORECASE)

    def _register_commands(self):
        self.register_command(r"^\s*!gender\s+(.+)\s*$", self._cmd_gender, name="gender", description="Set your gender/title")
        self.register_command(r"^\s*!pronouns\s+(.+)\s*$", self._cmd_pronouns, name="pronouns", description="Set your pronouns")
        self.register_command(r"^\s*!whoami\s*$", self._cmd_whoami, name="whoami", description="Show your profile")
        self.register_command(r"^\s*!profile\s+(\S+)\s*$", self._cmd_profile, name="profile", description="Show someone's profile")
        self.register_command(r"^\s*!forgetme\s*$", self._cmd_forget, name="forgetme", description="Delete your profile")
        self.register_command(r"^\s*!courtesy\s+stats\s*$", self._cmd_stats, name="courtesy stats", admin_only=True, description="Show courtesy statistics")
        self.register_command(r"^\s*!ignore(?:\s+(\S+))?\s*$", self._cmd_ignore, name="ignore", description="Add user to the ignore list. Admin required to ignore others.")
        self.register_command(r"^\s*!unignore(?:\s+(\S+))?\s*$", self._cmd_unignore, name="unignore", description="Remove user from the ignore list. Admin required to unignore others.")

    def is_user_ignored(self, username: str) -> bool:
        return self._canonical_nick(username) in self.get_state("ignored_users", [])

    def _cmd_ignore(self, connection, event, msg, username, match):
        target_nick = match.group(1)
        if target_nick and not self.bot.is_admin(event.source):
            self.safe_reply(connection, event, f"{username}, you do not have permission to ignore others.")
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
            self.safe_reply(connection, event, f"{username}, you do not have permission to unignore others.")
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
        
    def _canonical_nick(self, nick: str) -> str:
        if not nick: return ""
        nick_lower = nick.lower()
        aliases = self.get_state("nick_aliases", {})
        while nick_lower in aliases:
            nick_lower = aliases[nick_lower]
        return nick_lower
    
    # ... rest of the file is unchanged