# modules/youtube.py
# A module for searching YouTube and returning the most popular video.
import os
import re
import requests
import json
from typing import Optional, Tuple
from .base import SimpleCommandModule, admin_required

# The user will need to install this library: pip install google-api-python-client
try:
    from googleapiclient.discovery import build
except ImportError:
    build = None

def setup(bot, config):
    return YouTube(bot, config)

class YouTube(SimpleCommandModule):
    name = "youtube"
    version = "1.0.1" # version bumped for fix
    description = "Searches YouTube for a video and posts the most popular result."

    API_KEY = os.getenv("YOUTUBE_API_KEY")

    def __init__(self, bot, config):
        # Define module-specific attributes BEFORE calling the parent constructor
        self.COOLDOWN = config.get("cooldown_seconds", 15.0)
        super().__init__(bot) # This call now happens after COOLDOWN is set

        self.set_state("searches_performed", self.get_state("searches_performed", 0))
        self.set_state("videos_found", self.get_state("videos_found", 0))
        self.save_state()

        if not self.API_KEY or not build:
            self._record_error("YOUTUBE_API_KEY is not set or google-api-python-client is not installed. Module will not function.")
            self.youtube_service = None
        else:
            try:
                # build a service object for interacting with the API
                self.youtube_service = build('youtube', 'v3', developerKey=self.API_KEY, cache_discovery=False)
            except Exception as e:
                self._record_error(f"Failed to initialize YouTube service: {e}")
                self.youtube_service = None

    def _register_commands(self):
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

    def _search_youtube(self, query: str) -> Optional[Tuple[str, str]]:
        """Searches YouTube and returns the title and URL of the top result."""
        if not self.youtube_service:
            return None

        self.set_state("searches_performed", self.get_state("searches_performed", 0) + 1)
        self.save_state()

        try:
            search_response = self.youtube_service.search().list(
                q=query,
                part='snippet',
                maxResults=1,
                type='video',
                order='viewCount' # Sort by most popular
            ).execute()

            results = search_response.get('items', [])
            if not results:
                return None

            video = results[0]
            video_id = video['id']['videoId']
            video_title = video['snippet']['title']
            video_url = f"https://www.youtube.com/watch?v={video_id}"

            self.set_state("videos_found", self.get_state("videos_found", 0) + 1)
            self.save_state()
            return (video_title, video_url)

        except Exception as e:
            self._record_error(f"YouTube API request failed for query '{query}': {e}")
            return None

    def _cmd_yt(self, connection, event, msg, username, match):
        if not self.youtube_service:
            self.safe_reply(connection, event, f"My apologies, {self.bot.title_for(username)}, the YouTube service is not configured correctly.")
            return True

        query = match.group(1).strip()
        result = self._search_youtube(query)
        title = self.bot.title_for(username)

        if result:
            video_title, video_url = result
            self.safe_reply(connection, event, f"As requested {title}, your video: \"{video_title}\" - {video_url}")
        else:
            self.safe_reply(connection, event, f"My apologies, {title}, I could not find a suitable video for '{query}'.")

        return True

    @admin_required
    def _cmd_stats(self, connection, event, msg, username, match):
        requested = self.get_state("searches_performed", 0)
        found = self.get_state("videos_found", 0)
        success_rate = (found / requested * 100) if requested > 0 else 0

        self.safe_reply(connection, event, f"YouTube stats: {found}/{requested} successful searches ({success_rate:.1f}% success rate).")
        return True

