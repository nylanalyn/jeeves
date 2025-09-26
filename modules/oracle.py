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
    version = "1.1.3" # Added message splitting to respect IRC limits
    description = "Provides an AI-driven conversational mode in a specific channel."

    def __init__(self, bot, config, api_key, base_url):
        super().__init__(bot)
        self.on_config_reload(config)
        self.api_key = api_key
        self.base_url = base_url
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        self.history = {} # Keyed by channel

    def on_config_reload(self, config):
        self.AI_CHANNEL = config.get("ai_channel", "")
        self.MODEL = config.get("model", "claude-3-haiku-20240307")
        self.SYSTEM_PROMPT = config.get("system_prompt", "You are Jeeves, a helpful and witty robotic butler.")
        self.HISTORY_LENGTH = config.get("history_length", 10)
        self.MAX_IRC_LINE_BYTES = 450 # A safe buffer below the 512 byte limit

    def _register_commands(self):
        self.register_command(r"^\s*!oracle\s+reset\s*$", self._cmd_reset,
                              name="oracle reset", admin_only=True,
                              description="[Admin] Reset the conversation history in this channel.")

    def _split_and_send(self, connection, event, text):
        """Sanitizes and sends a long message in IRC-compliant chunks."""
        # Replace newlines and carriage returns, which are illegal in IRC messages
        text = text.replace('\n', ' ').replace('\r', ' ')
        words = text.split()
        
        current_line = ""
        for word in words:
            # Check if adding the next word would exceed the limit
            if len((current_line + ' ' + word).encode('utf-8')) > self.MAX_IRC_LINE_BYTES:
                # If the line has content, send it
                if current_line:
                    self.safe_reply(connection, event, current_line)
                # Start a new line with the current word
                current_line = word
            else:
                # Add the word to the current line
                if current_line:
                    current_line += ' ' + word
                else:
                    current_line = word
        
        # Send any remaining text in the buffer
        if current_line:
            self.safe_reply(connection, event, current_line)

    def on_ambient_message(self, connection, event, msg, username):
        if event.target != self.AI_CHANNEL or not self.is_mentioned(msg):
            return False

        if event.target not in self.history:
            self.history[event.target] = deque(maxlen=self.HISTORY_LENGTH)
        
        channel_history = self.history[event.target]
        channel_history.append({"role": "user", "content": f"{username}: {msg}"})

        try:
            messages = [{"role": "system", "content": self.SYSTEM_PROMPT}]
            messages.extend(list(channel_history))

            response = self.client.chat.completions.create(
                model=self.MODEL,
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

