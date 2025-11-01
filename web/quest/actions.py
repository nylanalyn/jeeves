# web/quest/actions.py
# Bridge helpers that let the web server invoke quest module logic safely.

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

import yaml

import schedule

from modules.quest_pkg import Quest, quest_core


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
            if isinstance(data, dict):
                return data
    except (json.JSONDecodeError, OSError):
        logging.exception("Failed to load JSON from %s", path)
    return {}


def _save_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
    tmp.replace(path)


class DummyConnection:
    """Minimal stand-in for an IRC connection that captures outgoing messages."""

    def __init__(self) -> None:
        self.messages: List[str] = []

    def privmsg(self, _target: str, text: str) -> None:
        self.messages.append(text)


@dataclass
class DummyEvent:
    target: str


class WebQuestBot:
    """Facade that satisfies the subset of Jeeves bot API used by the quest module."""

    def __init__(self, config: Dict[str, Any], config_dir: Path) -> None:
        self.config = config or {}
        self.config_dir = config_dir
        self.games_path = config_dir / "games.json"
        self.users_path = config_dir / "users.json"
        self.games_state = _load_json(self.games_path)
        self.users_state = _load_json(self.users_path)
        self._dirty_games = False
        self._dirty_users = False
        self._lock = threading.RLock()

    # --- Logging helpers -------------------------------------------------
    def log_debug(self, message: str) -> None:
        logging.debug("[web-quest] %s", message)

    # --- Admin / identity helpers ----------------------------------------
    def is_admin(self, _source: Any) -> bool:
        return False

    def get_user_id(self, nick: str) -> str:
        with self._lock:
            nick_map = (
                self.users_state.get("modules", {})
                .get("users", {})
                .get("nick_map", {})
            )
            user_id = nick_map.get(nick.lower())
            if user_id:
                return user_id
            # If the user does not exist yet, create a transient mapping
            user_id = str(uuid.uuid4())
            self._ensure_users_root()
            nick_map = self.users_state["modules"]["users"].setdefault("nick_map", {})
            user_map = self.users_state["modules"]["users"].setdefault("user_map", {})
            nick_map[nick.lower()] = user_id
            user_map[user_id] = {
                "id": user_id,
                "canonical_nick": nick,
                "seen_nicks": [nick.lower()],
                "first_seen": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
            }
            self._dirty_users = True
            return user_id

    def get_user_nick(self, user_id: str) -> str:
        with self._lock:
            user_map = (
                self.users_state.get("modules", {})
                .get("users", {})
                .get("user_map", {})
            )
            profile = user_map.get(user_id)
            if profile:
                return profile.get("canonical_nick") or profile.get("id", user_id)
        return user_id

    def get_utc_time(self) -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def title_for(self, nick: str) -> str:
        return nick

    def pronouns_for(self, _nick: str) -> str:
        return "they/them"

    # --- State helpers ---------------------------------------------------
    def _ensure_games_root(self) -> None:
        with self._lock:
            modules = self.games_state.setdefault("modules", {})
            modules.setdefault("quest", {})

    def _ensure_users_root(self) -> None:
        with self._lock:
            modules = self.users_state.setdefault("modules", {})
            modules.setdefault("users", {})

    def get_module_state(self, name: str) -> Dict[str, Any]:
        with self._lock:
            modules = self.games_state.setdefault("modules", {})
            return modules.setdefault(name, {}).copy()

    def update_module_state(self, name: str, updates: Dict[str, Any]) -> None:
        with self._lock:
            modules = self.games_state.setdefault("modules", {})
            modules[name] = updates
            self._dirty_games = True

    # --- Persistence -----------------------------------------------------
    def persist(self) -> None:
        with self._lock:
            if self._dirty_games:
                _save_json(self.games_path, self.games_state)
                self._dirty_games = False
            if self._dirty_users:
                _save_json(self.users_path, self.users_state)
                self._dirty_users = False


class QuestActionService:
    """Entry point used by the HTTP handlers to process quest requests."""

    def __init__(self, config_dir: Path, config_path: Path):
        self.config_dir = config_dir
        self.config_path = config_path
        self.config: Dict[str, Any] = {}
        self._load_config()
        self._lock = threading.RLock()

    def _load_config(self) -> None:
        if not self.config_path.exists():
            self.config = {}
            return
        try:
            with open(self.config_path, "r", encoding="utf-8") as handle:
                self.config = yaml.safe_load(handle) or {}
        except (yaml.YAMLError, OSError):
            logging.exception("Failed to load config.yaml for web quest actions")
            self.config = {}

    # --- Token handling --------------------------------------------------
    def consume_link_token(self, token: str) -> Optional[Dict[str, Any]]:
        games_path = self.config_dir / "games.json"
        games_state = _load_json(games_path)
        modules = games_state.get("modules", {})
        quest_state = modules.get("quest", {})
        tokens = quest_state.get("web_link_tokens", {})

        now = time.time()
        changed = False

        # Remove expired tokens
        for candidate, info in list(tokens.items()):
            expires_at = info.get("expires_at", 0)
            if expires_at <= now:
                tokens.pop(candidate, None)
                changed = True

        info = tokens.pop(token, None)
        if info:
            changed = True
        if changed:
            quest_state["web_link_tokens"] = tokens
            modules["quest"] = quest_state
            games_state["modules"] = modules
            _save_json(games_path, games_state)

        if not info:
            return None
        if info.get("expires_at", 0) <= now:
            return None
        return {"user_id": info.get("user_id"), "username": info.get("username")}

    # --- Quest actions ---------------------------------------------------
    def perform_solo_quest(self, user_id: str, difficulty: str = "normal") -> Dict[str, Any]:
        with self._lock:
            bot = WebQuestBot(self.config, self.config_dir)
            username = bot.get_user_nick(user_id)
            if not username:
                username = user_id

            quest = Quest(bot)
            connection = DummyConnection()
            event = DummyEvent(target="#web")

            handled = False
            try:
                quest._load_state()
                quest.on_load()
                schedule.run_pending()
                handled = quest_core.handle_solo_quest(quest, connection, event, username, difficulty)
            finally:
                quest.save_state(force=True)
                bot.persist()
                quest.on_unload()

            return {
                "handled": bool(handled),
                "messages": connection.messages,
                "username": username,
                "difficulty": difficulty,
            }
