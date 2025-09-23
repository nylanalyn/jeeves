# modules/gif.py
# A module for searching Giphy and returning a random GIF.
import random
import re
import requests
import sys
from typing import Optional, Dict, Any
from .base import SimpleCommandModule, admin_required

def setup(bot, config):
    """Initializes the Gif module."""
    api_key = bot.config.get("api_keys", {}).get("giphy")
    if not api_key:
        print("[gif] GIPHY API key not found in config.yaml. Module will not load.")
        return None
    return Gif(bot, config, api_key)

class Gif(SimpleCommandModule):
    name = "gif"
    version = "1.3.0" # Final refactor fix
    description = "Searches Giphy for a GIF and posts the link."
    
    def __init__(self, bot, config, api_key):
        """Initializes the module's state and configuration."""
        # --- Pre-super() setup ---
        self.API_KEY = api_key
        self.COOLDOWN = config.get("cooldown_seconds", 10.0)
        
        # --- super() call ---
        super().__init__(bot)

        # --- Post-super() setup ---
        self.set_state("gifs_requested", self.get_state("gifs_requested", 0))
        self.set_state("gifs_found", self.get_state("gifs_found", 0))
        self.save_state()
        
        self.http_session = self.requests_retry_session()

    def _register_commands(self):
        """Registers the !gif command."""
        self.register_command(
            r"^\s*!gif\s+(.+)$", self._cmd_gif,
            name="gif", cooldown=self.COOLDOWN,
            description="Search Giphy for a GIF. Usage: !gif <search term>"
        )
        self.register_command(
            r"^\s*!gif\s+stats\s*$", self._cmd_stats,
            name="gif stats", admin_only=True,
            description="Show GIF module statistics."
        )

    def _get_gif_url(self, query: str) -> Optional[str]:
        """Fetches a GIF URL from the Giphy API."""
        self.set_state("gifs_requested", self.get_state("gifs_requested", 0) + 1)
        self.save_state()

        api_url = "https://api.giphy.com/v1/gifs/search"
        params = {'api_key': self.API_KEY, 'q': query, 'limit': 25, 'rating': 'pg-13', 'lang': 'en'}

        try:
            response = self.http_session.get(api_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if data and data['data']:
                gif_obj = random.choice(data['data'])
                self.set_state("gifs_found", self.get_state("gifs_found") + 1)
                self.save_state()
                return gif_obj['images']['original']['url']
            
            return None
            
        except requests.exceptions.RequestException as e:
            self._record_error(f"Giphy API request failed for query '{query}': {e}")
            return None
        except (KeyError, IndexError, ValueError):
            self._record_error(f"Failed to parse Giphy response for query '{query}'")
            return None

    def _cmd_gif(self, connection, event, msg, username, match):
        """Handles the !gif command."""
        if not self.API_KEY:
            self.safe_reply(connection, event, f"{self.bot.title_for(username)}, the GIF service is not configured correctly.")
            return True

        query = match.group(1).strip()
        gif_url = self._get_gif_url(query)
        
        shorten_module = self.bot.pm.plugins.get("shorten")
        if shorten_module and shorten_module.enabled and gif_url:
            short_url = shorten_module._shorten_url(gif_url)
            if short_url:
                gif_url = short_url

        if gif_url:
            self.safe_reply(connection, event, f"{self.bot.title_for(username)}, for '{query}': {gif_url}")
        else:
            self.safe_reply(connection, event, f"My apologies, {self.bot.title_for(username)}, I could not find a suitable GIF for '{query}'.")
        
        return True

    @admin_required
    def _cmd_stats(self, connection, event, msg, username, match):
        """Handles the !gif stats command."""
        requested = self.get_state("gifs_requested", 0)
        found = self.get_state("gifs_found", 0)
        success_rate = (found / requested * 100) if requested > 0 else 0
        
        self.safe_reply(connection, event, f"GIF stats: {found}/{requested} successful requests ({success_rate:.1f}% success rate).")
        return True

