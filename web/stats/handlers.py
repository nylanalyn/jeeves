# web/stats/handlers.py
# HTTP request handlers for stats web UI

import json
import logging
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Tuple
from urllib.parse import urlparse, parse_qs

from .data_loader import JeevesStatsLoader, StatsAggregator
from .templates import render_overview_page, render_achievements_page, render_activity_page
from .config import load_stats_web_config, get_channel_filters, filter_channels


class StatsHTTPRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for stats web UI."""

    def __init__(self, *args, config_path: Path, **kwargs):
        # Initialize all instance attributes BEFORE calling super().__init__()
        # because BaseHTTPRequestHandler.__init__() immediately handles the request
        self.config_path = config_path
        self.loader = JeevesStatsLoader(config_path)
        self.stats = None
        self.aggregator = None
        # Now call parent init which will handle the request
        super().__init__(*args, **kwargs)

    def _load_stats(self) -> None:
        """Load all stats from config files."""
        try:
            self.stats = self.loader.load_all()
            self.aggregator = StatsAggregator(self.stats)
        except Exception as e:
            logging.error(f"Error loading stats: {e}")
            self.stats = None
            self.aggregator = None

    def _send_response(self, status: HTTPStatus, content: str, content_type: str = "text/html") -> None:
        """Send an HTTP response.

        Args:
            status: HTTP status code
            content: Response content
            content_type: Content-Type header value
        """
        self.send_response(status)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(content.encode('utf-8'))))
        self.end_headers()
        self.wfile.write(content.encode('utf-8'))

    def _send_error_page(self, status: HTTPStatus, message: str) -> None:
        """Send an error page.

        Args:
            status: HTTP status code
            message: Error message to display
        """
        html = f"""<!DOCTYPE html>
<html>
<head>
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
        }}
        h1 {{ font-size: 4rem; margin: 0; }}
        p {{ font-size: 1.2rem; }}
        a {{ color: #ffd700; }}
    </style>
</head>
<body>
    <div class="error-container">
        <h1>{status.value}</h1>
        <p>{message}</p>
        <p><a href="/">Return to Home</a></p>
    </div>
</body>
</html>"""
        self._send_response(status, html)

    def do_GET(self) -> None:
        """Handle GET requests."""
        # Parse URL
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        query = parse_qs(parsed_url.query or "")

        # Load stats
        self._load_stats()
        if self.stats is None:
            self._send_error_page(HTTPStatus.INTERNAL_SERVER_ERROR,
                                "Failed to load statistics. Please check the config files.")
            return

        # Route to appropriate handler
        if path == "/" or path == "/index.html":
            self._handle_overview()
        elif path == "/achievements":
            self._handle_achievements()
        elif path == "/activity":
            self._handle_activity(query)
        elif path == "/api/stats":
            self._handle_api_stats()
        else:
            self._send_error_page(HTTPStatus.NOT_FOUND, "Page not found")

    def _handle_overview(self) -> None:
        """Handle the overview/dashboard page."""
        try:
            html = render_overview_page(self.stats, self.aggregator)
            self._send_response(HTTPStatus.OK, html)
        except Exception as e:
            logging.error(f"Error rendering overview page: {e}")
            self._send_error_page(HTTPStatus.INTERNAL_SERVER_ERROR,
                                "Failed to render overview page.")

    def _handle_achievements(self) -> None:
        """Handle the achievements page."""
        try:
            html = render_achievements_page(self.stats)
            self._send_response(HTTPStatus.OK, html)
        except Exception as e:
            logging.error(f"Error rendering achievements page: {e}")
            self._send_error_page(HTTPStatus.INTERNAL_SERVER_ERROR,
                                "Failed to render achievements page.")

    def _handle_activity(self, query: dict) -> None:
        """Handle the activity page."""
        try:
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
            self._send_response(HTTPStatus.OK, html)
        except Exception as e:
            logging.error(f"Error rendering activity page: {e}")
            self._send_error_page(HTTPStatus.INTERNAL_SERVER_ERROR,
                                  "Failed to render activity page.")

    def _handle_api_stats(self) -> None:
        """Handle API request for raw stats (JSON)."""
        try:
            # Create a simplified version of stats for API
            api_stats = {
                "user_count": len(self.stats["users"]),
                "quest_players": len(self.stats["quest"]),
                "hunt_players": len(self.stats["hunt"]),
                "duel_players": len(self.stats["duel"].get("wins", {})),
                "absurdia_players": len(self.stats["absurdia"].get("players", {})),
            }

            json_data = json.dumps(api_stats, indent=2)
            self._send_response(HTTPStatus.OK, json_data, content_type="application/json")
        except Exception as e:
            logging.error(f"Error generating API stats: {e}")
            error_json = json.dumps({"error": "Failed to generate stats"})
            self._send_response(HTTPStatus.INTERNAL_SERVER_ERROR, error_json,
                              content_type="application/json")

    def log_message(self, format, *args):
        """Override to customize logging."""
        # Log to stderr with timestamp
        logging.info(f"{self.address_string()} - {format % args}")


def create_handler_class(config_path: Path):
    """Create a request handler class with bound config path.

    Args:
        config_path: Path to config directory

    Returns:
        Handler class with bound config path
    """
    def handler_init(self, *args, **kwargs):
        StatsHTTPRequestHandler.__init__(self, *args, config_path=config_path, **kwargs)

    # Create a new class that inherits from StatsHTTPRequestHandler
    # with the __init__ method bound to the config path
    handler_class = type(
        'BoundStatsHTTPRequestHandler',
        (StatsHTTPRequestHandler,),
        {'__init__': handler_init}
    )

    return handler_class
