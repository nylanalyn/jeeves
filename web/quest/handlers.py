# web/quest/handlers.py
# HTTP request handlers for quest web UI

import json
import logging
import secrets
import threading
import time
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Dict, Any, Tuple, Optional
from urllib.parse import parse_qs, urlparse

from .templates import TemplateEngine
from .themes import ThemeManager
from .utils import sanitize, validate_search_term, load_quest_state, load_challenge_paths, load_mob_cooldowns, sort_players_by_prestige
from .actions import QuestActionService

SESSION_COOKIE = "jeeves_quest_session"
SESSION_TTL = 24 * 60 * 60  # 24 hours


class QuestHTTPRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for quest web UI."""

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
        self.active_session_id: Optional[str] = None
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
        self.active_session_id = None

    # --- Session helpers -------------------------------------------------
    def _prune_sessions(self) -> None:
        now = time.time()
        with self.session_lock:
            for session_id, session in list(self.session_store.items()):
                if session.get("expires_at", 0) <= now:
                    self.session_store.pop(session_id, None)

    def _current_session(self) -> Optional[Dict[str, Any]]:
        self._prune_sessions()
        cookie_header = self.headers.get("Cookie")
        if not cookie_header:
            return None
        cookie = SimpleCookie()
        cookie.load(cookie_header)
        morsel = cookie.get(SESSION_COOKIE)
        if not morsel:
            return None
        session_id = morsel.value
        with self.session_lock:
            session = self.session_store.get(session_id)
            if not session:
                return None
            if session.get("expires_at", 0) <= time.time():
                self.session_store.pop(session_id, None)
                return None
            session["expires_at"] = time.time() + SESSION_TTL
            self.session_store[session_id] = session
            self.active_session_id = session_id
            return session

    def _start_session(self, user_id: str, username: str) -> str:
        session_id = secrets.token_urlsafe(24)
        session_data = {
            "user_id": user_id,
            "username": username,
            "created_at": time.time(),
            "expires_at": time.time() + SESSION_TTL,
        }
        with self.session_lock:
            self.session_store[session_id] = session_data
        self.active_session_id = session_id
        return f"{SESSION_COOKIE}={session_id}; Path=/; HttpOnly; SameSite=Lax"

    def _clear_current_session(self) -> None:
        if not self.active_session_id:
            return
        with self.session_lock:
            self.session_store.pop(self.active_session_id, None)
        self.active_session_id = None

    # --- Request helpers -------------------------------------------------
    def _read_json_body(self) -> Optional[Dict[str, Any]]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0:
            return {}
        body = self.rfile.read(length)
        try:
            return json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            return None

    def log_message(self, format: str, *args) -> None:  # noqa: A003 pylint: disable=redefined-builtin
        """Override to reduce log noise."""
        if "--debug" in args:  # Only log when debugging
            super().log_message(format, *args)

    def _handle_api_session(self) -> None:
        session = self._current_session()
        if not session:
            self._send_json({"authenticated": False})
            return
        self._send_json({
            "authenticated": True,
            "username": session.get("username"),
        })

    def _handle_api_link_claim(self) -> None:
        payload = self._read_json_body()
        if payload is None or "token" not in payload:
            self._send_json({"success": False, "error": "Invalid request payload"}, status=400)
            return

        token = str(payload.get("token", "")).strip()
        if not token:
            self._send_json({"success": False, "error": "Token is required"}, status=400)
            return

        result = self.action_service.consume_link_token(token)
        if not result or not result.get("user_id"):
            self._send_json({"success": False, "error": "Token is invalid or expired"}, status=400)
            return

        username = result.get("username") or result["user_id"]
        cookie_header = self._start_session(result["user_id"], username)
        self._send_json(
            {"success": True, "username": username},
            headers={"Set-Cookie": cookie_header}
        )

    def _handle_api_quest_solo(self) -> None:
        session = self._current_session()
        if not session:
            self._send_json({"success": False, "error": "Not authenticated"}, status=401)
            return

        payload = self._read_json_body() or {}
        difficulty = str(payload.get("difficulty", "normal")).lower()
        allowed = {"easy", "normal", "hard"}
        if difficulty not in allowed:
            self._send_json({"success": False, "error": "Invalid difficulty"}, status=400)
            return

        try:
            result = self.action_service.perform_solo_quest(session["user_id"], difficulty)
        except Exception as exc:  # pylint: disable=broad-except
            logging.exception("Failed to run solo quest via web: %s", exc)
            self._send_json({"success": False, "error": "Quest action failed"}, status=500)
            return

        # Keep username in session store up-to-date and extend cookie
        response_data = {"success": True}
        response_data.update(result)
        if result.get("username"):
            with self.session_lock:
                if self.active_session_id and self.active_session_id in self.session_store:
                    self.session_store[self.active_session_id]["username"] = result["username"]
        self._send_json(response_data)

    def do_GET(self) -> None:
        """Handle GET requests."""
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
            elif parsed_path.path == "/api/session":
                self._handle_api_session()
            elif parsed_path.path == "/api/reload":
                self._handle_api_reload()
            else:
                self._send_404()
        except Exception as e:
            logging.error(f"Error handling GET request: {e}")
            self._send_500()

    def do_POST(self) -> None:
        """Handle POST requests."""
        try:
            parsed_path = urlparse(self.path)
            if parsed_path.path == "/api/reload":
                self._handle_api_reload()
            elif parsed_path.path == "/api/link/claim":
                self._handle_api_link_claim()
            elif parsed_path.path == "/api/quest/solo":
                self._handle_api_quest_solo()
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

        session = self._current_session()
        current_user = session.get("username") if session else None

        content = self.template_engine.render_leaderboard(
            sorted_players,
            self.classes,
            search_term,
            self.challenge_info,
            self.mob_cooldowns,
            current_user
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
        content = self.template_engine.render_player_detail(player, player_class, self.challenge_info)
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
    """Create a request handler class with bound paths."""
    config_dir = games_path.parent
    config_path = config_dir / "config.yaml"
    shared_session_store: Dict[str, Dict[str, Any]] = {}
    shared_session_lock = threading.RLock()
    shared_action_service = QuestActionService(config_dir, config_path)

    class BoundRequestHandler(QuestHTTPRequestHandler):
        session_store = shared_session_store
        session_lock = shared_session_lock
        action_service = shared_action_service

        def __init__(self, *args, **kwargs):
            super().__init__(*args, games_path=games_path, content_path=content_path, **kwargs)

    return BoundRequestHandler
