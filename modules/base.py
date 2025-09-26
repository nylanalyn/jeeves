# modules/base.py
# Enhanced base class for all Jeeves modules with common utilities and patterns

import re
import time
import threading
import functools
import requests
import sys
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List, Callable, Union, Tuple
from datetime import datetime, timezone

def admin_required(func):
    """Decorator to require admin privileges for a command."""
    @functools.wraps(func)
    def wrapper(self, connection, event, msg, username, *args, **kwargs):
        if not self.bot.is_admin(event.source):
            return False
        return func(self, connection, event, msg, username, *args, **kwargs)
    return wrapper

class ModuleBase(ABC):
    name = "base"
    version = "1.4.0"
    description = "Base module class"
    
    def __init__(self, bot):
        self.bot = bot
        self._state_cache = {}
        self._state_dirty = False
        self._state_lock = threading.RLock()
        self._commands: Dict[str, Dict[str, Any]] = {}
        self._rate_limits = {}
        self._user_cooldowns = {}
        self._load_state()

    def on_load(self) -> None:
        """Called when module is loaded. Can be overridden in subclasses."""
        pass

    def on_unload(self) -> None:
        """Called when module is unloaded. Can be overridden in subclasses."""
        self.save_state(force=True)

    def on_config_reload(self, new_config: Dict[str, Any]) -> None:
        """Called when config.yaml is reloaded. Override in subclasses to react to changes."""
        pass

    def requests_retry_session(self, retries=3, backoff_factor=0.3, status_forcelist=(500, 502, 504), session=None):
        session = session or requests.Session()
        retry = Retry(total=retries, read=retries, connect=retries, backoff_factor=backoff_factor, status_forcelist=status_forcelist)
        adapter = HTTPAdapter(max_retries=retry)
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        return session

    # --- Geolocation Helpers ---

    def _get_geocode_data(self, location: str) -> Optional[Tuple[str, str, Dict[str, Any]]]:
        """Fetches geographic coordinates and structured address for a location string."""
        geo_url = f"https://nominatim.openstreetmap.org/search?q={requests.utils.quote(location)}&format=json&limit=1&addressdetails=1"
        try:
            # Use the requests_retry_session for resilience
            http_session = self.requests_retry_session()
            response = http_session.get(geo_url, headers={'User-Agent': 'JeevesIRCBot/1.0'}, timeout=10)
            response.raise_for_status()
            geo_data = response.json()
            if not geo_data:
                return None
            return (geo_data[0]["lat"], geo_data[0]["lon"], geo_data[0])
        except (requests.exceptions.RequestException, IndexError, ValueError, KeyError) as e:
            self._record_error(f"Geocoding request failed for '{location}': {e}")
            return None

    def _format_location_name(self, geo_data: Dict[str, Any]) -> str:
        """Builds a concise location name from structured geodata."""
        address = geo_data.get("address", {})
        parts = []
        
        # Find the most specific place name
        place = address.get("city") or address.get("town") or address.get("village") or address.get("hamlet")
        if place:
            parts.append(place)
        
        if address.get("state"):
            parts.append(address.get("state"))
            
        if address.get("country_code"):
            parts.append(address.get("country_code").upper())

        if parts:
            return ", ".join(parts)
        
        # Fallback to the long name if structured data is weird
        return geo_data.get("display_name", "an unknown location")

    # --- State Management ---

    def _load_state(self):
        with self._state_lock:
            self._state_cache = self.bot.get_module_state(self.name).copy()
            self._state_dirty = False

    def get_state(self, key: Optional[str] = None, default: Any = None) -> Any:
        with self._state_lock:
            return self._state_cache.copy() if key is None else self._state_cache.get(key, default)

    def set_state(self, key: str, value: Any) -> None:
        with self._state_lock:
            self._state_cache[key] = value
            self._state_dirty = True
            
    def update_state(self, updates: Dict[str, Any]) -> None:
        with self._state_lock:
            self._state_cache.update(updates)
            self._state_dirty = True

    def save_state(self, force: bool = False) -> None:
        with self._state_lock:
            if self._state_dirty or force:
                self.bot.update_module_state(self.name, self._state_cache)
                self._state_dirty = False

    # --- Command and Message Handling ---

    def register_command(self, pattern: Union[str, re.Pattern], 
                        handler: Callable, name: str, admin_only: bool = False,
                        cooldown: float = 0.0, description: str = "") -> None:
        if isinstance(pattern, str):
            pattern = re.compile(pattern, re.IGNORECASE)
        command_id = f"{self.name}_{name}"
        self._commands[command_id] = {
            "pattern": pattern, "handler": handler, "name": name.lower(),
            "admin_only": admin_only, "cooldown": cooldown, "description": description
        }

    def check_rate_limit(self, key: str, limit: float) -> bool:
        """Check if rate limit allows action."""
        now = time.time()
        last_time = self._rate_limits.get(key, 0)
        if now - last_time >= limit:
            self._rate_limits[key] = now
            return True
        return False

    def check_user_cooldown(self, username: str, command: str, cooldown: float) -> bool:
        if cooldown <= 0: return True
        key = f"{username.lower()}:{command}"
        now = time.time()
        last_use = self._user_cooldowns.get(key, 0)
        if now - last_use >= cooldown:
            self._user_cooldowns[key] = now
            return True
        return False

    def is_mentioned(self, msg: str) -> bool:
        pattern = re.compile(self.bot.JEEVES_NAME_RE, re.IGNORECASE)
        return bool(pattern.search(msg))

    def safe_reply(self, connection, event, text: str) -> bool:
        try:
            connection.privmsg(event.target, text)
            return True
        except Exception as e:
            self._record_error(f"Failed to reply: {e}")
            return False
            
    def safe_say(self, text: str, target: Optional[str] = None) -> bool:
        try:
            target = target or self.bot.primary_channel
            self.bot.connection.privmsg(target, text)
            return True
        except Exception as e:
            self._record_error(f"Failed to send message to {target}: {e}")
            return False

    def safe_privmsg(self, username: str, text: str) -> bool:
        try:
            self.bot.connection.privmsg(username, text)
            return True
        except Exception as e:
            self._record_error(f"Failed to send privmsg to {username}: {e}")
            return False

    def _dispatch_commands(self, connection, event, msg: str, username: str) -> bool:
        for cmd_id, cmd_info in self._commands.items():
            match = cmd_info["pattern"].match(msg)
            if match:
                if cmd_info["admin_only"] and not self.bot.is_admin(event.source): continue
                if not self.check_user_cooldown(username, cmd_id, cmd_info["cooldown"]): continue
                try:
                    if cmd_info["handler"](connection, event, msg, username, match):
                        if hasattr(self, "_update_stats"):
                            self._update_stats(cmd_info["name"])
                        return True
                except Exception as e:
                    self._record_error(f"Error in command {cmd_id}: {e}")
        return False
        
    def _record_error(self, error_msg: str) -> None:
        print(f"[{self.name}] ERROR: {error_msg}", file=sys.stderr)

class SimpleCommandModule(ModuleBase):
    def __init__(self, bot):
        super().__init__(bot)
        self._register_commands()
    
    def _register_commands(self) -> None:
        """Abstract method to be overridden in subclasses."""
        pass

