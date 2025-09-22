# modules/sed.py
# A module for handling sed-like s/find/replace syntax.
import re
from collections import deque
from .base import SimpleCommandModule

def setup(bot, config):
    return Sed(bot, config)

class Sed(SimpleCommandModule):
    name = "sed"
    version = "1.0.2"
    description = "Performs s/find/replace/ on recent channel messages."

    # This regex makes the final slash optional with /?
    SED_PATTERN = re.compile(r"^\s*s/([^/]+)/([^/]*)/?\s*$")

    def __init__(self, bot, config):
        super().__init__(bot)
        self.history = {} # Keyed by channel
        self.on_config_reload(config)

    def on_config_reload(self, config):
        self.mode = config.get("mode", "self") # "self" or "any"
        self.history_size = config.get("history_size", 20)
    
    def _register_commands(self):
        # This module has no !commands, only an ambient trigger.
        pass

    def _add_to_history(self, channel, username, message):
        if channel not in self.history:
            self.history[channel] = deque(maxlen=self.history_size)
        self.history[channel].append({'user': username, 'msg': message})

    def on_ambient_message(self, connection, event, msg: str, username: str) -> bool:
        # Don't process commands from the bot itself.
        if event.source.nick == self.bot.connection.get_nickname():
            return False

        match = self.SED_PATTERN.match(msg)

        # Log the message to history for potential future corrections.
        # We do this before checking for a match so the sed command itself is logged.
        self._add_to_history(event.target, username, msg)

        if not match:
            return False # Not a sed command, so we're done.

        find, replace = match.groups()
        channel_history = self.history.get(event.target, [])
        
        # Iterate backwards through recent history to find a message to correct.
        # We skip the very last message, which is the sed command itself.
        for prev_chat in reversed(list(channel_history)[:-1]):
            prev_user = prev_chat['user']
            prev_msg = prev_chat['msg']

            # Enforce mode: 'self' means you can only correct your own last message.
            if self.mode == "self" and prev_user.lower() != username.lower():
                continue

            try:
                # Attempt to perform the substitution.
                new_msg, count = re.subn(find, replace, prev_msg, count=1)
                if count > 0:
                    # On success, post the correction and stop searching.
                    title = self.bot.title_for(username)
                    self.safe_reply(connection, event, f"As {title} pointed out, {prev_user} meant to say: {new_msg}")
                    # Add the corrected message to history so it can also be corrected.
                    self._add_to_history(event.target, prev_user, new_msg)
                    return True # Handled
            except re.error:
                # The user provided an invalid regex in the 'find' part. Ignore it silently.
                return False

        return False # No match found in history

