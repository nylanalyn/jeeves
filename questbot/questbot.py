#!/usr/bin/env python3
# questbot.py — dedicated IRC quest game bot

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
import functools
import logging
from pathlib import Path
from datetime import datetime, timezone
from irc.bot import SingleServerIRCBot
from irc.connection import Factory
import schedule

# Add parent directory to path so we can import from modules
PARENT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PARENT_DIR))

UTC = timezone.utc
ROOT = Path(__file__).resolve().parent

# --- Path Configuration ---
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

# ----- Simplified State Manager (Quest Only) -----
class QuestStateManager:
    """Simplified state manager for quest bot - only manages games.json"""

    def __init__(self, base_dir):
        self.base_dir = Path(base_dir)
        self.games_path = self.base_dir / "games.json"
        self._lock = threading.RLock()
        self._state = {'modules': {}}
        self._dirty = False
        self._save_timer = None
        self._load()

    def _load(self):
        """Load games.json"""
        if self.games_path.exists():
            try:
                with open(self.games_path, 'r') as f:
                    self._state = json.load(f)
                print(f"[state] Loaded {self.games_path}")
            except Exception as e:
                print(f"[state] Error loading {self.games_path}: {e}", file=sys.stderr)
                self._state = {'modules': {}}

    def _schedule_save(self):
        """Schedule a save operation with 1 second debounce"""
        with self._lock:
            if self._save_timer:
                self._save_timer.cancel()
            self._save_timer = threading.Timer(1.0, self._save_now)
            self._save_timer.start()

    def _save_now(self):
        """Immediately save state to disk"""
        with self._lock:
            if not self._dirty:
                return
            try:
                self.games_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.games_path, 'w') as f:
                    json.dump(self._state, f, indent=2)
                self._dirty = False
                print(f"[state] Saved {self.games_path}")
            except Exception as e:
                print(f"[state] Error saving {self.games_path}: {e}", file=sys.stderr)
                traceback.print_exc()

    def get_state(self):
        """Get full state snapshot"""
        with self._lock:
            return self._state.copy()

    def update_state(self, updates):
        """Update top-level state"""
        with self._lock:
            self._state.update(updates)
            self._dirty = True
            self._schedule_save()

    def get_module_state(self, module_name):
        """Get state for a specific module"""
        with self._lock:
            return self._state.get('modules', {}).get(module_name, {})

    def update_module_state(self, module_name, updates):
        """Update module-specific state"""
        with self._lock:
            if 'modules' not in self._state:
                self._state['modules'] = {}
            if module_name not in self._state['modules']:
                self._state['modules'][module_name] = {}
            self._state['modules'][module_name].update(updates)
            self._dirty = True
            self._schedule_save()

    def force_save(self):
        """Force immediate save"""
        with self._lock:
            if self._save_timer:
                self._save_timer.cancel()
                self._save_timer = None
            self._save_now()

