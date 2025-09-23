# modules/youtube.py
# YouTube search module using Google API
import re
from typing import Optional
from .base import SimpleCommandModule, admin_required

# This library is now required: pip install google-api-python-client
try:
    from googleapiclient.discovery import build
except ImportError:
    build = None

def setup(bot, config):
    """Initializes the YouTube module."""
    if not build:
        print("[youtube] google-api-python-client is not installed. Module will not load.")
        return None
    api_key = bot.config.get("api_keys", {}).get("youtube")
    if not api_key:
        print("[youtube] YouTube API key not found in config.yaml. Module will not load.")
        return None
    return YouTube(bot, config, api_key)

class YouTube(SimpleCommandModule):
    name = "youtube"
    version = "1.4.1" # Initialization fix
    description = "Searches YouTube for a video and posts a link with details."

    YOUTUBE_URL_PATTERN = re.compile(r'(?:https?://)?(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)([\w\-]{11})')

    def __init__(self, bot, config, api_key):
        """Initializes the module's state and configuration."""
        # --- Pre-super() setup ---
        self.API_KEY = api_key
        self.COOLDOWN = config.get("cooldown_seconds", 15.0)

        # --- super() call ---
        super().__init__(bot)

        # --- Post-super() setup ---
        self.set_state("searches_performed", self.get_state("searches_performed", 0))
        self.set_state("videos_found", self.get_state("videos_found", 0))
        self.save_state()

        try:
            self.youtube_service = build('youtube', 'v3', developerKey=self.API_KEY)
        except Exception as e:
            self._record_error(f"Failed to build YouTube service: {e}")
            self.youtube_service = None

    def _register_commands(self):
        """Registers the !yt command."""
        self.register_command(
            r"^\s*!yt\s+(.+)$", self._cmd_yt,
            name="yt", cooldown=self.COOLDOWN,
            description="Search YouTube for a video. Usage: !yt <search term>"
        )
        self.register_command(
            r"^\s*!yt\s+stats\s*$", self._cmd_stats,
            name="yt stats", admin_only=True,
            description="Show YouTube search statistics."
        )

    def on_ambient_message(self, connection, event, msg, username):
        """Handles ambient YouTube links."""
        match = self.YOUTUBE_URL_PATTERN.search(msg)
        if not match:
            return False

        if not self.check_rate_limit("ambient_yt_link", 30.0):
            return False

        video_id = match.group(1)
        video_info = self._get_video_info_by_id(video_id)

        if video_info:
            title = self.bot.title_for(username)
            view_str = f"{video_info['views']:,}"
            response = (
                f"Ah, {title}, I see you've found \"{video_info['title']}\". "
                f"It runs for {video_info['duration']} and has garnered {view_str} views."
            )
            self.safe_reply(connection, event, response)
            return True
        return False

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

    def _get_video_info_by_id(self, video_id: str) -> Optional[dict]:
        """Gets video details for a given video ID."""
        if not self.youtube_service: return None
        try:
            video_request = self.youtube_service.videos().list(
                part='snippet,statistics,contentDetails', id=video_id
            )
            video_response = video_request.execute()
            if not video_response.get('items'): return None
            
            video_data = video_response['items'][0]
            self.set_state("videos_found", self.get_state("videos_found", 0) + 1)
            self.save_state()

            return {
                "title": video_data['snippet']['title'],
                "views": int(video_data['statistics']['viewCount']),
                "duration": self._parse_duration(video_data['contentDetails']['duration']),
                "url": f"https://www.youtube.com/watch?v={video_id}"
            }
        except Exception as e:
            self._record_error(f"YouTube API video request failed for ID '{video_id}': {e}")
            return None

    def _get_video_info_by_query(self, query: str) -> Optional[dict]:
        """Searches for a video and returns its details."""
        if not self.youtube_service: return None
        self.set_state("searches_performed", self.get_state("searches_performed", 0) + 1)
        self.save_state()

        try:
            search_request = self.youtube_service.search().list(
                q=query, part='snippet', maxResults=1, type='video', order='viewCount'
            )
            search_response = search_request.execute()
            if not search_response.get('items'): return None
            
            video_id = search_response['items'][0]['id']['videoId']
            return self._get_video_info_by_id(video_id)
        except Exception as e:
            self._record_error(f"YouTube API search request failed for query '{query}': {e}")
            return None

    def _cmd_yt(self, connection, event, msg, username, match):
        """Handles the !yt command."""
        if not self.youtube_service:
            self.safe_reply(connection, event, f"{self.bot.title_for(username)}, the YouTube service is not configured correctly.")
            return True

        query = match.group(1).strip()
        video_info = self._get_video_info_by_query(query)
        title = self.bot.title_for(username)

        if video_info:
            view_str = f"{video_info['views']:,}"
            response = (
                f"As you requested, {title}. For '{query}', I present: \"{video_info['title']}\". "
                f"It has garnered {view_str} views and runs for {video_info['duration']}. "
                f"{video_info['url']}"
            )
            self.safe_reply(connection, event, response)
        else:
            self.safe_reply(connection, event, f"My apologies, {title}, I could not find a suitable video for '{query}'.")
        
        return True

    @admin_required
    def _cmd_stats(self, connection, event, msg, username, match):
        """Handles the !yt stats command."""
        searches = self.get_state("searches_performed", 0)
        found = self.get_state("videos_found", 0)
        success_rate = (found / searches * 100) if searches > 0 else 0
        
        self.safe_reply(connection, event, f"YouTube stats: {found}/{searches} successful searches ({success_rate:.1f}% success rate).")
        return True

