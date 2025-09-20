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
    version = "2.3.7" # version bumped for title inference
    description = "User courtesy, pronoun, and ignore list management"

    PRONOUN_MAP = {"he/him":"he/him","hehim":"he/him","he":"he/him", "she/her":"she/her","sheher":"she/her","she":"she/her", "they/them":"they/them","theythem":"they/them","they":"they/them", "xe/xem":"xe/xem","xexem":"xe/xem", "ze/zir":"ze/zir","zezir":"ze/zir", "fae/faer":"fae/faer","faefer":"fae/faer", "e/em":"e/em","eem":"e/em", "per/per":"per/per","perper":"per/per", "ve/ver":"ve/ver","vever":"ve/ver", "it/its":"it/its","itits":"it/its", "they/xe":"they/xe","she/they":"she/they","he/they":"he/they", "any":"any","any/all":"any/all", }
    GENDER_MAP = {"male":"sir","man":"sir","boy":"sir","masculine":"sir","masc":"sir","m":"sir", "female":"madam","woman":"madam","girl":"madam","feminine":"madam","fem":"madam","f":"madam", "nonbinary":"neutral","non-binary":"neutral","nb":"neutral","enby":"neutral", "neutral":"neutral","agender":"neutral","genderfluid":"neutral","genderqueer":"neutral", "demiboy":"neutral","demigirl":"neutral","bigender":"neutral","pangender":"neutral", "questioning":"neutral", }

    def __init__(self, bot, config):
        super().__init__(bot)
        
        self.set_state("profiles", self.get_state("profiles", {}))
        self.set_state("nick_aliases", self.get_state("nick_aliases", {}))
        self.set_state("prompted_users", self.get_state("prompted_users", {}))
        self.set_state("ignored_users", self.get_state("ignored_users", []))
        self.set_state("admin_hostnames", self.get_state("admin_hostnames", {}))
        
        for key in ["profiles_created", "profiles_updated", "profiles_deleted", "natural_language_uses", "command_uses"]:
            self.set_state(key, self.get_state(key, 0))
        for key in ["most_common_pronouns", "most_common_titles", "users_who_set_profiles"]:
            self.set_state(key, self.get_state(key, {}))
        self.save_state()

        name_pat = getattr(self.bot, "JEEVES_NAME_RE", r"(?:jeeves|jeevesbot)")
        self.RE_GENDER_SET = re.compile(rf"\b{name_pat}[,!\s]*\s*(?:i\s*am|i'?m)\s*(?:a\s+)?({self._gender_pattern()})\b", re.IGNORECASE)
        self.RE_PRONOUNS_SET = re.compile(rf"\b{name_pat}[,!\s]*\s*(?:my\s+pronouns\s+are|pronouns[:\s]+)\s*([a-zA-Z/\- ]{{2,40}})\b", re.IGNORECASE)
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
        # Admin commands to set user profiles
        self.register_command(r"^\s*!setgender\s+(\S+)\s+(.+)\s*$", self._cmd_set_gender, name="setgender", admin_only=True, description="[Admin] Set a user's gender/title.")
        self.register_command(r"^\s*!setpronouns\s+(\S+)\s+(.+)\s*$", self._cmd_set_pronouns, name="setpronouns", admin_only=True, description="[Admin] Set a user's pronouns.")

    def on_pubmsg(self, connection, event, msg, username):
        if super().on_pubmsg(connection, event, msg, username):
            return True # A command was handled

        # Check for natural language gender setting
        gender_match = self.RE_GENDER_SET.search(msg)
        if gender_match:
            gender = gender_match.group(1).strip()
            title = self._normalize_gender_to_title(gender)
            self._set_user_profile(username, title=title)
            display_title = self.bot.title_for(username)
            self.safe_reply(connection, event, f"Very good, {username}. I shall address you as {display_title} henceforth.")
            self.set_state("natural_language_uses", self.get_state("natural_language_uses", 0) + 1)
            self.save_state()
            return True

        # Check for natural language pronoun setting
        pronoun_match = self.RE_PRONOUNS_SET.search(msg)
        if pronoun_match:
            pronouns_str = pronoun_match.group(1).strip()
            if len(pronouns_str.split()) > 4: return False
            pronouns = self._normalize_pronouns(pronouns_str)
            self._set_user_profile(username, pronouns=pronouns)
            self.safe_reply(connection, event, f"Noted, {username}. Your pronouns are set to {pronouns}.")
            self.set_state("natural_language_uses", self.get_state("natural_language_uses", 0) + 1)
            self.save_state()
            return True
            
        if self.RE_NO_ASSUME.search(msg):
            self._set_user_profile(username, title="neutral")
            self.safe_reply(connection, event, f"My apologies, {username}. I shall use neutral address for you.")
            return True
            
        if self._should_prompt_user(username):
            self._prompt_user(connection, event, username)

        return False

    def is_user_ignored(self, username: str) -> bool:
        return self._canonical_nick(username) in self.get_state("ignored_users", [])

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
            title = profile.get("title", "neutral")
            pronouns = profile.get("pronouns", "they/them")
            updated = profile.get("updated_count", 1)
            self.safe_reply(connection, event, f"{username}, I have you as title={title}, pronouns={pronouns} (updated {updated} times).")
        else:
            self.safe_reply(connection, event, f"{username}, I have no notes on file. Try '!gender [identity]'.")
        return True

    def _cmd_profile(self, connection, event, msg, username, match):
        who = match.group(1)
        profile = self._get_user_profile(who)
        if profile:
            title = profile.get("title", "neutral")
            pronouns = profile.get("pronouns", "they/them")
            self.safe_reply(connection, event, f"{who}: title={title}, pronouns={pronouns}")
        else:
            self.safe_reply(connection, event, f"No profile found for {who}.")
        return True

    def _cmd_forget(self, connection, event, msg, username, match):
        profiles = self.get_state("profiles", {})
        key = self._get_profile_key(username)
        if profiles.pop(key, None) is not None:
            self.set_state("profiles", profiles)
            self.save_state()
            self.safe_reply(connection, event, f"{username}, your preferences are removed.")
        else:
            self.safe_reply(connection, event, f"{username}, there were no preferences on file.")
        return True

    @admin_required
    def _cmd_stats(self, connection, event, msg, username, match):
        profiles = self.get_state("profiles", {})
        pron_stats = self.get_state("most_common_pronouns", {})
        lines = [f"Profiles: {len(profiles)}", f"Natural lang: {self.get_state('natural_language_uses', 0)}"]
        if pron_stats:
            top = sorted(pron_stats.items(), key=lambda x: x[1], reverse=True)[:3]
            lines.append("Top pronouns: " + ", ".join(f"{p}({c})" for p, c in top))
        self.safe_reply(connection, event, "Courtesy stats: " + "; ".join(lines))
        return True
        
    def _gender_pattern(self) -> str:
        genders = "|".join(re.escape(g) for g in self.GENDER_MAP.keys())
        return f"(?:{genders})"

    def _canonical_nick(self, nick: str) -> str:
        if not nick: return ""
        nick_lower = nick.lower()
        aliases = self.get_state("nick_aliases", {})
        while nick_lower in aliases:
            nick_lower = aliases[nick_lower]
        return nick_lower
        
    def _normalize_pronouns(self, s: str) -> str:
        """Normalizes a pronoun string, allowing for spaces and common separators."""
        user_input_cleaned = s.strip().lower()
        
        # Replace common separators like " and " or "," with "/"
        standardized = re.sub(r'(\s+and\s+|\s*,\s*|\s+or\s+)', '/', user_input_cleaned)
        
        # Create a spaceless version for checking against the map, e.g., "she her" -> "sheher"
        spaceless_for_check = standardized.replace(" ", "").replace("/", "").replace("_", "").replace("-", "")
        
        if spaceless_for_check in self.PRONOUN_MAP:
            return self.PRONOUN_MAP[spaceless_for_check]

        # If no map match, validate the user's original (but cleaned) input
        if len(user_input_cleaned) <= 40 and re.match(r"^[a-z/\s]+$", user_input_cleaned):
            # Prefer the standardized version if it looks like a pair
            if '/' in standardized:
                return standardized
            return user_input_cleaned

        return "they/them" # Fallback

    def _normalize_gender_to_title(self, gender: str) -> str:
        return self.GENDER_MAP.get(gender.lower().strip(), "neutral")
        
    def on_nick(self, connection, event, old_nick: str, new_nick: str):
        try:
            self._link_nicks(old_nick, new_nick)
        except Exception as e:
            self._record_error(f"Error linking nicks {old_nick}->{new_nick}: {e}")
            
    def _link_nicks(self, old_nick: str, new_nick: str):
        old_canonical = self._canonical_nick(old_nick)
        new_lower = new_nick.lower().strip()
        if old_canonical == new_lower: return
        aliases = self.get_state("nick_aliases", {})
        aliases[new_lower] = old_canonical
        self.set_state("nick_aliases", aliases)
        self.save_state()

    def _get_profile_key(self, nick: str) -> str:
        return self._canonical_nick(nick)

    def _get_user_profile(self, username: str):
        profiles = self.get_state("profiles", {})
        key = self._get_profile_key(username)
        return profiles.get(key)

    def _set_user_profile(self, username: str, *, title=None, pronouns=None):
        profile_key = self._get_profile_key(username)
        profiles = self.get_state("profiles", {})
        profile = profiles.get(profile_key, {})
        
        if title is not None:
            profile["title"] = title

        # --- FIX: Infer title from pronouns if they are set ---
        if pronouns is not None:
            profile["pronouns"] = pronouns
            # If user sets he/him or she/her, automatically set the corresponding title.
            if pronouns == "he/him":
                profile["title"] = "sir"
            elif pronouns == "she/her":
                profile["title"] = "madam"
        
        profile["updated_at"] = datetime.now(UTC).isoformat()
        profile['updated_count'] = profile.get('updated_count', 0) + 1 # Track updates
        profiles[profile_key] = profile
        self.set_state("profiles", profiles)
        self.save_state()

    def _should_prompt_user(self, username: str) -> bool:
        if self._get_user_profile(username): return False
        prompted = self.get_state("prompted_users", {})
        key = username.lower()
        if key in prompted:
            return (time.time() - prompted[key]) > 86400
        return True

    def _mark_user_prompted(self, username: str):
        prompted = self.get_state("prompted_users", {})
        prompted[username.lower()] = time.time()
        self.set_state("prompted_users", prompted)
        self.save_state()

    def _prompt_user(self, connection, event, username: str):
        prompts = [ f"Good day, {username}! I use neutral address by default. You may say 'Jeeves, I am [male/female/nonbinary]' or use '!gender male' and '!pronouns he/him'.", f"Welcome, {username}! I shall address you as Mx. unless you specify otherwise. Try 'my pronouns are they/them' or '!pronouns she/her'.", f"Greetings, {username}! If you'd prefer sir/madam or specific pronouns, let me know: 'Jeeves, I am a woman' or '!gender female' both work.", ]
        self.safe_reply(connection, event, random.choice(prompts))
        self._mark_user_prompted(username)
