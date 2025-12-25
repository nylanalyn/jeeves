# modules/convenience.py
# Merged module for common, convenient search commands and URL title fetching.
import re
import xml.etree.ElementTree as ET
import random
import html
import time
import requests
from urllib.parse import quote_plus
from typing import Optional, Dict, Any

try:
    from modules.exception_utils import (
        handle_exceptions, safe_api_call, safe_file_operation,
        ExternalAPIException, NetworkException, UserInputException
    )
except ImportError:
    # Fallback for when exception_utils is not available
    def handle_exceptions(func):
        return func
    def safe_api_call(func, *args, **kwargs):
        try:
            return func(*args, **kwargs), None
        except Exception:
            return None, "An error occurred"
    def safe_file_operation(func, *args, **kwargs):
        return func(*args, **kwargs)
    class ExternalAPIException(Exception): pass
    class NetworkException(Exception): pass
    class UserInputException(Exception): pass

from .base import ModuleBase

# Import shared utilities
try:
    from .http_utils import get_http_client
    from .config_manager import create_config_manager
    HTTP_CLIENT = get_http_client()
except ImportError:
    # Fallback for when shared utilities are not available
    HTTP_CLIENT = None
    create_config_manager = None 

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

try:
    from googleapiclient.discovery import build
except ImportError:
    build = None

def setup(bot):
    if not BeautifulSoup:
        print("[convenience] beautifulsoup4 is not installed. !g and title fetching will be limited.")
    if not build:
        print("[convenience] google-api-python-client is not installed. !yt command will not load.")
    return Convenience(bot)

