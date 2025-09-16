# modules/gif.py
# A module for searching Giphy and returning a random GIF.
import os
import random
import re
import requests
import sys
from typing import Optional, Dict, Any
from .base import SimpleCommandModule, admin_required

def setup(bot):
    return Gif(bot)

class Gif(SimpleCommandModule):
    name = "gif"
    version = "1.0.0"
    description = "Searches Giphy for a GIF and posts the link."

    # --- Configuration ---
    # Your Giphy API key, stored in your jeeves.env file
    API_KEY = os.getenv("GIPHY_API_KEY")
    # Cooldown in seconds to prevent spam
    COOLDOWN = 10.0

    def __init__(self, bot):
        super().__init__(bot)
        
        # Initialize state for statistics
        self.set_state("gifs_requested", self.get_state("gifs_requested", 0))
        self.set_state("gifs_found", self.get_state("gifs_found", 0))
        self.save_state()

        if not self.API_KEY:
            print("[gif] WARNING: GIPHY_API_KEY environment variable is not set. The !gif command will not work.", file=sys.stderr)
            self._record_error("GIPHY_API_KEY is not set.")

    def _register_commands(self):
        """Register the commands that this module will handle."""
        self.register_command(
            r"^\s*!gif\s+(.+)$",
            self._cmd_gif,
            cooldown=self.COOLDOWN, # Use the cooldown from ModuleBase
            description="Search Giphy for a GIF. Usage: !gif <search term>"
        )
        self.register_command(
            r"^\s*!gif\s+stats\s*$",
            self._cmd_stats,
            admin_only=True,
            description="Show GIF module statistics."
        )

    def _get_gif_url(self, query: str) -> Optional[str]:
        """Queries the Giphy API and returns a URL, or None if an error occurs."""
        # Update stats for total requests
        self.set_state("gifs_requested", self.get_state("gifs_requested") + 1)
        self.save_state()

        api_url = f"https://api.giphy.com/v1/gifs/search"
        params = {
            'api_key': self.API_KEY,
            'q': query,
            'limit': 25,  # Get a decent number of results to choose from
            'rating': 'pg-13',
            'lang': 'en'
        }

        try:
            response = requests.get(api_url, params=params, timeout=10)
            response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)
            data = response.json()

            if data and data['data']:
                # Choose a random GIF from the results
                gif_obj = random.choice(data['data'])
                # Update stats for successful finds
                self.set_state("gifs_found", self.get_state("gifs_found") + 1)
                self.save_state()
                return gif_obj['images']['original']['url']
            
            return None # No results found
            
        except requests.exceptions.RequestException as e:
            self._record_error(f"Giphy API request failed for query '{query}': {e}")
            return None
        except (KeyError, IndexError) as e:
            self._record_error(f"Failed to parse Giphy response for query '{query}': {e}")
            return None

    def _cmd_gif(self, connection, event, msg, username, match):
        """Handles the !gif command."""
        if not self.API_KEY:
            self.safe_reply(connection, event, f"{username}, I'm sorry, but the GIF service is not configured correctly.")
            return True

        query = match.group(1).strip()
        gif_url = self._get_gif_url(query)

        title = self.bot.title_for(username)

        if gif_url:
            self.safe_reply(connection, event, f"{title} {username}, for '{query}': {gif_url}")
        else:
            self.safe_reply(connection, event, f"My apologies, {title}, I could not find a suitable GIF for '{query}'.")
        
        return True

    @admin_required
    def _cmd_stats(self, connection, event, msg, username, match):
        """Handles the !gif stats command."""
        requested = self.get_state("gifs_requested", 0)
        found = self.get_state("gifs_found", 0)
        success_rate = (found / requested * 100) if requested > 0 else 0
        
        self.safe_reply(
            connection, event,
            f"GIF stats: {found}/{requested} successful requests ({success_rate:.1f}% success rate)."
        )
        return True