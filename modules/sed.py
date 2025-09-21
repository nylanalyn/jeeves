# modules/sed.py
# A module for performing sed-style find/replace on recent messages.
import re
from collections import deque
from .base import ModuleBase

def setup(bot, config):
    return Sed(bot, config)

class Sed(ModuleBase):
    name = "sed"
    version = "1.0.0"
    description = "Performs s/find/replace/ style corrections on recent messages."

    # The regex to capture the sed-style command.
    # It captures the search part, the replace part, and optional flags.
    SED_PATTERN = re.compile(r"^s/((?:\\/|[^/])+)/((?:\\/|[^/])*)/(i)?g?")

    def __init__(self, bot, config):
        super().__init__(bot)
        # Load configuration with defaults
        self.MODE = config.get("mode", "self").lower()
        self.HISTORY_SIZE = config.get("history_size", 20)
        self.RESPONSE_TEMPLATE = config.get("response_template", "Perhaps {user} meant to say: {message}")

        # In-memory store for message history, keyed by channel
        self._message_history = {}

    def on_ambient_message(self, connection, event, msg, username):
        channel = event.target
        
        # First, check if the message is a sed command
        sed_match = self.SED_PATTERN.match(msg)
        
        if sed_match:
            search_term, replace_term, flags = sed_match.groups()
            
            # Unescape any escaped forward slashes
            search_term = search_term.replace('\\/', '/')
            replace_term = replace_term.replace('\\/', '/')
            
            # Determine regex flags
            re_flags = 0
            if flags and 'i' in flags:
                re_flags = re.IGNORECASE

            # Get the history for the current channel
            history = self._message_history.get(channel, [])
            
            # Find the message to correct
            target_message = None
            original_author = None

            for past_msg, author in reversed(history):
                # Skip the command message itself
                if author == username and past_msg == msg:
                    continue

                if self.MODE == "self" and author != username:
                    continue

                if re.search(search_term, past_msg, re_flags):
                    target_message = past_msg
                    original_author = author
                    break # Found our message, stop searching
            
            if target_message:
                try:
                    # Perform the substitution
                    corrected_message = re.sub(search_term, replace_term, target_message, flags=re_flags)
                    
                    # Don't respond if the message is unchanged
                    if corrected_message != target_message:
                        response = self.RESPONSE_TEMPLATE.format(user=original_author, message=corrected_message)
                        self.safe_reply(connection, event, response)
                except re.error as e:
                    # Handle invalid regex in the search term
                    self.safe_reply(connection, event, f"My apologies, but that appears to be an invalid expression: {e}")

        # After processing, add the current message to history for the next time
        if channel not in self._message_history:
            self._message_history[channel] = deque(maxlen=self.HISTORY_SIZE)
        
        self._message_history[channel].append((msg, username))
        
        # This module never "handles" the message in a way that should stop others, so we return False
        return False
