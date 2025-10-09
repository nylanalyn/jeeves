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
from pathlib import Path
from datetime import datetime, timezone
from irc.bot import SingleServerIRCBot
from irc.connection import Factory
import schedule

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
        # User data modules
        'users': 'users',
        'weather': 'users',
        'memos': 'users',
        'profiles': 'users',
        # Stats modules
        'coffee': 'stats',
        'courtesy': 'stats',
        'leveling': 'stats',
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

        for file_type in ['state', 'games', 'users', 'stats']:
            self._states[file_type] = {}
            self._dirty[file_type] = False
            self._save_timers[file_type] = None

        self._load_all()

    def _get_path(self, file_type):
        """Get the path for a given file type."""
        return self.base_dir / f"{file_type}.json"

    def _load_all(self):
        """Load all state files."""
        for file_type in ['state', 'games', 'users', 'stats']:
            self._load_file(file_type)

    def _load_file(self, file_type):
        """Load a specific state file with backup support."""
        path = self._get_path(file_type)
        backup_path = path.with_suffix(".json.backup")

        # Create backup if file exists and is valid
        if path.exists():
            try:
                with open(path, "r") as f:
                    test_load = json.load(f)
                shutil.copy2(path, backup_path)
                print(f"[state] Created backup: {backup_path}", file=sys.stderr)
            except Exception as e:
                print(f"[state] Warning: Could not backup {file_type}.json: {e}", file=sys.stderr)

        # Try to load main file
        try:
            if path.exists():
                with open(path, "r") as f:
                    self._states[file_type] = json.load(f)
                print(f"[state] Loaded {file_type}.json", file=sys.stderr)
            else:
                self._states[file_type] = {}
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

    def _get_file_type_for_module(self, module_name):
        """Determine which file type a module should use."""
        return self.STATE_FILE_MAPPING.get(module_name, 'state')

    def get_state(self):
        """Get the entire main state (for backward compatibility)."""
        with self._locks['state']:
            return json.loads(json.dumps(self._states['state']))

    def update_state(self, updates):
        """Update the main state file (for backward compatibility)."""
        with self._locks['state']:
            self._states['state'].update(updates)
            self._mark_dirty('state')

    def get_module_state(self, name):
        """Get a module's state from the appropriate file."""
        file_type = self._get_file_type_for_module(name)
        with self._locks[file_type]:
            mods = self._states[file_type].setdefault("modules", {})
            return mods.setdefault(name, {})

    def update_module_state(self, name, updates):
        """Update a module's state in the appropriate file."""
        file_type = self._get_file_type_for_module(name)
        with self._locks[file_type]:
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
                tmp = path.with_suffix(".tmp")
                tmp.write_text(json.dumps(self._states[file_type], indent=4))
                tmp.replace(path)
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
    def __init__(self, server, port, channel, nickname, username=None, password=None, config=None):
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
        
        core_state = state_manager.get_module_state("core")
        persisted_channels = set(core_state.get("joined_channels", []))
        persisted_channels.add(self.primary_channel)
        self.joined_channels = persisted_channels

    # --- Core Bot Functions ---

    def _setup_logging(self):
        self.debug_mode = self.config.get("core", {}).get("debug_mode_on_startup", False)
        self.module_debug = {}  # Track per-module debug status
        log_file = self.config.get("core", {}).get("debug_log_file", "debug.log")

        self.logger = logging.getLogger('jeeves_debug')
        self.logger.setLevel(logging.INFO)

        handler = logging.FileHandler(ROOT / log_file, encoding='utf-8')
        formatter = logging.Formatter('%(asctime)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        handler.setFormatter(formatter)

        if (self.logger.hasHandlers()):
            self.logger.handlers.clear()

        self.logger.addHandler(handler)
        # Always write initialization message to ensure file is created
        self.logger.info(f"[core] Logging initialized. Debug mode is {'ON' if self.debug_mode else 'OFF'}.")

    def log_debug(self, message: str):
        # Extract module name from message like "[modulename] ..."
        module_match = re.match(r'^\[(\w+)\]', message)
        if module_match:
            module_name = module_match.group(1)
            # Log if global debug is on OR module-specific debug is on
            if self.debug_mode or self.module_debug.get(module_name, False):
                self.logger.info(message)
        elif self.debug_mode:
            # No module prefix, log if global debug is on
            self.logger.info(message)

    def set_debug_mode(self, status: bool):
        self.debug_mode = status
        self.log_debug(f"[core] Debug mode has been turned {'ON' if status else 'OFF'}.")

    def set_module_debug(self, module_name: str, status: bool):
        self.module_debug[module_name] = status
        self.log_debug(f"[core] Module debug for '{module_name}' has been turned {'ON' if status else 'OFF'}.")

    def core_reload_plugins(self):
        return self.pm.load_all()

    def core_reload_config(self):
        self.log_debug("[core] Reloading configuration from config.yaml...")
        try:
            self.config = load_config()
            if not self.config:
                self.log_debug("[core] ERROR: Failed to reload config.yaml")
                return False
            for name, instance in self.pm.plugins.items():
                if hasattr(instance, "on_config_reload"):
                    instance.on_config_reload(self.config.get(name, {}))
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
            admin_hostnames[user_id] = host
            self.update_module_state("courtesy", {"admin_hostnames": admin_hostnames})
            self.connection.privmsg(nick, f"For security, I have updated your registered hostname to '{host}' for this session.")
        
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
        
        loaded_modules = self.pm.load_all()
        self.log_debug(f"[core] Modules loaded: {', '.join(sorted(loaded_modules))}")

        for channel in list(self.joined_channels):
            connection.join(channel)
            
        self._ensure_scheduler_thread()

    def on_join(self, connection, event):
        self.log_debug(f"[core] JOIN event: {event.source.nick} joined {event.target}")
        if event.source.nick == self.connection.get_nickname():
            self.joined_channels.add(event.target)
            self._update_joined_channels_state()
        else:
            self.get_user_id(event.source.nick)

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
        try:
            courtesy = self.pm.plugins.get("courtesy")
            if courtesy:
                user_id = self.get_user_id(nick)
                profile = courtesy._get_user_profile(user_id)
                if profile and "title" in profile:
                    title = profile.get("title")
                    if title == "sir": return "Sir"
                    if title == "madam": return "Madam"
        except Exception:
            pass
        return nick

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
        sys.exit(0)
    
    global state_manager
    state_manager = StateManager(CONFIG_DIR)

    # Load config directly from config.yaml (not from state)
    print("[boot] Loading configuration from config.yaml...", file=sys.stderr)
    config = load_config()
    if not config:
        print("[boot] CRITICAL: config.yaml is empty or could not be read.", file=sys.stderr)
        sys.exit(1)
        
    irc_config = config.get("connection", {})
    server = irc_config.get("server", "irc.libera.chat")
    port = irc_config.get("port", 6697)
    channel = irc_config.get("channel", "#bots")
    nick = irc_config.get("nick", "JeevesBot")

    print("\n" + "="*40, file=sys.stderr)
    print(f"[boot] Preparing to connect...", file=sys.stderr)
    print(f"       Server:   {server}:{port}", file=sys.stderr)
    print(f"       Nickname: {nick}", file=sys.stderr)
    print(f"       Channel:  {channel}", file=sys.stderr)
    print("="*40 + "\n", file=sys.stderr)

    bot = Jeeves(server, port, channel, nick, config=config)
    
    def on_exit(sig, frame):
        bot.log_debug("[core] shutting down...")
        if state_manager:
            state_manager.force_save()
        if bot and bot.pm:
            bot.pm.unload_all()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, on_exit)
    signal.signal(signal.SIGTERM, on_exit)

    bot.log_debug("[boot] Starting bot...")
    bot.start()

if __name__ == "__main__":
    main()

