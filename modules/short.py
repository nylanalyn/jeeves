# modules/shorten.py
# URL shortener with automatic trigger for long URLs, using a self-hosted Shlink instance.
import os
import re
import requests
import json
from typing import Optional
from .base import SimpleCommandModule

def setup(bot, config):
    return Shorten(bot, config)

class Shorten(SimpleCommandModule):
    name = "shorten"
    version = "2.0.0"
    description = "Shortens URLs using a self-hosted Shlink instance."

    URL_PATTERN = re.compile(r'(https?://\S+)')
    SHLINK_API_URL = os.getenv("SHLINK_API_URL")
    SHLINK_API_KEY = os.getenv("SHLINK_API_KEY")

    def __init__(self, bot, config):
        self.COOLDOWN = config.get("cooldown_seconds", 10.0)
        self.MIN_LENGTH = config.get("min_length_for_auto_shorten", 70)
        super().__init__(bot)

        if not self.SHLINK_API_URL or not self.SHLINK_API_KEY:
            self._record_error("SHLINK_API_URL or SHLINK_API_KEY environment variables are not set.")
        
        self.http_session = self.requests_retry_session()

    def _register_commands(self):
        self.register_command(
            r"^\s*!shorten\s+(https?://\S+)\s*$", self._cmd_shorten,
            name="shorten", cooldown=self.COOLDOWN,
            description="Shorten a URL. Usage: !shorten <url>"
        )

    def _shorten_url(self, url_to_shorten: str) -> Optional[str]:
        if not self.SHLINK_API_URL or not self.SHLINK_API_KEY:
            return None

        api_endpoint = f"{self.SHLINK_API_URL.rstrip('/')}/rest/v2/short-urls"
        headers = {
            "X-Api-Key": self.SHLINK_API_KEY,
            "Content-Type": "application/json"
        }
        payload = {
            "longUrl": url_to_shorten,
            "findIfExists": True
        }

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
        long_url = match.group(1)
        short_url = self._shorten_url(long_url)
        
        if short_url:
            self.safe_reply(connection, event, f"{username}, your shortened link: {short_url}")
        else:
            self.safe_reply(connection, event, f"{username}, I'm afraid I could not shorten that URL at this time.")
        return True

    def on_pubmsg(self, connection, event, msg, username):
        if super().on_pubmsg(connection, event, msg, username):
            return True

        # Automatic shortening logic
        if self.MIN_LENGTH <= 0:
            return False

        match = self.URL_PATTERN.search(msg)
        if match:
            url = match.group(1)
            # Avoid shortening URLs that are already short
            if "://" in self.SHLINK_API_URL and self.SHLINK_API_URL.split("://")[1] in url:
                return False

            if len(url) > self.MIN_LENGTH:
                # Check rate limit to avoid spamming the channel
                if not self.check_rate_limit("auto_shorten", 30.0):
                     return False
                
                short_url = self._shorten_url(url)
                if short_url:
                    title = self.bot.title_for(username)
                    self.safe_reply(connection, event, f"I took the liberty of shortening that for you, {title}: {short_url}")
                    return True
        return False

