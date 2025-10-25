# web/quest/server.py
# HTTP server setup for quest web UI

import argparse
import signal
import sys
from http.server import HTTPServer
from pathlib import Path

from .handlers import create_handler_class


class QuestWebServer:
    """Web server for quest leaderboard."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8080,
                 games_path: Path = None, content_path: Path = None,
                 challenge_paths: Path = None):
        self.host = host
        self.port = port
        self.server = None

        # Default paths if not provided
        if games_path is None:
            games_path = Path(__file__).resolve().parent.parent.parent / "config" / "games.json"
        if content_path is None:
            content_path = Path(__file__).resolve().parent.parent.parent
        if challenge_paths is None:
            challenge_paths = content_path / "challenge_paths.json"

        # Validate paths
        if not games_path.exists():
            print(f"Error: Games file not found at {games_path}", file=sys.stderr)
            print("Please ensure the bot has been run at least once to generate game data.", file=sys.stderr)
            sys.exit(1)

        if not content_path.exists():
            print(f"Error: Content directory not found at {content_path}", file=sys.stderr)
            sys.exit(1)

        # Store paths for handler
        self.games_path = games_path
        self.content_path = content_path
        self.challenge_paths = challenge_paths

        # Setup signal handler for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        print(f"\nReceived signal {signum}. Shutting down gracefully...", file=sys.stderr)
        if self.server:
            self.server.shutdown()
        sys.exit(0)

    def start(self) -> None:
        """Start the web server."""
        # Create handler class with bound paths
        handler_class = create_handler_class(self.games_path, self.content_path)

        # Create server
        try:
            self.server = HTTPServer((self.host, self.port), handler_class)
        except OSError as e:
            print(f"Error: Failed to start server on {self.host}:{self.port}: {e}", file=sys.stderr)
            sys.exit(1)

        print(f"🌐 Quest Web Server starting...", file=sys.stderr)
        print(f"   Server: http://{self.host}:{self.port}", file=sys.stderr)
        print(f"   Games: {self.games_path}", file=sys.stderr)
        print(f"   Content: {self.content_path}", file=sys.stderr)
        print(f"   Press Ctrl+C to stop the server", file=sys.stderr)
        print("=" * 50, file=sys.stderr)

        try:
            self.server.serve_forever()
        except KeyboardInterrupt:
            print("\nServer stopped by user.", file=sys.stderr)
        except Exception as e:
            print(f"Error: Server encountered an error: {e}", file=sys.stderr)
            sys.exit(1)

    def stop(self) -> None:
        """Stop the web server."""
        if self.server:
            self.server.shutdown()
            print("Server stopped.", file=sys.stderr)


def main():
    """Main entry point for the web server."""
    parser = argparse.ArgumentParser(
        description="Quest Web Server - Jeeves Quest Leaderboard",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                           # Start with defaults (127.0.0.1:8080)
  %(prog)s --host 0.0.0.0 --port 8080  # Listen on all interfaces
  %(prog)s --games /path/to/games.json  # Custom games file path
        """
    )

    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind the server to (default: 127.0.0.1)"
    )

    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port to bind the server to (default: 8080)"
    )

    parser.add_argument(
        "--games",
        type=Path,
        help="Path to games.json file (default: config/games.json)"
    )

    parser.add_argument(
        "--content",
        type=Path,
        help="Path to content directory (default: current directory)"
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging"
    )

    args = parser.parse_args()

    # Set up logging
    if args.debug:
        import logging
        logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

    # Create and start server
    server = QuestWebServer(
        host=args.host,
        port=args.port,
        games_path=args.games,
        content_path=args.content
    )
    server.start()


if __name__ == "__main__":
    main()