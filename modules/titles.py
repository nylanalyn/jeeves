# modules/titles.py
# A module to automatically fetch and display the titles of URLs posted in chat.
import re
import requests
import html
from typing import Optional
from .base import ModuleBase

# The user will need to install this library: pip install beautifulsoup4
try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

def setup(bot, config):
    return Titles(bot, config)

class Titles(ModuleBase):
    name = "titles"
    version = "1.0.1" # version bumped
    description = "Automatically fetches titles from URLs posted in chat."

    # A robust regex for finding URLs in messages
    URL_PATTERN = re.compile(r'(https?://\S+)')
    # A regex to find the title tag in a chunk of HTML
    TITLE_PATTERN = re.compile(r'<title>(.*?)</title>', re.IGNORECASE | re.DOTALL)

    def __init__(self, bot, config):
        super().__init__(bot)
        self.enabled = config.get("enabled", True)
        self.COOLDOWN = config.get("cooldown_seconds", 5.0)
        self.MAX_DOWNLOAD_BYTES = config.get("max_download_bytes", 32 * 1024) # 32KB

        if not BeautifulSoup:
            self._record_error("beautifulsoup4 is not installed. Module will not function.")

        # Use the resilient session from the base class
        self.http_session = self.requests_retry_session()

    def on_ambient_message(self, connection, event, msg: str, username: str) -> bool:
        if not self.enabled or not BeautifulSoup:
            return False

        match = self.URL_PATTERN.search(msg)
        if not match:
            return False

        url = match.group(1)

        # Avoid fetching titles from our own shortened URLs to prevent loops
        if "shorten" in self.bot.pm.plugins:
            shlink_url = self.bot.pm.plugins["shorten"].SHLINK_API_URL
            if shlink_url and shlink_url in url:
                return False

        # Check rate limit to avoid spamming
        if not self.check_rate_limit("url_title", self.COOLDOWN):
            return False

        title = self._get_url_title(url)

        if title:
            title_cleaned = " ".join(title.strip().split()) # Normalize whitespace
            response = f"Allow me to present the title of that link for you, {self.bot.title_for(username)}: \"{title_cleaned}\""
            self.safe_reply(connection, event, response)
            return True

        return False

    def _get_url_title(self, url: str) -> Optional[str]:
        """
        Fetches the title of a URL by streaming the response and parsing the first chunk.
        """
        headers = {
            'User-Agent': 'JeevesIRCBot/1.0 (URL Title Fetcher)'
        }
        try:
            with self.http_session.get(url, headers=headers, stream=True, timeout=5) as response:
                response.raise_for_status()

                # Read only the beginning of the response to find the title
                content_chunk = response.iter_content(chunk_size=1024, decode_unicode=True)
                html_head = ""
                for part in content_chunk:
                    html_head += part
                    # Simple regex check first for performance
                    title_match = self.TITLE_PATTERN.search(html_head)
                    if title_match:
                         # Use BeautifulSoup for proper parsing of entities, etc.
                        soup = BeautifulSoup(title_match.group(1), 'html.parser')
                        return html.unescape(soup.get_text())
                    
                    if len(html_head) > self.MAX_DOWNLOAD_BYTES:
                        break # Stop if we haven't found a title after a reasonable amount

                # If regex fails but we have content, try a full parse on the head
                if html_head:
                    soup = BeautifulSoup(html_head, 'html.parser')
                    if soup.title and soup.title.string:
                        return html.unescape(soup.title.string)

        except requests.exceptions.RequestException as e:
            # Don't log common errors like 404s, but do log connection errors
            if not isinstance(e, requests.exceptions.HTTPError) or e.response.status_code >= 500:
                 self._record_error(f"Failed to fetch title for {url}: {e}")
            return None
        except Exception as e:
            self._record_error(f"Error parsing title for {url}: {e}")
            return None

        return None

