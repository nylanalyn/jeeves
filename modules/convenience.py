# modules/convenience.py
# Merged module for common, convenient search commands and URL title fetching.
import re
import requests
import xml.etree.ElementTree as ET
import random
import html
from urllib.parse import quote_plus
from typing import Optional, Dict, Any

from .base import ModuleBase 

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
        print("[convenience] beautifulsoup4 is not installed. !g and title fetching will be limited.")
    if not build:
        print("[convenience] google-api-python-client is not installed. !yt command will not load.")
    return Convenience(bot, config)

class Convenience(ModuleBase):
    name = "convenience"
    version = "1.7.0" # Merged titles.py and fixed initialization
    description = "Provides convenient, common search commands and URL title fetching."

    YOUTUBE_URL_PATTERN = re.compile(r'(?:https?://)?(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)([\w\-]{11})')
    URL_PATTERN = re.compile(r'(https?://\S+)')
    TITLE_PATTERN = re.compile(r'<title>(.*?)</title>', re.IGNORECASE | re.DOTALL)

    def __init__(self, bot, config):
        super().__init__(bot)
        self._register_commands()
        self.http_session = self.requests_retry_session()
        
        youtube_api_key = self.bot.config.get("api_keys", {}).get("youtube")
        self.youtube_service = None
        if youtube_api_key and build:
            try:
                self.youtube_service = build('youtube', 'v3', developerKey=youtube_api_key)
            except Exception as e:
                self._record_error(f"Failed to build YouTube service: {e}")

    def _register_commands(self):
        self.register_command(r"^\s*!g\s+(.+)$", self._cmd_google, name="g")
        self.register_command(r"^\s*!ud\s+(.+)$", self._cmd_ud, name="ud")
        self.register_command(r"^\s*!wiki\s+(.+)$", self._cmd_wiki, name="wiki")
        self.register_command(r"^\s*!news\s*$", self._cmd_news, name="news")
        self.register_command(r"^\s*!yt\s+(.+)$", self._cmd_yt, name="yt")

    def on_ambient_message(self, connection, event, msg, username):
        if not self.is_enabled(event.target): return False

        if self._handle_ambient_youtube(connection, event, msg, username):
            return True

        if self._handle_ambient_titles(connection, event, msg, username):
            return True

        return False

    def _handle_ambient_youtube(self, connection, event, msg, username):
        match = self.YOUTUBE_URL_PATTERN.search(msg)
        if not match:
            return False

        if not self.check_rate_limit("ambient_yt_link", 30.0):
            return False

        video_id = match.group(1)
        video_info = self._get_youtube_video_info_by_id(video_id)

        if video_info:
            title = self.bot.title_for(username)
            view_str = f"{video_info['views']:,}" if video_info.get('views') is not None else "an unknown number of"
            response = (
                f"Ah, {title}, I see you've found \"{video_info['title']}\". "
                f"It runs for {video_info['duration']} and has garnered {view_str} views."
            )
            self.safe_reply(connection, event, response)
            return True
        return False

    def _handle_ambient_titles(self, connection, event, msg, username):
        if not self.get_config_value("titles_enabled", event.target, default=True):
            return False

        match = self.URL_PATTERN.search(msg)
        if not match:
            return False

        url = match.group(1)
        
        if "youtube.com" in url or "youtu.be" in url:
            return False
        shlink_config = self.bot.config.get("api_keys", {}).get("shlink_url", "")
        if shlink_config and shlink_config in url:
            return False

        cooldown = self.get_config_value("titles_cooldown_seconds", event.target, default=5.0)
        if not self.check_rate_limit("url_title", cooldown):
            return False

        title = self._get_url_title(url)

        if title:
            title_cleaned = " ".join(title.strip().split())
            response = f"Allow me to present the title of that link for you, {self.bot.title_for(username)}: \"{title_cleaned}\""
            self.safe_reply(connection, event, response)
            return True

        return False

    def _get_url_title(self, url: str) -> Optional[str]:
        headers = {'User-Agent': 'JeevesIRCBot/1.0 (URL Title Fetcher)'}
        max_bytes = self.get_config_value("titles_max_download_bytes", default=32768)
        try:
            with self.http_session.get(url, headers=headers, stream=True, timeout=5) as response:
                response.raise_for_status()
                content_chunk = response.iter_content(chunk_size=1024, decode_unicode=True)
                html_head = ""
                for part in content_chunk:
                    html_head += part
                    title_match = self.TITLE_PATTERN.search(html_head)
                    if title_match:
                        soup = BeautifulSoup(title_match.group(1), 'html.parser')
                        return html.unescape(soup.get_text())
                    if len(html_head) > max_bytes:
                        break
                if html_head:
                    soup = BeautifulSoup(html_head, 'html.parser')
                    if soup.title and soup.title.string:
                        return html.unescape(soup.title.string)
        except Exception as e:
            self.log_debug(f"Error parsing title for {url}: {e}")
            return None
        return None

    def _cmd_google(self, connection, event, msg, username, match):
        query = match.group(1).strip()
        encoded_query = quote_plus(query)
        sassy_chance = self.get_config_value("sassy_google_chance", event.target, default=0.1)

        if random.random() < sassy_chance:
            self.safe_reply(connection, event, f"Allow me to demonstrate, {self.bot.title_for(username)}: https://letmegooglethat.com/?q={encoded_query}")
            return True
        search_url = f"https://www.google.com/search?q={encoded_query}"
        self.safe_reply(connection, event, f"{self.bot.title_for(username)}, your Google search for '{query}': {self._get_short_url(search_url)}")
        return True

    def _cmd_ud(self, connection, event, msg, username, match):
        term = match.group(1).strip()
        sassy_chance = self.get_config_value("sassy_ud_chance", event.target, default=0.05)
        sassy_terms = self.get_config_value("sassy_ud_terms", event.target, default=[])
        
        if sassy_terms and random.random() < sassy_chance:
            original_term, term = term, random.choice(sassy_terms)
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
        sassy_chance = self.get_config_value("sassy_wiki_chance", event.target, default=0.1)
        
        if random.random() < sassy_chance:
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
        try:
            response = self.http_session.get(rss_url, timeout=10)
            response.raise_for_status()
            root = ET.fromstring(response.content)
            top_item = root.find('.//item')
            if top_item is not None and (title := top_item.find('title')) is not None and (link := top_item.find('link')) is not None:
                return {"title": title.text, "link": link.text}
        except Exception as e:
            self._record_error(f"Google News RSS request failed for '{rss_url}': {e}")
        return None

    def _cmd_news(self, connection, event, msg, username, match):
        user_id = self.bot.get_user_id(username)
        location_obj = self.bot.get_module_state("weather").get("user_locations", {}).get(user_id)
        if location_obj and location_obj.get("short_name"):
            short_name, cc = location_obj["short_name"], location_obj.get("country_code", "US").upper()
            rss_url = f"https://news.google.com/rss/search?q={quote_plus(short_name)}&hl=en-{cc}&gl={cc}&ceid={cc}:en"
            if (news_item := self._get_news_from_rss(rss_url)):
                self.safe_reply(connection, event, f"The top story for {short_name} is: \"{news_item['title']}\"")
                self.safe_reply(connection, event, self._get_short_url(news_item['link']))
                return True
        
        self.safe_reply(connection, event, "I'm afraid the news service is unavailable at this time.")
        return True

    def _cmd_yt(self, connection, event, msg, username, match):
        if not self.youtube_service:
            self.safe_reply(connection, event, f"{self.bot.title_for(username)}, the YouTube service is not configured correctly.")
            return True
        query = match.group(1).strip()
        video_info = self._get_youtube_video_info_by_query(query)
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
        if shorten_module and shorten_module.is_enabled(self.bot.primary_channel):
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

    def _get_youtube_video_info_by_id(self, video_id: str) -> Optional[dict]:
        if not self.youtube_service: return None
        try:
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
            self._record_error(f"YouTube API video request failed for ID '{video_id}': {e}")
            return None

    def _get_youtube_video_info_by_query(self, query: str) -> Optional[dict]:
        if not self.youtube_service: return None
        try:
            search_request = self.youtube_service.search().list(q=query, part='snippet', maxResults=1, type='video', order='relevance')
            search_response = search_request.execute()
            if not search_response.get('items'): return None
            video_id = search_response['items'][0]['id']['videoId']
            return self._get_youtube_video_info_by_id(video_id)
        except Exception as e:
            self._record_error(f"YouTube API request failed for query '{query}': {e}")
            return None

