# modules/oracle.py
# An experimental module for a fully AI-driven conversational mode.
import re
import sys
from collections import deque
from pathlib import Path
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
    return Oracle(bot, config)

class Oracle(SimpleCommandModule):
    name = "oracle"
    version = "1.2.0" # Added external prompt file with parameter support
    description = "Provides an AI-driven conversational mode in a specific channel."

    def __init__(self, bot, config):
        super().__init__(bot)
        self.api_key = self.bot.config.get("api_keys", {}).get("openai_api_key")
        self.base_url = self.get_config_value("openai_base_url")
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        self.history = {} # Keyed by channel
        self.on_config_reload(config) # Initial load of settings

    def on_config_reload(self, config):
        self.MODEL = self.get_config_value("model", default="claude-3-haiku-20240307")
        self.HISTORY_LENGTH = self.get_config_value("history_length", default=10)
        self.MAX_IRC_LINE_BYTES = 450
        self._load_system_prompt_and_params()

    def _load_system_prompt_and_params(self):
        # Default values from config
        self.current_system_prompt = self.get_config_value("system_prompt", default="You are a helpful assistant.")
        self.api_params = {
            "temperature": self.get_config_value("temperature", default=0.7),
            "top_p": self.get_config_value("top_p", default=1.0)
        }

        prompt_filename = self.get_config_value("system_prompt_file")
        if not prompt_filename:
            return

        prompt_path = self.bot.ROOT / "config" / prompt_filename
        if not prompt_path.exists():
            self.log_debug(f"Prompt file '{prompt_filename}' not found. Using default prompt from config.")
            return

        try:
            self.log_debug(f"Loading system prompt from '{prompt_filename}'...")
            content = prompt_path.read_text(encoding='utf-8')
            lines = content.splitlines()
            
            prompt_lines = []
            for line in lines:
                if line.startswith("@@"):
                    try:
                        key, value = line.strip("@@").split(":", 1)
                        key = key.strip().lower()
                        value = value.strip()
                        if key in self.api_params:
                            self.api_params[key] = float(value)
                            self.log_debug(f"Loaded param from prompt file: {key} = {self.api_params[key]}")
                    except (ValueError, IndexError):
                        self.log_debug(f"Could not parse parameter line in prompt file: {line}")
                else:
                    prompt_lines.append(line)
            
            if prompt_lines:
                self.current_system_prompt = "\n".join(prompt_lines).strip()

        except Exception as e:
            self._record_error(f"Failed to read or parse prompt file '{prompt_filename}': {e}")

    def _register_commands(self):
        self.register_command(r"^\s*!oracle\s+reset\s*$", self._cmd_reset,
                              name="oracle reset", admin_only=True,
                              description="[Admin] Reset the conversation history in this channel.")
        self.register_command(r"^\s*!oracle\s+reload\s*$", self._cmd_reload_prompt,
                              name="oracle reload", admin_only=True,
                              description="[Admin] Reload the system prompt from its file.")

    def _split_and_send(self, connection, event, text):
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
        ai_channel = self.get_config_value("ai_channel", event.target)
        if event.target != ai_channel or not self.is_mentioned(msg):
            return False

        if event.target not in self.history:
            self.history[event.target] = deque(maxlen=self.HISTORY_LENGTH)
        
        channel_history = self.history[event.target]
        channel_history.append({"role": "user", "content": f"{username}: {msg}"})

        try:
            messages = [{"role": "system", "content": self.current_system_prompt}]
            messages.extend(list(channel_history))

            response = self.client.chat.completions.create(
                model=self.MODEL,
                messages=messages,
                temperature=self.api_params.get("temperature", 0.7),
                top_p=self.api_params.get("top_p", 1.0)
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
        if event.target in self.history:
            self.history[event.target].clear()
            self.safe_reply(connection, event, "Very good. I have cleared my memory of our recent conversations in this channel.")
        else:
            self.safe_reply(connection, event, "There is no conversation history to reset in this channel.")
        return True

    def _cmd_reload_prompt(self, connection, event, msg, username, match):
        self.log_debug(f"Admin {username} triggered prompt reload.")
        self._load_system_prompt_and_params()
        self.safe_reply(connection, event, "I have re-read my instructions from the prompt file.")
        return True

