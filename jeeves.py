#!/usr/bin/env python3
# jeeves.py — modular IRC butler core

import os
import sys
import time
import json
import re
import ssl
import signal
import threading
import traceback
import importlib.util
import yaml
import shutil
import functools
import logging
import random
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import datetime, timezone
from irc.bot import SingleServerIRCBot
from irc.connection import Factory
import schedule
from file_lock import FileLock
import bcrypt

# Import configuration validator
try:
    from config_validator import load_and_validate_config
except ImportError:
    print("Error: Configuration validator not found. Please ensure config_validator.py is in the same directory.", file=sys.stderr)
    sys.exit(1)

UTC = timezone.utc
ROOT = Path(__file__).resolve().parent

# --- Self-Contained Path Configuration ---
CONFIG_DIR = ROOT / "config"
STATE_PATH = CONFIG_DIR / "state.json"
CONFIG_PATH = CONFIG_DIR / "config.yaml"

def load_config():
    """Loads the YAML configuration file."""
    if not CONFIG_PATH.exists():
        return {}
    try:
        with open(CONFIG_PATH, 'r') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"[boot] error loading config.yaml: {e}", file=sys.stderr)
        return {}

# ----- Multi-File State Manager -----
class MultiFileStateManager:
    """
    Manages multiple state files for different categories of data.
    - state.json: Core config and non-critical module data
    - games.json: Game state (quest, hunt, bell, adventure, roadtrip)
    - users.json: User profiles, locations, memos
    - stats.json: Statistics and tracking data (coffee, courtesy)
    """

    STATE_FILE_MAPPING = {
        # Game modules
        'quest': 'games',
        'hunt': 'games',
        'bell': 'games',
        'adventure': 'games',
        'roadtrip': 'games',
        'fishing': 'games',
        # User data modules
        'users': 'users',
        'weather': 'users',
        'memos': 'users',
        'profiles': 'users',
        # Stats modules
        'coffee': 'stats',
        'courtesy': 'stats',
        'leveling': 'stats',
        'duel': 'stats',
        'karma': 'stats',
        'activity': 'stats',
        # Everything else uses 'state' (config storage)
    }

    def __init__(self, base_dir):
        self.base_dir = Path(base_dir)
        self._locks = {
            'state': threading.RLock(),
            'games': threading.RLock(),
            'users': threading.RLock(),
            'stats': threading.RLock(),
        }
        self._states = {}
        self._dirty = {}
        self._save_timers = {}
        self._mtimes = {}

        for file_type in ['state', 'games', 'users', 'stats']:
            self._states[file_type] = {}
            self._dirty[file_type] = False
            self._save_timers[file_type] = None
            self._mtimes[file_type] = 0.0

        self._load_all()

    def _get_path(self, file_type):
        """Get the path for a given file type."""
        return self.base_dir / f"{file_type}.json"

    def _load_all(self):
        """Load all state files."""
        for file_type in ['state', 'games', 'users', 'stats']:
            self._load_file(file_type)

    def _update_mtime(self, file_type):
        path = self._get_path(file_type)
        try:
            self._mtimes[file_type] = path.stat().st_mtime
        except FileNotFoundError:
            self._mtimes[file_type] = 0.0

    def _load_file(self, file_type, create_backup=True, quiet=False):
        """Load a specific state file with backup support."""
        path = self._get_path(file_type)
        backup_path = path.with_suffix(".json.backup")

        # Acquire file lock for the entire read operation
        with FileLock(path):
            # Create backup if file exists and is valid
            if path.exists() and create_backup:
                try:
                    with open(path, "r") as f:
                        test_load = json.load(f)
                    shutil.copy2(path, backup_path)
                    if not quiet:
                        print(f"[state] Created backup: {backup_path}", file=sys.stderr)
                except Exception as e:
                    print(f"[state] Warning: Could not backup {file_type}.json: {e}", file=sys.stderr)

            # Try to load main file
            try:
                if path.exists():
                    with open(path, "r") as f:
                        self._states[file_type] = json.load(f)
                    if not quiet:
                        print(f"[state] Loaded {file_type}.json", file=sys.stderr)
                else:
                    self._states[file_type] = {}
                    if not quiet:
                        print(f"[state] No existing {file_type}.json, starting fresh", file=sys.stderr)
            except Exception as e:
                print(f"[state] Load error for {file_type}.json: {e}", file=sys.stderr)
                # Try to restore from backup
                if backup_path.exists():
                    try:
                        print(f"[state] Attempting to restore {file_type}.json from backup...", file=sys.stderr)
                        with open(backup_path, "r") as f:
                            self._states[file_type] = json.load(f)
                        print(f"[state] Successfully restored {file_type}.json from backup!", file=sys.stderr)
                    except Exception as backup_err:
                        print(f"[state] Backup restore failed for {file_type}.json: {backup_err}", file=sys.stderr)
                        self._states[file_type] = {}
                else:
                    self._states[file_type] = {}
            finally:
                self._update_mtime(file_type)

    def _get_file_type_for_module(self, module_name):
        """Determine which file type a module should use."""
        return self.STATE_FILE_MAPPING.get(module_name, 'state')

    def _ensure_latest(self, file_type):
        path = self._get_path(file_type)
        try:
            mtime = path.stat().st_mtime
        except FileNotFoundError:
            mtime = 0.0

        current = self._mtimes.get(file_type, 0.0)
        if mtime == 0.0 and current != 0.0:
            self._load_file(file_type, create_backup=False, quiet=True)
        elif mtime > current:
            self._load_file(file_type, create_backup=False, quiet=True)

    def get_state(self):
        """Get the entire main state (for backward compatibility)."""
        with self._locks['state']:
            self._ensure_latest('state')
            return json.loads(json.dumps(self._states['state']))

    def update_state(self, updates):
        """Update the main state file (for backward compatibility)."""
        with self._locks['state']:
            self._ensure_latest('state')
            self._states['state'].update(updates)
            self._mark_dirty('state')

    def get_module_state(self, name):
        """Get a module's state from the appropriate file."""
        file_type = self._get_file_type_for_module(name)
        with self._locks[file_type]:
            self._ensure_latest(file_type)
            mods = self._states[file_type].setdefault("modules", {})
            return mods.setdefault(name, {})

    def update_module_state(self, name, updates):
        """Update a module's state in the appropriate file."""
        file_type = self._get_file_type_for_module(name)
        with self._locks[file_type]:
            self._ensure_latest(file_type)
            mods = self._states[file_type].setdefault("modules", {})
            mods[name] = updates
            self._mark_dirty(file_type)

    def _mark_dirty(self, file_type):
        """Mark a specific file as dirty and schedule save."""
        self._dirty[file_type] = True
        if self._save_timers[file_type]:
            self._save_timers[file_type].cancel()
        self._save_timers[file_type] = threading.Timer(0.5, lambda: self._save_now(file_type))
        self._save_timers[file_type].daemon = True
        self._save_timers[file_type].start()

    def _save_now(self, file_type):
        """Save a specific state file."""
        with self._locks[file_type]:
            if not self._dirty[file_type]:
                return
            try:
                path = self._get_path(file_type)
                # Acquire file lock for the entire write operation
                with FileLock(path):
                    tmp = path.with_suffix(".tmp")
                    tmp.write_text(json.dumps(self._states[file_type], indent=4))
                    tmp.replace(path)
                    self._update_mtime(file_type)
                self._dirty[file_type] = False
                print(f"[state] Saved {file_type}.json", file=sys.stderr)
            except Exception as e:
                print(f"[state] Save error for {file_type}.json: {e}\n{traceback.format_exc()}", file=sys.stderr)

    def force_save(self):
        """Force save all dirty state files."""
        for file_type in ['state', 'games', 'users', 'stats']:
            if self._save_timers[file_type]:
                self._save_timers[file_type].cancel()
            self._save_now(file_type)

