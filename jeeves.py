#!/usr/bin/env python3
# jeeves.py — modular IRC butler core with base.py integration

import os, sys, time, json, re, ssl, signal, threading, traceback, importlib.util, base64
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
        self._plugin_stats = {}

    def get_state(self, name):
        state = state_manager.get_state()
        mods = state.setdefault("modules", {})
        return mods.setdefault(name, {})

    def update_state(self, name, updates):
        state_manager.update_module_state(name, updates)

    def load_all(self):
        """Load all modules with proper base.py support"""
        errors = []
        temp_plugins = {}
        temp_modules = {}
        
        # First, ensure base.py is loaded into the modules namespace
        try:
            base_path = MODULES_DIR / "base.py"
            if base_path.exists():
                spec = importlib.util.spec_from_file_location("modules.base", base_path)
                base_module = importlib.util.module_from_spec(spec)
                sys.modules["modules.base"] = base_module  # Make it importable
                spec.loader.exec_module(base_module)
                print("[plugins] loaded base module", file=sys.stderr)
            else:
                print("[plugins] warning: base.py not found", file=sys.stderr)
        except Exception as e:
            errors.append(f"[plugins] failed to load base.py: {e}")
            print(f"[plugins] failed to load base.py: {e}", file=sys.stderr)

        # Get all module files
        remaining_files = [p for p in MODULES_DIR.glob("*.py") 
                          if p.name not in ("__init__.py", "base.py")]

        # Load modules with dependency resolution (simple retry loop)
        for attempt in range(10):
            made_progress = False
            
            for py in list(remaining_files):
                name = py.stem
                try:
                    spec = importlib.util.spec_from_file_location(f"modules.{name}", py)
                    mod = importlib.util.module_from_spec(spec)
                    
                    # Add to sys.modules so imports work
                    sys.modules[f"modules.{name}"] = mod
                    spec.loader.exec_module(mod)

                    # Skip helpers or any module without setup(bot)
                    if not hasattr(mod, "setup"):
                        remaining_files.remove(py)
                        made_progress = True
                        continue

                    # Try to instantiate the module
                    instance = mod.setup(self.bot)
                    temp_plugins[name] = instance
                    temp_modules[name] = mod
                    made_progress = True
                    remaining_files.remove(py)

                except ImportError as e:
                    # Dependency not ready yet, try again later
                    if attempt < 5:  # Only show import errors after a few attempts
                        continue
                    errors.append(f"[plugins] import error in {py.name}: {e}")
                except Exception as e:
                    errors.append(f"[plugins] failed to load {py.name}: {e}")
                    remaining_files.remove(py)  # Don't retry non-import errors
                    made_progress = True

            if not made_progress:
                break

        # Report any remaining errors
        if errors:
            for err in errors:
                print(err, file=sys.stderr)

        # Clean shutdown of old plugins
        self.unload_all()
        
        # Install new plugins
        self.modules = temp_modules
        self.plugins = temp_plugins

        # Initialize plugin stats
        for name in self.plugins:
            self._plugin_stats[name] = {
                "calls": 0, 
                "total_time": 0.0, 
                "errors": 0, 
                "last_error": None
            }

        # Call on_load for all plugins
        for name, obj in self.plugins.items():
            try:
                if hasattr(obj, "on_load"):
                    obj.on_load()
            except Exception as e:
                print(f"[plugins] on_load error in {name}: {e}", file=sys.stderr)

        print(f"[plugins] loaded: {', '.join(sorted(self.plugins.keys()))}", file=sys.stderr)
        return len(errors) == 0

    def unload_all(self):
        """Properly unload all plugins"""
        for name, obj in list(self.plugins.items()):
            try:
                if hasattr(obj, "on_unload"):
                    obj.on_unload()
            except Exception as e:
                print(f"[plugins] on_unload error in {name}: {e}", file=sys.stderr)
        
        self.plugins.clear()
        self.modules.clear()

