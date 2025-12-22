# modules/activity.py
# Tracks message activity by day-of-week and hour for stats UI.

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, List

from .base import SimpleCommandModule

UTC = timezone.utc
HEATMAP_BINS = 7 * 24


def setup(bot: Any) -> "Activity":
    """Initializes the Activity module."""
    return Activity(bot)


def _empty_bucket(now_iso: str) -> Dict[str, Any]:
    return {"grid": [0] * HEATMAP_BINS, "total": 0, "updated_at": now_iso}


def _ensure_bucket(bucket: Any, now_iso: str) -> Dict[str, Any]:
    if not isinstance(bucket, dict):
        return _empty_bucket(now_iso)
    grid = bucket.get("grid")
    if not isinstance(grid, list) or len(grid) != HEATMAP_BINS:
        return _empty_bucket(now_iso)
    if not isinstance(bucket.get("total"), int):
        bucket["total"] = int(bucket.get("total", 0) or 0)
    return bucket


def _increment_bucket(bucket: Dict[str, Any], index: int, now_iso: str) -> None:
    bucket["grid"][index] = int(bucket["grid"][index]) + 1
    bucket["total"] = int(bucket.get("total", 0)) + 1
    bucket["updated_at"] = now_iso


class Activity(SimpleCommandModule):
    """Tracks non-command channel message activity for stats/heatmaps."""

    name = "activity"
    version = "1.0.0"
    description = "Tracks channel/user activity heatmaps for the stats UI."

    def __init__(self, bot: Any) -> None:
        super().__init__(bot)

        now_iso = datetime.now(UTC).isoformat()
        self.set_state("schema_version", int(self.get_state("schema_version", 1)))
        self.set_state("global", _ensure_bucket(self.get_state("global"), now_iso))
        self.set_state("channels", self.get_state("channels", {}))
        self.set_state("users", self.get_state("users", {}))
        self.save_state()

        self._pending_updates = 0
        self._last_flush_ts = time.time()

    def _register_commands(self) -> None:
        return

    def on_ambient_message(self, connection: Any, event: Any, msg: str, username: str) -> bool:
        if not self.is_enabled(event.target):
            return False

        channel = event.target
        if not isinstance(channel, str) or not channel.startswith("#"):
            return False

        if not msg or not isinstance(msg, str):
            return False

        # This hook only runs when no command matched, but keep this consistent with seen.py.
        if msg.startswith("!"):
            return False

        include_sed = bool(self.get_config_value("track_sed_messages", default=False))
        if not include_sed and msg.lstrip().startswith("s/"):
            return False

        now = datetime.now(UTC)
        index = (now.weekday() * 24) + now.hour
        now_iso = now.isoformat()

        global_bucket = _ensure_bucket(self.get_state("global"), now_iso)
        channels = self.get_state("channels", {})
        users = self.get_state("users", {})

        channel_bucket = _ensure_bucket(channels.get(channel), now_iso)

        user_id = self.bot.get_user_id(username)
        user_bucket = _ensure_bucket(users.get(user_id), now_iso)

        _increment_bucket(global_bucket, index, now_iso)
        _increment_bucket(channel_bucket, index, now_iso)
        _increment_bucket(user_bucket, index, now_iso)

        channels[channel] = channel_bucket
        users[user_id] = user_bucket

        self.set_state("global", global_bucket)
        self.set_state("channels", channels)
        self.set_state("users", users)

        self._pending_updates += 1
        flush_every_messages = int(self.get_config_value("flush_every_messages", default=50))
        flush_interval_seconds = float(self.get_config_value("flush_interval_seconds", default=30))
        now_ts = time.time()

        if self._pending_updates >= max(1, flush_every_messages) or (now_ts - self._last_flush_ts) >= max(1.0, flush_interval_seconds):
            self.save_state()
            self._pending_updates = 0
            self._last_flush_ts = now_ts

        return False

    def on_unload(self) -> None:
        self.save_state(force=True)