# ----- Simple Plugin Manager -----
class QuestPluginManager:
    """Simplified plugin manager - only loads quest module"""

    def __init__(self, bot):
        self.bot = bot
        self.plugins = {}
        self.module_dir = PARENT_DIR / "modules"

    def load_module(self, module_name):
        """Load a single module"""
        module_path = self.module_dir / f"{module_name}.py"
        if not module_path.exists():
            print(f"[plugins] Module not found: {module_path}")
            return False

        try:
            spec = importlib.util.spec_from_file_location(module_name, module_path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            if hasattr(module, "setup"):
                instance = module.setup(self.bot)
                if instance:
                    self.plugins[module_name] = instance
                    if hasattr(instance, "on_load"):
                        instance.on_load()
                    print(f"[plugins] Loaded: {module_name}")
                    return True
            else:
                print(f"[plugins] No setup() in {module_name}")
                return False
        except Exception as e:
            print(f"[plugins] Error loading {module_name}: {e}")
            traceback.print_exc()
            return False

    def unload_all(self):
        """Unload all modules"""
        for name, obj in list(self.plugins.items()):
            try:
                if hasattr(obj, "on_unload"):
                    obj.on_unload()
            except Exception as e:
                print(f"[plugins] Error unloading {name}: {e}")
        self.plugins.clear()

# ----- QuestBot Class -----
class QuestBot(SingleServerIRCBot):
    """Dedicated IRC bot for quest module only"""

    def __init__(self, config, state_manager):
        self.config = config
        self.state_manager = state_manager

        server = config['connection']['server']
        port = config['connection']['port']
        nickname = config['connection']['nickname']
        use_ssl = config['connection'].get('use_ssl', True)

        if use_ssl:
            factory = Factory(wrapper=ssl.wrap_socket)
        else:
            factory = Factory()

        SingleServerIRCBot.__init__(self, [(server, port)], nickname, nickname, connect_factory=factory)

        self.pm = QuestPluginManager(self)
        self._debug = False
        self._user_mapping = {}  # Simple user ID mapping

        # Register shutdown handler
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        print("\n[questbot] Shutting down...")
        self.pm.unload_all()
        self.state_manager.force_save()
        self.die("QuestBot shutting down")
        sys.exit(0)

    def log_debug(self, msg):
        """Debug logging"""
        if self._debug:
            timestamp = datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')
            print(f"[{timestamp}] {msg}")

    def get_user_id(self, nickname):
        """Simple user ID mapping (just uses nickname)"""
        if nickname not in self._user_mapping:
            self._user_mapping[nickname] = nickname.lower()
        return self._user_mapping[nickname]

    def title_for(self, nick):
        """Get title for user (checks quest module for legend suffix)"""
        base_title = nick
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

    def is_admin(self, hostmask):
        """Check if user is admin"""
        admins = self.config.get('core', {}).get('admins', [])
        for admin in admins:
            if admin['nick'] == hostmask.nick and admin['host'] == hostmask.host:
                return True
        return False

    def on_welcome(self, connection, event):
        """Called when bot connects to server"""
        print(f"[questbot] Connected to {self.config['connection']['server']}")

        # Identify with NickServ if configured
        nickserv_pass = self.config.get('connection', {}).get('nickserv_pass')
        if nickserv_pass:
            connection.privmsg("NickServ", f"IDENTIFY {nickserv_pass}")
            time.sleep(2)

        # Join channels
        channels = self.config.get('connection', {}).get('channels', [])
        for channel in channels:
            connection.join(channel)
            print(f"[questbot] Joined {channel}")

        # Load quest module
        if self.pm.load_module("quest"):
            print("[questbot] Quest module loaded successfully")
        else:
            print("[questbot] ERROR: Failed to load quest module!")

        # Start scheduler thread
        self._ensure_scheduler_thread()

    def on_pubmsg(self, connection, event):
        """Handle public messages"""
        msg, username = event.arguments[0], event.source.nick
        self.log_debug(f"PUBMSG from {username} in {event.target}: {msg}")

        self.get_user_id(username)

        # Try command phase
        command_handled = False
        quest_module = self.pm.plugins.get("quest")
        if quest_module and hasattr(quest_module, "_dispatch_commands"):
            try:
                if quest_module._dispatch_commands(connection, event, msg, username):
                    command_handled = True
            except Exception as e:
                self.log_debug(f"[quest] Command error: {e}\n{traceback.format_exc()}")

        if command_handled:
            return

        # Try ambient phase
        if quest_module and hasattr(quest_module, "on_ambient_message"):
            try:
                quest_module.on_ambient_message(connection, event, msg, username)
            except Exception as e:
                self.log_debug(f"[quest] Ambient error: {e}\n{traceback.format_exc()}")

    def on_privmsg(self, connection, event):
        """Handle private messages"""
        msg, username = event.arguments[0], event.source.nick
        self.log_debug(f"PRIVMSG from {username}: {msg}")

        quest_module = self.pm.plugins.get("quest")
        if quest_module and hasattr(quest_module, "on_privmsg"):
            try:
                quest_module.on_privmsg(connection, event)
            except Exception as e:
                self.log_debug(f"[quest] privmsg error: {e}\n{traceback.format_exc()}")

    def _ensure_scheduler_thread(self):
        """Start background scheduler thread"""
        def loop():
            while True:
                schedule.run_pending()
                time.sleep(1)
        t = threading.Thread(target=loop, daemon=True, name="questbot-scheduler")
        t.start()

# ----- Main Entry Point -----
def main():
    CONFIG_DEFAULT_PATH = ROOT / "config.yaml.default"

    if not CONFIG_PATH.exists() and CONFIG_DEFAULT_PATH.exists():
        print(f"[boot] Creating default config from {CONFIG_DEFAULT_PATH}...")
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_DEFAULT_PATH, 'r') as src:
            with open(CONFIG_PATH, 'w') as dst:
                dst.write(src.read())
        print(f"[boot] Please edit {CONFIG_PATH} and run again.")
        return

    config = load_config()
    if not config:
        print("[boot] Failed to load config", file=sys.stderr)
        return

    state_manager = QuestStateManager(CONFIG_DIR)
    bot = QuestBot(config, state_manager)

    print("[questbot] Starting QuestBot...")
    try:
        bot.start()
    except KeyboardInterrupt:
        print("\n[questbot] Interrupted by user")
    finally:
        bot.pm.unload_all()
        state_manager.force_save()

if __name__ == "__main__":
    main()
