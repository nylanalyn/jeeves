# modules/sed.py
# A module for handling sed-like s/find/replace syntax.
import re
from collections import deque
from .base import SimpleCommandModule

def setup(bot, config):
    return Sed(bot, config)

class Sed(SimpleCommandModule):
    name = "sed"
    version = "2.0.0" # Dynamic configuration refactor
    description = "Performs s/find/replace/ on recent channel messages."

    SED_PATTERN = re.compile(r"^\s*s/([^/]+)/([^/]*)/?\s*$")

    def __init__(self, bot, config):
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
        
        # Iterate backwards through history, skipping the sed command itself
        for prev_chat in reversed(list(channel_history)[:-1]):
            if mode == "self" and prev_chat['user'].lower() != username.lower():
                continue

            try:
                new_msg, count = re.subn(find, replace, prev_chat['msg'], count=1)
                if count > 0:
                    title = self.bot.title_for(username)
                    self.safe_reply(connection, event, f"As {title} noted, {prev_chat['user']} meant to say: {new_msg}")
                    self._add_to_history(event.target, prev_chat['user'], new_msg)
                    return True
            except re.error:
                return False # Invalid regex, ignore silently.

        return False
