# modules/translate.py
# A module for translating text using the DeepL API.
import re
from typing import Optional, List, Dict, Any

from .base import SimpleCommandModule, admin_required

try:
    import deepl
except ImportError:
    deepl = None

def setup(bot):
    """Initializes the Translate module."""
    if not deepl:
        print("[translate] deepl library not installed (pip install deepl). Module will not load.")
        return None
    api_key = bot.config.get("api_keys", {}).get("deepl_api_key")
    if not api_key:
        print("[translate] DeepL API key not found in config.yaml. Module will not load.")
        return None
    return Translate(bot, api_key)

class Translate(SimpleCommandModule):
    """A module for text translation using the DeepL API."""
    name = "translate"
    version = "2.0.0" # Switched to DeepL API
    description = "Translates text using the DeepL API."

    def __init__(self, bot, api_key):
        super().__init__(bot)
        try:
            self.translator = deepl.Translator(api_key)
        except Exception as e:
            self._record_error(f"Failed to initialize DeepL translator: {e}")
            self.translator = None

        self.set_state("translations_done", 0)
        self.save_state()

    def _register_commands(self):
        """Registers all commands for the module."""
        self.register_command(
            r"^\s*!translate\s+langs\s*$",
            self._cmd_langs,
            name="translate langs",
            description="Get a link to supported language codes."
        )
        self.register_command(
            r"^\s*!translate\s+(.+)$",
            self._cmd_translate,
            name="translate",
            description="Translate text. Usage: !translate [target_lang] <text>"
        )
        # --- ALIASES ---
        self.register_command(
            r"^\s*!tr\s+(.+)$",
            self._cmd_translate,
            name="tr",
            description="Alias for !translate."
        )

    # --- Command Handlers ---

    def _cmd_langs(self, connection, event, msg, username, match):
        """Handles the !translate langs command."""
        self.safe_reply(connection, event, "A full list of supported language codes can be found here: https://www.deepl.com/docs-api/general/languages")
        return True

    def _cmd_translate(self, connection, event, msg, username, match):
        """Handles the main !translate command."""
        if not self.translator:
            self.safe_reply(connection, event, "My apologies, the translation service is not correctly configured.")
            return True

        args_str = match.group(1).strip()
        args = args_str.split()

        target_lang = self.get_config_value("default_target_language", event.target, default="EN-US")
        text_to_translate = args_str
        
        # Check if the first argument is a language code (e.g., DE, FR, PT-BR)
        # Simple check: 2-5 chars, contains only letters and possibly a hyphen.
        if len(args) > 1 and 2 <= len(args[0]) <= 5 and re.match(r'^[A-Z-]+$', args[0], re.IGNORECASE):
            # The DeepL library will validate the language code for us.
            target_lang = args[0].upper()
            text_to_translate = " ".join(args[1:])

        try:
            result = self.translator.translate_text(text_to_translate, target_lang=target_lang)
            detected_lang = result.detected_source_lang
            translated_text = result.text

            self.set_state("translations_done", self.get_state("translations_done", 0) + 1)
            self.save_state()
            
            self.safe_reply(connection, event, f"{self.bot.title_for(username)}, ({detected_lang} -> {target_lang}): \"{translated_text}\"")

        except deepl.DeepLException as e:
            self._record_error(f"DeepL API error: {e}")
            self.safe_reply(connection, event, f"My apologies, {self.bot.title_for(username)}, an error occurred during translation. Please check the language code or try again later.")
        
        return True

