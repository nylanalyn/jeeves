# modules/convenience.py
# A module for common, convenient search commands.
import re
import requests
import xml.etree.ElementTree as ET
import random
from urllib.parse import quote_plus
from typing import Optional, Dict, Any

from .base import ModuleBase # Inherit from ModuleBase for more control

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

try:
    from googleapiclient.discovery import build
except ImportError:
    build = None

def setup(bot, config):
    if not BeautifulSoup:
        print("[convenience] beautifulsoup4 is not installed. !g command will be limited.")
    if not build:
        print("[convenience] google-api-python-client is not installed. !yt command will not load.")
    return Convenience(bot, config)

class Convenience(ModuleBase): # Changed to ModuleBase
    name = "convenience"
    version = "1.4.3" # Switched to multi-line responses to avoid length limits
    description = "Provides convenient, common search commands."

    def __init__(self, bot, config):
        # 1. Call the base __init__ first. This sets up self.bot.
        super().__init__(bot)
        
        # 2. Now that self.bot exists, we can safely load our config.
        self.on_config_reload(config)
        
        # 3. Now that config is loaded, we can register commands with correct cooldowns.
        self._register_commands()

        # 4. Perform final setup.
        self.http_session = self.requests_retry_session()
        
        # Build YouTube service if API key is present
        self.youtube_service = None
        if self.YOUTUBE_API_KEY and build:
            try:
                self.youtube_service = build('youtube', 'v3', developerKey=self.YOUTUBE_API_KEY)
            except Exception as e:
                self._record_error(f"Failed to build YouTube service: {e}")

    def on_config_reload(self, config):
        self.COOLDOWN_G = config.get("google_cooldown", 5.0)
        self.COOLDOWN_UD = config.get("ud_cooldown", 10.0)
        self.COOLDOWN_WIKI = config.get("wiki_cooldown", 10.0)
        self.COOLDOWN_NEWS = config.get("news_cooldown", 15.0)
        self.COOLDOWN_YT = config.get("youtube_cooldown", 15.0)
        self.SASSY_GOOGLE_CHANCE = config.get("sassy_google_chance", 0.1)
        self.SASSY_WIKI_CHANCE = config.get("sassy_wiki_chance", 0.1)
        self.SASSY_UD_CHANCE = config.get("sassy_ud_chance", 0.05)
        self.SASSY_UD_TERMS = config.get("sassy_ud_terms", ["lazy", "procrastination", "slacker"])
        
        # Get the API key from the global bot config, which is safe now.
        self.YOUTUBE_API_KEY = self.bot.config.get("api_keys", {}).get("youtube")

    def _register_commands(self):
        self.register_command(r"^\s*!g\s+(.+)$", self._cmd_google, name="g", cooldown=self.COOLDOWN_G)
        self.register_command(r"^\s*!ud\s+(.+)$", self._cmd_ud, name="ud", cooldown=self.COOLDOWN_UD)
        self.register_command(r"^\s*!wiki\s+(.+)$", self._cmd_wiki, name="wiki", cooldown=self.COOLDOWN_WIKI)
        self.register_command(r"^\s*!news\s*$", self._cmd_news, name="news", cooldown=self.COOLDOWN_NEWS)
        self.register_command(r"^\s*!yt\s+(.+)$", self._cmd_yt, name="yt", cooldown=self.COOLDOWN_YT)

    # --- Command Handlers ---

    def _cmd_google(self, connection, event, msg, username, match):
        """Handles the !g command."""
        query = match.group(1).strip()
        encoded_query = quote_plus(query)
        
        if random.random() < self.SASSY_GOOGLE_CHANCE:
            url = f"https://letmegooglethat.com/?q={encoded_query}"
            message = f"Allow me to demonstrate, {self.bot.title_for(username)}: {url}"
            self.safe_reply(connection, event, message)
            return True

        search_url = f"https://www.google.com/search?q={encoded_query}"
        
        if not BeautifulSoup:
            self.safe_reply(connection, event, f"{self.bot.title_for(username)}, your Google search for '{query}': {self._get_short_url(search_url)}")
            return True

        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36'}
            response = self.http_session.get(search_url, headers=headers, timeout=5)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            result_block = soup.find('div', class_='g')
            if result_block:
                title_tag = result_block.find('h3')
                link_tag = result_block.find('a')
                snippet_tag = result_block.find('div', style=re.compile(r'line-clamp'))

                if title_tag and link_tag and snippet_tag:
                    title = title_tag.get_text()
                    link = link_tag['href']
                    snippet = snippet_tag.get_text()

                    self.safe_reply(connection, event, f"\"{title}\" — {snippet}")
                    self.safe_reply(connection, event, self._get_short_url(link))
                    return True
        except Exception as e:
            self._record_error(f"Google search scraping failed: {e}")
        
        self.safe_reply(connection, event, f"{self.bot.title_for(username)}, your Google search for '{query}': {self._get_short_url(search_url)}")
        return True

    def _cmd_ud(self, connection, event, msg, username, match):
        """Handles the !ud command."""
        term = match.group(1).strip()
        sassy_triggered = random.random() < self.SASSY_UD_CHANCE and self.SASSY_UD_TERMS

        if sassy_triggered:
            original_term = term
            term = random.choice(self.SASSY_UD_TERMS)
            intro_message = f"While searching for '{original_term}', I was reminded of a more relevant term, {self.bot.title_for(username)}. For '{term}':"
        else:
            intro_message = f"For '{term}':"

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
            
            self.safe_reply(connection, event, intro_message)
            self.safe_reply(connection, event, cleaned_def)

        except requests.exceptions.RequestException as e:
            self._record_error(f"Urban Dictionary API request failed: {e}")
            self.safe_reply(connection, event, "I'm afraid the Urban Dictionary service is unavailable at the moment.")
        
        return True

    def _cmd_wiki(self, connection, event, msg, username, match):
        """Handles the !wiki command."""
        query = match.group(1).strip()
        
        if random.random() < self.SASSY_WIKI_CHANCE:
            url = f"https://en.wikipedia.org/w/index.php?search={quote_plus(query)}"
            message = f"A moment, {self.bot.title_for(username)}, while I consult the grand library for you... Ah, here is the relevant section: {self._get_short_url(url)}"
            self.safe_reply(connection, event, message)
            return True

        search_url = f"https://en.wikipedia.org/w/index.php?search={quote_plus(query)}"
        fallback_message = f"{self.bot.title_for(username)}, your Wikipedia search for '{query}': {self._get_short_url(search_url)}"
        api_url = f"https://en.wikipedia.org/w/api.php?action=query&format=json&prop=extracts&exintro=true&explaintext=true&redirects=1&titles={quote_plus(query)}"

        try:
            response = self.http_session.get(api_url, timeout=5)
            response.raise_for_status()
            data = response.json()
            
            pages = data.get("query", {}).get("pages", {})
            if not pages or "-1" in pages:
                self.safe_reply(connection, event, fallback_message)
                return True

            page_id = next(iter(pages))
            extract = pages[page_id].get("extract")
            page_title = pages[page_id].get("title")

            if extract:
                summary = extract.replace('\n', ' ').strip()
                page_url = f"https://en.wikipedia.org/wiki/{quote_plus(page_title)}"
                
                self.safe_reply(connection, event, summary)
                self.safe_reply(connection, event, self._get_short_url(page_url))
                return True
        except requests.exceptions.RequestException as e:
            self._record_error(f"Wikipedia API request failed: {e}")

        self.safe_reply(connection, event, fallback_message)
        return True

    def _cmd_news(self, connection, event, msg, username, match):
        """Handles the !news command."""
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
            
            self.safe_reply(connection, event, f"The top {location_name} story is: \"{news_title}\"")
            self.safe_reply(connection, event, self._get_short_url(news_link))

        except (requests.exceptions.RequestException, ET.ParseError) as e:
            self._record_error(f"Google News RSS request failed for '{location_name}': {e}")
            self.safe_reply(connection, event, "I'm afraid the news service is unavailable at this time.")

        return True

    def _cmd_yt(self, connection, event, msg, username, match):
        """Handles the !yt command."""
        if not self.youtube_service:
            self.safe_reply(connection, event, f"{self.bot.title_for(username)}, the YouTube service is not configured correctly.")
            return True

        query = match.group(1).strip()
        video_info = self._get_youtube_video_info(query)
        title = self.bot.title_for(username)

        if video_info:
            view_str = f"{video_info['views']:,}" if video_info.get('views') is not None else "N/A"
            self.safe_reply(connection, event, f"For '{query}', I present: \"{video_info['title']}\".")
            self.safe_reply(connection, event, f"Duration: {video_info['duration']}. Views: {view_str}. {self._get_short_url(video_info['url'])}")
        else:
            self.safe_reply(connection, event, f"My apologies, {title}, I could not find a suitable video for '{query}'.")
        return True
    
    # --- Helper Methods ---

    def _get_short_url(self, url: str) -> str:
        """Helper to shorten a URL if the shorten module is available."""
        shorten_module = self.bot.pm.plugins.get("shorten")
        if shorten_module and shorten_module.enabled:
            short_url = shorten_module._shorten_url(url)
            if short_url:
                return short_url
        return url

    def _parse_duration(self, iso_duration: str) -> str:
        """Converts an ISO 8601 duration string into a human-readable format."""
        match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', iso_duration)
        if not match: return "N/A"
        hours, minutes, seconds = match.groups()
        parts = []
        if hours: parts.append(f"{int(hours)}h")
        if minutes: parts.append(f"{int(minutes)}m")
        if seconds: parts.append(f"{int(seconds)}s")
        return " ".join(parts) if parts else "0s"

    def _get_youtube_video_info(self, query: str) -> Optional[dict]:
        """Searches for a video by relevance and returns its details."""
        if not self.youtube_service: return None
        try:
            search_request = self.youtube_service.search().list(
                q=query, part='snippet', maxResults=1, type='video', order='relevance'
            )
            search_response = search_request.execute()
            if not search_response.get('items'): return None
            
            video_id = search_response['items'][0]['id']['videoId']
            
            video_request = self.youtube_service.videos().list(
                part='snippet,statistics,contentDetails', id=video_id
            )
            video_response = video_request.execute()
            if not video_response.get('items'): return None
            
            video_data = video_response['items'][0]
            
            return {
                "title": video_data['snippet']['title'],
                "views": int(video_data['statistics'].get('viewCount', 0)),
                "duration": self._parse_duration(video_data['contentDetails']['duration']),
                "url": f"https://www.youtube.com/watch?v={video_id}"
            }
        except Exception as e:
            self._record_error(f"YouTube API request failed for query '{query}': {e}")
            return None

