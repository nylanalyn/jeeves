# modules/courtesy.py
# Courtesy ledger: gender titles & pronouns with friendly natural-language triggers.
# Works with "Jeeves" or "JeevesBot", allows "I'm a man/woman", and stores profiles case-insensitively.
import re
from datetime import datetime, timezone

UTC = timezone.utc

def setup(bot): return Courtesy(bot)

class Courtesy:
    name = "courtesy"

    def __init__(self, bot):
        self.bot = bot
        self.st = bot.get_module_state(self.name)  # unused, but available

        # Addressable names (tab-complete friendly)
        name_pat = getattr(self.bot, "JEEVES_NAME_RE", r"(?:jeeves|jeevesbot)")

        # Natural language:
        # "JeevesBot, I am male" / "Jeeves, I'm a woman" / "Jeeves, I am non-binary / nb / enby / neutral"
        self.RE_GENDER_SET = re.compile(
            rf"\b{name_pat}[,!\s]*\b(i\s*am|i'?m)\s*(?:a\s+)?"
            r"(male|man|female|woman|non[-\s]*binary|nb|enby|neutral)\b",
            re.IGNORECASE
        )
        # "my pronouns are they/them"  or  "pronouns: she/her"
        self.RE_PRONOUNS_SET = re.compile(
            r"\b(my\s+pronouns\s+are|pronouns[:\s]+)\s*([a-zA-Z/ -]{2,40})\b",
            re.IGNORECASE
        )
        # "Jeeves, don't assume my gender"
        self.RE_NO_ASSUME = re.compile(
            rf"\b{name_pat}[,!\s]*\b(don'?t\s+assume\s+my\s+gender)\b",
            re.IGNORECASE
        )

        # Commands
        self.RE_CMD_GENDER   = re.compile(r"^\s*!gender\s+(male|female|neutral|nonbinary|nb|enby)\s*$", re.IGNORECASE)
        self.RE_CMD_PRONOUNS = re.compile(r"^\s*!pronouns\s+([a-zA-Z/ -]{2,40})\s*$", re.IGNORECASE)
        self.RE_CMD_WHOAMI   = re.compile(r"^\s*!whoami\s*$", re.IGNORECASE)
        self.RE_CMD_FORGET   = re.compile(r"^\s*!forgetme\s*$", re.IGNORECASE)

    # ---------- helpers ----------
    def _normalize_title_from_gender(self, g: str) -> str:
        g = g.lower().strip()
        if g in ("male", "man"): return "sir"
        if g in ("female", "woman"): return "madam"
        # nonbinary / nb / enby / neutral
        return "neutral"

    def _normalize_pronouns(self, s: str) -> str:
        s = s.strip().lower().replace(" ", "")
        if s in ("he/him","hehim","he"): return "he/him"
        if s in ("she/her","sheher","she"): return "she/her"
        if s in ("they/them","theythem","they"): return "they/them"
        # allow custom sets (ze/zir, fae/faer, etc.)
        return s.replace("//", "/")

    def _set_profile_lower(self, nick: str, *, title=None, pronouns=None):
        """
        Store profiles case-insensitively by keying on lowercase nick.
        Uses bot.set_profile if present; also ensures the stored key is lowercase.
        """
        nick_key = nick.lower()

        # If core provides set_profile, call it first (so any core hooks run)
        if hasattr(self.bot, "set_profile"):
            self.bot.set_profile(nick, title=title, pronouns=pronouns)

        # Ensure lowercase key in bot.state regardless of core implementation
        profiles = self.bot.state.setdefault("profiles", {})
        # If there is a mixed-case entry, merge it down
        if nick in profiles and nick != nick_key:
            existing = profiles.pop(nick)
            profiles[nick_key] = {**existing, **profiles.get(nick_key, {})}

        prof = profiles.get(nick_key, {})
        if title is not None:
            prof["title"] = title
        if pronouns is not None:
            prof["pronouns"] = pronouns
        prof["set_at"] = datetime.now(UTC).isoformat()
        profiles[nick_key] = prof

        # Persist
        if hasattr(self.bot, "save"):
            self.bot.save()

    def _title_for(self, nick: str) -> str:
        # Use core helper if available; fallback to reading state directly
        if hasattr(self.bot, "title_for"):
            return self.bot.title_for(nick)
        prof = self.bot.state.get("profiles", {}).get(nick.lower(), {})
        t = prof.get("title")
        return t if t in ("sir", "madam") else "Mx."

    # ---------- IRC hook ----------
    def on_pubmsg(self, connection, event, msg, username):
        # Natural: "JeevesBot, I am male/female/nb..."
        m = self.RE_GENDER_SET.search(msg)
        if m:
            gender = m.group(2)
            title = self._normalize_title_from_gender(gender)
            self._set_profile_lower(username, title=title)
            connection.privmsg(event.target, f"{username}, very good, {self._title_for(username)}. I shall remember.")
            return True

        # Natural: "my pronouns are X/Y" or "pronouns: X/Y"
        m = self.RE_PRONOUNS_SET.search(msg)
        if m:
            pron = self._normalize_pronouns(m.group(2))
            self._set_profile_lower(username, pronouns=pron)
            connection.privmsg(event.target, f"{username}, noted. I shall use {pron} henceforth.")
            return True

        # Natural: "Jeeves, don't assume my gender"
        if self.RE_NO_ASSUME.search(msg):
            self._set_profile_lower(username, title="neutral", pronouns="they/them")
            connection.privmsg(event.target, f"{username}, as you wish. I shall keep to neutral address.")
            return True

        # Commands
        m = self.RE_CMD_GENDER.match(msg)
        if m:
            g = m.group(1).lower()
            # normalize aliases
            if g in ("nonbinary","nb","enby"): g = "neutral"
            title = self._normalize_title_from_gender(g)
            self._set_profile_lower(username, title=title)
            connection.privmsg(event.target, f"{username}, recorded: {self._title_for(username)}.")
            return True

        m = self.RE_CMD_PRONOUNS.match(msg)
        if m:
            pron = self._normalize_pronouns(m.group(1))
            self._set_profile_lower(username, pronouns=pron)
            connection.privmsg(event.target, f"{username}, recorded: {pron}.")
            return True

        if self.RE_CMD_WHOAMI.match(msg):
            prof = self.bot.state.get("profiles", {}).get(username.lower(), {})
            if prof:
                t = prof.get("title", "neutral")
                p = prof.get("pronouns", "they/them")
                connection.privmsg(event.target, f"{username}, I have you as title={t}, pronouns={p}.")
            else:
                connection.privmsg(event.target, f"{username}, I have no notes on file; shall I adopt neutral address?")
            return True

        if self.RE_CMD_FORGET.match(msg):
            profiles = self.bot.state.get("profiles", {})
            if profiles.pop(username.lower(), None) is not None:
                if hasattr(self.bot, "save"):
                    self.bot.save()
                connection.privmsg(event.target, f"{username}, your preferences are removed. I shall address neutrally.")
            else:
                connection.privmsg(event.target, f"{username}, there were no preferences on file.")
            return True

        return False

