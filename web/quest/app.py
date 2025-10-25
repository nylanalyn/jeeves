# web/quest/app.py
# Main application entry point for quest web UI

from .server import QuestWebServer, main

# Re-export main functions for backward compatibility
__all__ = ['QuestWebServer', 'main']


def create_server(host: str = "127.0.0.1", port: int = 8080,
                  games_path: str = None, content_path: str = None) -> QuestWebServer:
    """Create a QuestWebServer instance with the given parameters."""
    from pathlib import Path

    games_path_obj = Path(games_path) if games_path else None
    content_path_obj = Path(content_path) if content_path else None

    return QuestWebServer(
        host=host,
        port=port,
        games_path=games_path_obj,
        content_path=content_path_obj
    )