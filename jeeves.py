#!/usr/bin/env python3
# jeeves.py — modular IRC butler core

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

def get_admin_nicks_from_env():
    return {n.strip().lower() for n in os.getenv("JEEVES_ADMINS", "").split(",") if n.strip()}

JEEVES_NAME_RE = r"(?:jeeves|jeevesbot)"
JEEVES_MODULE_BLACKLIST = {f.strip() for f in os.getenv("JEEVES_MODULE_BLACKLIST", "").split(",") if f.strip()}


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
            if not self._dirty: return
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
        
        if JEEVES_MODULE_BLACKLIST:
            print(f"[boot] module blacklist active: {', '.join(sorted(list(JEEVES_MODULE_BLACKLIST)))}", file=sys.stderr)

        for py in sorted(MODULES_DIR.glob("*.py")):
            name = py.stem
            if name in ("__init__", "base"): continue
            
            if py.name in JEEVES_MODULE_BLACKLIST:
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
                    self.plugins[name] = instance
                    loaded_names.append(name)
            except Exception as e:
                print(f"[plugins] FAILED to load {name}: {e}", file=sys.stderr)
        
        for name, obj in self.plugins.items():
            if hasattr(obj, "on_load"): obj.on_load()
        
        return loaded_names
        
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
        self.nickserv_pass = os.getenv("JEEVES_NICKSERV_PASS", "").strip()
        self.pm = PluginManager(self)
        
        core_state = state_manager.get_state().get("core", {})
        self.joined_channels = set(core_state.get("joined_channels", [self.primary_channel]))

    def get_module_state(self, name):
        return state_manager.get_module_state(name)

    def update_module_state(self, name, updates):
        state_manager.update_module_state(name, updates)

    def reload_config_and_notify_modules(self):
        """Reloads config.yaml and tells modules to update themselves."""
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

    def _update_joined_channels_state(self):
        """Saves the current list of joined channels to the state file."""
        core_state = state_manager.get_state().get("core", {})
        core_state["joined_channels"] = list(self.joined_channels)
        state_manager.update_state({"core": core_state})

    def is_admin(self, event_source: str) -> bool:
        """Secure admin check using nick and hostname."""
        try:
            nick = event_source.split('!')[0].lower()
            host = event_source.split('@')[1]
        except IndexError:
            return False

        admin_nicks_from_env = get_admin_nicks_from_env()
        if nick not in admin_nicks_from_env:
            return False

        courtesy_state = self.get_module_state("courtesy")
        admin_hostnames = courtesy_state.get("admin_hostnames", {})

        if nick in admin_hostnames:
            return admin_hostnames[nick] == host
        else:
            print(f"[core] Registering new admin host for {nick}: {host}", file=sys.stderr)
            admin_hostnames[nick] = host
            self.update_module_state("courtesy", {"admin_hostnames": admin_hostnames})
            self.connection.privmsg(nick, f"For security, I have registered your hostname ({host}) for admin access. This is a one-time process.")
            return True

    def is_user_ignored(self, username: str) -> bool:
        """Checks if a user is on the ignore list via the courtesy module."""
        courtesy_module = self.pm.plugins.get("courtesy")
        if courtesy_module and hasattr(courtesy_module, "is_user_ignored"):
            return courtesy_module.is_user_ignored(username)
        return False

    def on_welcome(self, connection, event):
        if self.nickserv_pass:
            connection.privmsg("NickServ", f"IDENTIFY {self.nickserv_pass}")
        
        for channel in list(self.joined_channels):
            connection.join(channel)
            
        loaded_modules = self.pm.load_all()
        print(f"[core] modules loaded: {', '.join(sorted(loaded_modules))}", file=sys.stderr)
        self._ensure_scheduler_thread()

    def on_join(self, connection, event):
        if event.source.nick == self.connection.get_nickname():
            self.joined_channels.add(event.target)
            self._update_joined_channels_state()

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
        for name, obj in self.pm.plugins.items():
            if hasattr(obj, "on_nick"):
                obj.on_nick(connection, event, old_nick, new_nick)

    def title_for(self, nick):
        """
        Determines the correct title for a user.
        Returns "Sir" or "Madam" if set, otherwise defaults to the user's nickname.
        """
        try:
            courtesy = self.pm.plugins.get("courtesy")
            if courtesy and hasattr(courtesy, "_get_user_profile"):
                profile = courtesy._get_user_profile(nick)
                if profile and "title" in profile:
                    title = profile.get("title")
                    if title == "sir":
                        return "Sir"
                    if title == "madam":
                        return "Madam"
        except Exception:
            pass
        return nick # Default to the user's nickname in all other cases

    def pronouns_for(self, nick):
        """Gets a user's preferred pronouns, defaulting to 'they/them'."""
        try:
            courtesy = self.pm.plugins.get("courtesy")
            if courtesy and hasattr(courtesy, "_get_user_profile"):
                profile = courtesy._get_user_profile(nick)
                if profile and "pronouns" in profile:
                    return profile["pronouns"]
        except Exception: pass
        return "they/them"

    def on_pubmsg(self, connection, event):
        msg, username = event.arguments[0], event.source.nick

        if self.is_user_ignored(username) and not msg.strip().lower().startswith("!unignore"):
            return

        # --- Command Loop ---
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

        # --- Ambient Message Loop ---
        for name, obj in self.pm.plugins.items():
            if hasattr(obj, "on_ambient_message"):
                try:
                    if obj.on_ambient_message(connection, event, msg, username):
                        break
                except Exception as e:
                    print(f"[plugins] ambient error in {name}: {e}\n{traceback.format_exc()}", file=sys.stderr)
                        
    def on_privmsg(self, connection, event):
        """Handles private messages by dispatching them to modules."""
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
        print("\n[core] shutting down...", file=sys.stderr)
        state_manager.force_save()
        if bot and bot.pm:
            bot.pm.unload_all()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, on_exit)
    signal.signal(signal.SIGTERM, on_exit)

    bot.start()

if __name__ == "__main__":
    main()

