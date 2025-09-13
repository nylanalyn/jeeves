# modules/courtesy.py
# Enhanced courtesy ledger without base class dependency with first-time user prompting
import re
import time
import random
from datetime import datetime, timezone

UTC = timezone.utc

def setup(bot): 
    return Courtesy(bot)

class Courtesy:
    name = "courtesy"
    version = "2.0.0"
    
    # Valid pronouns with normalized forms
    PRONOUN_MAP = {
        # Standard pronouns
        "he/him": "he/him", "hehim": "he/him", "he": "he/him",
        "she/her": "she/her", "sheher": "she/her", "she": "she/her",
        "they/them": "they/them", "theythem": "they/them", "they": "they/them",
        
        # Neopronouns
        "xe/xem": "xe/xem", "xexem": "xe/xem",
        "ze/zir": "ze/zir", "zezir": "ze/zir",
        "fae/faer": "fae/faer", "faefer": "fae/faer",
        "e/em": "e/em", "eem": "e/em",
        "per/per": "per/per", "perper": "per/per",
        "ve/ver": "ve/ver", "vever": "ve/ver",
        "it/its": "it/its", "itits": "it/its",
        
        # Alternative forms
        "they/xe": "they/xe", "she/they": "she/they", "he/they": "he/they",
        "any": "any", "any/all": "any/all",
    }
    
    # Gender identity mapping
    GENDER_MAP = {
        # Male identities
        "male": "sir", "man": "sir", "boy": "sir", "masculine": "sir", "masc": "sir", "m": "sir",
        
        # Female identities
        "female": "madam", "woman": "madam", "girl": "madam", "feminine": "madam", "fem": "madam", "f": "madam",
        
        # Non-binary identities
        "nonbinary": "neutral", "non-binary": "neutral", "nb": "neutral", "enby": "neutral",
        "neutral": "neutral", "agender": "neutral", "genderfluid": "neutral", "genderqueer": "neutral",
        "demiboy": "neutral", "demigirl": "neutral", "bigender": "neutral", "pangender": "neutral",
        "questioning": "neutral",
    }

    def __init__(self, bot):
        self.bot = bot
        self.st = bot.get_module_state(self.name)
        
        # Initialize state
        self.st.setdefault("profiles", {})
        self.st.setdefault("profiles_created", 0)
        self.st.setdefault("profiles_updated", 0)
        self.st.setdefault("profiles_deleted", 0)
        self.st.setdefault("natural_language_uses", 0)
        self.st.setdefault("command_uses", 0)
        self.st.setdefault("most_common_pronouns", {})
        self.st.setdefault("most_common_titles", {})
        self.st.setdefault("prompted_users", {})
        self.st.setdefault("users_who_set_profiles", [])
        
        # Cache for performance
        self._profile_cache = {}
        self._cache_timeout = 300  # 5 minutes
        self._last_cache_update = 0
        
        # Set up patterns
        name_pat = getattr(self.bot, "JEEVES_NAME_RE", r"(?:jeeves|jeevesbot)")
        
        # Natural language patterns
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
        
        # Command patterns
        self.RE_CMD_GENDER = re.compile(r"^\s*!gender\s+(.+)\s*$", re.IGNORECASE)
        self.RE_CMD_PRONOUNS = re.compile(r"^\s*!pronouns\s+(.+)\s*$", re.IGNORECASE)
        self.RE_CMD_WHOAMI = re.compile(r"^\s*!whoami\s*$", re.IGNORECASE)
        self.RE_CMD_PROFILE = re.compile(r"^\s*!profile\s+(\S+)\s*$", re.IGNORECASE)
        self.RE_CMD_FORGET = re.compile(r"^\s*!forgetme\s*$", re.IGNORECASE)
        self.RE_CMD_STATS = re.compile(r"^\s*!courtesy\s+stats\s*$", re.IGNORECASE)
        
        bot.save()

    def on_load(self):
        pass

    def on_unload(self):
        self._profile_cache.clear()

    def _gender_pattern(self) -> str:
        """Generate regex pattern for all supported gender identities."""
        genders = "|".join(re.escape(g) for g in self.GENDER_MAP.keys())
        return f"(?:{genders})"

    def _should_prompt_new_user(self, username: str) -> bool:
        """Check if we should prompt a new user for their preferences."""
        # Check if user has a profile
        if self._get_user_profile(username):
            return False
        
        # Check if we've already prompted them recently
        prompted_users = self.st.get("prompted_users", {})
        username_key = username.lower()
        
        if username_key in prompted_users:
            # Check if it was recent (within last 24 hours)
            last_prompt = prompted_users[username_key]
            time_since = time.time() - last_prompt
            return time_since > 86400  # 24 hours
        
        return True

    def _mark_user_prompted(self, username: str):
        """Mark that we've prompted this user."""
        prompted_users = self.st.get("prompted_users", {})
        prompted_users[username.lower()] = time.time()
        self.st["prompted_users"] = prompted_users
        self.bot.save()

    def _prompt_user_preferences(self, connection, event, username: str):
        """Politely prompt user to specify their preferences."""
        prompts = [
            f"Good day, {username}! I use neutral address by default. How would you prefer to be addressed? You may say 'Jeeves, I am [male/female/nonbinary]' or use commands like '!gender male' and '!pronouns he/him'.",
            f"Welcome, {username}! I shall address you as Mx. unless you specify otherwise. Feel free to tell me your preferred pronouns - try 'my pronouns are they/them' or '!pronouns she/her'.",
            f"Greetings, {username}! I default to neutral forms of address. If you'd prefer sir/madam or specific pronouns, please let me know - 'Jeeves, I am a woman' or '!gender female' work well.",
        ]
        
        prompt = random.choice(prompts)
        connection.privmsg(event.target, prompt)
        self._mark_user_prompted(username)

    def _normalize_pronouns(self, pronoun_str: str) -> str:
        """Normalize pronoun string to standard format."""
        cleaned = pronoun_str.strip().lower().replace(" ", "").replace("_", "").replace("-", "")
        
        # Check direct mappings
        if cleaned in self.PRONOUN_MAP:
            return self.PRONOUN_MAP[cleaned]
        
        # Handle slash-separated pronouns
        if "/" in cleaned:
            parts = cleaned.split("/")
            if len(parts) == 2:
                canonical = f"{parts[0]}/{parts[1]}"
                if canonical in self.PRONOUN_MAP:
                    return self.PRONOUN_MAP[canonical]
                return canonical
        
        # For unrecognized pronouns, return cleaned version
        if len(cleaned) <= 20 and re.match(r'^[a-z/]+', cleaned):
            return cleaned
        
        return "they/them"  # Default fallback

    def _normalize_gender_to_title(self, gender: str) -> str:
        """Convert gender identity to appropriate title."""
        gender_clean = gender.lower().strip()
        return self.GENDER_MAP.get(gender_clean, "neutral")

    def _set_user_profile(self, username: str, *, title=None, pronouns=None):
        """Set user profile with proper normalization and validation."""
        username_key = username.lower()
        
        # Use bot's method if available
        if hasattr(self.bot, 'set_profile'):
            self.bot.set_profile(username, title=title, pronouns=pronouns)
        
        # Update our local state
        profiles = self.st.get("profiles", {})
        profile = profiles.get(username_key, {})
        
        old_title = profile.get("title")
        old_pronouns = profile.get("pronouns")
        
        if title is not None:
            profile["title"] = title
        if pronouns is not None:
            profile["pronouns"] = pronouns
            
        profile["updated_at"] = datetime.now(UTC).isoformat()
        profile["updated_count"] = profile.get("updated_count", 0) + 1
        
        profiles[username_key] = profile
        self.st["profiles"] = profiles
        self.bot.save()
        
        # Update statistics
        self._update_profile_stats(username, title, pronouns, old_title, old_pronouns)
        
        # Clear cache
        self._last_cache_update = 0

    def _update_profile_stats(self, username: str, title, pronouns, old_title, old_pronouns):
        """Update profile statistics."""
        # Track if this is a new profile
        if old_title is None and old_pronouns is None:
            self.st["profiles_created"] = self.st.get("profiles_created", 0) + 1
            users_list = self.st.get("users_who_set_profiles", [])
            if username.lower() not in users_list:
                users_list.append(username.lower())
                self.st["users_who_set_profiles"] = users_list
        else:
            self.st["profiles_updated"] = self.st.get("profiles_updated", 0) + 1
        
        # Track pronoun popularity
        if pronouns:
            pronoun_stats = self.st.get("most_common_pronouns", {})
            pronoun_stats[pronouns] = pronoun_stats.get(pronouns, 0) + 1
            self.st["most_common_pronouns"] = pronoun_stats
        
        # Track title popularity
        if title:
            title_stats = self.st.get("most_common_titles", {})
            title_stats[title] = title_stats.get(title, 0) + 1
            self.st["most_common_titles"] = title_stats
        
        self.bot.save()

    def _get_user_profile(self, username: str):
        """Get user profile by username."""
        username_key = username.lower()
        profiles = self.st.get("profiles", {})
        return profiles.get(username_key)

    def on_pubmsg(self, connection, event, msg, username):
        room = event.target
        
        # Check for first-time user prompting
        if self._should_prompt_new_user(username):
            # Only prompt if they're not already using courtesy commands
            is_courtesy_command = any([
                self.RE_GENDER_SET.search(msg), self.RE_PRONOUNS_SET.search(msg),
                self.RE_NO_ASSUME.search(msg), self.RE_CMD_GENDER.match(msg),
                self.RE_CMD_PRONOUNS.match(msg), self.RE_CMD_WHOAMI.match(msg),
                self.RE_CMD_FORGET.match(msg)
            ])
            
            name_pat = getattr(self.bot, "JEEVES_NAME_RE", r"(?:jeeves|jeevesbot)")
            is_natural_courtesy = any([
                re.search(rf"\b{name_pat}", msg, re.IGNORECASE),
                re.search(r"\b(?:my\s+pronouns|i\s+am|i'm)", msg, re.IGNORECASE)
            ])
            
            # Prompt if engaging but not setting courtesy preferences
            if not is_courtesy_command and not is_natural_courtesy and len(msg.strip()) > 5:
                # Use a timer to delay the prompt slightly
                import threading
                timer = threading.Timer(2.0, lambda: self._prompt_user_preferences(connection, event, username))
                timer.start()

        # Natural language: "Jeeves, I am male/female/nb..."
        match = self.RE_GENDER_SET.search(msg)
        if match:
            gender = match.group(1).lower().strip()
            title = self._normalize_gender_to_title(gender)
            
            self._set_user_profile(username, title=title)
            self.st["natural_language_uses"] = self.st.get("natural_language_uses", 0) + 1
            self.bot.save()
            
            display_title = self.bot.title_for(username) if hasattr(self.bot, 'title_for') else title
            connection.privmsg(room, f"{username}, very good, {display_title}. I shall remember.")
            return True

        # Natural language: "my pronouns are X/Y"
        match = self.RE_PRONOUNS_SET.search(msg)
        if match:
            pronouns_raw = match.group(1)
            pronouns = self._normalize_pronouns(pronouns_raw)
            
            self._set_user_profile(username, pronouns=pronouns)
            self.st["natural_language_uses"] = self.st.get("natural_language_uses", 0) + 1
            self.bot.save()
            
            connection.privmsg(room, f"{username}, noted. I shall use {pronouns} henceforth.")
            return True

        # Natural language: "Jeeves, don't assume my gender"
        if self.RE_NO_ASSUME.search(msg):
            self._set_user_profile(username, title="neutral", pronouns="they/them")
            self.st["natural_language_uses"] = self.st.get("natural_language_uses", 0) + 1
            self.bot.save()
            
            connection.privmsg(room, f"{username}, as you wish. I shall keep to neutral address.")
            return True

        # Commands
        match = self.RE_CMD_GENDER.match(msg)
        if match:
            gender = match.group(1).strip()
            title = self._normalize_gender_to_title(gender)
            
            if title == "neutral" and gender.lower() not in self.GENDER_MAP:
                connection.privmsg(room, f"{username}, I'm not familiar with '{gender}'. Using neutral address.")
            
            self._set_user_profile(username, title=title)
            self.st["command_uses"] = self.st.get("command_uses", 0) + 1
            self.bot.save()
            
            display_title = self.bot.title_for(username) if hasattr(self.bot, 'title_for') else title
            connection.privmsg(room, f"{username}, recorded: {display_title}.")
            return True

        match = self.RE_CMD_PRONOUNS.match(msg)
        if match:
            pronouns_raw = match.group(1)
            pronouns = self._normalize_pronouns(pronouns_raw)
            
            self._set_user_profile(username, pronouns=pronouns)
            self.st["command_uses"] = self.st.get("command_uses", 0) + 1
            self.bot.save()
            
            connection.privmsg(room, f"{username}, recorded: {pronouns}.")
            return True

        if self.RE_CMD_WHOAMI.match(msg):
            profile = self._get_user_profile(username)
            
            if profile:
                title = profile.get("title", "neutral")
                pronouns = profile.get("pronouns", "they/them")
                updated_count = profile.get("updated_count", 1)
                
                connection.privmsg(room, 
                    f"{username}, I have you as title={title}, pronouns={pronouns} (updated {updated_count} times).")
            else:
                connection.privmsg(room, 
                    f"{username}, I have no notes on file. Shall I use neutral address? "
                    f"Try 'Jeeves, I am [gender]' or '!gender [identity]'")
            return True

        match = self.RE_CMD_PROFILE.match(msg)
        if match:
            target_user = match.group(1)
            profile = self._get_user_profile(target_user)
            
            if profile:
                title = profile.get("title", "neutral")
                pronouns = profile.get("pronouns", "they/them")
                connection.privmsg(room, f"{target_user}: title={title}, pronouns={pronouns}")
            else:
                connection.privmsg(room, f"No profile found for {target_user}.")
            return True

        if self.RE_CMD_FORGET.match(msg):
            profiles = self.st.get("profiles", {})
            username_key = username.lower()
            
            if profiles.pop(username_key, None) is not None:
                self.st["profiles"] = profiles
                self.st["profiles_deleted"] = self.st.get("profiles_deleted", 0) + 1
                self.bot.save()
                
                self._last_cache_update = 0  # Clear cache
                
                connection.privmsg(room, f"{username}, your preferences are removed. I shall address neutrally.")
            else:
                connection.privmsg(room, f"{username}, there were no preferences on file.")
            return True

        # Admin stats command
        if self.bot.is_admin(username) and self.RE_CMD_STATS.match(msg):
            profiles = self.st.get("profiles", {})
            total_profiles = len(profiles)
            pronoun_stats = self.st.get("most_common_pronouns", {})
            
            lines = [
                f"Profiles: {total_profiles}",
                f"Created: {self.st.get('profiles_created', 0)}",
                f"Updated: {self.st.get('profiles_updated', 0)}",
                f"Natural lang: {self.st.get('natural_language_uses', 0)}",
                f"Commands: {self.st.get('command_uses', 0)}"
            ]
            
            # Top pronouns
            if pronoun_stats:
                top_pronouns = sorted(pronoun_stats.items(), key=lambda x: x[1], reverse=True)[:3]
                pron_str = ", ".join(f"{p}({c})" for p, c in top_pronouns)
                lines.append(f"Top pronouns: {pron_str}")
            
            connection.privmsg(room, f"Courtesy stats: {'; '.join(lines)}")
            return True

        return False
