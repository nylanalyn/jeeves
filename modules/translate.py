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
    version = "2.2.0" # Added !tr with no args to translate last message
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

        # Track recent messages per channel (max 50 per channel)
        self.recent_messages = {}  # {channel: [(username, message), ...]}

    def _register_commands(self):
        """Registers all commands for the module."""
        self.register_command(
            r"^\s*!translate\s+langs\s*$",
            self._cmd_langs,
            name="translate langs",
            description="Get a link to supported language codes."
        )
        self.register_command(
            r"^\s*!tr\s*$",
            self._cmd_translate_last,
            name="tr last",
            description="Translate the last message in the channel."
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

    # --- Message Tracking ---

    def on_ambient_message(self, connection, event, msg: str, username: str) -> bool:
        """Track all non-command messages for the translate-last feature."""
        if not self.is_enabled(event.target):
            return False

        # Don't track bot commands or messages from the bot itself
        if msg.strip().startswith('!') or msg.strip().startswith(','):
            return False

        channel = event.target
        if channel not in self.recent_messages:
            self.recent_messages[channel] = []

        # Add this message to the history
        self.recent_messages[channel].append((username, msg))

        # Keep only the last 50 messages
        if len(self.recent_messages[channel]) > 50:
            self.recent_messages[channel] = self.recent_messages[channel][-50:]

        return False  # Don't consume the message

    # --- Command Handlers ---

    def _cmd_langs(self, connection, event, msg, username, match):
        """Handles the !translate langs command."""
        self.safe_reply(connection, event, "A full list of supported language codes can be found here: https://www.deepl.com/docs-api/general/languages")
        return True

    def _cmd_translate_last(self, connection, event, msg, username, match):
        """Handles !tr with no arguments - translates the last message."""
        has_flavor = self.has_flavor_enabled(username)
        if not self.translator:
            if has_flavor:
                self.safe_reply(connection, event, "My apologies, the translation service is not correctly configured.")
            else:
                self.safe_reply(connection, event, "Translation service not configured.")
            return True

        channel = event.target
        if channel not in self.recent_messages or not self.recent_messages[channel]:
            if has_flavor:
                self.safe_reply(connection, event, f"{self.bot.title_for(username)}, I haven't observed any recent messages to translate.")
            else:
                self.safe_reply(connection, event, "No recent messages to translate.")
            return True

        # Get the last message (most recent is at the end)
        last_username, last_message = self.recent_messages[channel][-1]

        target_lang = self._normalize_target_lang(
            self.get_config_value("default_target_language", event.target, default="EN-US"),
            event.target
        )
        return self._do_translation(connection, event, username, last_message, target_lang, has_flavor)

    def _do_translation(self, connection, event, username, text_to_translate, target_lang, has_flavor):
        """Shared translation logic."""
        try:
            normalized_lang = self._normalize_target_lang(target_lang, event.target)
            result = self.translator.translate_text(text_to_translate, target_lang=normalized_lang)
            detected_lang = result.detected_source_lang
            translated_text = result.text

            self.set_state("translations_done", self.get_state("translations_done", 0) + 1)
            self.save_state()

            if has_flavor:
                self.safe_reply(connection, event, f"{self.bot.title_for(username)}, ({detected_lang} -> {normalized_lang}): \"{translated_text}\"")
            else:
                self.safe_reply(connection, event, f"({detected_lang} -> {normalized_lang}): \"{translated_text}\"")

        except deepl.DeepLException as e:
            self._record_error(f"DeepL API error: {e}")
            if has_flavor:
                self.safe_reply(connection, event, f"My apologies, {self.bot.title_for(username)}, an error occurred during translation. Please check the language code or try again later.")
            else:
                self.safe_reply(connection, event, "Translation error. Check language code or try again.")

        return True

    def _cmd_translate(self, connection, event, msg, username, match):
        """Handles the main !translate command."""
        has_flavor = self.has_flavor_enabled(username)
        if not self.translator:
            if has_flavor:
                self.safe_reply(connection, event, "My apologies, the translation service is not correctly configured.")
            else:
                self.safe_reply(connection, event, "Translation service not configured.")
            return True

        args_str = match.group(1).strip()
        args = args_str.split()

        target_lang = self._normalize_target_lang(
            self.get_config_value("default_target_language", event.target, default="EN-US"),
            event.target
        )
        text_to_translate = args_str

        # Check if the first argument is a language code (e.g., DE, FR, PT-BR)
        if len(args) > 1 and self._looks_like_language_code(args[0]):
            # The DeepL library will validate the language code for us.
            target_lang = self._normalize_target_lang(args[0], event.target)
            text_to_translate = " ".join(args[1:])

        return self._do_translation(connection, event, username, text_to_translate, target_lang, has_flavor)

    def _normalize_target_lang(self, value: str, channel: Optional[str] = None) -> str:
        """
        DeepL now requires regional variants for certain languages (e.g., EN-US/EN-GB, PT-PT/PT-BR).
        This helper maps the short codes to configurable defaults so older commands keep working.
        """
        if not value:
            return value

        normalized = value.strip().upper()

        # Allow overrides from config: translate.language_variant_overrides.{code}: "EN-GB"
        overrides = self.get_config_value("language_variant_overrides", channel, default={})
        if isinstance(overrides, dict):
            override = overrides.get(normalized) or overrides.get(normalized.lower())
            if override:
                return override.strip().upper()

        if normalized == "EN":
            preferred_english = self.get_config_value("default_english_variant", channel, default=None)
            return (preferred_english or "EN-US").upper()

        if normalized == "PT":
            preferred_portuguese = self.get_config_value("default_portuguese_variant", channel, default=None)
            return (preferred_portuguese or "PT-BR").upper()

        return normalized

    def _looks_like_language_code(self, candidate: str) -> bool:
        """
        Heuristically determine whether the provided token is likely a DeepL language code.
        DeepL uses two-letter codes or their regional variants (e.g., EN-US, PT-BR), so only
        treat the first argument as a language code if it matches that pattern. This prevents
        short words at the start of a sentence (e.g., 'Jag') from being mistaken for language codes.
        """
        if not candidate:
            return False
        return bool(re.fullmatch(r"[A-Z]{2}(?:-[A-Z]{2})?", candidate.strip().upper()))
