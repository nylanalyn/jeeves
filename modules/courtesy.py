# modules/courtesy.py
# Enhanced courtesy ledger with proper nick tracking and base class usage
import re
import time
import random
import sys
from datetime import datetime, timezone
from .base import SimpleCommandModule

UTC = timezone.utc

def setup(bot):
    return Courtesy(bot)

class Courtesy(SimpleCommandModule):
    name = "courtesy"
    version = "2.1.0"
    description = "User courtesy and pronoun management with nick tracking"

    PRONOUN_MAP = {
        "he/him":"he/him","hehim":"he/him","he":"he/him",
        "she/her":"she/her","sheher":"she/her","she":"she/her",
        "they/them":"they/them","theythem":"they/them","they":"they/them",
        "xe/xem":"xe/xem","xexem":"xe/xem",
        "ze/zir":"ze/zir","zezir":"ze/zir",
        "fae/faer":"fae/faer","faefer":"fae/faer",
        "e/em":"e/em","eem":"e/em",
        "per/per":"per/per","perper":"per/per",
        "ve/ver":"ve/ver","vever":"ve/ver",
        "it/its":"it/its","itits":"it/its",
        "they/xe":"they/xe","she/they":"she/they","he/they":"he/they",
        "any":"any","any/all":"any/all",
    }

    GENDER_MAP = {
        "male":"sir","man":"sir","boy":"sir","masculine":"sir","masc":"sir","m":"sir",
        "female":"madam","woman":"madam","girl":"madam","feminine":"madam","fem":"madam","f":"madam",
        "nonbinary":"neutral","non-binary":"neutral","nb":"neutral","enby":"neutral",
        "neutral":"neutral","agender":"neutral","genderfluid":"neutral","genderqueer":"neutral",
        "demiboy":"neutral","demigirl":"neutral","bigender":"neutral","pangender":"neutral",
        "questioning":"neutral",
    }

    def __init__(self, bot):
        super().__init__(bot)
        
        # Initialize state
        self.set_state("profiles", self.get_state("profiles", {}))
        self.set_state("nick_aliases", self.get_state("nick_aliases", {}))  # nick -> canonical_nick
        self.set_state("prompted_users", self.get_state("prompted_users", {}))
        
        # Stats
        for key in ["profiles_created", "profiles_updated", "profiles_deleted", 
                   "natural_language_uses", "command_uses"]:
            self.set_state(key, self.get_state(key, 0))
        
        for key in ["most_common_pronouns", "most_common_titles", "users_who_set_profiles"]:
            self.set_state(key, self.get_state(key, {}))

        # Natural language patterns
        name_pat = getattr(self.bot, "JEEVES_NAME_RE", r"(?:jeeves|jeevesbot)")
        self.RE_GENDER_SET = re.compile(
            rf"\b{name_pat}[,!\s]*\s*(?:i\s*am|i'?m)\s*(?:a\s+)?({self._gender_pattern()})\b",
            re.IGNORECASE
        )
        self.RE_PRONOUNS_SET = re.compile(
            r"\b(?:my\s+pronouns\s+are|pronouns[:\s]+)\s*([a-zA-Z/\- ]{2,40})\b",
            re.IGNORECASE
        )
        self.RE_NO_ASSUME = re.compile(
            rf"\b{name_pat}[,!\s]*\s*(?:don't\s+assume\s+my\s+gender|use\s+neutral)\b",
            re.IGNORECASE
        )

        self.save_state()

    def _register_commands(self):
        """Register all courtesy commands"""
        self.register_command(r"^\s*!gender\s+(.+)\s*$", self._cmd_gender, 
                            description="Set your gender/title")
        self.register_command(r"^\s*!pronouns\s+(.+)\s*$", self._cmd_pronouns,
                            description="Set your pronouns")
        self.register_command(r"^\s*!whoami\s*$", self._cmd_whoami,
                            description="Show your profile")
        self.register_command(r"^\s*!profile\s+(\S+)\s*$", self._cmd_profile,
                            description="Show someone's profile")
        self.register_command(r"^\s*!forgetme\s*$", self._cmd_forget,
                            description="Delete your profile")
        self.register_command(r"^\s*!courtesy\s+stats\s*$", self._cmd_stats, 
                            admin_only=True, description="Show courtesy statistics")

    def _gender_pattern(self) -> str:
        genders = "|".join(re.escape(g) for g in self.GENDER_MAP.keys())
        return f"(?:{genders})"

    # ---- Nick Management ----
    def _canonical_nick(self, nick: str) -> str:
        """Get the canonical nick for a user, following alias chain safely"""
        if not nick:
            return ""
        
        nick_lower = nick.lower().strip()
        aliases = self.get_state("nick_aliases", {})
        
        # Follow alias chain with cycle detection
        seen = set()
        current = nick_lower
        
        while current in aliases and current not in seen:
            seen.add(current)
            current = aliases[current]
        
        return current

    def _link_nicks(self, old_nick: str, new_nick: str):
        """Link old nick to new nick, preserving existing profiles"""
        old_canonical = self._canonical_nick(old_nick)
        new_lower = new_nick.lower().strip()
        
        # Don't create self-loops
        if old_canonical == new_lower:
            return
        
        aliases = self.get_state("nick_aliases", {})
        aliases[new_lower] = old_canonical
        self.set_state("nick_aliases", aliases)
        self.save_state()

    def _get_profile_key(self, nick: str) -> str:
        """Get the profile key for a nick (canonical nick)"""
        return self._canonical_nick(nick)

    # ---- Profile Management ----
    def _get_user_profile(self, username: str):
        """Get profile for a user"""
        profiles = self.get_state("profiles", {})
        key = self._get_profile_key(username)
        return profiles.get(key)

    def _set_user_profile(self, username: str, *, title=None, pronouns=None):
        """Set profile data for a user"""
        profile_key = self._get_profile_key(username)
        profiles = self.get_state("profiles", {})
        
        profile = profiles.get(profile_key, {})
        was_new = not bool(profile)
        
        if title is not None:
            profile["title"] = title
        if pronouns is not None:
            profile["pronouns"] = pronouns
        
        profile["updated_at"] = datetime.now(UTC).isoformat()
        profile["updated_count"] = profile.get("updated_count", 0) + 1
        
        profiles[profile_key] = profile
        self.set_state("profiles", profiles)
        
        # Update stats
        if was_new:
            self.set_state("profiles_created", self.get_state("profiles_created", 0) + 1)
            users = self.get_state("users_who_set_profiles", [])
            if username.lower() not in users:
                users.append(username.lower())
                self.set_state("users_who_set_profiles", users)
        else:
            self.set_state("profiles_updated", self.get_state("profiles_updated", 0) + 1)
        
        # Track popular choices
        if pronouns:
            pron_counts = self.get_state("most_common_pronouns", {})
            pron_counts[pronouns] = pron_counts.get(pronouns, 0) + 1
            self.set_state("most_common_pronouns", pron_counts)
        
        if title:
            title_counts = self.get_state("most_common_titles", {})
            title_counts[title] = title_counts.get(title, 0) + 1
            self.set_state("most_common_titles", title_counts)
        
        self.save_state()

    # ---- Prompting Logic ----
    def _should_prompt_user(self, username: str) -> bool:
        """Check if we should prompt this user for preferences"""
        if self._get_user_profile(username):
            return False
        
        prompted = self.get_state("prompted_users", {})
        key = username.lower()
        
        if key in prompted:
            # Only prompt again after 24 hours
            return (time.time() - prompted[key]) > 86400
        
        return True

    def _mark_user_prompted(self, username: str):
        """Mark that we've prompted this user"""
        prompted = self.get_state("prompted_users", {})
        prompted[username.lower()] = time.time()
        self.set_state("prompted_users", prompted)
        self.save_state()

    def _prompt_user(self, connection, event, username: str):
        """Send a courtesy prompt to a new user"""
        prompts = [
            f"Good day, {username}! I use neutral address by default. You may say 'Jeeves, I am [male/female/nonbinary]' or use '!gender male' and '!pronouns he/him'.",
            f"Welcome, {username}! I shall address you as Mx. unless you specify otherwise. Try 'my pronouns are they/them' or '!pronouns she/her'.",
            f"Greetings, {username}! If you'd prefer sir/madam or specific pronouns, let me know: 'Jeeves, I am a woman' or '!gender female' both work.",
        ]
        self.safe_reply(connection, event, random.choice(prompts))
        self._mark_user_prompted(username)

    # ---- Normalization ----
    def _normalize_pronouns(self, s: str) -> str:
        """Normalize pronouns to standard format"""
        cleaned = s.strip().lower().replace(" ", "").replace("_", "").replace("-", "")
        
        if cleaned in self.PRONOUN_MAP:
            return self.PRONOUN_MAP[cleaned]
        
        if "/" in cleaned:
            parts = cleaned.split("/")
            if len(parts) == 2:
                candidate = f"{parts[0]}/{parts[1]}"
                return self.PRONOUN_MAP.get(candidate, candidate)
        
        # Accept reasonable custom pronouns
        if len(cleaned) <= 20 and re.match(r"^[a-z/]+$", cleaned):
            return cleaned
        
        return "they/them"

    def _normalize_gender_to_title(self, gender: str) -> str:
        """Convert gender to title"""
        return self.GENDER_MAP.get(gender.lower().strip(), "neutral")

    # ---- Message Handler ----
    def _handle_message(self, connection, event, msg: str, username: str) -> bool:
        """Handle natural language courtesy expressions"""
        room = event.target
        
        # Prompt new users when they address the bot
        if self._should_prompt_user(username):
            if self.is_mentioned(msg) or msg.strip().startswith("!"):
                self.schedule_delayed_action(2.0, self._prompt_user, connection, event, username)
        
        # Natural language: "Jeeves, I am..."
        match = self.RE_GENDER_SET.search(msg)
        if match:
            gender = match.group(1).lower().strip()
            title = self._normalize_gender_to_title(gender)
            self._set_user_profile(username, title=title)
            self.set_state("natural_language_uses", self.get_state("natural_language_uses", 0) + 1)
            self.save_state()
            
            display_title = self.bot.title_for(username)
            self.safe_reply(connection, event, f"{username}, very good, {display_title}. I shall remember.")
            return True
        
        # Natural language: "my pronouns are..."
        match = self.RE_PRONOUNS_SET.search(msg)
        if match:
            pronouns = self._normalize_pronouns(match.group(1))
            self._set_user_profile(username, pronouns=pronouns)
            self.set_state("natural_language_uses", self.get_state("natural_language_uses", 0) + 1)
            self.save_state()
            
            self.safe_reply(connection, event, f"{username}, noted. I shall use {pronouns} henceforth.")
            return True
        
        # Natural language: "don't assume my gender"
        if self.RE_NO_ASSUME.search(msg):
            self._set_user_profile(username, title="neutral", pronouns="they/them")
            self.set_state("natural_language_uses", self.get_state("natural_language_uses", 0) + 1)
            self.save_state()
            
            self.safe_reply(connection, event, f"{username}, as you wish. I shall keep to neutral address.")
            return True
        
        return False

    # ---- Command Handlers ----
    def _cmd_gender(self, connection, event, msg, username, match):
        """Handle !gender command"""
        gender = match.group(1).strip()
        title = self._normalize_gender_to_title(gender)
        
        if title == "neutral" and gender.lower() not in self.GENDER_MAP:
            self.safe_say(f"{username}, I'm not familiar with '{gender}'. Using neutral address.")
        
        self._set_user_profile(username, title=title)
        self.set_state("command_uses", self.get_state("command_uses", 0) + 1)
        self.save_state()
        
        display_title = self.bot.title_for(username)
        self.safe_say(f"{username}, recorded: {display_title}.")
        return True

    def _cmd_pronouns(self, connection, event, msg, username, match):
        """Handle !pronouns command"""
        pronouns = self._normalize_pronouns(match.group(1))
        self._set_user_profile(username, pronouns=pronouns)
        self.set_state("command_uses", self.get_state("command_uses", 0) + 1)
        self.save_state()
        
        self.safe_say(f"{username}, recorded: {pronouns}.")
        return True

    def _cmd_whoami(self, connection, event, msg, username, match):
        """Handle !whoami command"""
        profile = self._get_user_profile(username)
        if profile:
            title = profile.get("title", "neutral")
            pronouns = profile.get("pronouns", "they/them")
            updated = profile.get("updated_count", 1)
            self.safe_say(f"{username}, I have you as title={title}, pronouns={pronouns} (updated {updated} times).")
        else:
            self.safe_say(f"{username}, I have no notes on file. Try 'Jeeves, I am [gender]' or '!gender [identity]'.")
        return True

    def _cmd_profile(self, connection, event, msg, username, match):
        """Handle !profile command"""
        who = match.group(1)
        profile = self._get_user_profile(who)
        if profile:
            title = profile.get("title", "neutral")
            pronouns = profile.get("pronouns", "they/them")
            self.safe_say(f"{who}: title={title}, pronouns={pronouns}")
        else:
            self.safe_say(f"No profile found for {who}.")
        return True

    def _cmd_forget(self, connection, event, msg, username, match):
        """Handle !forgetme command"""
        profiles = self.get_state("profiles", {})
        key = self._get_profile_key(username)
        
        if profiles.pop(key, None) is not None:
            self.set_state("profiles", profiles)
            self.set_state("profiles_deleted", self.get_state("profiles_deleted", 0) + 1)
            self.save_state()
            self.safe_say(f"{username}, your preferences are removed. I shall address neutrally.")
        else:
            self.safe_say(f"{username}, there were no preferences on file.")
        return True

    def _cmd_stats(self, connection, event, msg, username, match):
        """Handle !courtesy stats command (admin only)"""
        profiles = self.get_state("profiles", {})
        pron_stats = self.get_state("most_common_pronouns", {})
        
        lines = [
            f"Profiles: {len(profiles)}",
            f"Created: {self.get_state('profiles_created', 0)}",
            f"Updated: {self.get_state('profiles_updated', 0)}",
            f"Natural lang: {self.get_state('natural_language_uses', 0)}",
            f"Commands: {self.get_state('command_uses', 0)}",
        ]
        
        if pron_stats:
            top = sorted(pron_stats.items(), key=lambda x: x[1], reverse=True)[:3]
            lines.append("Top pronouns: " + ", ".join(f"{p}({c})" for p, c in top))
        
        self.safe_say("Courtesy stats: " + "; ".join(lines))
        return True

    # ---- IRC Events ----
    def on_nick(self, connection, event, old_nick: str, new_nick: str):
        """Handle nick changes by linking them"""
        try:
            self._link_nicks(old_nick, new_nick)
        except Exception as e:
            self._record_error(f"Error linking nicks {old_nick}->{new_nick}: {e}")
