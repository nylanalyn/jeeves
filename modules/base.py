# modules/base.py
# Enhanced base class for all Jeeves modules with common utilities and patterns

import re
import time
import threading
import functools
import requests
import sys
import traceback
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List, Callable, Union, Tuple
from datetime import datetime, timezone

# Import standardized exception handling utilities
try:
    from .exception_utils import (
        handle_exceptions, safe_execute, safe_api_call, safe_file_operation,
        validate_user_input, log_module_event, log_security_event,
        ModuleException, ExternalAPIException, UserInputException, StateException
    )
except ImportError:
    # Fallback for when exception_utils is not available
    def handle_exceptions(*args, **kwargs):
        def decorator(func):
            return func
        return decorator
    
    def safe_execute(func, *args, **kwargs):
        return func(*args, **kwargs), None
    
    safe_api_call = safe_execute
    safe_file_operation = safe_execute
    
    def validate_user_input(value, validation_func, *args, **kwargs):
        return validation_func(value)
    
    def log_module_event(module_name, event, details=None):
        print(f"[{module_name}] {event}", file=sys.stderr)
    
    def log_security_event(module_name, event, user=None, details=None):
        print(f"[SECURITY][{module_name}] {event}", file=sys.stderr)
    
    class ModuleException(Exception): pass
    class ExternalAPIException(Exception): pass
    class UserInputException(Exception): pass
    class StateException(Exception): pass

# Import centralized HTTP client
try:
    from .http_utils import get_http_client
except ImportError:
    # Should not happen in production, but safe fallback
    get_http_client = None

def admin_required(func):
    """Decorator to require admin privileges for a command."""
    @functools.wraps(func)
    def wrapper(self, connection, event, msg, username, *args, **kwargs):
        if not self.bot.is_admin(event.source):
            return False
        return func(self, connection, event, msg, username, *args, **kwargs)
    return wrapper

