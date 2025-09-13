# modules/flirt.py
# Polite flirt handling for Jeeves (pronoun-aware).
import re
import time
import random

FLIRT_COOLDOWN = 30  # seconds (global)

def setup(bot):
    return Flirt(bot)

class Flirt:
    name = "flirt"

    def __init__(self, bot):
        self.bot = bot
        self.st = bot.get_module_state(self.name)  # persisted dict
        self.st.setdefault("last_reply_epoch", 0.0)
        self._compile_patterns()
        self._build_replies()

    def on_load(self):  # not used
        pass

    def on_unload(self):
        pass

    # ---------- internals ----------
    def _compile_patterns(self):
        name_pat = getattr(self.bot, "JEEVES_NAME_RE", r"(?:jeeves|jeevesbot)")
        self.patterns = {
            "marry":         re.compile(rf"\b(?:{name_pat}[,!\s]*)?(marry\s+me|marry\s+us)\b", re.IGNORECASE),
            "date":          re.compile(rf"\b(?:{name_pat}[,!\s]*)?(date\s+me|go\s+out\s+with\s+me)\b", re.IGNORECASE),
            "like_me":       re.compile(rf"\b(?:{name_pat}[,!\s]*)?(do\s+you\s+like\s+me|do\s+you\s+fancy\s+me)\b", re.IGNORECASE),
            "love_you":      re.compile(rf"\b(i\s+love\s+you[,!\s]*{name_pat}|love\s+you[,!\s]*{name_pat})\b", re.IGNORECASE),
            "kiss":          re.compile(rf"\b(?:{name_pat}[,!\s]*)?(kiss\s+me|mwah|muah|blow\s+a\s+kiss)\b", re.IGNORECASE),
            "compliment_me": re.compile(rf"\b(?:{name_pat}[,!\s]*)?(am\s+i\s+(cute|handsome|pretty|attractive)|do\s+you\s+think\s+i'?m\s+(cute|handsome|pretty|attractive))\b", re.IGNORECASE),
            "be_mine":       re.compile(rf"\b(?:{name_pat}[,!\s]*)?(be\s+my\s+(boyfriend|girlfriend|partner)|you'?re\s+mine[,!]?\s*{name_pat})\b", re.IGNORECASE),
            "i_want_you":    re.compile(rf"\b(?:{name_pat}[,!\s]*)?i\s+want\s+you\b", re.IGNORECASE),
            "flirt_generic": re.compile(rf"\b(?:{name_pat}[,!\s]*)?(flirt\s+with\s+me|you'?re\s+(hot|sexy|cute))\b", re.IGNORECASE),
        }

    def _build_replies(self):
        # Include {title} and {pronouns} placeholders
        self.replies = {
            "marry": [
                "An honour to be asked, but alas I am already married to my duties, {title}.",
                "I fear matrimony would interfere with my housekeeping, {title}.",
                "My schedule leaves little room for vows beyond those to service, {title}."
            ],
            "date": [
                "My calendar is devoted to your convenience, not my own, {title}, I’m afraid.",
                "I must decline, {title}, but shall cheerfully arrange a splendid evening for you nonetheless.",
                "Alas, I am all appointments and brass polish, not courtship, {title}."
            ],
            "like_me": [
                "Immensely—in the professional sense, {title}.",
                "With the fondness appropriate to a devoted servant, {title}.",
                "I esteem you highly, {title}—strictly within the remit of service."
            ],
            "love_you": [
                "With due propriety, {title}, I reserve my affections for excellence and punctuality.",
                "A butler’s heart belongs to the household, {title}.",
                "In my fashion, yes—loyalty is the butler’s love language, {title}."
            ],
            "kiss": [
                "I shall offer a bow of precisely the correct depth instead, {title}.",
                "A discreet nod must suffice; one does try to keep fingerprints off the silver, {title}.",
                "I fear HR would frown; may I offer tea instead, {title}?"
            ],
            "compliment_me": [
                "Radiant, if I may say so, {title}—and I have your pronouns as {pronouns}.",
                "Positively dashing—one might even call it ‘server-room chic,’ {title}.",
                "You cut a fine figure, {title}; the carpet approves."
            ],
            "be_mine": [
                "I am yours already, {title}—professionally, comprehensively, and on retainer.",
                "At your service, {title}—ever and always, within policy.",
                "I belong to the bell, as tradition dictates, {title}."
            ],
            "i_want_you": [
                "I recommend wanting tea and biscuits, {title}; I can supply those at once.",
                "Allow me to redirect that admirable enthusiasm toward refreshments, {title}.",
                "Desire noted, {title}; I’ll file it under ‘appreciations’ between candlesticks and cufflinks."
            ],
            "flirt_generic": [
                "Flattery will get you excellent service and a fresh napkin, {title}.",
                "One blushes, discreetly, and fetches the tea, {title}.",
                "You are most kind; shall I book a table as well, {title}?"
            ],
            "fallback": [
                "You are charming; I remain dutiful, {title}.",
                "Ever your servant—professionally immaculate, {title}.",
                "Consider me flattered and reliably at your disposal, {title}."
            ],
        }

    def _choose_reply(self, intent: str) -> str:
        return random.choice(self.replies.get(intent) or self.replies["fallback"])

    # ---------- IRC hook ----------
    def on_pubmsg(self, connection, event, msg, username):
        now = time.time()
        if now - float(self.st.get("last_reply_epoch", 0.0)) < FLIRT_COOLDOWN:
            return False

        intent_hit = None
        for intent, pattern in self.patterns.items():
            if pattern.search(msg):
                intent_hit = intent
                break
        if not intent_hit:
            return False

        title = self.bot.title_for(username)
        pronouns = self.bot.pronouns_for(username)
        line = self._choose_reply(intent_hit).format(title=title, pronouns=pronouns)
        connection.privmsg(event.target, f"{username}, {line}")

        self.st["last_reply_epoch"] = now
        self.bot.save()
        return True

