#!/usr/bin/env python3
# jeeves.py — modular IRC butler core with base.py integration

import os, sys, time, json, re, ssl, signal, threading, traceback, importlib.util, base64, yaml
from pathlib import Path
from datetime import datetime, timezone
from irc.bot import SingleServerIRCBot
from irc.connection import Factory
import schedule

UTC = timezone.utc
ROOT = Path(__file__).resolve().parent

CONFIG_DIR = Path.home() / ".config" / "jeeves"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
STATE_PATH = CONFIG_DIR / "state.json"
CONFIG_PATH = ROOT / "config.yaml"

def load_config():
    """Loads the YAML configuration file."""
    if not CONFIG_PATH.exists():
        print(f"[boot] warning: config.yaml not found, using default values.", file=sys.stderr)
        return {}
    try:
        with open(CONFIG_PATH, 'r') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"[boot] error loading config.yaml: {e}", file=sys.stderr)
        return {}

def load_env_files():
    env_files = [
        CONFIG_DIR / "jeeves.env",
        ROOT / "jeeves.env",
        ROOT / ".env",
    ]
    for env_file in env_files:
        if env_file.exists():
            print(f"[boot] loading environment from {env_file}", file=sys.stderr)
            try:
                with open(env_file) as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            key, value = line.split('=', 1)
                            if key not in os.environ:
                                os.environ[key] = value
            except Exception as e:
                print(f"[boot] error loading {env_file}: {e}", file=sys.stderr)
            break
    else:
        print(f"[boot] no environment file found", file=sys.stderr)

load_env_files()

MODULES_DIR = ROOT / "modules"
MODULES_DIR.mkdir(exist_ok=True)

def get_admin_nicks():
    return {n.strip().lower() for n in os.getenv("JEEVES_ADMINS", "").split(",") if n.strip()}

JEEVES_NAME_RE = r"(?:jeeves|jeevesbot)"

# ----- State Manager -----
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
            if not self._dirty:
                return
            try:
                tmp = self.path.with_suffix(".tmp")
                tmp.write_text(json.dumps(self._state, indent=2, sort_keys=True))
                tmp.replace(self.path)
                self._dirty = False
            except Exception as e:
                print(f"[state] save error: {e}", file=sys.stderr)

    def force_save(self):
        if self._save_timer:
            self._save_timer.cancel()
        self._save_now()

state_manager = StateManager(STATE_PATH)

# ----- Plugin Manager -----
class PluginManager:
    def __init__(self, bot):
        self.bot = bot
        self.plugins = {}
        self.modules = {}

    def load_all(self):
        """Load all modules"""
        for py in sorted(MODULES_DIR.glob("*.py")):
            name = py.stem
            if name == "__init__":
                continue
            try:
                spec = importlib.util.spec_from_file_location(f"modules.{name}", py)
                mod = importlib.util.module_from_spec(spec)
                sys.modules[f"modules.{name}"] = mod
                spec.loader.exec_module(mod)

                if not hasattr(mod, "setup"):
                    continue

                module_config = self.bot.config.get(name, {})
                instance = mod.setup(self.bot, module_config)
                self.plugins[name] = instance

            except Exception as e:
                print(f"[plugins] FAILED to load {name}: {e}", file=sys.stderr)
                print(traceback.format_exc(), file=sys.stderr)

        for name, obj in self.plugins.items():
            if hasattr(obj, "on_load"):
                obj.on_load()
        
