# web/quest/handlers.py
# HTTP request handlers for quest web UI (read-only)

import json
import logging
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Dict, Any, Tuple, Optional
from urllib.parse import parse_qs, urlparse

from .templates import TemplateEngine
from .themes import ThemeManager
from .utils import sanitize, validate_search_term, load_quest_state, load_challenge_paths, load_mob_cooldowns, load_boss_hunt_data, sort_players_by_prestige


class QuestHTTPRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for quest web UI (read-only display)."""

    def __init__(self, *args, games_path: Path, content_path: Path, **kwargs):
        # Initialize all instance attributes BEFORE calling super().__init__()
        # because BaseHTTPRequestHandler.__init__() immediately handles the request
        self.games_path = games_path
        self.content_path = content_path
        self.theme_manager = ThemeManager(content_path)
        self.template_engine = TemplateEngine(self.theme_manager)
        self.players, self.classes = self._load_state()
        self.challenge_info = load_challenge_paths(content_path / "challenge_paths.json")
        self.mob_cooldowns = load_mob_cooldowns(games_path)
        self.boss_hunt_data = load_boss_hunt_data(games_path)
        # Now call parent init which will handle the request
        super().__init__(*args, **kwargs)

    def _load_state(self) -> Tuple[Dict[str, dict], Dict[str, str]]:
        """Load quest state from games.json."""
        return load_quest_state(self.games_path)

    def _reload_state(self) -> None:
        """Reload quest state."""
        self.players, self.classes = self._load_state()
        self.challenge_info = load_challenge_paths(self.content_path / "challenge_paths.json")
        self.mob_cooldowns = load_mob_cooldowns(self.games_path)
        self.boss_hunt_data = load_boss_hunt_data(self.games_path)

    def log_message(self, format: str, *args) -> None:  # noqa: A003 pylint: disable=redefined-builtin
        """Override to reduce log noise."""
        if "--debug" in args:  # Only log when debugging
            super().log_message(format, *args)

    def do_GET(self) -> None:
        """Handle GET requests (read-only)."""
        try:
            parsed_path = urlparse(self.path)
            if parsed_path.path == "/":
                self._handle_leaderboard()
            elif parsed_path.path == "/commands":
                self._handle_commands()
            elif parsed_path.path.startswith("/player/"):
                self._handle_player_detail()
            elif parsed_path.path == "/api/status":
                self._handle_api_status()
            elif parsed_path.path == "/api/reload":
                self._handle_api_reload()
            else:
                self._send_404()
        except Exception as e:
            logging.error(f"Error handling GET request: {e}")
            self._send_500()

    def do_POST(self) -> None:
        """Handle POST requests (read-only operations only)."""
        try:
            parsed_path = urlparse(self.path)
            if parsed_path.path == "/api/reload":
                self._handle_api_reload()
            else:
                self._send_404()
        except Exception as e:
            logging.error(f"Error handling POST request: {e}")
            self._send_500()

    def _handle_leaderboard(self) -> None:
        """Handle leaderboard page."""
        query = parse_qs(urlparse(self.path).query)
        search_term = validate_search_term(query.get("search", [""])[0] if "search" in query else "")

        if search_term:
            # Filter players by search term
            filtered_players = [
                player for player in self.players.values()
                if search_term.lower() in player.get("username", "").lower()
            ]
        else:
            filtered_players = list(self.players.values())

        # Sort players
        sorted_players = sort_players_by_prestige(filtered_players)

        content = self.template_engine.render_leaderboard(
            sorted_players,
            self.classes,
            search_term,
            self.challenge_info,
            self.mob_cooldowns,
            self.boss_hunt_data,
            None  # No authenticated user (interactive features removed)
        )

        html = self.template_engine.render_page(
            "Quest Leaderboard" + (f" - {search_term}" if search_term else ""),
            content,
            "leaderboard"
        )

        self._send_html(html)

    def _handle_commands(self) -> None:
        """Handle commands reference page."""
        content = self.template_engine.render_commands()
        html = self.template_engine.render_page("Quest Commands", content, "commands")
        self._send_html(html)

    def _handle_player_detail(self) -> None:
        """Handle player detail page."""
        # Extract user_id or username from path
        path_parts = self.path.split("/")
        if len(path_parts) < 3:
            self._send_404()
            return

        player_identifier = path_parts[2].split("?")[0]  # Remove query params

        # Find player by user_id or username
        player = None
        user_id = None
        for uid, p in self.players.items():
            if uid == player_identifier or p.get("username", "").lower() == player_identifier.lower():
                player = p
                user_id = uid
                break

        if not player:
            self._send_404()
            return

        player_class = self.classes.get(user_id, "No class")
        content = self.template_engine.render_player_detail(player, player_class, self.challenge_info, None)  # No authenticated user
        html = self.template_engine.render_page(
            f"{player.get('username', 'Player')} - Profile",
            content,
            ""
        )
        self._send_html(html)

    def _handle_api_status(self) -> None:
        """Handle API status endpoint."""
        status = {
            "players": len(self.players),
            "classes": len(self.classes),
            "theme": self.theme_manager.get_theme().get("name"),
            "challenge_active": self.challenge_info.get("active_path") is not None
        }
        self._send_json(status)

    def _handle_api_reload(self) -> None:
        """Handle API reload endpoint."""
        try:
            self._reload_state()
            self._send_json({"success": True, "message": "Data reloaded successfully"})
        except Exception as e:
            self._send_json({"success": False, "error": str(e)})

    def _send_html(self, html: str) -> None:
        """Send HTML response."""
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.send_header("Content-length", str(len(html.encode('utf-8'))))
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))

    def _send_json(self, data: Dict[str, Any], status: int = 200, headers: Optional[Dict[str, str]] = None) -> None:
        """Send JSON response."""
        json_data = json.dumps(data, indent=2)
        self.send_response(status)
        self.send_header("Content-type", "application/json; charset=utf-8")
        self.send_header("Content-length", str(len(json_data.encode('utf-8'))))
        if headers:
            for key, value in headers.items():
                self.send_header(key, value)
        self.end_headers()
        self.wfile.write(json_data.encode('utf-8'))

    def _send_404(self) -> None:
        """Send 404 response."""
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>404 - Page Not Found</title>
            <style>
                body { font-family: Arial, sans-serif; text-align: center; padding: 50px; }
                h1 { color: #f97316; }
            </style>
        </head>
        <body>
            <h1>404 - Page Not Found</h1>
            <p>The requested page could not be found.</p>
            <p><a href="/">Return to Leaderboard</a></p>
        </body>
        </html>
        """
        self.send_response(404)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.send_header("Content-length", str(len(html.encode('utf-8'))))
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))

    def _send_500(self) -> None:
        """Send 500 response."""
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>500 - Internal Server Error</title>
            <style>
                body { font-family: Arial, sans-serif; text-align: center; padding: 50px; }
                h1 { color: #ef4444; }
            </style>
        </head>
        <body>
            <h1>500 - Internal Server Error</h1>
            <p>Something went wrong. Please try again later.</p>
            <p><a href="/">Return to Leaderboard</a></p>
        </body>
        </html>
        """
        self.send_response(500)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.send_header("Content-length", str(len(html.encode('utf-8'))))
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))


def create_handler_class(games_path: Path, content_path: Path) -> type:
    """Create a request handler class with bound paths (read-only)."""
    class BoundRequestHandler(QuestHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, games_path=games_path, content_path=content_path, **kwargs)

    return BoundRequestHandler
