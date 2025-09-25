# modules/convenience.py
# A module for common, convenient search commands.
import re
import requests
import xml.etree.ElementTree as ET
from urllib.parse import quote_plus
from typing import Optional, Dict, Any

from .base import SimpleCommandModule

def setup(bot, config):
    return Convenience(bot, config)

class Convenience(SimpleCommandModule):
    name = "convenience"
    version = "1.1.0" # Added !news command
    description = "Provides convenient, common search commands."

    def __init__(self, bot, config):
        super().__init__(bot)
        self.on_config_reload(config)
        self.http_session = self.requests_retry_session()

    def on_config_reload(self, config):
        self.COOLDOWN_G = config.get("google_cooldown", 5.0)
        self.COOLDOWN_UD = config.get("ud_cooldown", 10.0)
        self.COOLDOWN_WIKI = config.get("wiki_cooldown", 10.0)
        self.COOLDOWN_NEWS = config.get("news_cooldown", 15.0)

    def _register_commands(self):
        # Google Search
        self.register_command(r"^\s*!g\s+(.+)$", self._cmd_google,
                              name="g", cooldown=self.COOLDOWN_G,
                              description="Generate a Google search link. Usage: !g <query>")
        # Urban Dictionary Search
        self.register_command(r"^\s*!ud\s+(.+)$", self._cmd_ud,
                              name="ud", cooldown=self.COOLDOWN_UD,
                              description="Search Urban Dictionary. Usage: !ud <term>")
        # Wikipedia Search
        self.register_command(r"^\s*!wiki\s+(.+)$", self._cmd_wiki,
                              name="wiki", cooldown=self.COOLDOWN_WIKI,
                              description="Search Wikipedia. Usage: !wiki <term>")
        # News Search
        self.register_command(r"^\s*!news\s*$", self._cmd_news,
                              name="news", cooldown=self.COOLDOWN_NEWS,
                              description="Get the top news story for your location, or globally.")

    # --- Command Handlers ---

    def _cmd_google(self, connection, event, msg, username, match):
        """Handles the !g command."""
        query = match.group(1).strip()
        encoded_query = quote_plus(query)
        url = f"https://www.google.com/search?q={encoded_query}"
        
        shorten_module = self.bot.pm.plugins.get("shorten")
        if shorten_module and shorten_module.enabled:
            short_url = shorten_module._shorten_url(url)
            if short_url:
                url = short_url

        self.safe_reply(connection, event, f"{self.bot.title_for(username)}, your Google search for '{query}': {url}")
        return True

    def _cmd_ud(self, connection, event, msg, username, match):
        """Handles the !ud command."""
        term = match.group(1).strip()
        api_url = f"http://api.urbandictionary.com/v0/define?term={quote_plus(term)}"
        
        try:
            response = self.http_session.get(api_url, timeout=5)
            response.raise_for_status()
            data = response.json()

            if not data or not data.get("list"):
                self.safe_reply(connection, event, f"My apologies, {self.bot.title_for(username)}, I could find no definition for '{term}'.")
                return True

            top_result = data["list"][0]
            definition = top_result.get("definition", "No definition provided.")
            cleaned_def = re.sub(r'\[|\]', '', definition).replace('\r', ' ').replace('\n', ' ').strip()
            
            if len(cleaned_def) > 350:
                cleaned_def = cleaned_def[:347] + "..."

            self.safe_reply(connection, event, f"For '{term}': {cleaned_def}")

        except requests.exceptions.RequestException as e:
            self._record_error(f"Urban Dictionary API request failed: {e}")
            self.safe_reply(connection, event, "I'm afraid the Urban Dictionary service is unavailable at the moment.")
        
        return True

    def _cmd_wiki(self, connection, event, msg, username, match):
        """Handles the !wiki command."""
        query = match.group(1).strip()
        encoded_query = quote_plus(query)
        url = f"https://en.wikipedia.org/w/index.php?search={encoded_query}"

        shorten_module = self.bot.pm.plugins.get("shorten")
        if shorten_module and shorten_module.enabled:
            short_url = shorten_module._shorten_url(url)
            if short_url:
                url = short_url

        self.safe_reply(connection, event, f"{self.bot.title_for(username)}, your Wikipedia search for '{query}': {url}")
        return True

    def _cmd_news(self, connection, event, msg, username, match):
        """Handles the !news command, fetching local or global news."""
        user_id = self.bot.get_user_id(username)
        user_locations = self.bot.get_module_state("weather").get("user_locations", {})
        location_obj = user_locations.get(user_id)
        
        location_name = "Global"
        if location_obj and location_obj.get("short_name"):
            location_name = location_obj.get("short_name")
            query = quote_plus(location_name)
            rss_url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
        else:
            rss_url = "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en"

        try:
            response = self.http_session.get(rss_url, timeout=10)
            response.raise_for_status()
            
            root = ET.fromstring(response.content)
            top_item = root.find('.//item')
            
            if top_item is None:
                self.safe_reply(connection, event, f"My apologies, I could not find any news for {location_name}.")
                return True
                
            news_title = top_item.find('title').text
            news_link = top_item.find('link').text

            shorten_module = self.bot.pm.plugins.get("shorten")
            if shorten_module and shorten_module.enabled:
                short_url = shorten_module._shorten_url(news_link)
                if short_url:
                    news_link = short_url

            self.safe_reply(connection, event, f"The top {location_name} story is: \"{news_title}\" — {news_link}")

        except (requests.exceptions.RequestException, ET.ParseError) as e:
            self._record_error(f"Google News RSS request failed for '{location_name}': {e}")
            self.safe_reply(connection, event, "I'm afraid the news service is unavailable at this time.")

        return True