def debug_log(message_template: str):
    """
    Decorator to add automatic debug logging to any method.

    Usage:
        @debug_log("Spawning animal: target_channel={target_channel}")
        def _spawn_animal(self, target_channel=None):
            ...

    The decorator will log the message with parameter values when the method is called.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            # Build a dict of all arguments
            import inspect
            sig = inspect.signature(func)
            bound_args = sig.bind(self, *args, **kwargs)
            bound_args.apply_defaults()

            # Format the message with actual parameter values
            try:
                formatted_msg = message_template.format(**bound_args.arguments)
                self.log_debug(f"{func.__name__}: {formatted_msg}")
            except (KeyError, AttributeError):
                # Fallback if formatting fails
                self.log_debug(f"{func.__name__} called with args={args}, kwargs={kwargs}")

            return func(self, *args, **kwargs)
        return wrapper
    return decorator

class ModuleBase(ABC):
    name = "base"
    version = "2.1.0" # Updated to use http_utils
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
        
        # Initialize shared HTTP client
        if get_http_client:
            self.http = get_http_client()
        else:
            self.http = None

    def requests_retry_session(self, retries: int = 3, backoff_factor: float = 0.3,
                                status_forcelist: tuple = (500, 502, 504)) -> requests.Session:
        """
        Compatibility method for modules still using the old session pattern.
        Returns a requests session with retry logic.
        """
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry

        session = requests.Session()
        retry = Retry(
            total=retries,
            read=retries,
            connect=retries,
            backoff_factor=backoff_factor,
            status_forcelist=status_forcelist,
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        return session

    def on_load(self) -> None:
        """Called when module is loaded. Can be overridden in subclasses."""
        pass

    def on_unload(self) -> None:
        """Called when module is unloaded. Can be overridden in subclasses."""
        self.save_state(force=True)

    def on_config_reload(self, new_config: Dict[str, Any]) -> None:
        """Called when config is reloaded. Override in subclasses to react to changes."""
        pass

    # --- Geolocation Helpers ---

    def _get_geocode_data(self, location: str) -> Optional[Tuple[str, str, Dict[str, Any]]]:
        """Fetches geographic coordinates and structured address for a location string."""
        geo_url = "https://nominatim.openstreetmap.org/search"
        params = {
            "q": location,
            "format": "json",
            "limit": 1,
            "addressdetails": 1
        }
        
        try:
            if self.http:
                geo_data = self.http.get_json(geo_url, params=params)
            else:
                # Fallback (should rarely be used)
                response = requests.get(geo_url, params=params, headers={'User-Agent': 'JeevesIRCBot/1.0'}, timeout=10)
                response.raise_for_status()
                geo_data = response.json()

            if not geo_data:
                return None
            return (geo_data[0]["lat"], geo_data[0]["lon"], geo_data[0])
        except Exception as e:
            self._record_error(f"Geocoding request failed for '{location}': {e}")
            return None

    def _format_location_name(self, geo_data: Dict[str, Any]) -> str:
        """Builds a concise location name from structured geodata."""
        address = geo_data.get("address", {})
        parts = []
        
        place = address.get("city") or address.get("town") or address.get("village") or address.get("hamlet")
        if place:
            parts.append(place)
        
        if address.get("state"):
            parts.append(address.get("state"))
            
        if address.get("country_code"):
            parts.append(address.get("country_code").upper())

        if parts:
            return ", ".join(parts)
        
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
                
    # --- NEW: Dynamic Configuration Management ---

    def get_config_value(self, key: str, channel: Optional[str] = None, default: Any = None) -> Any:
        """
        Gets a configuration value for the module, checking for a channel-specific
        override before falling back to the global setting. Supports dotted keys
        (e.g. "energy_system.enabled") for nested config blocks.
        """

        def resolve(config_section: Optional[Dict[str, Any]], dotted_key: str) -> Any:
            """Resolve dotted keys within a config section."""
            if not isinstance(config_section, dict) or dotted_key is None:
                return None

            if dotted_key in config_section:
                return config_section[dotted_key]

            if "." not in dotted_key:
                return None

            current: Any = config_section
            for part in dotted_key.split("."):
                if isinstance(current, dict) and part in current:
                    current = current[part]
                else:
                    return None
            return current

        try:
            full_config = self.bot.config
            module_config = full_config.get(self.name, {})

            if channel:
                channel_config = module_config.get("channels", {}).get(channel)
                channel_override = resolve(channel_config, key)
                if channel_override is not None:
                    return channel_override

            global_value = resolve(module_config, key)
            if global_value is not None:
                return global_value
        except Exception as e:
            self.log_debug(f"Error reading config key '{key}': {e}")

        return default

    def is_enabled(self, channel: str) -> bool:
        """
        Checks if the module is enabled for a given channel using allow/block lists.

        Logic:
        - If allowed_channels is defined and not empty, module ONLY works in those channels
        - If allowed_channels is empty/not defined, module works in all channels except blocked_channels
        - blocked_channels only applies when allowed_channels is empty
        """
        module_config = self.bot.config.get(self.name, {})

        # Check allowed_channels first (whitelist mode)
        allowed_channels = module_config.get("allowed_channels", [])
        if allowed_channels:
            return channel in allowed_channels

        # If no whitelist, check blocked_channels (blacklist mode)
        blocked_channels = module_config.get("blocked_channels", [])
        return channel not in blocked_channels


    # --- Command and Message Handling ---

    def register_command(self, pattern: Union[str, re.Pattern],
                        handler: Callable, name: str, admin_only: bool = False,
                        cooldown: float = 0.0, description: str = "", **kwargs) -> None:
        # Backward compatibility for older modules using cooldown_seconds keyword.
        if "cooldown_seconds" in kwargs:
            cooldown = kwargs.pop("cooldown_seconds")
        if kwargs:
            raise TypeError(f"register_command() got unexpected keyword arguments: {', '.join(kwargs.keys())}")
        if isinstance(pattern, str):
            # Convert ! prefix to accept both ! and ,
            pattern = pattern.replace(r'!', r'[!,]')
            pattern = re.compile(pattern, re.IGNORECASE)
        command_id = f"{self.name}_{name}"
        self._commands[command_id] = {
            "pattern": pattern, "handler": handler, "name": name.lower(),
            "admin_only": admin_only, "cooldown": cooldown, "description": description
        }

    def check_rate_limit(self, key: str, limit: float) -> bool:
        now = time.time()
        last_time = self._rate_limits.get(key, 0)
        if now - last_time >= limit:
            self._rate_limits[key] = now
            return True
        return False

    def check_user_cooldown(self, username: str, command: str, cooldown: float) -> bool:
        """Check if a user is on cooldown for a command. Does NOT record the cooldown."""
        if cooldown <= 0: return True
        key = f"{username.lower()}:{command}"
        now = time.time()
        last_use = self._user_cooldowns.get(key, 0)
        return now - last_use >= cooldown

    def record_user_cooldown(self, username: str, command: str) -> None:
        """Record that a user has used a command (for cooldown tracking)."""
        key = f"{username.lower()}:{command}"
        self._user_cooldowns[key] = time.time()

    def is_mentioned(self, msg: str) -> bool:
        pattern = re.compile(self.bot.JEEVES_NAME_RE, re.IGNORECASE)
        return bool(pattern.search(msg))

    def has_flavor_enabled(self, username: str) -> bool:
        """Check if a user has flavor text enabled. Defaults to True if users module unavailable."""
        users_module = self.bot.pm.plugins.get("users")
        if users_module and hasattr(users_module, "has_flavor_enabled"):
            return users_module.has_flavor_enabled(username)
        return True  # Default to flavor enabled if users module not available

    @handle_exceptions(
        error_message="Failed to send reply message",
        user_message="Unable to send message",
        log_exception=True,
        reraise=False
    )
    def safe_reply(self, connection, event, text: str) -> bool:
        lines = text.splitlines()
        if not lines:
            lines = [text]
        for line in lines:
            sanitized = line.replace("\r", "")
            if not sanitized:
                sanitized = " "
            connection.privmsg(event.target, sanitized)
        return True
            
    @handle_exceptions(
        error_message="Failed to send channel message",
        user_message="Unable to send message",
        log_exception=True,
        reraise=False
    )
    def safe_say(self, text: str, target: Optional[str] = None) -> bool:
        target = target or self.bot.primary_channel
        lines = text.splitlines()
        if not lines:
            lines = [text]
        for line in lines:
            sanitized = line.replace("\r", "")
            if not sanitized:
                sanitized = " "
            self.bot.connection.privmsg(target, sanitized)
        return True

    @handle_exceptions(
        error_message="Failed to send private message",
        user_message="Unable to send private message",
        log_exception=True,
        reraise=False
    )
    def safe_privmsg(self, username: str, text: str) -> bool:
        lines = text.splitlines()
        if not lines:
            lines = [text]
        for line in lines:
            sanitized = line.replace("\r", "")
            if not sanitized:
                sanitized = " "
            self.bot.connection.privmsg(username, sanitized)
        return True

    def _dispatch_commands(self, connection, event, msg: str, username: str) -> bool:
        # MODIFIED: Check if module is enabled before processing any commands
        if not self.is_enabled(event.target):
            return False
            
        for cmd_id, cmd_info in self._commands.items():
            match = cmd_info["pattern"].match(msg)
            if match:
                self.log_debug(f"Command '{cmd_info['name']}' matched by user {username} with pattern: {cmd_info['pattern'].pattern}")
                if cmd_info["admin_only"] and not self.bot.is_admin(event.source): 
                    self.log_debug(f"Denying admin command '{cmd_info['name']}' for non-admin {username}")
                    continue
                
                # Cooldown is now fetched dynamically
                cooldown_val = self.get_config_value("cooldown_seconds", event.target, cmd_info["cooldown"])

                if not self.check_user_cooldown(username, cmd_id, cooldown_val):
                    self.log_debug(f"Command '{cmd_info['name']}' on cooldown for user {username}")
                    continue
                try:
                    if cmd_info["handler"](connection, event, msg, username, match):
                        self.log_debug(f"Command '{cmd_info['name']}' handled successfully.")
                        # Record cooldown after successful command execution
                        if cooldown_val > 0:
                            self.record_user_cooldown(username, cmd_id)
                        if hasattr(self, "_update_stats"):
                            self._update_stats(cmd_info["name"])
                        return True
                except UserInputException as e:
                    # User input errors - log but don't expose details
                    self.log_debug(f"User input error in command {cmd_id}: {e}")
                except Exception as e:
                    # Log other errors with full traceback
                    self.log_debug(f"Unexpected error in command {cmd_id}: {e}\n{traceback.format_exc()}")
                    log_security_event(self.name, "Command execution error", username, {"command": cmd_id, "error": str(e)})
        return False
        
    def _record_error(self, error_msg: str, severity: str = "ERROR") -> None:
        """Record an error with standardized severity levels."""
        if severity == "SECURITY":
            log_security_event(self.name, error_msg)
        elif severity == "WARNING":
            self.log_debug(f"WARNING: {error_msg}")
        else:
            self.log_debug(f"ERROR: {error_msg}")
        
    def log_module_event(self, severity: str, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        """
        Bridge helper so subclasses can log standardized events without importing
        exception_utils directly.
        """
        event_message = f"{severity}: {message}"
        log_module_event(self.name, event_message, details)

    def log_debug(self, message: str):
        self.bot.log_debug(f"[{self.name}] {message}")

    def log_debug_vars(self, context: str, **variables):
        """
        Log multiple variables at once for debugging.

        Usage:
            self.log_debug_vars("spawn_check",
                                active_animal=self.get_state("active_animal"),
                                spawn_locations=spawn_locations,
                                target_channel=target_channel)
        """
        var_strs = [f"{k}={v}" for k, v in variables.items()]
        self.log_debug(f"{context}: {', '.join(var_strs)}")

class SimpleCommandModule(ModuleBase):
    def __init__(self, bot): # CORRECTED: Removed 'config' parameter
        super().__init__(bot)
        self._register_commands()
    
    @abstractmethod
    def _register_commands(self) -> None:
        """Abstract method to be overridden in subclasses."""
        pass

    # IMPORTANT: Any module implementing on_ambient_message must now
    # add `if not self.is_enabled(event.target): return False`
    # as the first line of that method.