class Convenience(ModuleBase):
    name = "convenience"
    version = "1.9.2" # Anti-spam: suppress repeated title announcements
    description = "Provides convenient, common search commands and URL title fetching."

    YOUTUBE_URL_PATTERN = re.compile(r'(?:https?://)?(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)([\w\-]{11})')
    URL_PATTERN = re.compile(r'(https?://\S+)')
    TITLE_PATTERN = re.compile(r'<title>(.*?)</title>', re.IGNORECASE | re.DOTALL)

    def __init__(self, bot):
        super().__init__(bot)
        self._register_commands()

        # Track recently announced titles to avoid spam (title -> list of timestamps)
        self._recent_titles: Dict[str, list] = {}
        self._title_max_repeats = 2  # Stop announcing after this many repeats
        self._title_window_seconds = 300  # 5 minute window for tracking repeats

        # Use shared HTTP client if available, otherwise fallback
        if HTTP_CLIENT:
            self.http_session = HTTP_CLIENT.session
        else:
            self.http_session = self.requests_retry_session()
        
        # Use config manager if available
        if create_config_manager:
            self.config_manager = create_config_manager(self.bot.config)
            youtube_api_key = self.config_manager.get_api_key("youtube", required=False)
        else:
            youtube_api_key = self.bot.config.get("api_keys", {}).get("youtube")
        
        self.youtube_service = None
        if youtube_api_key and build:
            try:
                self.youtube_service = build('youtube', 'v3', developerKey=youtube_api_key)
            except (ImportError, AttributeError, Exception) as e:
                self.log_module_event("ERROR", f"Failed to build YouTube service: {e}")
                self._record_error(f"Failed to build YouTube service: {e}")

    def _register_commands(self):
        self.register_command(r"^\s*!g\s+(.+)$", self._cmd_google, name="g", description="Search Google")
        self.register_command(r"^\s*!dict\s+(.+)$", self._cmd_dict, name="dict", description="Look up a word in the dictionary")
        self.register_command(r"^\s*!ud\s+(.+)$", self._cmd_dict, name="ud", description="Look up a word in Urban Dictionary")
        self.register_command(r"^\s*!wiki\s+(.+)$", self._cmd_wiki, name="wiki", description="Search Wikipedia")
        self.register_command(r"^\s*!news\s*$", self._cmd_news, name="news", description="Get top news headlines")
        self.register_command(r"^\s*!yt\s+(.+)$", self._cmd_yt, name="yt", description="Search YouTube")

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
            if self.has_flavor_enabled(username):
                title = self.bot.title_for(username)
                view_str = f"{video_info['views']:,}" if video_info.get('views') is not None else "an unknown number of"
                response = (
                    f"Ah, {title}, I see you've found \"{video_info['title']}\". "
                    f"It runs for {video_info['duration']} and has garnered {view_str} views."
                )
            else:
                view_str = f"{video_info['views']:,}" if video_info.get('views') is not None else "N/A"
                response = f"\"{video_info['title']}\" - {video_info['duration']} - {view_str} views"
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
        # Use config manager if available
        if create_config_manager:
            shlink_config = self.config_manager.get_api_key("shlink_url", required=False) or ""
        else:
            shlink_config = self.bot.config.get("api_keys", {}).get("shlink_url", "")
        if shlink_config and shlink_config in url:
            return False

        cooldown = self.get_config_value("titles_cooldown_seconds", event.target, default=5.0)
        if not self.check_rate_limit("url_title", cooldown):
            return False

        title = self._get_url_title(url)

        if title:
            title_cleaned = " ".join(title.strip().split())

            # Check if we've announced this title too many times recently
            if self._is_title_spam(title_cleaned):
                self.log_module_event("DEBUG", f"Suppressing repeated title announcement: \"{title_cleaned}\"")
                return False

            if self.has_flavor_enabled(username):
                response = f"Allow me to present the title of that link for you, {self.bot.title_for(username)}: \"{title_cleaned}\""
            else:
                response = f"\"{title_cleaned}\""
            self.safe_reply(connection, event, response)
            return True

        return False

    def _is_title_spam(self, title: str) -> bool:
        """Check if a title has been announced too many times recently.

        Returns True if the title should be suppressed (spam), False if it's okay to announce.
        Also records this announcement for future spam detection.
        """
        now = time.time()
        cutoff = now - self._title_window_seconds

        # Clean up old entries from all tracked titles
        titles_to_remove = []
        for tracked_title, timestamps in self._recent_titles.items():
            # Remove timestamps outside the window
            self._recent_titles[tracked_title] = [t for t in timestamps if t > cutoff]
            # Mark empty entries for removal
            if not self._recent_titles[tracked_title]:
                titles_to_remove.append(tracked_title)
        for tracked_title in titles_to_remove:
            del self._recent_titles[tracked_title]

        # Check if this title has been announced too many times
        if title in self._recent_titles:
            if len(self._recent_titles[title]) >= self._title_max_repeats:
                return True  # Suppress this announcement

        # Record this announcement
        if title not in self._recent_titles:
            self._recent_titles[title] = []
        self._recent_titles[title].append(now)

        return False  # Okay to announce

    def _get_url_title(self, url: str) -> Optional[str]:
        headers = {'User-Agent': 'JeevesIRCBot/1.0 (URL Title Fetcher)'}
        max_bytes = self.get_config_value("titles_max_download_bytes", default=32768)
        max_total_time = 10  # Maximum 10 seconds for entire download

        try:
            with self.http_session.get(url, headers=headers, stream=True, timeout=5) as response:
                response.raise_for_status()
                content_chunk = response.iter_content(chunk_size=1024, decode_unicode=False)
                html_head = ""
                start_time = time.time()
                encoding = response.encoding or response.apparent_encoding or "utf-8"

                for part in content_chunk:
                    if time.time() - start_time > max_total_time:
                        self.log_module_event("WARNING", f"URL title fetch timed out for {url}")
                        break

                    if isinstance(part, bytes):
                        part = part.decode(encoding, errors="ignore")

                    html_head += part
                    title_match = self.TITLE_PATTERN.search(html_head)
                    if title_match:
                        title_text = title_match.group(1).strip()
                        title_text = re.sub(r'<[^>]+>', '', title_text)
                        return html.unescape(title_text)
                    if len(html_head) > max_bytes:
                        break

                if html_head and BeautifulSoup:
                    soup = BeautifulSoup(html_head, 'html.parser')
                    if soup.title and soup.title.string:
                        return html.unescape(soup.title.string)
        except Exception as e:
            self.log_module_event("WARNING", f"Error parsing title for {url}: {e}")
            return None
        return None

    def _cmd_google(self, connection, event, msg, username, match):
        query = match.group(1).strip()
        encoded_query = quote_plus(query)
        sassy_chance = self.get_config_value("sassy_google_chance", event.target, default=0.1)
        fallback_url = self._get_short_url(f"https://duckduckgo.com/?q={encoded_query}")

        if random.random() < sassy_chance:
            if self.has_flavor_enabled(username):
                self.safe_reply(connection, event, f"Allow me to demonstrate, {self.bot.title_for(username)}: https://letmegooglethat.com/?q={encoded_query}")
            else:
                self.safe_reply(connection, event, f"https://letmegooglethat.com/?q={encoded_query}")
            return True

        search_result = self._perform_duckduckgo_search(query)
        if search_result:
            display_url = self._get_short_url(search_result["url"])
            snippet = search_result.get("snippet", "")
            snippet = " ".join(snippet.split())
            if len(snippet) > 200:
                snippet = f"{snippet[:197]}..."

            if self.has_flavor_enabled(username):
                title = self.bot.title_for(username)
                snippet_part = f" — {snippet}" if snippet else ""
                self.safe_reply(connection, event, f"{title}, DuckDuckGo offers \"{search_result['title']}\" for '{query}'{snippet_part}")
                self.safe_reply(connection, event, display_url)
            else:
                response = f"{search_result['title']} - {display_url}"
                if snippet:
                    response += f" — {snippet}"
                self.safe_reply(connection, event, response)
            return True

        if self.has_flavor_enabled(username):
            self.safe_reply(connection, event, f"{self.bot.title_for(username)}, DuckDuckGo is speechless—here's a direct link instead: {fallback_url}")
        else:
            self.safe_reply(connection, event, fallback_url)
        return True

    def _cmd_dict(self, connection, event, msg, username, match):
        word = match.group(1).strip().lower()
        has_flavor = self.has_flavor_enabled(username)
        sassy_chance = self.get_config_value("sassy_dict_chance", event.target, default=0.02)
        lazy_words = ["indolent", "slothful", "idle", "lethargic", "languid", "sluggish", "lazy", "lackadaisical", "listless", "torpid"]

        # 2% chance to be sassy and define a word meaning lazy instead
        original_word = None
        if random.random() < sassy_chance:
            original_word = word
            word = random.choice(lazy_words)

        api_url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{quote_plus(word)}"
        try:
            response = self.http_session.get(api_url, timeout=5)
            response.raise_for_status()
            data = response.json()

            if not data or not isinstance(data, list) or len(data) == 0:
                if has_flavor:
                    self.safe_reply(connection, event, f"My apologies, {self.bot.title_for(username)}, I could find no definition for '{word}'.")
                else:
                    self.safe_reply(connection, event, f"No definition found for '{word}'.")
                return True

            entry = data[0]
            word_text = entry.get("word", word)
            phonetic = entry.get("phonetic", "")

            # Get first meaning and definition
            meanings = entry.get("meanings", [])
            if not meanings:
                if has_flavor:
                    self.safe_reply(connection, event, f"My apologies, {self.bot.title_for(username)}, I could find no definition for '{word}'.")
                else:
                    self.safe_reply(connection, event, f"No definition found for '{word}'.")
                return True

            first_meaning = meanings[0]
            part_of_speech = first_meaning.get("partOfSpeech", "")
            definitions = first_meaning.get("definitions", [])

            if not definitions:
                if has_flavor:
                    self.safe_reply(connection, event, f"My apologies, {self.bot.title_for(username)}, I could find no definition for '{word}'.")
                else:
                    self.safe_reply(connection, event, f"No definition found for '{word}'.")
                return True

            first_def = definitions[0].get("definition", "No definition available.")
            example = definitions[0].get("example", "")

            # Format the output
            if has_flavor:
                if original_word:
                    header = f"While searching for '{original_word}', I was reminded of a more relevant term, {self.bot.title_for(username)}. For '{word_text}'"
                else:
                    header = f"{self.bot.title_for(username)}, for '{word_text}'"
                if phonetic:
                    header += f" ({phonetic})"
                header += ":"
                self.safe_reply(connection, event, header)
            else:
                header = f"'{word_text}'"
                if phonetic:
                    header += f" ({phonetic})"
                header += ":"
                self.safe_reply(connection, event, header)

            # Definition line
            def_line = f"({part_of_speech}) {first_def}" if part_of_speech else first_def
            self.safe_reply(connection, event, def_line)

            # Example if available
            if example and has_flavor:
                self.safe_reply(connection, event, f"Example: \"{example}\"")
            elif example:
                self.safe_reply(connection, event, f"e.g., \"{example}\"")

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                if has_flavor:
                    self.safe_reply(connection, event, f"My apologies, {self.bot.title_for(username)}, I could find no definition for '{word}'.")
                else:
                    self.safe_reply(connection, event, f"No definition found for '{word}'.")
            else:
                self._record_error(f"Dictionary API request failed: {e}")
                if has_flavor:
                    self.safe_reply(connection, event, "I'm afraid the dictionary service is unavailable at the moment.")
                else:
                    self.safe_reply(connection, event, "Dictionary service unavailable.")
        except requests.exceptions.RequestException as e:
            self._record_error(f"Dictionary API request failed: {e}")
            if has_flavor:
                self.safe_reply(connection, event, "I'm afraid the dictionary service is unavailable at the moment.")
            else:
                self.safe_reply(connection, event, "Dictionary service unavailable.")
        return True

    def _cmd_wiki(self, connection, event, msg, username, match):
        query = match.group(1).strip()
        sassy_chance = self.get_config_value("sassy_wiki_chance", event.target, default=0.1)
        has_flavor = self.has_flavor_enabled(username)
        search_url = self._get_short_url(f'https://en.wikipedia.org/w/index.php?search={quote_plus(query)}')

        if random.random() < sassy_chance:
            if has_flavor:
                self.safe_reply(connection, event, f"A moment, {self.bot.title_for(username)}, while I consult the grand library... Ah, here is the relevant section: {search_url}")
            else:
                self.safe_reply(connection, event, search_url)
            return True

        api_url = f"https://en.wikipedia.org/w/api.php?action=query&format=json&prop=extracts&exintro=true&explaintext=true&redirects=1&titles={quote_plus(query)}"
        headers = {'User-Agent': 'JeevesIRCBot/1.0 (IRC Bot; https://github.com/anthropics/jeeves)'}
        try:
            response = self.http_session.get(api_url, headers=headers, timeout=5)
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

        if has_flavor:
            self.safe_reply(connection, event, f"{self.bot.title_for(username)}, your Wikipedia search for '{query}': {search_url}")
        else:
            self.safe_reply(connection, event, search_url)
        return True

    def _get_news_from_rss(self, rss_url: str) -> Optional[Dict[str, str]]:
        try:
            response = self.http_session.get(rss_url, timeout=10)
            response.raise_for_status()
            root = ET.fromstring(response.content)
            top_item = root.find('.//item')
            if top_item is not None and (title := top_item.find('title')) is not None and (link := top_item.find('link')) is not None:
                return {"title": title.text, "link": link.text}
        except (requests.RequestException, ET.ParseError, AttributeError, ValueError) as e:
            self.log_module_event("ERROR", f"Google News RSS request failed for '{rss_url}': {e}")
            self._record_error(f"Google News RSS request failed for '{rss_url}': {e}")
        return None

    def _cmd_news(self, connection, event, msg, username, match):
        user_id = self.bot.get_user_id(username)
        location_obj = self.bot.get_module_state("weather").get("user_locations", {}).get(user_id)
        has_flavor = self.has_flavor_enabled(username)

        # First attempt: Local news based on city/state
        if location_obj and location_obj.get("short_name"):
            short_name, cc = location_obj["short_name"], location_obj.get("country_code", "US").upper()
            rss_url = f"https://news.google.com/rss/search?q={quote_plus(short_name)}&hl=en-{cc}&gl={cc}&ceid={cc}:en"
            if (news_item := self._get_news_from_rss(rss_url)):
                if has_flavor:
                    self.safe_reply(connection, event, f"The top story for {short_name} is: \"{news_item['title']}\"")
                else:
                    self.safe_reply(connection, event, f"\"{news_item['title']}\"")
                self.safe_reply(connection, event, self._get_short_url(news_item['link']))
                return True
            else:
                if has_flavor:
                    self.safe_reply(connection, event, f"I found no specific news for {short_name}, broadening the search...")

        # Second attempt: National news based on country code
        if location_obj and location_obj.get("country_code"):
            cc = location_obj.get("country_code", "US").upper()
            rss_url = f"https://news.google.com/rss?hl=en-{cc}&gl={cc}&ceid={cc}:en"
            if (news_item := self._get_news_from_rss(rss_url)):
                if has_flavor:
                    self.safe_reply(connection, event, f"The top national story is: \"{news_item['title']}\"")
                else:
                    self.safe_reply(connection, event, f"\"{news_item['title']}\"")
                self.safe_reply(connection, event, self._get_short_url(news_item['link']))
                return True

        # Third attempt: Global (US) news as the final fallback
        if (news_item := self._get_news_from_rss("https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en")):
            if has_flavor:
                self.safe_reply(connection, event, f"The top global story is: \"{news_item['title']}\"")
            else:
                self.safe_reply(connection, event, f"\"{news_item['title']}\"")
            self.safe_reply(connection, event, self._get_short_url(news_item['link']))
        else:
            if has_flavor:
                self.safe_reply(connection, event, "I'm afraid the news service is unavailable at this time.")
            else:
                self.safe_reply(connection, event, "News service unavailable.")
        return True

    def _cmd_yt(self, connection, event, msg, username, match):
        has_flavor = self.has_flavor_enabled(username)
        if not self.youtube_service:
            if has_flavor:
                self.safe_reply(connection, event, f"{self.bot.title_for(username)}, the YouTube service is not configured correctly.")
            else:
                self.safe_reply(connection, event, "YouTube service not configured.")
            return True
        query = match.group(1).strip()
        video_info = self._get_youtube_video_info_by_query(query)
        if video_info:
            view_str = f"{video_info['views']:,}" if video_info.get('views') is not None else "N/A"
            if has_flavor:
                self.safe_reply(connection, event, f"For '{query}', I present: \"{video_info['title']}\".")
                self.safe_reply(connection, event, f"Duration: {video_info['duration']}. Views: {view_str}. {self._get_short_url(video_info['url'])}")
            else:
                self.safe_reply(connection, event, f"\"{video_info['title']}\" - {video_info['duration']} - {view_str} views")
                self.safe_reply(connection, event, self._get_short_url(video_info['url']))
        else:
            if has_flavor:
                self.safe_reply(connection, event, f"My apologies, {self.bot.title_for(username)}, I could not find a suitable video for '{query}'.")
            else:
                self.safe_reply(connection, event, f"No video found for '{query}'.")
        return True
    
    # --- Helper Methods ---

    def _perform_duckduckgo_search(self, query: str) -> Optional[Dict[str, str]]:
        """Use DuckDuckGo's Instant Answer API to grab a quick hit."""
        endpoint = "https://api.duckduckgo.com/"
        params = {
            "q": query,
            "format": "json",
            "no_redirect": "1",
            "no_html": "1",
            "skip_disambig": "1"
        }

        try:
            response = self.http_session.get(endpoint, params=params, timeout=6)
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as exc:
            self._record_error(f"DuckDuckGo search failed: {exc}")
            return None
        except ValueError as exc:
            self._record_error(f"DuckDuckGo returned invalid JSON: {exc}")
            return None

        if data.get("AbstractText") and data.get("AbstractURL"):
            return {
                "title": data.get("Heading") or "Result",
                "url": data.get("AbstractURL"),
                "snippet": data.get("AbstractText")
            }

        related_topics = data.get("RelatedTopics", [])
        for topic in related_topics:
            if isinstance(topic, dict) and topic.get("FirstURL") and topic.get("Text"):
                return {
                    "title": topic.get("Text"),
                    "url": topic.get("FirstURL"),
                    "snippet": ""
                }
            if isinstance(topic, dict) and topic.get("Topics"):
                subtopics = topic.get("Topics", [])
                for sub in subtopics:
                    if sub.get("FirstURL") and sub.get("Text"):
                        return {
                            "title": sub.get("Text"),
                            "url": sub.get("FirstURL"),
                            "snippet": ""
                        }

        return None

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
        except (AttributeError, KeyError, ValueError, Exception) as e:
            self.log_module_event("ERROR", f"YouTube API video request failed for ID '{video_id}': {e}")
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
        except (AttributeError, KeyError, ValueError, Exception) as e:
            self.log_module_event("ERROR", f"YouTube API request failed for query '{query}': {e}")
            self._record_error(f"YouTube API request failed for query '{query}': {e}")
            return None
