# modules/flirt.py
# Enhanced polite flirt handling
import re
import time
import random
import functools
from typing import Optional, Dict, Any, List, Callable, Union
from .base import SimpleCommandModule, admin_required

def setup(bot):
    return Flirt(bot)

class Flirt(SimpleCommandModule):
    name = "flirt"
    version = "3.0.0" # Dynamic configuration refactor
    description = "Polite and professional flirt handling."

    def __init__(self, bot):
        super().__init__(bot)
        
        self.set_state("total_flirts_received", self.get_state("total_flirts_received", 0))
        self.set_state("responses_given", self.get_state("responses_given", 0))
        self.set_state("last_global_response", self.get_state("last_global_response", 0.0))
        self.set_state("user_last_response", self.get_state("user_last_response", {}))
        self.save_state()
        
        name_pat = getattr(self.bot, "JEEVES_NAME_RE", r"(?:jeeves|jeevesbot)")
        self.patterns = {
            "greeting": re.compile(rf"\b(?:{name_pat}[,!\s]*(?:hi|hello|hey|yo|howdy|greetings|good\s+(?:morning|afternoon|evening|day))|(?:hi|hello|hey|yo|howdy|greetings|good\s+(?:morning|afternoon|evening|day))[,!\s]*{name_pat}|{name_pat}[,!\s]*how\s+are\s+you|how\s+are\s+you[,!\s]*{name_pat})\b", re.IGNORECASE),
            "marry": re.compile(rf"\b(?:{name_pat}[,!\s]*)?(marry\s+me|marry\s+us)\b", re.IGNORECASE),
            "date": re.compile(rf"\b(?:{name_pat}[,!\s]*)?(date\s+me|go\s+out\s+with\s+me)\b", re.IGNORECASE),
            "like_me": re.compile(rf"\b(?:{name_pat}[,!\s]*)?(do\s+you\s+like\s+me|do\s+you\s+fancy\s+me)\b", re.IGNORECASE),
            "love_you": re.compile(rf"\b(i\s+love\s+you[,!\s]*{name_pat}|love\s+you[,!\s]*{name_pat})\b", re.IGNORECASE),
            "kiss": re.compile(rf"\b(?:{name_pat}[,!\s]*)?(kiss\s+me|mwah|muah|blow\s+a\s+kiss)\b", re.IGNORECASE),
            "compliment_me": re.compile(rf"\b(?:{name_pat}[,!\s]*)?(am\s+i\s+(cute|handsome|pretty|attractive)|do\s+you\s+think\s+i'?m\s+(cute|handsome|pretty|attractive))\b", re.IGNORECASE),
            "be_mine": re.compile(rf"\b(?:{name_pat}[,!\s]*)?(be\s+my\s+(boyfriend|girlfriend|partner)|you'?re\s+mine[,!]?\s*{name_pat})\b", re.IGNORECASE),
            "i_want_you": re.compile(rf"\b(?:{name_pat}[,!\s]*)?i\s+want\s+you\b", re.IGNORECASE),
            "flirt_generic": re.compile(rf"\b(?:{name_pat}[,!\s]*)?(flirt\s+with\s+me|you'?re\s+(hot|sexy|cute))\b", re.IGNORECASE),
        }

    def _register_commands(self):
        self.register_command(r"^\s*!flirt\s+stats\s*$", self._cmd_stats,
                              name="flirt stats", admin_only=True, description="Show flirt statistics.")
        self.register_command(r"^\s*!flirt\s+reset\s*$", self._cmd_reset,
                              name="flirt reset", admin_only=True, description="Reset flirt cooldowns.")

    def on_ambient_message(self, connection, event, msg: str, username: str) -> bool:
        if not self.is_enabled(event.target):
            return False
            
        for intent, pattern in self.patterns.items():
            if pattern.search(msg):
                if self._handle_flirt(connection, event, intent, username):
                    return True
        return False

    def _can_respond_globally(self, channel: str) -> bool:
        cooldown = self.get_config_value("global_cooldown", channel, 30.0)
        last_response = self.get_state("last_global_response", 0.0)
        return time.time() - last_response >= cooldown

    def _can_respond_to_user(self, username: str, channel: str) -> bool:
        cooldown = self.get_config_value("per_user_cooldown", channel, 60.0)
        user_responses = self.get_state("user_last_response", {})
        last_response = user_responses.get(username.lower(), 0.0)
        return time.time() - last_response >= cooldown

    def _handle_flirt(self, connection, event, intent: str, username: str) -> bool:
        channel = event.target
        if not self._can_respond_globally(channel) or not self._can_respond_to_user(username, channel):
            return False
        
        reply = self._choose_reply(intent, username)
        self.safe_reply(connection, event, f"{username}, {reply}")

        self.set_state("total_flirts_received", self.get_state("total_flirts_received") + 1)
        self.set_state("responses_given", self.get_state("responses_given") + 1)
        self.set_state("last_global_response", time.time())
        user_last_response = self.get_state("user_last_response", {})
        user_last_response[username.lower()] = time.time()
        self.set_state("user_last_response", user_last_response)
        self.save_state()
        return True

    def _get_reply_templates(self):
        return {"greeting": ["Good day to you, {title}!", "A pleasure to see you, {title}.", "Well, thank you for asking, {title}—ever at your service.", "Hello, {title}. How may I be of assistance?", "Delighted to hear from you, {title}.", "At your service as always, {title}.", "Most pleased to greet you, {title}."], "marry": ["An honour to be asked, but alas I am already married to my duties, {title}.", "I fear matrimony would interfere with my housekeeping, {title}."], "date": ["My calendar is devoted to your convenience, not my own, {title}, I'm afraid.", "I must decline, {title}, but shall cheerfully arrange a splendid evening for you nonetheless."],"like_me": ["Immensely—in the professional sense, {title}.", "With the fondness appropriate to a devoted servant, {title}."], "love_you": ["With due propriety, {title}, I reserve my affections for excellence and punctuality.", "A butler's heart belongs to the household, {title}."], "kiss": ["I shall offer a bow of precisely the correct depth instead, {title}.", "A discreet nod must suffice; one does try to keep fingerprints off the silver, {title}."], "compliment_me": ["Radiant, if I may say so, {title}—and I have your pronouns as {pronouns}.", "Positively dashing—one might even call it 'server-room chic,' {title}."], "be_mine": ["I am yours already, {title}—professionally, comprehensively, and on retainer.", "At your service, {title}—ever and always, within policy."], "i_want_you": ["I recommend wanting tea and biscuits, {title}; I can supply those at once.", "Allow me to redirect that admirable enthusiasm toward refreshments, {title}."], "flirt_generic": ["Flattery will get you excellent service and a fresh napkin, {title}.", "One blushes, discreetly, and fetches the tea, {title}."], "fallback": ["You are charming; I remain dutiful, {title}.", "Ever your servant—professionally immaculate, {title}."]}

    def _choose_reply(self, intent: str, username: str) -> str:
        templates = self._get_reply_templates()
        template_list = templates.get(intent, templates["fallback"])
        title = self.bot.title_for(username)
        pronouns = self.bot.pronouns_for(username)
        template = random.choice(template_list)
        return template.format(title=title, pronouns=pronouns)

    @admin_required
    def _cmd_stats(self, connection, event, msg, username, match):
        total = self.get_state("total_flirts_received", 0)
        responded = self.get_state("responses_given", 0)
        rate = (responded / total * 100) if total > 0 else 0
        self.safe_reply(connection, event, f"Flirt stats: Received={total}, Responded={responded} ({rate:.1f}% response rate).")
        return True

    @admin_required
    def _cmd_reset(self, connection, event, msg, username, match):
        self.set_state("last_global_response", 0.0)
        self.set_state("user_last_response", {})
        self.save_state()
        self.safe_reply(connection, event, "Flirt cooldowns have been reset.")
        return True
