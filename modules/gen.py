# modules/gen.py
# A module for generating AI images using pollinations.ai
import re

from .base import SimpleCommandModule

def setup(bot):
    """Initializes the Gen module."""
    return Gen(bot)

class Gen(SimpleCommandModule):
    name = "gen"
    version = "1.0.0"
    description = "Generates AI images using pollinations.ai and returns a shortened link."

    def __init__(self, bot):
        """Initializes the module's state and configuration."""
        super().__init__(bot)
        self.BASE_URL = "https://image.pollinations.ai/prompt/"

    def _register_commands(self):
        """Registers the !gen command."""
        self.register_command(
            r"^\s*!gen\s+(.+)$", self._cmd_gen,
            name="gen", cooldown=10.0,
            description="Generate an AI image. Usage: !gen <prompt>"
        )

    def _format_prompt(self, prompt: str) -> str:
        """
        Formats the prompt for the pollinations.ai URL.
        Replaces spaces with +, removes special punctuation.

        Raises:
            ValueError: If the formatted prompt is empty after sanitization.
        """
        # Remove or replace problematic punctuation (keep alphanumeric and basic punctuation)
        # Replace apostrophes and quotes with nothing
        cleaned = re.sub(r"['\"]", '', prompt)
        # Replace other special characters with spaces (which will become %20)
        cleaned = re.sub(r"[^a-zA-Z0-9\s]", ' ', cleaned)
        # Replace multiple spaces with single space
        cleaned = re.sub(r'\s+', ' ', cleaned)
        # Strip leading/trailing spaces
        cleaned = cleaned.strip()
        # Properly percent-encode the prompt for URL path segment
        from urllib.parse import quote
        formatted = quote(cleaned, safe='')

        # Validate that the formatted prompt is not empty
        if not formatted:
            raise ValueError("Prompt contains only invalid characters and cannot be processed")

        return formatted

    def _cmd_gen(self, connection, event, msg, username, match):
        """Handles the !gen command."""
        prompt = match.group(1).strip()

        if not prompt:
            self.safe_reply(connection, event, f"{self.bot.title_for(username)}, please provide a prompt for the image generation.")
            return True

        # Format the prompt for the URL
        try:
            formatted_prompt = self._format_prompt(prompt)
        except ValueError as e:
            self.safe_reply(connection, event, f"{self.bot.title_for(username)}, error: {str(e)}")
            return True

        # Create the full pollinations.ai URL
        full_url = f"{self.BASE_URL}{formatted_prompt}"

        # Try to shorten the URL using the shorten module if available
        shorten_module = self.bot.pm.plugins.get("shorten")
        short_url = None

        if shorten_module and shorten_module.is_enabled(event.target):
            # Use the public API method if available
            shorten_method = getattr(shorten_module, "shorten_url", None)
            if shorten_method and callable(shorten_method):
                short_url = shorten_method(full_url)

        # Reply with shortened URL if available, otherwise use full URL
        if short_url:
            self.safe_reply(connection, event, f"{self.bot.title_for(username)}, your generated image: {short_url}")
        else:
            self.safe_reply(connection, event, f"{self.bot.title_for(username)}, your generated image: {full_url}")

        return True
