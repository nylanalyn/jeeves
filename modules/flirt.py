# modules/flirt.py
# Enhanced polite flirt handling using the ResponseModule framework
import re
import time
import random
from typing import Optional
from .base import ResponseModule

def setup(bot):
    return Flirt(bot)

class Flirt(ResponseModule):
    name = "flirt"
    version = "2.1.0"
    description = "Polite and professional flirt handling."
    
    # Configuration
    GLOBAL_COOLDOWN = 30.0  # seconds between any flirt responses
    PER_USER_COOLDOWN = 60.0  # seconds before same user can trigger again

    def __init__(self, bot):
        super().__init__(bot)
        
        # Initialize state
        self.set_state("total_flirts_received", self.get_state("total_flirts_received", 0))
        self.set_state("responses_given", self.get_state("responses_given", 0))
        self.set_state("intent_counts", self.get_state("intent_counts", {}))
        self.set_state("unique_flirters", self.get_state("unique_flirters", []))
        self.set_state("last_global_response", self.get_state("last_global_response", 0.0))
        self.set_state("user_last_response", self.get_state("user_last_response", {}))
        
        self.save_state()
        
        self._register_responses()

    def _register_responses(self):
        """Add all flirt response patterns."""
        name_pat = getattr(self.bot, "JEEVES_NAME_RE", r"(?:jeeves|jeevesbot)")

        # Each pattern has a custom handler that checks cooldowns and chooses a reply
        self.add_response_pattern(
            re.compile(rf"\b(?:{name_pat}[,!\s]*)?(marry\s+me|marry\s+us)\b", re.IGNORECASE),
            lambda msg, user: self._handle_flirt("marry", user),
        )
        self.add_response_pattern(
            re.compile(rf"\b(?:{name_pat}[,!\s]*)?(date\s+me|go\s+out\s+with\s+me)\b", re.IGNORECASE),
            lambda msg, user: self._handle_flirt("date", user),
        )
        self.add_response_pattern(
            re.compile(rf"\b(?:{name_pat}[,!\s]*)?(do\s+you\s+like\s+me|do\s+you\s+fancy\s+me)\b", re.IGNORECASE),
            lambda msg, user: self._handle_flirt("like_me", user),
        )
        self.add_response_pattern(
            re.compile(rf"\b(i\s+love\s+you[,!\s]*{name_pat}|love\s+you[,!\s]*{name_pat})\b", re.IGNORECASE),
            lambda msg, user: self._handle_flirt("love_you", user),
        )
        self.add_response_pattern(
            re.compile(rf"\b(?:{name_pat}[,!\s]*)?(kiss\s+me|mwah|muah|blow\s+a\s+kiss)\b", re.IGNORECASE),
            lambda msg, user: self._handle_flirt("kiss", user),
        )
        self.add_response_pattern(
            re.compile(rf"\b(?:{name_pat}[,!\s]*)?(am\s+i\s+(cute|handsome|pretty|attractive)|do\s+you\s+think\s+i'?m\s+(cute|handsome|pretty|attractive))\b", re.IGNORECASE),
            lambda msg, user: self._handle_flirt("compliment_me", user),
        )
        self.add_response_pattern(
            re.compile(rf"\b(?:{name_pat}[,!\s]*)?(be\s+my\s+(boyfriend|girlfriend|partner)|you'?re\s+mine[,!]?\s*{name_pat})\b", re.IGNORECASE),
            lambda msg, user: self._handle_flirt("be_mine", user),
        )
        self.add_response_pattern(
            re.compile(rf"\b(?:{name_pat}[,!\s]*)?i\s+want\s+you\b", re.IGNORECASE),
            lambda msg, user: self._handle_flirt("i_want_you", user),
        )
        self.add_response_pattern(
            re.compile(rf"\b(?:{name_pat}[,!\s]*)?(flirt\s+with\s+me|you'?re\s+(hot|sexy|cute))\b", re.IGNORECASE),
            lambda msg, user: self._handle_flirt("flirt_generic", user),
        )

        # Admin stats command (registered as a command, not a response)
        self.register_command(r"^\s*!flirt\s+stats\s*$", self._cmd_stats,
                              admin_only=True, description="Show flirt statistics.")
        self.register_command(r"^\s*!flirt\s+reset\s*$", self._cmd_reset,
                              admin_only=True, description="Reset flirt cooldowns.")

    def _handle_flirt(self, intent: str, username: str) -> Optional[str]:
        """Handles a flirt attempt and returns a response if cooldowns are clear."""
        # Use the base class's rate limiting
        if not self.check_rate_limit("global", self.GLOBAL_COOLDOWN):
            return None
        
        if not self.check_user_cooldown(username, "flirt", self.PER_USER_COOLDOWN):
            return None

        reply = self._choose_reply(intent, username)
        
        # Update stats
        self.update_state({
            "total_flirts_received": self.get_state("total_flirts_received") + 1,
            "responses_given": self.get_state("responses_given") + 1,
        })
        intent_counts = self.get_state("intent_counts", {})
        intent_counts[intent] = intent_counts.get(intent, 0) + 1
        self.set_state("intent_counts", intent_counts)
        unique_flirters = self.get_state("unique_flirters", [])
        if username.lower() not in unique_flirters:
            unique_flirters.append(username.lower())
            self.set_state("unique_flirters", unique_flirters)
        
        self.save_state()

        return f"{username}, {reply}"

    def _choose_reply(self, intent: str, username: str) -> str:
        # ... (same logic as before) ...
        pass

    # Command handlers for admin commands
    def _cmd_stats(self, connection, event, msg, username, match):
        stats = self.get_state()
        # ... (same stats logic as before) ...
        self.safe_reply(connection, event, f"Flirt stats: {'; '.join(lines)}")
        return True

    def _cmd_reset(self, connection, event, msg, username, match):
        self.update_state({
            "last_global_response": 0.0,
            "user_last_response": {}
        })
        self.save_state()
        self.safe_reply(connection, event, "Flirt cooldowns reset.")
        return True