# modules/shorten.py
# A module for shortening long URLs, both manually and automatically.
import re
import requests
from typing import Optional
from .base import SimpleCommandModule

def setup(bot, config):
    return Shorten(bot, config)

class Shorten(SimpleCommandModule):
    name = "shorten"
    version = "1.0.1" # version bumped
    description = "Shortens long URLs."

    # A robust regex to find URLs in a message.
    URL_REGEX = re.compile(
        r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
    )

    def __init__(self, bot, config):
        # Define attributes BEFORE calling the parent's __init__
        # to ensure they are available when _register_commands is called.
        self.MIN_LENGTH_FOR_AUTO_SHORTEN = config.get("min_length_for_auto_shorten", 70)
        self.COOLDOWN = config.get("cooldown", 10.0)
        
        super().__init__(bot)
        
        self.set_state("urls_shortened", self.get_state("urls_shortened", 0))
        self.save_state()
        self.http_session = self.requests_retry_session()

    def _register_commands(self):
        self.register_command(
            r"^\s*!shorten\s+(https?://\S+)\s*$", self._cmd_shorten,
            name="shorten", cooldown=self.COOLDOWN,
            description="Shorten a URL. Usage: !shorten <URL>"
        )

    def on_pubmsg(self, connection, event, msg, username):
        # First, handle any commands this module has.
        if super().on_pubmsg(connection, event, msg, username):
            return True

        # Then, check for long URLs to shorten automatically.
        match = self.URL_REGEX.search(msg)
        if match:
            url = match.group(0)
            if len(url) > self.MIN_LENGTH_FOR_AUTO_SHORTEN:
                if self.check_rate_limit("auto_shorten", self.COOLDOWN):
                    short_url = self._get_short_url(url)
                    if short_url:
                        title = self.bot.title_for(username)
                        self.safe_reply(connection, event,
                            f"I took the liberty of shortening that for you, {title}: {short_url}")
                        return True
        return False

    def _get_short_url(self, long_url: str) -> Optional[str]:
        """
        This is a placeholder for a real URL shortening service.
        You can replace the contents of this function with an API call
        to a service like TinyURL, bit.ly, etc.
        """
        try:
            # EXAMPLE USING TINYURL'S API (no key required)
            api_url = f"http://tinyurl.com/api-create.php?url={requests.utils.quote(long_url)}"
            response = self.http_session.get(api_url, timeout=10)
            response.raise_for_status()
            
            # The response body is the short URL
            short_url = response.text
            
            if short_url and short_url.startswith("http"):
                 self.set_state("urls_shortened", self.get_state("urls_shortened", 0) + 1)
                 self.save_state()
                 return short_url
            else:
                self._record_error(f"API returned an invalid short URL: {short_url}")
                return None

        except requests.exceptions.RequestException as e:
            self._record_error(f"URL shortening API request failed: {e}")
            return None

    def _cmd_shorten(self, connection, event, msg, username, match):
        long_url = match.group(1)
        short_url = self._get_short_url(long_url)
        title = self.bot.title_for(username)

        if short_url:
            self.safe_reply(connection, event, f"As you wish, {title}: {short_url}")
        else:
            self.safe_reply(connection, event, f"My apologies, {title}, I was unable to shorten that URL.")
        
        return True