# ----- Jeeves Bot -----
class Jeeves(SingleServerIRCBot):
    def __init__(self, server, port, channel, nickname, username=None, password=None, config=None):
        ssl_factory = Factory(wrapper=ssl.wrap_socket)
        super().__init__([(server, port)], nickname, nickname, connect_factory=ssl_factory)

        self.server = server
        self.port = port
        self.primary_channel = channel
        self.nickname = nickname
        self.config = config or {}
        self.JEEVES_NAME_RE = JEEVES_NAME_RE

        env_user = os.getenv("JEEVES_USER", "").strip()
        env_pass = os.getenv("JEEVES_PASS", "").strip()
        self.sasl_user = (username or env_user).strip()
        self.sasl_pass = (password or env_pass).strip()
        self.nickserv_pass = os.getenv("JEEVES_NICKSERV_PASS", "").strip()
        
        self.pm = PluginManager(self)
        self.joined_channels = set()

    def get_module_state(self, name):
        return state_manager.get_module_state(name)

    def update_module_state(self, name, updates):
        state_manager.update_module_state(name, updates)

    def is_admin(self, nick):
        return nick.lower() in get_admin_nicks()

    def is_ignored(self, username: str) -> bool:
        """Checks if a user is on the ignore list via the courtesy module."""
        try:
            courtesy = self.pm.plugins.get("courtesy")
            if courtesy and hasattr(courtesy, "is_user_ignored"):
                return courtesy.is_user_ignored(username)
        except Exception as e:
            print(f"[core] Error checking ignore status for {username}: {e}", file=sys.stderr)
        return False

    def title_for(self, nick):
        try:
            courtesy = self.pm.plugins.get("courtesy")
            if courtesy and hasattr(courtesy, "_get_user_profile"):
                profile = courtesy._get_user_profile(nick)
                if profile and "title" in profile:
                    return {"sir":"Sir","madam":"Madam","neutral":"Mx."}.get(profile["title"], "Mx.")
        except Exception:
            pass
        return "Mx."

    def pronouns_for(self, nick):
        try:
            courtesy = self.pm.plugins.get("courtesy")
            if courtesy and hasattr(courtesy, "_get_user_profile"):
                profile = courtesy._get_user_profile(nick)
                if profile and "pronouns" in profile:
                    return profile["pronouns"]
        except Exception:
            pass
        return "they/them"

    def on_welcome(self, connection, event):
        if self.nickserv_pass:
            connection.privmsg("NickServ", f"IDENTIFY {self.nickserv_pass}")
        connection.join(self.primary_channel)
        self.pm.load_all()
        self._ensure_scheduler_thread()

    def on_join(self, connection, event):
        if event.source.nick == self.connection.get_nickname():
            self.joined_channels.add(event.target)

    def on_nick(self, connection, event):
        old_nick = event.source.nick
        new_nick = event.target
        for name, obj in self.pm.plugins.items():
            if hasattr(obj, "on_nick"):
                obj.on_nick(connection, event, old_nick, new_nick)

    def on_pubmsg(self, connection, event):
        msg = event.arguments[0]
        username = event.source.nick
        
        # Global ignore check
        if not msg.strip().lower().startswith("!unignore") and self.is_ignored(username):
            return

        if self.is_admin(username) and msg.strip().lower() == "!reload":
            self.pm.load_all()
            connection.privmsg(event.target, "Reloaded.")
            return

        for name, obj in self.pm.plugins.items():
            if hasattr(obj, "on_pubmsg"):
                try:
                    if obj.on_pubmsg(connection, event, msg, username):
                        break
                except Exception as e:
                    print(f"[plugins] {name} error: {e}\n{traceback.format_exc()}", file=sys.stderr)
                    if hasattr(obj, "_record_error"):
                        obj._record_error(str(e))
                        
    def _ensure_scheduler_thread(self):
        def loop():
            while True:
                schedule.run_pending()
                time.sleep(1)
        t = threading.Thread(target=loop, daemon=True, name="jeeves-scheduler")
        t.start()

def main():
    server = os.getenv("JEEVES_SERVER", "irc.libera.chat").strip()
    port = int(os.getenv("JEEVES_PORT", "6697").strip())
    channel = os.getenv("JEEVES_CHANNEL", "#bots").strip()
    nick = os.getenv("JEEVES_NICK", "JeevesBot").strip()
    user = os.getenv("JEEVES_USER", "").strip() or None
    passwd = os.getenv("JEEVES_PASS", "").strip() or None

    config = load_config()
    bot = Jeeves(server, port, channel, nick, user, passwd, config=config)
    
    def on_exit(sig, frame):
        state_manager.force_save()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, on_exit)
    signal.signal(signal.SIGTERM, on_exit)

    bot.start()

if __name__ == "__main__":
    main()