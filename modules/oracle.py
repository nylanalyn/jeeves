# modules/oracle.py
# An experimental module for a fully AI-driven conversational mode.
import re
import sys
from collections import deque
from pathlib import Path
from .base import SimpleCommandModule

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

def setup(bot):
    if not OpenAI:
        print("[oracle] openai library not installed. Module will not load.", file=sys.stderr)
        return None
    
    api_key = bot.config.get("api_keys", {}).get("openai_api_key")
    base_url = bot.config.get("oracle", {}).get("openai_base_url")
    
    if not api_key or not base_url:
        print("[oracle] OpenAI API key or Base URL not found in config.yaml. Module will not load.", file=sys.stderr)
        return None
        
    return Oracle(bot)

class Oracle(SimpleCommandModule):
    name = "oracle"
    version = "1.2.0" # Added enable/disable check
    description = "Provides an AI-driven conversational mode in a specific channel."

    def __init__(self, bot):
        super().__init__(bot)
        self.history = {} # Keyed by channel
        self.generation_params = {}
        self._load_prompt_and_params()

    def _load_prompt_and_params(self):
        """Loads the system prompt and generation parameters from a file or config."""
        prompt_file_name = self.get_config_value("system_prompt_file")
        
        self.SYSTEM_PROMPT = self.get_config_value("system_prompt", default="You are Jeeves, a helpful and witty robotic butler.")
        self.generation_params = {}
        
        if prompt_file_name:
            prompt_path = Path(self.bot.ROOT) / "config" / prompt_file_name
            if prompt_path.exists():
                self.log_debug(f"Loading system prompt from {prompt_path}")
                try:
                    lines = prompt_path.read_text(encoding='utf-8').splitlines()
                    prompt_lines = []
                    for line in lines:
                        if line.startswith("@@"):
                            key, value = line.strip("@@ ").split(":", 1)
                            key = key.strip().lower()
                            value = value.strip()
                            try:
                                if '.' in value: self.generation_params[key] = float(value)
                                else: self.generation_params[key] = int(value)
                            except ValueError:
                                self.log_debug(f"Could not parse parameter '{key}' value '{value}'")
                        else:
                            prompt_lines.append(line)
                    self.SYSTEM_PROMPT = "\n".join(prompt_lines)
                    self.log_debug(f"Loaded generation params: {self.generation_params}")
                except Exception as e:
                    self._record_error(f"Failed to read or parse prompt file {prompt_path}: {e}")
            else:
                 self.log_debug(f"Prompt file '{prompt_file_name}' not found. Using default prompt.")

    def on_config_reload(self, config):
        """Called by core when config is reloaded."""
        self._load_prompt_and_params()

    def _register_commands(self):
        self.register_command(r"^\s*!oracle\s+reset\s*$", self._cmd_reset,
                              name="oracle reset", admin_only=True,
                              description="[Admin] Reset the conversation history in this channel.")
        self.register_command(r"^\s*!oracle\s+reload\s*$", self._cmd_reload_prompt,
                              name="oracle reload", admin_only=True,
                              description="[Admin] Reload the system prompt file from disk.")

    def _split_and_send(self, connection, event, text):
        """Sanitizes and sends a long message in IRC-compliant chunks."""
        text = text.replace('\n', ' ').replace('\r', ' ')
        words = text.split()
        max_line_bytes = self.get_config_value("max_irc_line_bytes", default=450)
        
        current_line = ""
        for word in words:
            if len((current_line + ' ' + word).encode('utf-8')) > max_line_bytes:
                if current_line:
                    self.safe_reply(connection, event, current_line)
                current_line = word
            else:
                if current_line: current_line += ' ' + word
                else: current_line = word
        
        if current_line:
            self.safe_reply(connection, event, current_line)

    def on_ambient_message(self, connection, event, msg, username):
        # --- THIS IS THE CORRECTED LOGIC ---
        if not self.is_enabled(event.target):
            return False

        ai_channel = self.get_config_value("ai_channel", event.target)
        if event.target != ai_channel or not self.is_mentioned(msg):
            return False
            
        history_len = self.get_config_value("history_length", event.target, default=10)
        if event.target not in self.history:
            self.history[event.target] = deque(maxlen=history_len)
        
        channel_history = self.history[event.target]
        channel_history.append({"role": "user", "content": f"{username}: {msg}"})

        try:
            client = OpenAI(
                api_key=self.bot.config.get("api_keys", {}).get("openai_api_key"),
                base_url=self.get_config_value("openai_base_url")
            )
            messages = [{"role": "system", "content": self.SYSTEM_PROMPT}]
            messages.extend(list(channel_history))
            model_name = self.get_config_value("model", default="claude-3-haiku-20240307")

            response = client.chat.completions.create(
                model=model_name,
                messages=messages,
                **self.generation_params
            )
            
            ai_response = response.choices[0].message.content
            if ai_response:
                channel_history.append({"role": "assistant", "content": ai_response})
                self._split_and_send(connection, event, ai_response)

        except Exception as e:
            import traceback
            error_msg = f"OpenAI API call failed: {e}\n{traceback.format_exc()}"
            self._record_error(error_msg)
            self.log_debug(error_msg)
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
        
    def _cmd_reload_prompt(self, connection, event, msg, username, match):
        """Reloads the system prompt file."""
        self._load_prompt_and_params()
        self.safe_reply(connection, event, "System prompt and parameters have been reloaded from disk.")
        return True