# ----- Connection Manager -----
class ConnectionManager:
    def __init__(self, bot):
        self.bot = bot
        self._last_pong = time.time()
        self._hb = None

    def start(self):
        if self._hb:
            try:
                self._hb.cancel()
            except Exception:
                pass
        self._hb = threading.Timer(60.0, self._tick)
        self._hb.daemon = True
        self._hb.start()

    def _tick(self):
        try:
            now = time.time()
            if now - self._last_pong > 120:
                try:
                    self.bot.connection.ping(self.bot.server)
                except Exception:
                    pass
        finally:
            self.start()

    def mark_pong(self):
        self._last_pong = time.time()

# ----- Jeeves Bot -----
class Jeeves(SingleServerIRCBot):
    def __init__(self, server, port, channel, nickname, username=None, password=None):
        ssl_factory = Factory(wrapper=ssl.wrap_socket)
        super().__init__([(server, port)], nickname, nickname, connect_factory=ssl_factory)

        self.server = server
        self.port = port
        self.primary_channel = channel
        self.nickname = nickname

        # Store the name pattern for modules to use
        self.JEEVES_NAME_RE = JEEVES_NAME_RE

        env_user = os.getenv("JEEVES_USER", "").strip()
        env_pass = os.getenv("JEEVES_PASS", "").strip()
        self.sasl_user = (username or env_user).strip()
        self.sasl_pass = (password or env_pass).strip()
        self.nickserv_pass = os.getenv("JEEVES_NICKSERV_PASS", "").strip()
        self.auth_debug = os.getenv("JEEVES_AUTH_DEBUG", "0").lower() in ("1","true","yes","on")

        self._sasl_try = bool(self.sasl_user and self.sasl_pass)
        self._sasl_done = False

        self.pm = PluginManager(self)
        self.conn_manager = ConnectionManager(self)

        chans_env = os.getenv("JEEVES_CHANNELS", "").strip()
        self.start_channels = {channel} if not chans_env else {c.strip() for c in chans_env.split(",") if c.strip()}
        self.joined_channels = set()

        self.conn_manager.start()

    def get_state(self):
        return state_manager.get_state()

    def get_module_state(self, name):
        return state_manager.get_module_state(name)

    def update_module_state(self, name, updates):
        return state_manager.update_module_state(name, updates)

    def save(self):
        state_manager._mark_dirty()

    def is_admin(self, nick):
        return nick.lower() in get_admin_nicks()

    def title_for(self, nick):
        """Get proper title for user (integrates with courtesy module)"""
        try:
            # Try to get from courtesy module if loaded
            courtesy = self.pm.plugins.get("courtesy")
            if courtesy and hasattr(courtesy, "_get_user_profile"):
                profile = courtesy._get_user_profile(nick)
                if profile and "title" in profile:
                    title = profile["title"]
                    return {"sir":"Sir","madam":"Madam","neutral":"Mx."}.get(title, "Mx.")
        except Exception:
            pass
        
        # Fallback to legacy state-based lookup
        profiles = state_manager.get_module_state("courtesy")
        profs = profiles.get("profiles", {})
        p = profs.get(nick.lower(), {})
        title = p.get("title", "neutral")
        return {"sir":"Sir","madam":"Madam"}.get(title, "Mx.")

    def pronouns_for(self, nick):
        """Get pronouns for user (integrates with courtesy module)"""
        try:
            # Try to get from courtesy module if loaded
            courtesy = self.pm.plugins.get("courtesy")
            if courtesy and hasattr(courtesy, "_get_user_profile"):
                profile = courtesy._get_user_profile(nick)
                if profile and "pronouns" in profile:
                    return profile["pronouns"]
        except Exception:
            pass
        
        # Fallback to legacy state-based lookup
        profiles = state_manager.get_module_state("courtesy")
        profs = profiles.get("profiles", {})
        p = profs.get(nick.lower(), {})
        return p.get("pronouns", "they/them")

    def say(self, text):
        try:
            self.connection.privmsg(self.primary_channel, text)
        except Exception as e:
            print(f"[say] error: {e}", file=sys.stderr)

    def say_to(self, target, text):
        try:
            self.connection.privmsg(target, text)
        except Exception as e:
            print(f"[say_to] error: {e}", file=sys.stderr)

    def privmsg(self, nick, text):
        try:
            self.connection.privmsg(nick, text)
        except Exception as e:
            print(f"[privmsg] error: {e}", file=sys.stderr)

    # ----- IRC Events -----
    def on_connect(self, connection, event):
        print("[core] connected", file=sys.stderr)

    def on_disconnect(self, connection, event):
        print("[core] disconnected", file=sys.stderr)

    def on_cap(self, connection, event):
        if event.arguments and event.arguments[0] == "LS":
            if self._sasl_try:
                self._cap_req_sasl()
            else:
                connection.send_raw("CAP END")

    def on_authenticate(self, connection, event):
        if self._sasl_try and not self._sasl_done:
            self._send_sasl_plain()

    def on_welcome(self, connection, event):
        try:
            connection.send_raw("CAP END")
        except Exception:
            pass
        if self.auth_debug:
            threading.Timer(5.0, self._whois_self).start()
        if not self._sasl_try and self.nickserv_pass:
            threading.Timer(2.0, self._maybe_identify_nickserv).start()
        for room in sorted(self.start_channels):
            try:
                connection.join(room)
            except Exception as e:
                print(f"[join] failed: {e}", file=sys.stderr)
        try:
            for room in self.start_channels:
                connection.mode(room, "+B")
        except Exception:
            pass
        self.pm.load_all()
        self._ensure_scheduler_thread()

    def on_join(self, connection, event):
        room = event.target
        nick = event.source.split('!')[0]
        if nick == self.nickname:
            self.joined_channels.add(room)

    def on_nick(self, connection, event):
        """Enhanced nick change handler that works with base.py modules"""
        try:
            old_nick = (event.source or "").split("!", 1)[0]
        except Exception:
            old_nick = ""
        
        new_nick = ""
        try:
            if getattr(event, "arguments", None):
                new_nick = event.arguments[0] or ""
        except Exception:
            pass
        if not new_nick:
            new_nick = getattr(event, "target", "") or ""
        
        if not old_nick or not new_nick or old_nick == new_nick:
            return
        
        # Call on_nick for all plugins with proper error handling
        for name, obj in list(self.pm.plugins.items()):
            try:
                start_time = time.time()
                
                if hasattr(obj, "on_nick"):
                    obj.on_nick(connection, event, old_nick, new_nick)
                
                # Update performance stats for base.py modules
                if hasattr(obj, "_update_performance_stats"):
                    response_time = time.time() - start_time
                    obj._update_performance_stats(response_time)
                    
            except Exception as e:
                print(f"[plugins] on_nick error in {name}: {e}", file=sys.stderr)
                
                # Record error for base.py modules
                if hasattr(obj, "_record_error"):
                    obj._record_error(f"on_nick error: {e}")

    def on_part(self, connection, event):
        room = event.target
        nick = event.source.split('!')[0]
        if nick == self.nickname:
            self.joined_channels.discard(room)

    def on_pong(self, connection, event):
        self.conn_manager.mark_pong()

    def on_privmsg(self, connection, event):
        """Handle private messages."""
        msg = event.arguments[0] if event.arguments else ""
        username = event.source.split('!')[0]

        # Process through all plugins
        for name, obj in list(self.pm.plugins.items()):
            try:
                start = time.time()
                handled = False
                
                # Call the private message handler if it exists
                if hasattr(obj, "on_privmsg"):
                    result = obj.on_privmsg(connection, event)
                    if result:
                        handled = True
                        break  # Stop after first handler claims it
                
                # Update performance tracking for base.py modules
                if hasattr(obj, "_update_performance_stats"):
                    response_time = time.time() - start
                    obj._update_performance_stats(response_time)
                    
            except Exception as e:
                # Record error for base.py modules
                if hasattr(obj, "_record_error"):
                    obj._record_error(f"on_privmsg error: {e}")
                
                print(f"[plugins] {name} privmsg error: {e}", file=sys.stderr)

    def on_pubmsg(self, connection, event):
        """Enhanced message handler that works with base.py modules"""
        room = event.target
        msg = event.arguments[0] if event.arguments else ""
        username = event.source.split('!')[0]

        # Admin reload command
        if self.is_admin(username) and msg.strip().lower() == "!reload":
            ok = self.pm.load_all()
            connection.privmsg(room, "Reloaded." if ok else "Reload had errors; check logs.")
            return

        # Process through all plugins
        for name, obj in list(self.pm.plugins.items()):
            try:
                start = time.time()
                handled = False
                
                # Call the appropriate method based on what the plugin supports
                if hasattr(obj, "on_pubmsg"):
                    result = obj.on_pubmsg(connection, event, msg, username)
                    if result:
                        handled = True
                
                # Update performance tracking
                dur = time.time() - start
                stats = self.pm._plugin_stats.get(name, {})
                stats["calls"] = stats.get("calls", 0) + 1
                stats["total_time"] = stats.get("total_time", 0.0) + dur
                
                # Also update base.py module stats if applicable
                if hasattr(obj, "_update_performance_stats"):
                    obj._update_performance_stats(dur)
                if hasattr(obj, "_call_stats") and handled:
                    obj._call_stats["commands_executed"] += 1
                    
            except Exception as e:
                # Update error stats
                stats = self.pm._plugin_stats.get(name, {})
                stats["errors"] = stats.get("errors", 0) + 1
                stats["last_error"] = str(e)
                
                # Also record in base.py module if applicable
                if hasattr(obj, "_record_error"):
                    obj._record_error(str(e))
                
                print(f"[plugins] {name} error: {e}\n{traceback.format_exc()}", file=sys.stderr)

    # ----- Auth Helpers -----
    def _cap_req_sasl(self):
        self.connection.send_raw("CAP REQ :sasl")

    def _send_sasl_plain(self):
        try:
            msg = f"{self.nickname}\0{self.sasl_user}\0{self.sasl_pass}".encode("utf-8")
            b64 = base64.b64encode(msg).decode("ascii")
            self.connection.send_raw("AUTHENTICATE PLAIN")
            self.connection.send_raw("AUTHENTICATE " + b64)
        except Exception as e:
            print(f"[sasl] error: {e}", file=sys.stderr)

    def _maybe_identify_nickserv(self):
        try:
            if self.nickserv_pass:
                self.connection.privmsg("NickServ", f"IDENTIFY {self.nickserv_pass}")
        except Exception as e:
            print(f"[nickserv] identify error: {e}", file=sys.stderr)

    def _whois_self(self):
        try:
            self.connection.whois([self.nickname])
        except Exception:
            pass

    def _ensure_scheduler_thread(self):
        def loop():
            while True:
                try:
                    schedule.run_pending()
                except Exception as e:
                    print(f"[schedule] error: {e}", file=sys.stderr)
                time.sleep(1)
        t = threading.Thread(target=loop, daemon=True, name="jeeves-scheduler")
        t.start()
# ----- CLI -----
def main():
    server = os.getenv("JEEVES_SERVER", "irc.libera.chat").strip()
    port = int(os.getenv("JEEVES_PORT", "6697").strip())
    channel = os.getenv("JEEVES_CHANNEL", "#bots").strip()
    nick = os.getenv("JEEVES_NICK", "JeevesBot").strip()
    user = os.getenv("JEEVES_USER", "").strip() or None
    passwd = os.getenv("JEEVES_PASS", "").strip() or None

    retry_count = 0
    max_retries = 10

    while True:
        try:
            bot = Jeeves(server, port, channel, nick, user, passwd)
            bot.start()
        except KeyboardInterrupt:
            print("[core] interrupted", file=sys.stderr)
            break
        except Exception as e:
            retry_count += 1
            print(f"[core] crash: {e}\n{traceback.format_exc()}", file=sys.stderr)
            if retry_count >= max_retries:
                print(f"[core] max retries exceeded", file=sys.stderr)
                break
            backoff = min(300, 5 * (2 ** retry_count))
            print(f"[core] retrying in {backoff} seconds", file=sys.stderr)
            time.sleep(backoff)

    state_manager.force_save()

if __name__ == "__main__":
    main()