# Backward compatibility: StateManager is now an alias
StateManager = MultiFileStateManager

class PluginManager:
    def __init__(self, bot):
        self.bot = bot
        self.plugins = {}
        self.modules = {}

    def unload_all(self):
        for name in list(self.plugins.keys()):
            self.unload_module(name)

    def load_all(self):
        self.unload_all()
        self.plugins = {}
        self.modules = {}
        loaded_names = []
        
        self.bot.log_debug(f"[plugins] Loading modules from: {ROOT / 'modules'}")
        module_files = list(ROOT.glob("modules/*.py"))
        self.bot.log_debug(f"[plugins] Found {len(module_files)} python files in modules directory.")
        
        blacklist = {f.strip() for f in self.bot.config.get("core", {}).get("module_blacklist", [])}
        if blacklist:
            self.bot.log_debug(f"[plugins] Blacklist active: {', '.join(sorted(list(blacklist)))}")

        for py in sorted(module_files):
            name = py.stem
            if py.name in blacklist:
                self.bot.log_debug(f"[plugins] Skipping blacklisted module: {py.name}")
                continue
            
            if self.load_module(name):
                loaded_names.append(name)
        
        return loaded_names

    def unload_module(self, name: str) -> bool:
        """Unloads a single module by name."""
        if name in self.plugins:
            obj = self.plugins[name]
            if hasattr(obj, "on_unload"):
                try:
                    obj.on_unload()
                except Exception as e:
                    self.bot.log_debug(f"[plugins] error unloading {name}: {e}")
            del self.plugins[name]
            self.bot.log_debug(f"[plugins] Unloaded module: {name}")
            return True
        return False

    def load_module(self, name: str) -> bool:
        """Loads a single module by name."""
        if name in self.plugins or name in ("__init__", "base"):
            return False

        py_path = ROOT / "modules" / f"{name}.py"
        if not py_path.exists():
            self.bot.log_debug(f"[plugins] FAILED to load {name}: file not found at {py_path}")
            return False

        try:
            spec = importlib.util.spec_from_file_location(f"modules.{name}", py_path)
            mod = importlib.util.module_from_spec(spec)
            sys.modules[f"modules.{name}"] = mod
            spec.loader.exec_module(mod)
            if hasattr(mod, "setup"):
                # Setup function now only receives the bot instance
                instance = mod.setup(self.bot)
                if instance:
                    self.plugins[name] = instance
                    if hasattr(instance, "on_load"):
                        instance.on_load()
                    self.bot.log_debug(f"[plugins] Loaded module: {name}")
                    return True
        except Exception as e:
            self.bot.log_debug(f"[plugins] FAILED to load {name}: {e}\n{traceback.format_exc()}")
        
        return False


