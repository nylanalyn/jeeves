# modules/shorten.py
# URL shortener with automatic trigger for long URLs, using a self-hosted Shlink instance.
import re
import requests
import json
from typing import Optional
from .base import SimpleCommandModule

def setup(bot, config):
    """Initializes the Shorten module."""
    api_keys = bot.config.get("api_keys", {})
    shlink_url = api_keys.get("shlink_url")
    shlink_key = api_keys.get("shlink_key")
    if not shlink_url or not shlink_key:
        print("[shorten] Shlink URL or API key not found in config.yaml. Module will not load.")
        return None
    return Shorten(bot, config, shlink_url, shlink_key)

class Shorten(SimpleCommandModule):
    name = "shorten"
    version = "3.0.0" # Dynamic configuration refactor
    description = "Shortens URLs using a self-hosted Shlink instance."

    URL_PATTERN = re.compile(r'(https?://\S+)')

    def __init__(self, bot, config, shlink_url, shlink_key):
        """Initializes the module's state and configuration."""
        super().__init__(bot)
        self.SHLINK_API_URL = shlink_url
        self.SHLINK_API_KEY = shlink_key
        self.http_session = self.requests_retry_session()

    def _register_commands(self):
        """Registers the !shorten command."""
        self.register_command(
            r"^\s*!shorten\s+(https?://\S+)\s*$", self._cmd_shorten,
            name="shorten", cooldown=10.0, # Default cooldown
            description="Shorten a URL. Usage: !shorten <url>"
        )

    def _shorten_url(self, url_to_shorten: str) -> Optional[str]:
        """Shortens a URL using the Shlink API."""
        if not self.SHLINK_API_URL or not self.SHLINK_API_KEY:
            return None

        api_endpoint = f"{self.SHLINK_API_URL.rstrip('/')}/rest/v2/short-urls"
        headers = {"X-Api-Key": self.SHLINK_API_KEY, "Content-Type": "application/json"}
        payload = {"longUrl": url_to_shorten, "findIfExists": True}

        try:
            response = self.http_session.post(api_endpoint, headers=headers, json=payload, timeout=10)
            response.raise_for_status()
            data = response.json()
            return data.get("shortUrl")
        except requests.exceptions.RequestException as e:
            self._record_error(f"Shlink API request failed: {e}")
            return None
        except (KeyError, json.JSONDecodeError) as e:
            self._record_error(f"Failed to parse Shlink response: {e}")
            return None

    def _cmd_shorten(self, connection, event, msg, username, match):
        """Handles the !shorten command."""
        # is_enabled check is handled by the command dispatcher in base.py
        long_url = match.group(1)
        short_url = self._shorten_url(long_url)
        
        if short_url:
            self.safe_reply(connection, event, f"{username}, your shortened link: {short_url}")
        else:
            self.safe_reply(connection, event, f"{username}, I'm afraid I could not shorten that URL at this time.")
        return True

    def on_ambient_message(self, connection, event, msg: str, username: str) -> bool:
        """Handles automatic URL shortening."""
        if not self.is_enabled(event.target):
            return False

        min_length = self.get_config_value("min_length_for_auto_shorten", event.target, 70)
        if min_length <= 0:
            return False

        match = self.URL_PATTERN.search(msg)
        if match:
            url = match.group(1)
            # Avoid shortening our own shortened URLs
            if "://" in self.SHLINK_API_URL and self.SHLINK_API_URL.split("://")[1] in url:
                return False

            if len(url) > min_length:
                if not self.check_rate_limit("auto_shorten", 30.0):
                     return False
                
                short_url = self._shorten_url(url)
                if short_url:
                    title = self.bot.title_for(username)
                    self.safe_reply(connection, event, f"I took the liberty of shortening that for you, {title}: {short_url}")
                    return True
        return False
