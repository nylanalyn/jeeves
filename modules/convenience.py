# modules/convenience.py
# A module for common, convenient search commands and URL title fetching.
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
    version = "2.0.0" # Merged titles.py functionality
    description = "Provides convenient search commands and automatic URL title fetching."

    # Patterns for different URL types
    YOUTUBE_URL_PATTERN = re.compile(r'(?:https?://)?(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)([\w\-]{11})')
    URL_PATTERN = re.compile(r'(https?://\S+)')
    TITLE_PATTERN = re.compile(r'<title>(.*?)</title>', re.IGNORECASE | re.DOTALL)


    def __init__(self, bot, config):
        super().__init__(bot)
        self.http_session = self.requests_retry_session()
        
        self.youtube_service = None
        youtube_api_key = self.bot.config.get("api_keys", {}).get("youtube")
        if youtube_api_key and build:
            try:
                self.youtube_service = build('youtube', 'v3', developerKey=youtube_api_key)
            except Exception as e:
                self._record_error(f"Failed to build YouTube service: {e}")

    def _register_commands(self):
        self.register_command(r"^\s*!g\s+(.+)$", self._cmd_google, name="g", cooldown=5.0)
        self.register_command(r"^\s*!ud\s+(.+)$", self._cmd_ud, name="ud", cooldown=10.0)
        self.register_command(r"^\s*!wiki\s+(.+)$", self._cmd_wiki, name="wiki", cooldown=10.0)
        self.register_command(r"^\s*!news\s*$", self._cmd_news, name="news", cooldown=15.0)
        self.register_command(r"^\s*!yt\s+(.+)$", self._cmd_yt, name="yt", cooldown=15.0)

    def on_ambient_message(self, connection, event, msg, username):
        if not self.is_enabled(event.target):
            return False

        # --- 1. YouTube Link Handling ---
        yt_match = self.YOUTUBE_URL_PATTERN.search(msg)
        if yt_match:
            if self.check_rate_limit(f"ambient_yt_{event.target}", 30.0):
                video_id = yt_match.group(1)
                video_info = self._get_youtube_video_info_by_id(video_id)
                if video_info:
                    title = self.bot.title_for(username)
                    view_str = f"{video_info['views']:,}" if video_info.get('views') is not None else "an unknown number of"
                    response = (f"Ah, {title}, I see you've found \"{video_info['title']}\". "
                                f"It runs for {video_info['duration']} and has garnered {view_str} views.")
                    self.safe_reply(connection, event, response)
                    return True # Handled, so we stop here.
        
        # --- 2. Generic URL Title Handling (from titles.py) ---
        titles_enabled = self.get_config_value("titles_enabled", event.target, True)
        if not titles_enabled or not BeautifulSoup:
            return False

        url_match = self.URL_PATTERN.search(msg)
        if not url_match:
            return False

        url = url_match.group(1)

        # Avoid fetching titles from our own shortened URLs to prevent loops
        if "shorten" in self.bot.pm.plugins:
            shlink_url = self.bot.pm.plugins["shorten"].SHLINK_API_URL
            if shlink_url and "://" in shlink_url and shlink_url.split("://")[1] in url:
                return False

        cooldown = self.get_config_value("titles_cooldown_seconds", event.target, 5.0)
        if not self.check_rate_limit(f"url_title_{event.target}", cooldown):
            return False

        title = self._get_url_title(url, event.target)

        if title:
            title_cleaned = " ".join(title.strip().split())
            response = f"Allow me to present the title of that link, {self.bot.title_for(username)}: \"{title_cleaned}\""
            self.safe_reply(connection, event, response)
            return True

        return False

    def _cmd_google(self, connection, event, msg, username, match):
        query = match.group(1).strip()
        encoded_query = quote_plus(query)
        sassy_chance = self.get_config_value("sassy_google_chance", event.target, 0.1)

        if random.random() < sassy_chance:
            self.safe_reply(connection, event, f"Allow me to demonstrate, {self.bot.title_for(username)}: https://letmegooglethat.com/?q={encoded_query}")
            return True

        search_url = f"https://www.google.com/search?q={encoded_query}"
        self.safe_reply(connection, event, f"{self.bot.title_for(username)}, your Google search for '{query}': {self._get_short_url(search_url)}")
        return True

    def _cmd_ud(self, connection, event, msg, username, match):
        term = match.group(1).strip()
        sassy_chance = self.get_config_value("sassy_ud_chance", event.target, 0.05)
        sassy_terms = self.get_config_value("sassy_ud_terms", ["lazy", "procrastination"])

        if random.random() < sassy_chance and sassy_terms:
            original_term, term = term, random.choice(sassy_terms)
            intro = f"While searching for '{original_term}', I was reminded of a more relevant term, {self.bot.title_for(username)}. For '{term}':"
        else:
            intro = f"For '{term}':"

        api_url = f"http://api.urbandictionary.com/v0/define?term={quote_plus(term)}"
        try:
            response = self.http_session.get(api_url, timeout=5)
            response.raise_for_status()
            data = response.json()
            if not data or not data.get("list"):
                self.safe_reply(connection, event, f"My apologies, no definition for '{term}'.")
                return True
            top_def = re.sub(r'\[|\]', '', data["list"][0].get("definition", "")).replace('\r\n', ' ').strip()
            self.safe_reply(connection, event, f"{intro} {top_def}")
        except requests.exceptions.RequestException:
            self.safe_reply(connection, event, "The Urban Dictionary service is unavailable.")
        return True

    def _cmd_wiki(self, connection, event, msg, username, match):
        query = match.group(1).strip()
        wiki_url = f"https://en.wikipedia.org/w/index.php?search={quote_plus(query)}"
        self.safe_reply(connection, event, f"{self.bot.title_for(username)}, your Wikipedia search: {self._get_short_url(wiki_url)}")
        return True

    def _cmd_news(self, connection, event, msg, username, match):
        user_id = self.bot.get_user_id(username)
        location = self.bot.get_module_state("weather").get("user_locations", {}).get(user_id)
        
        if location and (short_name := location.get("short_name")):
            cc = location.get("country_code", "US").upper()
            rss_url = f"https://news.google.com/rss/search?q={quote_plus(short_name)}&hl=en-{cc}&gl={cc}&ceid={cc}:en"
            if item := self._get_news_from_rss(rss_url):
                self.safe_reply(connection, event, f"Top story for {short_name}: \"{item['title']}\" {self._get_short_url(item['link'])}")
                return True

        if item := self._get_news_from_rss("https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en"):
            self.safe_reply(connection, event, f"Top global story: \"{item['title']}\" {self._get_short_url(item['link'])}")
        else:
            self.safe_reply(connection, event, "The news service is unavailable.")
        return True

    def _cmd_yt(self, connection, event, msg, username, match):
        if not self.youtube_service:
            self.safe_reply(connection, event, "The YouTube service is not configured.")
            return True
        query = match.group(1).strip()
        if video_info := self._get_youtube_video_info_by_query(query):
            views = f"{video_info['views']:,}" if video_info.get('views') is not None else "N/A"
            self.safe_reply(connection, event, f"For '{query}': \"{video_info['title']}\" | Duration: {video_info['duration']}. Views: {views}. {self._get_short_url(video_info['url'])}")
        else:
            self.safe_reply(connection, event, f"No suitable video found for '{query}'.")
        return True
    
    # --- Helper Methods ---

    def _get_url_title(self, url: str, channel: str) -> Optional[str]:
        headers = {'User-Agent': 'JeevesIRCBot/1.0 (URL Title Fetcher)'}
        max_bytes = self.get_config_value("titles_max_download_bytes", channel, 32768)
        try:
            with self.http_session.get(url, headers=headers, stream=True, timeout=5) as r:
                r.raise_for_status()
                head = ""
                for chunk in r.iter_content(chunk_size=1024, decode_unicode=True):
                    head += chunk
                    if (match := self.TITLE_PATTERN.search(head)):
                        return html.unescape(BeautifulSoup(match.group(1), 'html.parser').get_text())
                    if len(head.encode('utf-8')) > max_bytes: break
                if head and (soup := BeautifulSoup(head, 'html.parser')) and soup.title and soup.title.string:
                    return html.unescape(soup.title.string)
        except Exception:
            return None
        return None

    def _get_news_from_rss(self, rss_url: str) -> Optional[Dict[str, str]]:
        try:
            r = self.http_session.get(rss_url, timeout=10)
            r.raise_for_status()
            item = ET.fromstring(r.content).find('.//item')
            if item is not None and (title := item.find('title')) is not None and (link := item.find('link')) is not None:
                return {"title": title.text, "link": link.text}
        except Exception:
            return None

    def _get_short_url(self, url: str) -> str:
        if shorten_mod := self.bot.pm.plugins.get("shorten"):
            if short_url := shorten_mod._shorten_url(url):
                return short_url
        return url

    def _parse_duration(self, iso: str) -> str:
        if not (match := re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', iso)): return "N/A"
        h, m, s = match.groups()
        return " ".join(f"{int(p)}{u}" for p, u in zip((h, m, s), ('h', 'm', 's')) if p) or "0s"

    def _get_youtube_video_info_by_id(self, video_id: str) -> Optional[dict]:
        if not self.youtube_service: return None
        try:
            res = self.youtube_service.videos().list(part='snippet,statistics,contentDetails', id=video_id).execute()
            if not res.get('items'): return None
            d = res['items'][0]
            return {"title": d['snippet']['title'], "views": int(d['statistics'].get('viewCount', 0)),
                    "duration": self._parse_duration(d['contentDetails']['duration']),
                    "url": f"https://youtu.be/{video_id}"}
        except Exception as e:
            self._record_error(f"YouTube API video request failed for ID '{video_id}': {e}")
            return None

    def _get_youtube_video_info_by_query(self, query: str) -> Optional[dict]:
        if not self.youtube_service: return None
        try:
            res = self.youtube_service.search().list(q=query, part='snippet', maxResults=1, type='video').execute()
            if not res.get('items'): return None
            return self._get_youtube_video_info_by_id(res['items'][0]['id']['videoId'])
        except Exception as e:
            self._record_error(f"YouTube API search request failed for query '{query}': {e}")
            return None

