# modules/oracle.py
# An experimental module for a fully AI-driven conversational mode.
import re
import sys
from collections import deque
from .base import SimpleCommandModule, admin_required

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

def setup(bot, config):
    if not OpenAI:
        print("[oracle] openai library not installed. Module will not load.", file=sys.stderr)
        return None
    api_key = bot.config.get("api_keys", {}).get("openai_api_key")
    base_url = bot.config.get("oracle", {}).get("openai_base_url")
    if not api_key or not base_url:
        print("[oracle] OpenAI API key or Base URL not found in config.yaml. Module will not load.", file=sys.stderr)
        return None
    return Oracle(bot, config, api_key, base_url)

class Oracle(SimpleCommandModule):
    name = "oracle"
    version = "2.0.0" # Dynamic configuration refactor
    description = "Provides an AI-driven conversational mode in a specific channel."

    def __init__(self, bot, config, api_key, base_url):
        super().__init__(bot)
        self.api_key = api_key
        self.base_url = base_url
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        self.history = {} # Keyed by channel
        self.MAX_IRC_LINE_BYTES = 450 # A safe buffer below the 512 byte limit

    def _register_commands(self):
        self.register_command(r"^\s*!oracle\s+reset\s*$", self._cmd_reset,
                              name="oracle reset", admin_only=True,
                              description="[Admin] Reset the conversation history in this channel.")

    def _split_and_send(self, connection, event, text):
        """Sanitizes and sends a long message in IRC-compliant chunks."""
        text = text.replace('\n', ' ').replace('\r', ' ')
        words = text.split()
        
        current_line = ""
        for word in words:
            if len((current_line + ' ' + word).encode('utf-8')) > self.MAX_IRC_LINE_BYTES:
                if current_line:
                    self.safe_reply(connection, event, current_line)
                current_line = word
            else:
                if current_line:
                    current_line += ' ' + word
                else:
                    current_line = word
        
        if current_line:
            self.safe_reply(connection, event, current_line)

    def on_ambient_message(self, connection, event, msg, username):
        if not self.is_enabled(event.target):
            return False

        # This module only functions in one designated channel, read from global config.
        ai_channel = self.get_config_value("ai_channel", default="")
        if event.target != ai_channel or not self.is_mentioned(msg):
            return False

        history_length = self.get_config_value("history_length", default=10)
        if event.target not in self.history:
            self.history[event.target] = deque(maxlen=history_length)
        
        channel_history = self.history[event.target]
        channel_history.append({"role": "user", "content": f"{username}: {msg}"})

        try:
            model = self.get_config_value("model", default="claude-3-haiku-20240307")
            system_prompt = self.get_config_value("system_prompt", default="You are a helpful butler.")
            messages = [{"role": "system", "content": system_prompt}]
            messages.extend(list(channel_history))

            response = self.client.chat.completions.create(
                model=model,
                messages=messages
            )
            
            ai_response = response.choices[0].message.content
            if ai_response:
                channel_history.append({"role": "assistant", "content": ai_response})
                self._split_and_send(connection, event, ai_response)

        except Exception as e:
            self._record_error(f"OpenAI API call failed: {e}")
            self.safe_reply(connection, event, "My apologies, I seem to be having trouble with my higher cognitive functions at the moment.")
        
        return True

    def _cmd_reset(self, connection, event, msg, username, match):
        """Resets the conversation history for the current channel."""
        if event.target in self.history:
            self.history[event.target].clear()
            self.safe_reply(connection, event, "Very good. I have cleared my memory of our recent conversations in this channel.")
        else:
            self.safe_reply(connection, event, "There is no conversation history to reset in this channel.")
        return True
