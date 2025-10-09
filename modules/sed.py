# modules/sed.py
# A module for handling sed-like s/find/replace syntax.
import re
import signal
from collections import deque
from .base import SimpleCommandModule

def setup(bot):
    return Sed(bot)

class Sed(SimpleCommandModule):
    name = "sed"
    version = "2.0.0" # Dynamic configuration refactor
    description = "Performs s/find/replace/ on recent channel messages."

    SED_PATTERN = re.compile(r"^\s*s/([^/]+)/([^/]*)/?\s*$")

    def __init__(self, bot):
        super().__init__(bot)
        self.history = {} # Keyed by channel, contains deques

    def _register_commands(self):
        # This module has no !commands.
        pass

    def _add_to_history(self, channel, username, message):
        history_size = self.get_config_value("history_size", channel, 20)
        if channel not in self.history:
            self.history[channel] = deque(maxlen=history_size)
        
        # If config changed, update the deque's maxlen
        if self.history[channel].maxlen != history_size:
            self.history[channel] = deque(self.history[channel], maxlen=history_size)

        self.history[channel].append({'user': username, 'msg': message})

    def _highlight_replacement(self, pattern: str, replacement: str, original: str, new_text: str) -> str:
        """Return the new text with the replaced segment wrapped in *...* markers."""
        try:
            match_obj = re.search(pattern, original)
            if not match_obj:
                return new_text

            replaced_value = match_obj.expand(replacement)
            if not replaced_value:
                return new_text

            return f"{original[:match_obj.start()]}*{replaced_value}*{original[match_obj.end():]}"
        except re.error:
            return new_text

    def on_ambient_message(self, connection, event, msg: str, username: str) -> bool:
        if not self.is_enabled(event.target):
            return False
            
        if event.source.nick == self.bot.connection.get_nickname():
            return False

        match = self.SED_PATTERN.match(msg)
        self._add_to_history(event.target, username, msg)

        if not match:
            return False

        find, replace = match.groups()
        channel_history = self.history.get(event.target, [])
        mode = self.get_config_value("mode", event.target, "self")
        
        # Validate regex complexity to prevent ReDoS attacks
        if not self._is_safe_regex(find):
            return False

        # Iterate backwards through history, skipping the sed command itself
        for prev_chat in reversed(list(channel_history)[:-1]):
            if mode == "self" and prev_chat['user'].lower() != username.lower():
                continue

            try:
                # Perform substitution with timeout protection
                new_msg, count = self._safe_regex_subn(find, replace, prev_chat['msg'])
                if count > 0:
                    title = self.bot.title_for(username)
                    display_msg = self._highlight_replacement(find, replace, prev_chat['msg'], new_msg)
                    self.safe_reply(connection, event, f"As {title} noted, {prev_chat['user']} meant to say: {display_msg}")
                    self._add_to_history(event.target, prev_chat['user'], new_msg)
                    return True
            except (re.error, ValueError):
                return False # Invalid or dangerous regex, ignore silently.

        return False

    def _is_safe_regex(self, pattern: str) -> bool:
        """Check if regex pattern is safe from ReDoS attacks."""
        # Reject patterns that are too long
        if len(pattern) > 100:
            return False

        # Reject patterns with excessive repetition operators
        dangerous_patterns = [
            r'\+.*\+',      # Multiple consecutive +
            r'\*.*\*',      # Multiple consecutive *
            r'\{.*\{',      # Nested quantifiers
            r'(\(.*\+.*\))\+',  # Nested groups with repetition
            r'(\(.*\*.*\))\*',  # Nested groups with repetition
        ]

        for dangerous in dangerous_patterns:
            if re.search(dangerous, pattern):
                self.bot.log_debug(f"[sed] Rejected potentially dangerous regex: {pattern}")
                return False

        return True

    def _safe_regex_subn(self, pattern: str, replacement: str, text: str, timeout: int = 1) -> tuple:
        """Perform regex substitution with timeout protection."""
        result = [None, 0]
        exception = [None]

        def handler(signum, frame):
            raise TimeoutError("Regex operation timed out")

        def do_subn():
            try:
                result[0], result[1] = re.subn(pattern, replacement, text, count=1)
            except Exception as e:
                exception[0] = e

        # On Unix-like systems, use signal-based timeout
        try:
            old_handler = signal.signal(signal.SIGALRM, handler)
            signal.alarm(timeout)
            try:
                do_subn()
            finally:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)

            if exception[0]:
                raise exception[0]
            if result[0] is None:
                raise ValueError("Regex operation failed")

            return result[0], result[1]
        except (AttributeError, ValueError):
            # signal.SIGALRM not available on Windows, fall back to simple execution
            do_subn()
            if exception[0]:
                raise exception[0]
            return result[0], result[1]
