# web/quest/utils.py
# Utility functions for quest web UI

import html
import json
from typing import Dict, Any, List, Tuple
from pathlib import Path


def sanitize(text: str) -> str:
    """Sanitize text for HTML output."""
    return html.escape(str(text))


def load_quest_state(games_path: Path) -> Tuple[Dict[str, dict], Dict[str, str]]:
    """Read quest players and class selections from games.json.

    Returns:
        Tuple of (players_dict, classes_dict) where players_dict has user_id as keys
        and each player object includes 'user_id' and 'username' fields.
    """
    if not games_path.exists():
        return {}, {}

    try:
        with open(games_path, 'r') as f:
            data = json.load(f)
            if not isinstance(data, dict):
                return {}, {}

            # Quest data is nested under modules.quest
            modules = data.get("modules", {})
            if not isinstance(modules, dict):
                return {}, {}

            quest_state = modules.get("quest", {})
            if not isinstance(quest_state, dict):
                return {}, {}

            players_raw = quest_state.get("players", {})
            classes = quest_state.get("player_classes", {})

            if not isinstance(players_raw, dict):
                players_raw = {}
            if not isinstance(classes, dict):
                classes = {}

            # Transform players dict to include user_id and username in each player object
            players = {}
            for user_id, player_data in players_raw.items():
                if isinstance(player_data, dict):
                    # Create a copy with user_id and username added
                    player = player_data.copy()
                    player["user_id"] = user_id
                    # Use "name" field as "username" for template compatibility
                    if "name" in player_data:
                        player["username"] = player_data["name"]
                    players[user_id] = player

            return players, classes
    except (json.JSONDecodeError, IOError):
        return {}, {}


def load_challenge_paths(paths_file: Path) -> Dict[str, Any]:
    """Load challenge paths configuration."""
    if not paths_file.exists():
        return {"paths": {}, "active_path": None}

    try:
        with open(paths_file, 'r') as f:
            data = json.load(f)
            if not isinstance(data, dict):
                return {"paths": {}, "active_path": None}

            # Ensure required structure
            if "paths" not in data:
                data["paths"] = {}
            if "active_path" not in data:
                data["active_path"] = None

            return data
    except (json.JSONDecodeError, IOError):
        return {"paths": {}, "active_path": None}


def format_number(num: int) -> str:
    """Format large numbers with commas."""
    return f"{num:,}"


def format_xp(xp: int) -> str:
    """Format XP display."""
    return format_number(xp)


def format_percentage(value: float, total: float) -> str:
    """Format percentage calculation."""
    if total == 0:
        return "0.0%"
    percentage = (value / total) * 100
    return f"{percentage:.1f}%"


def calculate_win_rate(wins: int, losses: int) -> str:
    """Calculate win rate percentage."""
    total = wins + losses
    if total == 0:
        return "0.0%"
    return f"{(wins / total) * 100:.1f}%"


def format_cooldown_timestamp(timestamp: float) -> str:
    """Format cooldown timestamp for display."""
    import time
    from datetime import datetime, timezone

    if timestamp <= time.time():
        return "Ready"

    dt = datetime.fromtimestamp(timestamp, timezone.utc)
    return dt.strftime("%H:%M:%S")


def get_rank_suffix(rank: int) -> str:
    """Get ordinal suffix for rank numbers."""
    if 11 <= rank <= 13:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(rank % 10, "th")


def truncate_text(text: str, max_length: int = 50) -> str:
    """Truncate text to specified length."""
    if len(text) <= max_length:
        return text
    return text[:max_length-3] + "..."


def safe_int(value: Any, default: int = 0) -> int:
    """Safely convert value to int."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def safe_float(value: Any, default: float = 0.0) -> float:
    """Safely convert value to float."""
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def validate_search_term(term: str) -> str:
    """Validate and sanitize search term."""
    if not term:
        return ""
    # Remove potentially harmful characters
    term = sanitize(term.strip())
    # Limit length
    return truncate_text(term, 100)


def sort_players_by_prestige(players: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sort players by prestige, then level, then XP."""
    def sort_key(player):
        prestige = safe_int(player.get("prestige", 0))
        level = safe_int(player.get("level", 1))
        xp = safe_int(player.get("xp", 0))
        return (-prestige, -level, -xp)

    return sorted(players, key=sort_key)


def get_player_display_name(nick: str, user_data: Dict[str, Any]) -> str:
    """Get formatted display name for a player."""
    return sanitize(nick)


def calculate_level_progress(player: Dict[str, Any]) -> Tuple[int, int, float]:
    """Calculate level progress (current_level, current_xp, progress_percentage)."""
    level = safe_int(player.get("level", 1))
    current_xp = safe_int(player.get("xp", 0))

    # Simple linear XP formula for web display
    xp_for_current = level * 100
    xp_for_next = (level + 1) * 100
    progress = ((current_xp - xp_for_current) / (xp_for_next - xp_for_current)) * 100 if current_xp >= xp_for_current else 0

    return level, current_xp, min(100.0, max(0.0, progress))


def format_streak(streak: int) -> str:
    """Format win streak with appropriate styling."""
    if streak >= 10:
        return f'<span class="streak-high">{streak}</span>'
    elif streak >= 5:
        return f'<span class="streak-medium">{streak}</span>'
    elif streak > 0:
        return f'<span class="streak-low">{streak}</span>'
    else:
        return f'<span class="streak-none">{streak}</span>'


def get_medal_emoji(rank: int) -> str:
    """Get medal emoji for rank."""
    if rank == 1:
        return "🥇"
    elif rank == 2:
        return "🥈"
    elif rank == 3:
        return "🥉"
    else:
        return f"{rank}."