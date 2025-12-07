# web/stats/server.py
# HTTP server setup for stats web UI

import argparse
import signal
import sys
from http.server import HTTPServer
from pathlib import Path

from .handlers import create_handler_class


class StatsWebServer:
    """Web server for Jeeves statistics dashboard."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8081,
                 config_path: Path = None):
        self.host = host
        self.port = port
        self.server = None

        # Default path if not provided
        if config_path is None:
            config_path = Path(__file__).resolve().parent.parent.parent / "config"

        # Validate paths
        if not config_path.exists():
            print(f"Error: Config directory not found at {config_path}", file=sys.stderr)
            sys.exit(1)

        # Store path for handler
        self.config_path = config_path

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
        handler_class = create_handler_class(self.config_path)

        # Create server
        try:
            self.server = HTTPServer((self.host, self.port), handler_class)
        except OSError as e:
            print(f"Error: Failed to start server on {self.host}:{self.port}: {e}", file=sys.stderr)
            sys.exit(1)

        print(f"📊 Jeeves Stats Web Server starting...", file=sys.stderr)
        print(f"   Server: http://{self.host}:{self.port}", file=sys.stderr)
        print(f"   Config: {self.config_path}", file=sys.stderr)
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
        description="Jeeves Stats Web Server - Comprehensive Statistics Dashboard",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                           # Start with defaults (127.0.0.1:8081)
  %(prog)s --host 0.0.0.0 --port 8081  # Listen on all interfaces
  %(prog)s --config /path/to/config    # Custom config directory
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
        default=8081,
        help="Port to bind the server to (default: 8081)"
    )

    parser.add_argument(
        "--config",
        type=Path,
        help="Path to config directory (default: config/)"
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
    server = StatsWebServer(
        host=args.host,
        port=args.port,
        config_path=args.config
    )
    server.start()


if __name__ == "__main__":
    main()
