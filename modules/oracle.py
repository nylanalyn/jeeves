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
    version = "1.1.2" # Added response sanitization for IRC compatibility
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


    def _register_commands(self):
        # This module primarily works through ambient messages.
        self.register_command(r"^\s*!oracle\s+reset\s*$", self._cmd_reset,
                              name="oracle reset", admin_only=True,
                              description="[Admin] Reset the conversation history in this channel.")

    def on_ambient_message(self, connection, event, msg, username):
        # Only operate in the designated channel and when the bot is mentioned.
        if event.target != self.AI_CHANNEL or not self.is_mentioned(msg):
            return False

        # Get or create the conversation history for this channel
        if event.target not in self.history:
            self.history[event.target] = deque(maxlen=self.HISTORY_LENGTH)
        
        channel_history = self.history[event.target]
        
        # Add the user's message to the history
        channel_history.append({"role": "user", "content": f"{username}: {msg}"})

        try:
            # Prepare the messages for the API call
            messages = [{"role": "system", "content": self.SYSTEM_PROMPT}]
            messages.extend(list(channel_history))

            response = self.client.chat.completions.create(
                model=self.MODEL,
                messages=messages
            )
            
            ai_response = response.choices[0].message.content
            if ai_response:
                # Add the AI's original response to the history for context
                channel_history.append({"role": "assistant", "content": ai_response})
                
                # Sanitize and send the response line by line for IRC compatibility
                for line in ai_response.split('\n'):
                    cleaned_line = line.strip()
                    if cleaned_line: # Avoid sending empty lines
                        self.safe_reply(connection, event, cleaned_line)

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

