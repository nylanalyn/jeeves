# web/stats/config.py
# Config helpers for stats web UI.

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None


def load_stats_web_config(config_dir: Path) -> Dict[str, Any]:
    """Load `config.yaml` from the Jeeves config directory, if present."""
    config_path = Path(config_dir) / "config.yaml"
    if not config_path.exists() or yaml is None:
        return {}
    try:
        with open(config_path, "r") as f:
            data = yaml.safe_load(f) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def get_channel_filters(full_config: Dict[str, Any]) -> Tuple[Optional[List[str]], List[str]]:
    """Return (visible_channels, hidden_channels) lists from config.

    Config block:
      stats_web:
        visible_channels: ["#a", "#b"]   # optional allowlist
        hidden_channels: ["#secret"]     # optional blocklist
    """
    stats_web = full_config.get("stats_web", {})
    if not isinstance(stats_web, dict):
        return None, []

    visible = stats_web.get("visible_channels")
    hidden = stats_web.get("hidden_channels")

    visible_list = [str(x) for x in visible] if isinstance(visible, list) and visible else None
    hidden_list = [str(x) for x in hidden] if isinstance(hidden, list) and hidden else []
    return visible_list, hidden_list


def filter_channels(available: List[str], visible_channels: Optional[List[str]], hidden_channels: List[str]) -> List[str]:
    available_set = {str(x) for x in available}
    hidden_set = {str(x) for x in (hidden_channels or [])}

    if visible_channels:
        ordered = [str(ch) for ch in visible_channels if str(ch) in available_set and str(ch) not in hidden_set]
        return ordered

    ordered = [str(ch) for ch in sorted(available_set) if str(ch) not in hidden_set]
    return ordered

