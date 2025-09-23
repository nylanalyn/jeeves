# modules/translate.py
# A module for translating text using the LibreTranslate API.
import requests
import re
from typing import Optional, List, Dict, Any
from .base import SimpleCommandModule, admin_required

def setup(bot, config):
    """Initializes the Translate module."""
    return Translate(bot, config)

class Translate(SimpleCommandModule):
    """A module for text translation using LibreTranslate."""
    name = "translate"
    version = "1.0.2"
    description = "Translates text using the LibreTranslate API."

    def __init__(self, bot, config):
        # --- Pre-super() setup ---
        self.on_config_reload(config)
        self.http_session = self.requests_retry_session()
        self.supported_languages: List[Dict[str, str]] = []
        
        # --- super() call ---
        super().__init__(bot)

        # --- Post-super() setup ---
        self.set_state("translations_done", 0)
        self.save_state()
        self._fetch_supported_languages()

    def on_config_reload(self, config):
        """Handles reloading the module's configuration."""
        self.API_URL = config.get("api_url", "https://libretranslate.com")
        self.COOLDOWN = config.get("cooldown_seconds", 15.0)
        self.DEFAULT_TARGET_LANG = config.get("default_target_language", "en")

    def _register_commands(self):
        """Registers all commands for the module."""
        self.register_command(
            r"^\s*!translate\s+langs\s*$",
            self._cmd_langs,
            name="translate langs",
            description="Get a list of supported language codes."
        )
        self.register_command(
            r"^\s*!translate\s+(.+)$",
            self._cmd_translate,
            name="translate",
            cooldown=self.COOLDOWN,
            description="Translate text. Usage: !translate [target_lang] <text>"
        )
        # --- ALIASES ---
        self.register_command(
            r"^\s*!tr\s+langs\s*$",
            self._cmd_langs,
            name="tr langs",
            description="Alias for !translate langs."
        )
        self.register_command(
            r"^\s*!tr\s+(.+)$",
            self._cmd_translate,
            name="tr",
            cooldown=self.COOLDOWN,
            description="Alias for !translate."
        )

    def _fetch_supported_languages(self):
        """Fetches and caches the list of supported languages from the API."""
        headers = {'User-Agent': 'JeevesIRCBot/1.0'}
        try:
            response = self.http_session.get(f"{self.API_URL}/languages", headers=headers)
            response.raise_for_status()
            self.supported_languages = response.json()
        except (requests.exceptions.RequestException, ValueError) as e:
            self._record_error(f"Could not fetch supported languages: {e}")
            self.supported_languages = []

    def _is_valid_lang_code(self, code: str) -> bool:
        """Checks if a given string is a valid, supported language code."""
        return any(lang['code'] == code for lang in self.supported_languages)

    def _perform_translation(self, text: str, target_lang: str, source_lang: str = "auto") -> Optional[str]:
        """Performs the actual translation via the LibreTranslate API."""
        headers = {'User-Agent': 'JeevesIRCBot/1.0', 'Content-Type': 'application/json'}
        try:
            payload = {
                "q": text,
                "source": source_lang,
                "target": target_lang,
                "format": "text"
            }
            response = self.http_session.post(f"{self.API_URL}/translate", json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            
            if "translatedText" in data:
                self.set_state("translations_done", self.get_state("translations_done", 0) + 1)
                self.save_state()
                return data["translatedText"]
                
        except (requests.exceptions.RequestException, ValueError) as e:
            self._record_error(f"Translation API error: {e}")
        return None

    # --- Command Handlers ---

    def _cmd_langs(self, connection, event, msg, username, match):
        """Handles the !translate langs command."""
        self.safe_reply(connection, event, "A full list of supported language codes can be found at: https://libretranslate.com/docs/#/translate/get_languages_languages_get")
        return True

    def _cmd_translate(self, connection, event, msg, username, match):
        """Handles the main !translate command."""
        args_str = match.group(1).strip()
        args = args_str.split()

        target_lang = self.DEFAULT_TARGET_LANG
        text_to_translate = args_str
        
        # Check if the first argument is a valid language code
        if len(args) > 1 and self._is_valid_lang_code(args[0]):
            target_lang = args[0]
            text_to_translate = " ".join(args[1:])

        translated_text = self._perform_translation(text_to_translate, target_lang)

        if translated_text:
            self.safe_reply(connection, event, f"{self.bot.title_for(username)}, the translation is: \"{translated_text}\"")
        else:
            self.safe_reply(connection, event, f"My apologies, {self.bot.title_for(username)}, I was unable to complete the translation.")
        
        return True

