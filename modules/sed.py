# modules/sed.py
# A module for s/find/replace/ style text substitution.
import re
from collections import deque
from typing import Optional, Dict, Any
from .base import SimpleCommandModule

def setup(bot, config):
    return Sed(bot, config)

class Sed(SimpleCommandModule):
    name = "sed"
    version = "1.1.0"
    description = "Provides s/find/replace/ text substitution."

    SED_PATTERN = re.compile(r"^\s*s/((?:\\/|[^/])+)/((?:\\/|[^/])*)/(i?)\s*$")

    def __init__(self, bot, config):
        super().__init__(bot)
        self._load_config(config)
        self.history: Dict[str, deque] = {}

    def _load_config(self, config: Dict[str, Any]):
        self.MODE = config.get("mode", "self")  # "self" or "any"
        self.HISTORY_SIZE = config.get("history_size", 10)

    def on_config_reload(self, new_config: Dict[str, Any]):
        self._load_config(new_config)

    def _register_commands(self):
        # This module has no !commands, it only listens for ambient messages.
        pass

    def on_ambient_message(self, connection, event, msg: str, username: str) -> bool:
        channel = event.target
        
        # First, check if this message is a sed command
        sed_match = self.SED_PATTERN.match(msg)
        if sed_match:
            find, replace, flags = sed_match.groups()
            find = find.replace('\\/', '/')
            replace = replace.replace('\\/', '/')
            
            # Determine whose message to search
            target_user = None if self.MODE == "any" else username
            
            # Search history for a match
            for prev_user, prev_msg in reversed(self.history.get(channel, [])):
                if target_user and prev_user != target_user:
                    continue
                
                try:
                    re_flags = re.IGNORECASE if 'i' in flags else 0
                    if re.search(find, prev_msg, flags=re_flags):
                        # Found a match, perform replacement
                        new_msg, count = re.subn(find, replace, prev_msg, count=1, flags=re_flags)
                        if count > 0:
                            title = self.bot.title_for(username)
                            self.safe_reply(connection, event, f"I believe {prev_user} meant to say: {new_msg}")
                            # Add the corrected message to history so it can also be corrected
                            self._add_to_history(channel, prev_user, new_msg)
                            return True # Handled
                except re.error:
                    # Ignore invalid regex patterns
                    pass
            
            return True # Consume the message even if no match was found

        # If it's not a sed command, add it to history
        self._add_to_history(channel, username, msg)
        return False

    def _add_to_history(self, channel: str, username: str, msg: str):
        if channel not in self.history:
            self.history[channel] = deque(maxlen=self.HISTORY_SIZE)
        self.history[channel].append((username, msg))

