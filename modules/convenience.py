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
    version = "1.4.4" # Implemented robust news fallback logic
    description = "Provides convenient, common search commands."

    def __init__(self, bot, config):
        super().__init__(bot)
        self.on_config_reload(config)
        self._register_commands()
        self.http_session = self.requests_retry_session()
        
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
        self.YOUTUBE_API_KEY = self.bot.config.get("api_keys", {}).get("youtube")

    def _register_commands(self):
        self.register_command(r"^\s*!g\s+(.+)$", self._cmd_google, name="g", cooldown=self.COOLDOWN_G)
        self.register_command(r"^\s*!ud\s+(.+)$", self._cmd_ud, name="ud", cooldown=self.COOLDOWN_UD)
        self.register_command(r"^\s*!wiki\s+(.+)$", self._cmd_wiki, name="wiki", cooldown=self.COOLDOWN_WIKI)
        self.register_command(r"^\s*!news\s*$", self._cmd_news, name="news", cooldown=self.COOLDOWN_NEWS)
        self.register_command(r"^\s*!yt\s+(.+)$", self._cmd_yt, name="yt", cooldown=self.COOLDOWN_YT)

    # --- Command Handlers ---

    def _cmd_google(self, connection, event, msg, username, match):
        query = match.group(1).strip()
        encoded_query = quote_plus(query)
        if random.random() < self.SASSY_GOOGLE_CHANCE:
            self.safe_reply(connection, event, f"Allow me to demonstrate, {self.bot.title_for(username)}: https://letmegooglethat.com/?q={encoded_query}")
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
            if result_block and (title_tag := result_block.find('h3')) and (link_tag := result_block.find('a')) and (snippet_tag := result_block.find('div', style=re.compile(r'line-clamp'))):
                self.safe_reply(connection, event, f"\"{title_tag.get_text()}\" — {snippet_tag.get_text()}")
                self.safe_reply(connection, event, self._get_short_url(link_tag['href']))
                return True
        except Exception as e:
            self._record_error(f"Google search scraping failed: {e}")
        self.safe_reply(connection, event, f"{self.bot.title_for(username)}, your Google search for '{query}': {self._get_short_url(search_url)}")
        return True

    def _cmd_ud(self, connection, event, msg, username, match):
        term = match.group(1).strip()
        sassy_triggered = random.random() < self.SASSY_UD_CHANCE and self.SASSY_UD_TERMS
        if sassy_triggered:
            original_term, term = term, random.choice(self.SASSY_UD_TERMS)
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
        query = match.group(1).strip()
        if random.random() < self.SASSY_WIKI_CHANCE:
            self.safe_reply(connection, event, f"A moment, {self.bot.title_for(username)}, while I consult the grand library... Ah, here is the relevant section: {self._get_short_url(f'https://en.wikipedia.org/w/index.php?search={quote_plus(query)}')}")
            return True
        api_url = f"https://en.wikipedia.org/w/api.php?action=query&format=json&prop=extracts&exintro=true&explaintext=true&redirects=1&titles={quote_plus(query)}"
        try:
            response = self.http_session.get(api_url, timeout=5)
            response.raise_for_status()
            data = response.json()
            pages = data.get("query", {}).get("pages", {})
            if pages and "-1" not in pages:
                page_id = next(iter(pages))
                extract = pages[page_id].get("extract")
                page_title = pages[page_id].get("title")
                if extract:
                    self.safe_reply(connection, event, extract.replace('\n', ' ').strip())
                    self.safe_reply(connection, event, self._get_short_url(f"https://en.wikipedia.org/wiki/{quote_plus(page_title)}"))
                    return True
        except requests.exceptions.RequestException as e:
            self._record_error(f"Wikipedia API request failed: {e}")
        self.safe_reply(connection, event, f"{self.bot.title_for(username)}, your Wikipedia search for '{query}': {self._get_short_url(f'https://en.wikipedia.org/w/index.php?search={quote_plus(query)}')}")
        return True

    def _get_news_from_rss(self, rss_url: str) -> Optional[Dict[str, str]]:
        """Helper to fetch and parse a Google News RSS feed."""
        try:
            response = self.http_session.get(rss_url, timeout=10)
            response.raise_for_status()
            root = ET.fromstring(response.content)
            top_item = root.find('.//item')
            if top_item is not None and (title := top_item.find('title')) is not None and (link := top_item.find('link')) is not None:
                return {"title": title.text, "link": link.text}
        except (requests.exceptions.RequestException, ET.ParseError) as e:
            self._record_error(f"Google News RSS request failed for '{rss_url}': {e}")
        return None

    def _cmd_news(self, connection, event, msg, username, match):
        user_id = self.bot.get_user_id(username)
        location_obj = self.bot.get_module_state("weather").get("user_locations", {}).get(user_id)
        
        # Attempt 1: Specific local news
        if location_obj and location_obj.get("short_name"):
            short_name = location_obj["short_name"]
            cc = location_obj.get("country_code", "US").upper()
            rss_url = f"https://news.google.com/rss/search?q={quote_plus(short_name)}&hl=en-{cc}&gl={cc}&ceid={cc}:en"
            news_item = self._get_news_from_rss(rss_url)
            if news_item:
                self.safe_reply(connection, event, f"The top story for {short_name} is: \"{news_item['title']}\"")
                self.safe_reply(connection, event, self._get_short_url(news_item['link']))
                return True
            else:
                self.safe_reply(connection, event, f"I found no specific news for {short_name}, broadening the search to the national level...")

        # Attempt 2: National news (if location is set)
        if location_obj and location_obj.get("country_code"):
            cc = location_obj.get("country_code", "US").upper()
            rss_url = f"https://news.google.com/rss?hl=en-{cc}&gl={cc}&ceid={cc}:en"
            news_item = self._get_news_from_rss(rss_url)
            if news_item:
                self.safe_reply(connection, event, f"The top national story is: \"{news_item['title']}\"")
                self.safe_reply(connection, event, self._get_short_url(news_item['link']))
                return True

        # Attempt 3: Global news (fallback)
        rss_url = "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en"
        news_item = self._get_news_from_rss(rss_url)
        if news_item:
            self.safe_reply(connection, event, f"The top global story is: \"{news_item['title']}\"")
            self.safe_reply(connection, event, self._get_short_url(news_item['link']))
        else:
            self.safe_reply(connection, event, "I'm afraid the news service is unavailable at this time.")
        return True

    def _cmd_yt(self, connection, event, msg, username, match):
        if not self.youtube_service:
            self.safe_reply(connection, event, f"{self.bot.title_for(username)}, the YouTube service is not configured correctly.")
            return True
        query = match.group(1).strip()
        video_info = self._get_youtube_video_info(query)
        if video_info:
            view_str = f"{video_info['views']:,}" if video_info.get('views') is not None else "N/A"
            self.safe_reply(connection, event, f"For '{query}', I present: \"{video_info['title']}\".")
            self.safe_reply(connection, event, f"Duration: {video_info['duration']}. Views: {view_str}. {self._get_short_url(video_info['url'])}")
        else:
            self.safe_reply(connection, event, f"My apologies, {self.bot.title_for(username)}, I could not find a suitable video for '{query}'.")
        return True
    
    # --- Helper Methods ---

    def _get_short_url(self, url: str) -> str:
        shorten_module = self.bot.pm.plugins.get("shorten")
        if shorten_module and shorten_module.enabled:
            short_url = shorten_module._shorten_url(url)
            if short_url:
                return short_url
        return url

    def _parse_duration(self, iso_duration: str) -> str:
        match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', iso_duration)
        if not match: return "N/A"
        hours, minutes, seconds = match.groups()
        parts = [f"{int(p)}{unit}" for p, unit in zip((hours, minutes, seconds), ('h', 'm', 's')) if p]
        return " ".join(parts) if parts else "0s"

    def _get_youtube_video_info(self, query: str) -> Optional[dict]:
        if not self.youtube_service: return None
        try:
            search_request = self.youtube_service.search().list(q=query, part='snippet', maxResults=1, type='video', order='relevance')
            search_response = search_request.execute()
            if not search_response.get('items'): return None
            video_id = search_response['items'][0]['id']['videoId']
            video_request = self.youtube_service.videos().list(part='snippet,statistics,contentDetails', id=video_id)
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