# ----- Jeeves Bot -----
class Jeeves(SingleServerIRCBot):
    def __init__(self, server, port, channel, nickname, config=None, additional_channels=None):
        self.config = config or {}
        self.ROOT = ROOT
        self._setup_logging()

        if port == 6697:
            ssl_context = ssl.create_default_context()
            wrapper = functools.partial(ssl_context.wrap_socket, server_hostname=server)
            connect_factory = Factory(wrapper=wrapper)
        else:
            connect_factory = Factory()

        super().__init__([(server, port)], nickname, nickname, connect_factory=connect_factory)
        self.server = server
        self.port = port
        self.primary_channel = channel
        self.nickname = nickname
        self.JEEVES_NAME_RE = self.config.get("core", {}).get("name_pattern", "(?:jeeves|jeevesbot)")
        self.nickserv_pass = self.config.get("connection", {}).get("nickserv_pass", "")
        self.pm = PluginManager(self)

        # Build initial channel list from config
        config_channels = set([self.primary_channel])
        if additional_channels:
            config_channels.update(additional_channels)

        # Merge with persisted channels from state
        core_state = state_manager.get_module_state("core")
        persisted_channels = set(core_state.get("joined_channels", []))
        print(f"[core] Loaded persisted channels from state: {persisted_channels}", file=sys.stderr)

        # Combine config channels with persisted channels
        all_channels = config_channels | persisted_channels
        print(f"[core] Config channels: {config_channels}", file=sys.stderr)
        print(f"[core] Final channel list to join: {all_channels}", file=sys.stderr)

        self.joined_channels = all_channels
        self.state_manager = state_manager

    # --- Core Bot Functions ---

    def _setup_logging(self):
        self.debug_mode = self.config.get("core", {}).get("debug_mode_on_startup", False)
        self.module_debug = {}  # Track per-module debug status
        log_file = self.config.get("core", {}).get("debug_log_file", "debug.log")

        self.logger = logging.getLogger('jeeves_debug')
        self.logger.setLevel(logging.INFO)

        # Use RotatingFileHandler for automatic log rotation
        # maxBytes=102400 = 100KB per file, backupCount=10 keeps 10 old log files
        handler = RotatingFileHandler(
            ROOT / log_file,
            maxBytes=102400,  # 100KB
            backupCount=10,
            encoding='utf-8'
        )
        formatter = logging.Formatter('%(asctime)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        handler.setFormatter(formatter)

        if (self.logger.hasHandlers()):
            self.logger.handlers.clear()

        self.logger.addHandler(handler)
        # Always write initialization message to ensure file is created
        self.logger.info(f"[core] Logging initialized. Debug mode is {'ON' if self.debug_mode else 'OFF'}. Log rotation: 100KB per file, 10 backups.")

    def _redact_sensitive_data(self, message: str) -> str:
        """Redact sensitive information from log messages."""
        # Patterns for sensitive data
        patterns = [
            (r'(password["\']?\s*[:=]\s*["\']?)([^"\'}\s,]+)(["\']?)', r'\1[REDACTED]\3'),
            (r'(api_key["\']?\s*[:=]\s*["\']?)([^"\'}\s,]+)(["\']?)', r'\1[REDACTED]\3'),
            (r'(token["\']?\s*[:=]\s*["\']?)([^"\'}\s,]+)(["\']?)', r'\1[REDACTED]\3'),
            (r'(secret["\']?\s*[:=]\s*["\']?)([^"\'}\s,]+)(["\']?)', r'\1[REDACTED]\3'),
            (r'(key["\']?\s*[:=]\s*["\']?)([^"\'}\s,]+)(["\']?)', r'\1[REDACTED]\3'),
            # Redact bearer tokens
            (r'(Bearer\s+)([A-Za-z0-9\-._~+/]+)', r'\1[REDACTED]'),
            # Redact long alphanumeric strings that look like tokens (32+ chars)
            (r'\b([A-Za-z0-9]{32,})\b', r'[REDACTED_TOKEN]'),
        ]

        redacted = message
        for pattern, replacement in patterns:
            redacted = re.sub(pattern, replacement, redacted, flags=re.IGNORECASE)

        return redacted

    def log_debug(self, message: str):
        # Redact sensitive data before logging
        safe_message = self._redact_sensitive_data(message)

        # Extract module name from message like "[modulename] ..."
        module_match = re.match(r'^\[(\w+)\]', safe_message)
        if module_match:
            module_name = module_match.group(1)
            # Log if global debug is on OR module-specific debug is on
            if self.debug_mode or self.module_debug.get(module_name, False):
                self.logger.info(safe_message)
        elif self.debug_mode:
            # No module prefix, log if global debug is on
            self.logger.info(safe_message)

    def set_debug_mode(self, status: bool):
        self.debug_mode = status
        self.log_debug(f"[core] Debug mode has been turned {'ON' if status else 'OFF'}.")

    def set_module_debug(self, module_name: str, status: bool):
        self.module_debug[module_name] = status
        self.log_debug(f"[core] Module debug for '{module_name}' has been turned {'ON' if status else 'OFF'}.")

    def core_reload_plugins(self):
        return self.pm.load_all()

    def core_reload_config(self):
        self.log_debug("[core] Validating and reloading configuration from config.yaml...")
        try:
            new_config, success = load_and_validate_config(CONFIG_PATH)
            if not success or not new_config:
                self.log_debug("[core] ERROR: Configuration validation failed during reload")
                return False
            self.config = new_config
            for name, instance in self.pm.plugins.items():
                if hasattr(instance, "on_config_reload"):
                    instance.on_config_reload(self.config.get(name, {}))
            self.log_debug("[core] Configuration reloaded and validated successfully")
            return True
        except Exception as e:
            self.log_debug(f"[core] FAILED to reload configuration from state: {e}")
            return False

    def core_reset_and_reload_config(self):
        """Core function to reload config from config.yaml and reload plugins."""
        self.log_debug("[core] Reloading configuration from config.yaml...")
        try:
            if not self.core_reload_config():
                return False

            self.core_reload_plugins()

            self.log_debug("[core] Configuration has been reloaded from config.yaml.")
            return True
        except Exception as e:
            self.log_debug(f"[core] FAILED to reload configuration: {e}")
            return False

    def get_user_id(self, nick: str) -> str:
        users_module = self.pm.plugins.get("users")
        if users_module:
            return users_module.get_user_id(nick)
        return nick.lower()

    def get_user_nick(self, user_id: str) -> str:
        users_module = self.pm.plugins.get("users")
        if users_module and hasattr(users_module, "get_user_nick"):
            return users_module.get_user_nick(user_id)
        return user_id
    
    def get_utc_time(self) -> str:
        return datetime.now(UTC).isoformat()

    def get_module_state(self, name):
        return state_manager.get_module_state(name)

    def update_module_state(self, name, updates):
        state_manager.update_module_state(name, updates)

    def _update_joined_channels_state(self):
        state_manager.update_module_state("core", {"joined_channels": list(self.joined_channels)})

    def is_admin(self, event_source: str) -> bool:
        try:
            nick = event_source.split('!')[0]
            host = event_source.split('@')[1]
        except IndexError:
            return False

        admin_nicks = {n.strip().lower() for n in self.config.get("core", {}).get("admins", [])}
        if nick.lower() not in admin_nicks:
            return False

        user_id = self.get_user_id(nick)
        courtesy_state = self.get_module_state("courtesy")
        admin_hostnames = courtesy_state.get("admin_hostnames", {})
        stored_host = admin_hostnames.get(user_id)

        if not stored_host or stored_host.lower() != host.lower():
            self.log_debug(f"[core] Updating registered admin host for {nick} ({user_id}) to: {host}")
            courtesy_module = self.pm.plugins.get("courtesy")
            if courtesy_module and hasattr(courtesy_module, "register_admin_hostname"):
                courtesy_module.register_admin_hostname(user_id, host)
            else:
                updated_courtesy_state = dict(courtesy_state)
                updated_hosts = dict(admin_hostnames)
                updated_hosts[user_id] = host
                updated_courtesy_state["admin_hostnames"] = updated_hosts
                self.update_module_state("courtesy", updated_courtesy_state)
            self.connection.privmsg(nick, f"For security, I have updated your registered hostname to '{host}' for this session.")

        return True

    def is_super_admin(self, nick: str) -> bool:
        """
        Check if a nick has authenticated as a super admin with password.

        Super admin authentication is required for dangerous commands like reload.
        If no password hash is configured, all regular admins are treated as super admins.

        Args:
            nick: The nickname to check

        Returns:
            True if the nick is authenticated as super admin, False otherwise
        """
        # If no password hash is configured, fall back to regular admin check
        password_hash = self.config.get("core", {}).get("super_admin_password_hash", "")
        if not password_hash or not password_hash.strip():
            # No password protection - all admins are super admins
            return nick.lower() in {n.strip().lower() for n in self.config.get("core", {}).get("admins", [])}

        # Check if nick is authenticated
        core_state = self.get_module_state("core")
        super_admin_sessions = core_state.get("super_admin_sessions", {})

        session_expiry = super_admin_sessions.get(nick.lower())
        if session_expiry is None:
            return False

        # Check if session is still valid
        if time.time() > session_expiry:
            # Session expired, clean it up
            self.log_debug(f"[core] Super admin session expired for {nick}")
            updated_sessions = dict(super_admin_sessions)
            del updated_sessions[nick.lower()]
            self.update_module_state("core", {"super_admin_sessions": updated_sessions})
            return False

        return True

    def authenticate_super_admin(self, nick: str, password: str) -> bool:
        """
        Authenticate a user as a super admin using password.

        Args:
            nick: The nickname attempting to authenticate
            password: The password to verify

        Returns:
            True if authentication succeeds, False otherwise
        """
        # Check if nick is an admin first
        if nick.lower() not in {n.strip().lower() for n in self.config.get("core", {}).get("admins", [])}:
            self.log_debug(f"[core] Super admin auth failed for {nick}: not in admin list")
            return False

        # Get password hash from config
        password_hash = self.config.get("core", {}).get("super_admin_password_hash", "")
        self.log_debug(f"[core] DEBUG: password_hash = {repr(password_hash)}, length = {len(password_hash) if password_hash else 0}")
        if not password_hash or not password_hash.strip():
            self.log_debug(f"[core] Super admin auth failed: no password hash configured")
            return False

        # Verify password
        try:
            if not bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8')):
                self.log_debug(f"[core] Super admin auth failed for {nick}: incorrect password")
                return False
        except Exception as e:
            self.log_debug(f"[core] Super admin auth failed for {nick}: bcrypt error: {e}")
            return False

        # Authentication successful - create session
        session_hours = self.config.get("core", {}).get("super_admin_session_hours", 1)
        expiry_time = time.time() + (session_hours * 3600)

        core_state = self.get_module_state("core")
        super_admin_sessions = dict(core_state.get("super_admin_sessions", {}))
        super_admin_sessions[nick.lower()] = expiry_time

        self.update_module_state("core", {"super_admin_sessions": super_admin_sessions})
        self.log_debug(f"[core] Super admin authenticated: {nick} (expires in {session_hours}h)")

        return True

    def is_user_ignored(self, username: str) -> bool:
        courtesy_module = self.pm.plugins.get("courtesy")
        if courtesy_module:
            user_id = self.get_user_id(username)
            return courtesy_module.is_user_ignored(user_id)
        return False

    # --- IRC Event Handlers ---

    def on_welcome(self, connection, event):
        self.log_debug("[core] on_welcome received, identifying and joining channels...")
        if self.nickserv_pass:
            connection.privmsg("NickServ", f"IDENTIFY {self.nickserv_pass}")

        # Set mode +B on self (server rules requirement)
        connection.mode(self.connection.get_nickname(), "+B")
        self.log_debug(f"[core] Set mode +B on {self.connection.get_nickname()}")

        loaded_modules = self.pm.load_all()
        self.log_debug(f"[core] Modules loaded: {', '.join(sorted(loaded_modules))}")

        channels_to_join = list(self.joined_channels)
        self.log_debug(f"[core] Channels to auto-join: {channels_to_join}")
        for channel in channels_to_join:
            self.log_debug(f"[core] Sending JOIN command for: {channel}")
            connection.join(channel)

        self._ensure_scheduler_thread()

    def on_join(self, connection, event):
        self.log_debug(f"[core] JOIN event: {event.source.nick} joined {event.target}")
        if event.source.nick == self.connection.get_nickname():
            self.joined_channels.add(event.target)
            self._update_joined_channels_state()
        else:
            self.get_user_id(event.source.nick)

        # Dispatch to modules that have on_join handlers
        for name, obj in self.pm.plugins.items():
            if hasattr(obj, "on_join"):
                try:
                    obj.on_join(connection, event)
                except Exception as e:
                    self.log_debug(f"[plugins] on_join error in {name}: {e}\n{traceback.format_exc()}")

    def on_part(self, connection, event):
        self.log_debug(f"[core] PART event: {event.source.nick} left {event.target}")
        if event.source.nick == self.connection.get_nickname():
            if event.target in self.joined_channels:
                self.joined_channels.remove(event.target)
                self._update_joined_channels_state()

    def on_kick(self, connection, event):
        kicked_nick = event.arguments[0]
        self.log_debug(f"[core] KICK event: {kicked_nick} was kicked from {event.target} by {event.source.nick}")
        if kicked_nick == self.connection.get_nickname():
            if event.target in self.joined_channels:
                self.joined_channels.remove(event.target)
                self._update_joined_channels_state()

    def on_nick(self, connection, event):
        old_nick, new_nick = event.source.nick, event.target
        self.log_debug(f"[core] NICK event: {old_nick} is now known as {new_nick}")
        users_module = self.pm.plugins.get("users")
        if users_module:
            users_module.on_nick(connection, event, old_nick, new_nick)

    def title_for(self, nick):
        base_title = nick
        try:
            courtesy = self.pm.plugins.get("courtesy")
            if courtesy:
                user_id = self.get_user_id(nick)
                profile = courtesy._get_user_profile(user_id)
                if profile and "title" in profile:
                    title = profile.get("title")
                    if isinstance(title, str):
                        title = title.strip().lower()
                    else:
                        title = None

                    if title == "sir":
                        base_title = "Sir"
                    elif title == "madam":
                        base_title = "Madam"
                    elif title and title != "neutral":
                        base_title = title.capitalize()
        except Exception:
            pass

        try:
            quest_module = self.pm.plugins.get("quest")
            if quest_module and hasattr(quest_module, "get_legend_suffix_for_user"):
                user_id = self.get_user_id(nick)
                suffix = quest_module.get_legend_suffix_for_user(user_id)
                if suffix and not base_title.endswith(suffix):
                    base_title = f"{base_title} {suffix}"
        except Exception:
            pass

        return base_title

    def pronouns_for(self, nick):
        try:
            courtesy = self.pm.plugins.get("courtesy")
            if courtesy:
                user_id = self.get_user_id(nick)
                profile = courtesy._get_user_profile(user_id)
                if profile and "pronouns" in profile:
                    return profile["pronouns"]
        except Exception: pass
        return "they/them"

    def on_pubmsg(self, connection, event):
        msg, username = event.arguments[0], event.source.nick
        self.log_debug(f"PUBMSG from {username} in {event.target}: {msg}")
        
        self.get_user_id(username)

        if self.is_user_ignored(username) and not msg.strip().lower().startswith("!unignore"):
            self.log_debug(f"Ignoring message from ignored user {username}")
            return

        command_handled = False
        for name, obj in self.pm.plugins.items():
            if hasattr(obj, "_dispatch_commands"):
                try:
                    if obj._dispatch_commands(connection, event, msg, username):
                        command_handled = True
                        break 
                except Exception as e:
                    self.log_debug(f"[plugins] Command error in {name}: {e}\n{traceback.format_exc()}")
        if command_handled:
            return

        for name, obj in self.pm.plugins.items():
            if hasattr(obj, "on_ambient_message"):
                try:
                    if obj.on_ambient_message(connection, event, msg, username):
                        self.log_debug(f"Ambient trigger handled by module: {name}")
                        break
                except Exception as e:
                    self.log_debug(f"[plugins] Ambient error in {name}: {e}\n{traceback.format_exc()}")
                        
    def on_privmsg(self, connection, event):
        msg, username = event.arguments[0], event.source.nick
        self.log_debug(f"PRIVMSG from {username}: {msg}")
        for name, obj in self.pm.plugins.items():
            if hasattr(obj, "on_privmsg"):
                try:
                    if obj.on_privmsg(connection, event):
                        self.log_debug(f"Private message handled by module: {name}")
                        break
                except Exception as e:
                    self.log_debug(f"[plugins] privmsg error in {name}: {e}\n{traceback.format_exc()}")

    def _ensure_scheduler_thread(self):
        def loop():
            while True:
                schedule.run_pending()
                time.sleep(1)
        t = threading.Thread(target=loop, daemon=True, name="jeeves-scheduler")
        t.start()

# --- Global State Manager Instance ---
state_manager = None

def main():
    CONFIG_DEFAULT_PATH = ROOT / "config.yaml.default"

    if not CONFIG_PATH.exists() and CONFIG_DEFAULT_PATH.exists():
        print(f"[boot] Creating default config from {CONFIG_DEFAULT_PATH}...", file=sys.stderr)
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy(CONFIG_DEFAULT_PATH, CONFIG_PATH)
        print("\n--- FIRST RUN SETUP COMPLETE ---", file=sys.stderr)
        print(f"A default configuration has been created at: {CONFIG_PATH}", file=sys.stderr)
        print("Please edit this file with your IRC server details and any necessary API keys.", file=sys.stderr)
        print("\n🔧 **Configuration Tips:**", file=sys.stderr)
        print("• Use environment variables for sensitive data: ${VARIABLE_NAME}", file=sys.stderr)
        print("• Example: api_keys.openai_api_key: ${OPENAI_API_KEY}", file=sys.stderr)
        print("• Run 'python3 config_validator.py' to validate your configuration", file=sys.stderr)
        sys.exit(0)

    global state_manager
    state_manager = StateManager(CONFIG_DIR)

    # Validate and load configuration
    print("[boot] Validating and loading configuration...", file=sys.stderr)
    config, success = load_and_validate_config(CONFIG_PATH)

    if not success:
        print("[boot] CRITICAL: Configuration validation failed. Please fix the errors above.", file=sys.stderr)
        print("Run 'python3 config_validator.py config/config.yaml' for detailed validation.", file=sys.stderr)
        sys.exit(1)

    irc_config = config.get("connection", {})
    server = irc_config.get("server", "irc.libera.chat")
    port = irc_config.get("port", 6697)
    # Support both old 'channel' and new 'main_channel' config keys
    main_channel = irc_config.get("main_channel") or irc_config.get("channel", "#bots")
    additional_channels = irc_config.get("additional_channels", [])
    nick = irc_config.get("nick", "JeevesBot")

    print("\n" + "="*40, file=sys.stderr)
    print(f"[boot] Configuration validated successfully!", file=sys.stderr)
    print(f"[boot] Preparing to connect...", file=sys.stderr)
    print(f"       Server:   {server}:{port}", file=sys.stderr)
    print(f"       Nickname: {nick}", file=sys.stderr)
    print(f"       Main Channel: {main_channel}", file=sys.stderr)
    if additional_channels:
        print(f"       Additional Channels: {', '.join(additional_channels)}", file=sys.stderr)
    print("="*40 + "\n", file=sys.stderr)

    bot = Jeeves(server, port, main_channel, nick, config=config, additional_channels=additional_channels)

    def on_exit(sig, frame):
        """Graceful shutdown handler with proper IRC disconnect and timeout."""
        bot.log_debug("[core] shutting down...")

        # Set up a timeout to force exit if graceful shutdown hangs
        def force_exit():
            bot.log_debug("[core] Shutdown timeout reached, forcing exit")
            os._exit(1)

        shutdown_timer = threading.Timer(5.0, force_exit)
        shutdown_timer.daemon = True
        shutdown_timer.start()

        try:
            # Send IRC QUIT message and close connection properly
            if bot and hasattr(bot, 'connection') and bot.connection.is_connected():
                try:
                    # Random Jeeves-appropriate quit messages
                    quit_messages = [
                        "My duties require me elsewhere, I'm afraid.",
                        "I must take my leave. Good day.",
                        "Duty calls elsewhere. I shall return.",
                        "If you'll excuse me, I have matters to attend to.",
                        "I shall return momentarily.",
                        "Pardon the interruption. I shall return shortly.",
                    ]
                    quit_msg = random.choice(quit_messages)
                    bot.log_debug(f"[core] Sending QUIT message to IRC server: {quit_msg}")
                    bot.connection.quit(quit_msg)
                    # Give the QUIT message a moment to send
                    time.sleep(0.5)
                except Exception as e:
                    bot.log_debug(f"[core] Error sending QUIT: {e}")

            # Save all state
            if state_manager:
                bot.log_debug("[core] Saving state...")
                state_manager.force_save()

            # Unload all modules
            if bot and bot.pm:
                bot.log_debug("[core] Unloading modules...")
                bot.pm.unload_all()

            bot.log_debug("[core] Shutdown complete")
            shutdown_timer.cancel()
            sys.exit(0)

        except Exception as e:
            bot.log_debug(f"[core] Error during shutdown: {e}")
            shutdown_timer.cancel()
            sys.exit(1)

    signal.signal(signal.SIGINT, on_exit)
    signal.signal(signal.SIGTERM, on_exit)

    bot.log_debug("[boot] Starting bot...")
    bot.start()

if __name__ == "__main__":
    main()
