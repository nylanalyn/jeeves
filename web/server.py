# web/server.py
# Unified HTTP server for Jeeves quest + stats web UIs

from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from web.quest.templates import TemplateEngine
from web.quest.themes import ThemeManager
from web.quest.utils import (
    load_boss_hunt_data,
    load_challenge_paths,
    load_mob_cooldowns,
    load_quest_state,
    sort_players_by_prestige,
    validate_search_term,
)
from web.stats.config import filter_channels, get_channel_filters, load_stats_web_config
from web.stats.data_loader import JeevesStatsLoader, StatsAggregator
from web.stats.templates import render_achievements_page, render_activity_page, render_overview_page


class JeevesHTTPRequestHandler(BaseHTTPRequestHandler):
    """Unified request handler for quest + stats pages."""

    def __init__(
        self,
        *args,
        games_path: Path,
        content_path: Path,
        config_path: Path,
        debug: bool = False,
        **kwargs,
    ):
        self.games_path = games_path
        self.content_path = content_path
        self.config_path = config_path
        self.debug = bool(debug)

        self.quest_theme_manager = ThemeManager(content_path)
        self.quest_template_engine = TemplateEngine(self.quest_theme_manager, mount_path="/quest")
        self._quest_reload_state()

        self.stats_loader = JeevesStatsLoader(config_path)
        self.stats: dict | None = None
        self.aggregator: StatsAggregator | None = None
        self._stats_cache_time: float = 0.0

        super().__init__(*args, **kwargs)

    def _quest_reload_state(self) -> None:
        self.quest_players, self.quest_classes = load_quest_state(self.games_path)
        self.quest_challenge_info = load_challenge_paths(self.content_path / "challenge_paths.json")
        self.quest_mob_cooldowns = load_mob_cooldowns(self.games_path)
        self.quest_boss_hunt_data = load_boss_hunt_data(self.games_path)

    _STATS_CACHE_TTL = 30.0  # seconds

    def _load_stats(self) -> bool:
        now = time.time()
        if self.stats is not None and (now - self._stats_cache_time) < self._STATS_CACHE_TTL:
            return True
        try:
            self.stats = self.stats_loader.load_all()
            self.aggregator = StatsAggregator(self.stats)
            self._stats_cache_time = now
            return True
        except Exception as exc:  # pragma: no cover
            logging.exception(f"Error loading stats: {exc}")
            self.stats = None
            self.aggregator = None
            self._stats_cache_time = 0.0
            return False

    def _send_response(self, status: HTTPStatus, content: str, content_type: str = "text/html") -> None:
        self.send_response(status.value)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(content.encode("utf-8"))))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'")
        self.end_headers()
        self.wfile.write(content.encode("utf-8"))

    def _send_html(self, html: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        self._send_response(status, html, content_type="text/html")

    def _send_json(self, data: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        payload = json.dumps(data, indent=2)
        self._send_response(status, payload, content_type="application/json")

    def _send_error_page(
        self,
        status: HTTPStatus,
        message: str,
        home_path: str = "/",
        debug_details: str | None = None,
    ) -> None:
        debug_block = ""
        if self.debug and debug_details:
            safe = (
                debug_details.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
            debug_block = f"<pre style=\"text-align:left; white-space:pre-wrap; opacity:0.9;\">{safe}</pre>"

        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Error {status.value}</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
        }}
        .error-container {{
            background: rgba(0, 0, 0, 0.3);
            padding: 2rem;
            border-radius: 10px;
            text-align: center;
            backdrop-filter: blur(10px);
            max-width: 720px;
        }}
        h1 {{ font-size: 4rem; margin: 0; }}
        p {{ font-size: 1.1rem; line-height: 1.5; }}
        a {{ color: #ffd700; }}
    </style>
</head>
<body>
    <div class="error-container">
        <h1>{status.value}</h1>
        <p>{message}</p>
        <p><a href="{home_path}">Return to Home</a></p>
        {debug_block}
    </div>
</body>
</html>"""
        self._send_html(html, status=status)

    def do_GET(self) -> None:  # noqa: N802
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        query = parse_qs(parsed_url.query or "")

        try:
            # Stats pages (landing experience)
            if path in ("/", "/index.html", "/stats", "/stats/", "/stats/index.html"):
                self._handle_stats_overview()
                return
            if path in ("/activity", "/stats/activity"):
                self._handle_stats_activity(query)
                return
            if path in ("/achievements", "/stats/achievements"):
                self._handle_stats_achievements()
                return
            if path in ("/api/stats", "/stats/api/stats"):
                self._handle_stats_api_stats()
                return

            # Quest pages (mounted under /quest; keep legacy aliases for compatibility)
            if path in ("/quest", "/quest/", "/quest/index.html"):
                self._handle_quest_leaderboard(query)
                return
            if path in ("/commands", "/quest/commands"):
                self._handle_quest_commands()
                return
            if path.startswith("/player/"):
                self._handle_quest_player_detail(path)
                return
            if path.startswith("/quest/player/"):
                self._handle_quest_player_detail(path.replace("/quest", "", 1))
                return
            if path in ("/api/status", "/quest/api/status"):
                self._handle_quest_api_status()
                return
            self._send_error_page(HTTPStatus.NOT_FOUND, "Page not found.", home_path="/")
        except Exception as exc:  # pragma: no cover
            import traceback

            logging.exception(f"Error handling request {path}: {exc}")
            self._send_error_page(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                "Internal server error.",
                home_path="/",
                debug_details=traceback.format_exc(),
            )

    def do_POST(self) -> None:  # noqa: N802
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        try:
            if path in ("/api/reload", "/quest/api/reload"):
                self._handle_quest_api_reload()
                return
            self._send_error_page(HTTPStatus.NOT_FOUND, "Page not found.", home_path="/")
        except Exception as exc:  # pragma: no cover
            import traceback

            logging.exception(f"Error handling POST request {path}: {exc}")
            self._send_error_page(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                "Internal server error.",
                home_path="/",
                debug_details=traceback.format_exc(),
            )

    # Quest handlers
    def _handle_quest_leaderboard(self, query: dict) -> None:
        search_term = validate_search_term(query.get("search", [""])[0] if "search" in query else "")
        if search_term:
            filtered_players = [
                player for player in self.quest_players.values()
                if search_term.lower() in player.get("username", "").lower()
            ]
        else:
            filtered_players = list(self.quest_players.values())

        sorted_players = sort_players_by_prestige(filtered_players)
        content = self.quest_template_engine.render_leaderboard(
            sorted_players,
            self.quest_classes,
            search_term,
            self.quest_challenge_info,
            self.quest_mob_cooldowns,
            self.quest_boss_hunt_data,
            None,
        )

        html = self.quest_template_engine.render_page(
            "Quest Leaderboard" + (f" - {search_term}" if search_term else ""),
            content,
            "leaderboard",
        )
        self._send_html(html)

    def _handle_quest_commands(self) -> None:
        content = self.quest_template_engine.render_commands()
        html = self.quest_template_engine.render_page("Quest Commands", content, "commands")
        self._send_html(html)

    def _handle_quest_player_detail(self, path: str) -> None:
        player_identifier = path.split("/", 2)[2].split("?")[0]

        player = None
        user_id = None
        for uid, candidate in self.quest_players.items():
            if uid == player_identifier or candidate.get("username", "").lower() == player_identifier.lower():
                player = candidate
                user_id = uid
                break

        if not player or not user_id:
            self._send_error_page(HTTPStatus.NOT_FOUND, "Player not found.", home_path="/quest")
            return

        player_class = self.quest_classes.get(user_id, "No class")
        content = self.quest_template_engine.render_player_detail(
            player,
            player_class,
            self.quest_challenge_info,
            None,
        )
        html = self.quest_template_engine.render_page(
            f"{player.get('username', 'Player')} - Profile",
            content,
            "",
        )
        self._send_html(html)

    def _handle_quest_api_status(self) -> None:
        status = {
            "players": len(self.quest_players),
            "classes": len(self.quest_classes),
            "theme": self.quest_theme_manager.get_theme().get("name"),
            "challenge_active": self.quest_challenge_info.get("active_path") is not None,
        }
        self._send_json(status)

    # Rate limit: minimum 5 seconds between reloads
    _last_reload_time: float = 0.0

    def _handle_quest_api_reload(self) -> None:
        # Only allow from localhost
        client_ip = self.client_address[0]
        if client_ip not in ("127.0.0.1", "::1", "localhost"):
            self._send_json({"success": False, "error": "Forbidden"}, status=HTTPStatus.FORBIDDEN)
            return

        # Rate limit reloads
        now = time.time()
        if now - JeevesHTTPRequestHandler._last_reload_time < 5.0:
            self._send_json(
                {"success": False, "error": "Rate limited. Try again in a few seconds."},
                status=HTTPStatus.TOO_MANY_REQUESTS,
            )
            return

        try:
            self._quest_reload_state()
            JeevesHTTPRequestHandler._last_reload_time = now
            self._send_json({"success": True, "message": "Quest data reloaded successfully"})
        except Exception as exc:  # pragma: no cover
            self._send_json({"success": False, "error": "Internal server error"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    # Stats handlers
    def _handle_stats_overview(self) -> None:
        if not self._load_stats():
            self._send_error_page(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                "Failed to load statistics. Please check the config files.",
                home_path="/",
            )
            return
        html = render_overview_page(self.stats, self.aggregator)
        self._send_html(html)

    def _handle_stats_achievements(self) -> None:
        if not self._load_stats():
            self._send_error_page(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                "Failed to load statistics. Please check the config files.",
                home_path="/",
            )
            return
        html = render_achievements_page(self.stats)
        self._send_html(html)

    def _handle_stats_activity(self, query: dict) -> None:
        if not self._load_stats():
            self._send_error_page(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                "Failed to load statistics. Please check the config files.",
                home_path="/",
            )
            return

        full_config = load_stats_web_config(self.config_path)
        visible_channels, hidden_channels = get_channel_filters(full_config)

        available_channels = sorted((self.stats.get("activity", {}).get("channels") or {}).keys())
        channels = filter_channels(available_channels, visible_channels, hidden_channels)

        selected_channel = (query.get("channel", [None])[0] or None)
        if selected_channel and selected_channel not in channels:
            selected_channel = None

        user_query = (query.get("user", [None])[0] or None)
        html = render_activity_page(
            self.stats,
            self.aggregator,
            channels=channels,
            selected_channel=selected_channel,
            user_query=user_query,
        )
        self._send_html(html)

    def _handle_stats_api_stats(self) -> None:
        if not self._load_stats():
            self._send_json({"error": "Failed to load statistics"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        api_stats = {
            "user_count": len(self.stats["users"]),
            "quest_players": len(self.stats["quest"]),
            "hunt_players": len(self.stats["hunt"]),
            "duel_players": len(self.stats["duel"].get("wins", {})),
            "absurdia_players": len(self.stats["absurdia"].get("players", {})),
        }
        self._send_json(api_stats)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        logging.info(f"{self.address_string()} - {format % args}")


def create_handler_class(games_path: Path, content_path: Path, config_path: Path, debug: bool = False) -> type:
    def handler_init(self, *args, **kwargs):
        JeevesHTTPRequestHandler.__init__(
            self,
            *args,
            games_path=games_path,
            content_path=content_path,
            config_path=config_path,
            debug=debug,
            **kwargs,
        )

    return type(
        "BoundJeevesHTTPRequestHandler",
        (JeevesHTTPRequestHandler,),
        {"__init__": handler_init},
    )


class JeevesWebServer:
    """Web server for unified Jeeves dashboards."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8080,
        games_path: Path | None = None,
        content_path: Path | None = None,
        config_path: Path | None = None,
        debug: bool = False,
    ):
        self.host = host
        self.port = port
        self.server: HTTPServer | None = None
        self.debug = bool(debug)
        self._shutdown_requested = False

        repo_root = Path(__file__).resolve().parent.parent

        if games_path is None:
            games_path = repo_root / "config" / "games.json"
        if content_path is None:
            content_path = repo_root
        if config_path is None:
            config_path = repo_root / "config"

        if not games_path.exists():
            print(f"Error: Games file not found at {games_path}", file=sys.stderr)
            print("Please ensure the bot has been run at least once to generate game data.", file=sys.stderr)
            sys.exit(1)

        if not config_path.exists():
            print(f"Error: Config directory not found at {config_path}", file=sys.stderr)
            sys.exit(1)

        self.games_path = games_path
        self.content_path = content_path
        self.config_path = config_path

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        print(f"\nReceived signal {signum}. Shutting down gracefully...", file=sys.stderr)
        self._shutdown_requested = True
        if not self.server:
            sys.exit(0)

        # `HTTPServer.shutdown()` must not be called from the same thread running
        # `serve_forever()`, otherwise it can deadlock.
        import threading

        threading.Thread(target=self.server.shutdown, daemon=True).start()

    def start(self) -> None:
        handler_class = create_handler_class(self.games_path, self.content_path, self.config_path, debug=self.debug)

        try:
            self.server = HTTPServer((self.host, self.port), handler_class)
        except OSError as exc:
            print(f"Error: Failed to start server on {self.host}:{self.port}: {exc}", file=sys.stderr)
            sys.exit(1)

        print("🌐 Jeeves Web Server starting...", file=sys.stderr)
        print(f"   Server: http://{self.host}:{self.port}", file=sys.stderr)
        print(f"   Games: {self.games_path}", file=sys.stderr)
        print(f"   Config: {self.config_path}", file=sys.stderr)
        print("   Pages: / (Stats), /quest, /activity, /achievements", file=sys.stderr)
        print("   Press Ctrl+C to stop the server", file=sys.stderr)
        print("=" * 50, file=sys.stderr)

        try:
            self.server.serve_forever()
        except KeyboardInterrupt:
            print("\nServer stopped by user.", file=sys.stderr)
        except Exception as exc:  # pragma: no cover
            print(f"Error: Server encountered an error: {exc}", file=sys.stderr)
            sys.exit(1)
        finally:
            try:
                self.server.server_close()
            except Exception:
                pass
            if self._shutdown_requested:
                sys.exit(0)

    def stop(self) -> None:
        if self.server:
            self.server.shutdown()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Jeeves Web Server - Quest + Stats Dashboard",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                           # Start with defaults (127.0.0.1:8080)
  %(prog)s --host 0.0.0.0 --port 8080  # Listen on all interfaces
  %(prog)s --games /path/to/games.json  # Custom games file path
  %(prog)s --config /path/to/config     # Custom config directory
        """,
    )

    parser.add_argument("--host", default="127.0.0.1", help="Host to bind the server to (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8080, help="Port to bind the server to (default: 8080)")
    parser.add_argument("--games", type=Path, help="Path to games.json file (default: config/games.json)")
    parser.add_argument("--content", type=Path, help="Path to content directory (default: repo root)")
    parser.add_argument("--config", type=Path, help="Path to config directory (default: config/)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")

    server = JeevesWebServer(
        host=args.host,
        port=args.port,
        games_path=args.games,
        content_path=args.content,
        config_path=args.config,
        debug=args.debug,
    )
    server.start()


if __name__ == "__main__":
    main()
