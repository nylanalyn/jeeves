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

# ----- State Manager & Plugin Manager -----
class StateManager:
    def __init__(self, path):
        self.path = path
        self._lock = threading.RLock()
        self._dirty = False
        self._state = {}
        self._save_timer = None
        self._load()

    def _load(self):
        try:
            if self.path.exists():
                with open(self.path, "r") as f:
                    self._state = json.load(f)
            else:
                self._state = {}
        except Exception as e:
            print(f"[state] load error: {e}", file=sys.stderr)
            self._state = {}

    def get_state(self):
        with self._lock:
            return json.loads(json.dumps(self._state))

    def update_state(self, updates):
        with self._lock:
            self._state.update(updates)
            self._mark_dirty()

    def get_module_state(self, name):
        with self._lock:
            mods = self._state.setdefault("modules", {})
            return mods.setdefault(name, {})

    def update_module_state(self, name, updates):
        with self._lock:
            mods = self._state.setdefault("modules", {})
            mod = mods.setdefault(name, {})
            mod.update(updates)
            self._mark_dirty()

    def _mark_dirty(self):
        self._dirty = True
        if self._save_timer:
            self._save_timer.cancel()
        self._save_timer = threading.Timer(1.0, self._save_now)
        self._save_timer.daemon = True
        self._save_timer.start()

    def _save_now(self):
        with self._lock:
            if not self._dirty: return
            try:
                tmp = self.path.with_suffix(".tmp")
                tmp.write_text(json.dumps(self._state, indent=4))
                tmp.replace(self.path)
                self._dirty = False
            except Exception as e:
                print(f"[state] save error: {e}", file=sys.stderr)

    def force_save(self):
        if self._save_timer:
            self._save_timer.cancel()
        self._save_now()

class PluginManager:
    def __init__(self, bot):
        self.bot = bot
        self.plugins = {}
        self.modules = {}

    def unload_all(self):
        for name, obj in self.plugins.items():
            if hasattr(obj, "on_unload"):
                try:
                    obj.on_unload()
                except Exception as e:
                    print(f"[plugins] error unloading {name}: {e}", file=sys.stderr)

    def load_all(self):
        self.unload_all()
        self.plugins = {}
        self.modules = {}
        loaded_names = []
        
        blacklist = {f.strip() for f in self.bot.config.get("core", {}).get("module_blacklist", [])}
        if blacklist:
            print(f"[boot] module blacklist active: {', '.join(sorted(list(blacklist)))}", file=sys.stderr)

        for py in sorted(ROOT.glob("modules/*.py")):
            name = py.stem
            if name in ("__init__", "base"): continue
            
            if py.name in blacklist:
                print(f"[plugins] skipping blacklisted module: {py.name}", file=sys.stderr)
                continue
                
            try:
                spec = importlib.util.spec_from_file_location(f"modules.{name}", py)
                mod = importlib.util.module_from_spec(spec)
                sys.modules[f"modules.{name}"] = mod
                spec.loader.exec_module(mod)
                if hasattr(mod, "setup"):
                    module_config = self.bot.config.get(name, {})
                    instance = mod.setup(self.bot, module_config)
                    if instance:
                        self.plugins[name] = instance
                        loaded_names.append(name)
            except Exception as e:
                print(f"[plugins] FAILED to load {name}: {e}", file=sys.stderr)
                traceback.print_exc()
        
        for name, obj in self.plugins.items():
            if hasattr(obj, "on_load"): obj.on_load()
        
        return loaded_names

# ----- Jeeves Bot -----
class Jeeves(SingleServerIRCBot):
    def __init__(self, server, port, channel, nickname, username=None, password=None, config=None):
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
        self.config = config or {}
        self.JEEVES_NAME_RE = self.config.get("core", {}).get("name_pattern", r"(?:jeeves|jeevesbot)")
        self.nickserv_pass = self.config.get("connection", {}).get("nickserv_pass", "")
        self.pm = PluginManager(self)
        
        core_state = state_manager.get_module_state("core")
        persisted_channels = set(core_state.get("joined_channels", []))
        persisted_channels.add(self.primary_channel)
        self.joined_channels = persisted_channels

    # --- Core Bot Functions ---

    def core_reload_plugins(self):
        """Core function to reload all plugins, called by the admin module."""
        return self.pm.load_all()

    def core_reload_config(self):
        """Core function to reload config, called by the admin module."""
        print("[core] Reloading configuration file...", file=sys.stderr)
        try:
            new_config = load_config()
            self.config = new_config
            for name, instance in self.pm.plugins.items():
                if hasattr(instance, "on_config_reload"):
                    module_config = self.config.get(name, {})
                    instance.on_config_reload(module_config)
            return True
        except Exception as e:
            print(f"[core] FAILED to reload configuration: {e}", file=sys.stderr)
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
            print(f"[core] Updating registered admin host for {nick} ({user_id}) to: {host}", file=sys.stderr)
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
        if self.nickserv_pass:
            connection.privmsg("NickServ", f"IDENTIFY {self.nickserv_pass}")
        
        loaded_modules = self.pm.load_all()
        print(f"[core] modules loaded: {', '.join(sorted(loaded_modules))}", file=sys.stderr)

        for channel in list(self.joined_channels):
            connection.join(channel)
            
        self._ensure_scheduler_thread()

    def on_join(self, connection, event):
        if event.source.nick == self.connection.get_nickname():
            self.joined_channels.add(event.target)
            self._update_joined_channels_state()
        else:
            self.get_user_id(event.source.nick)

    def on_part(self, connection, event):
        if event.source.nick == self.connection.get_nickname():
            if event.target in self.joined_channels:
                self.joined_channels.remove(event.target)
                self._update_joined_channels_state()

    def on_kick(self, connection, event):
        try:
            if event.target == self.connection.get_nickname():
                kicked_from_channel = event.arguments[0]
                if kicked_from_channel in self.joined_channels:
                    self.joined_channels.remove(kicked_from_channel)
                    self._update_joined_channels_state()
        except Exception:
            pass

    def on_nick(self, connection, event):
        old_nick, new_nick = event.source.nick, event.target
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
        
        self.get_user_id(username)

        if self.is_user_ignored(username) and not msg.strip().lower().startswith("!unignore"):
            return

        command_handled = False
        for name, obj in self.pm.plugins.items():
            if hasattr(obj, "_dispatch_commands"):
                try:
                    if obj._dispatch_commands(connection, event, msg, username):
                        command_handled = True
                        break 
                except Exception as e:
                    print(f"[plugins] command error in {name}: {e}\n{traceback.format_exc()}", file=sys.stderr)
        if command_handled:
            return

        for name, obj in self.pm.plugins.items():
            if hasattr(obj, "on_ambient_message"):
                try:
                    if obj.on_ambient_message(connection, event, msg, username):
                        break
                except Exception as e:
                    print(f"[plugins] ambient error in {name}: {e}\n{traceback.format_exc()}", file=sys.stderr)
                        
    def on_privmsg(self, connection, event):
        for name, obj in self.pm.plugins.items():
            if hasattr(obj, "on_privmsg"):
                try:
                    if obj.on_privmsg(connection, event):
                        break
                except Exception as e:
                    print(f"[plugins] privmsg error in {name}: {e}\n{traceback.format_exc()}", file=sys.stderr)

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
    
    config_created = False
    if not CONFIG_PATH.exists():
        print("[boot] config.yaml not found.", file=sys.stderr)
        if CONFIG_DEFAULT_PATH.exists():
            print(f"[boot] Creating default config from {CONFIG_DEFAULT_PATH}...", file=sys.stderr)
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            shutil.copy(CONFIG_DEFAULT_PATH, CONFIG_PATH)
            config_created = True
        else:
            print(f"[boot] ERROR: Default config {CONFIG_DEFAULT_PATH} not found. Cannot proceed.", file=sys.stderr)
            sys.exit(1)
            
    state_created = False
    if not STATE_PATH.exists():
        print("[boot] state.json not found. Creating empty state file...", file=sys.stderr)
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text('{}', encoding='utf-8')
        state_created = True

    if config_created or state_created:
        print("\n--- FIRST RUN SETUP COMPLETE ---", file=sys.stderr)
        print(f"A default configuration has been created at: {CONFIG_PATH}", file=sys.stderr)
        print("Please edit this file with your IRC server details and any necessary API keys.", file=sys.stderr)
        print("Jeeves will now exit.", file=sys.stderr)
        sys.exit(0)
    
    global state_manager
    state_manager = StateManager(STATE_PATH)

    config = load_config()
    
    loaded_admins = config.get("core", {}).get("admins", [])
    if loaded_admins:
        print(f"[boot] Loaded admins from config: {', '.join(loaded_admins)}", file=sys.stderr)
    else:
        print("[boot] WARNING: No admins loaded from config.yaml. Admin commands will not work.", file=sys.stderr)
        
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
        print("\n[core] shutting down...", file=sys.stderr)
        if state_manager:
            state_manager.force_save()
        if bot and bot.pm:
            bot.pm.unload_all()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, on_exit)
    signal.signal(signal.SIGTERM, on_exit)

    print("[boot] Starting bot...", file=sys.stderr)
    bot.start()

if __name__ == "__main__":
    main()

