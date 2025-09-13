#!/usr/bin/env python3
# jeeves.py — optimized modular IRC butler core

import os, sys, time, json, re, ssl, signal, threading, traceback, importlib.util, base64
from pathlib import Path
from datetime import datetime, timezone
from irc.bot import SingleServerIRCBot
from irc.connection import Factory
import schedule

# ---------- constants & paths ----------
UTC = timezone.utc
ROOT = Path(__file__).resolve().parent

# Use XDG config directory for state storage
CONFIG_DIR = Path.home() / ".config" / "jeeves"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
STATE_PATH = CONFIG_DIR / "state.json"

# Load environment variables from config directory first, then local
def load_env_files():
    """Load environment files from config directory first, then local directory."""
    env_files = [
        CONFIG_DIR / "jeeves.env",  # ~/.config/jeeves/jeeves.env
        ROOT / "jeeves.env",        # ./jeeves.env (fallback)
        ROOT / ".env"               # ./.env (fallback)
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
                            # Only set if not already in environment
                            if key not in os.environ:
                                os.environ[key] = value
            except Exception as e:
                print(f"[boot] error loading {env_file}: {e}", file=sys.stderr)
            break  # Use first found file
    else:
        print(f"[boot] no environment file found in {[str(f) for f in env_files]}", file=sys.stderr)

# Load environment variables early
load_env_files()

# Modules still relative to script location
MODULES_DIR = ROOT / "modules"
MODULES_DIR.mkdir(exist_ok=True)

# Admin list - now supports environment variable updates without restart
def get_admin_nicks():
    return {n.strip().lower() for n in os.getenv("JEEVES_ADMINS", "").split(",") if n.strip()}

JEEVES_NAME_RE = r"(?:jeeves|jeevesbot)"

# ---------- optimized state i/o ----------
class StateManager:
    """Thread-safe state management with atomic writes and batching."""
    
    def __init__(self, path):
        self.path = path
        self._lock = threading.RLock()
        self._dirty = False
        self._save_timer = None
        self._state = self._load()
    
    def _load(self):
        if self.path.exists():
            try:
                return json.loads(self.path.read_text())
            except Exception as e:
                print(f"[state] could not parse {self.path}: {e}", file=sys.stderr)
        return {"modules": {}, "profiles": {}}
    
    def get_state(self):
        with self._lock:
            return self._state.copy()
    
    def update_state(self, updates):
        """Update state with a dict of changes."""
        with self._lock:
            self._state.update(updates)
            self._mark_dirty()
    
    def _mark_dirty(self):
        self._dirty = True
        if self._save_timer:
            self._save_timer.cancel()
        # Batch saves - only save after 1 second of no changes
        self._save_timer = threading.Timer(1.0, self._save_now)
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
        """Immediate save, useful for shutdown."""
        if self._save_timer:
            self._save_timer.cancel()
        self._save_now()

# Global state manager
state_manager = StateManager(STATE_PATH)

# ---------- enhanced plugin manager ----------
class PluginManager:
    def __init__(self, bot):
        self.bot = bot
        self.plugins = {}
        self.modules = {}
        self._plugin_stats = {}  # Track performance stats

    def get_state(self, name):
        state = state_manager.get_state()
        return state.setdefault("modules", {}).setdefault(name, {})

    def update_module_state(self, name, updates):
        """Efficient state updates without full dict copy."""
        state = state_manager.get_state()
        mod_state = state.setdefault("modules", {}).setdefault(name, {})
        mod_state.update(updates)
        state_manager.update_state({"modules": state["modules"]})

    def _import_file(self, path: Path):
        name = path.stem
        spec = importlib.util.spec_from_file_location(f"jeeves.modules.{name}", str(path))
        if not spec or not spec.loader:
            raise ImportError(f"Could not load spec for {name}")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return name, mod

    def unload_all(self):
        for name, obj in list(self.plugins.items()):
            try:
                if hasattr(obj, "on_unload"):
                    obj.on_unload()
            except Exception:
                print(f"[plugins] on_unload error in {name}:\n{traceback.format_exc()}", file=sys.stderr)
        self.plugins.clear()
        self.modules.clear()
        self._plugin_stats.clear()

    def load_all(self):
        """Atomic reload with better error handling and dependency resolution."""
        import importlib
        importlib.invalidate_caches()

        temp_plugins, temp_modules, errors = {}, {}, []

        # Get valid module files
        try:
            files = [
                p for p in MODULES_DIR.iterdir()
                if (p.is_file() and p.suffix == ".py" and 
                    not p.name.startswith("_") and p.parent.samefile(MODULES_DIR))
            ]
        except Exception as e:
            errors.append(f"[plugins] cannot list modules directory: {e}")
            return False

        # Load plugins with dependency order
        loaded_names = set()
        remaining_files = list(files)
        max_attempts = len(files) * 2  # Prevent infinite loops
        
        while remaining_files and max_attempts > 0:
            max_attempts -= 1
            made_progress = False
            
            for py in remaining_files[:]:  # Copy list to modify during iteration
                try:
                    name, mod = self._import_file(py)
                    if not hasattr(mod, "setup"):
                        remaining_files.remove(py)
                        continue
                    
                    # Check dependencies if module has them
                    if hasattr(mod, "DEPENDENCIES"):
                        deps = getattr(mod, "DEPENDENCIES", [])
                        if not all(dep in loaded_names for dep in deps):
                            continue  # Try again later
                    
                    obj = mod.setup(self.bot)
                    temp_modules[name] = mod
                    temp_plugins[name] = obj
                    loaded_names.add(name)
                    remaining_files.remove(py)
                    made_progress = True
                    
                except Exception as e:
                    errors.append(f"[plugins] failed to load {py.name}: {e}")
                    remaining_files.remove(py)
            
            if not made_progress:
                break

        if errors:
            for err in errors:
                print(err, file=sys.stderr)
            # Don't fail completely - load what we can
            if not temp_plugins:
                return False

        # Swap in the new set
        self.unload_all()
        self.modules = temp_modules
        self.plugins = temp_plugins

        # Initialize stats tracking
        for name in self.plugins:
            self._plugin_stats[name] = {
                "calls": 0,
                "total_time": 0.0,
                "errors": 0,
                "last_error": None
            }

        # Call on_load hooks
        for name, obj in self.plugins.items():
            try:
                if hasattr(obj, "on_load"):
                    obj.on_load()
                print(f"[plugins] loaded {name}")
            except Exception as e:
                print(f"[plugins] on_load error in {name}: {e}", file=sys.stderr)
                self._plugin_stats[name]["errors"] += 1
                self._plugin_stats[name]["last_error"] = str(e)
        
        return True

    def dispatch_pubmsg(self, connection, event, msg, username):
        """Enhanced message dispatch with performance monitoring."""
        start_time = time.time()
        
        for name, obj in self.plugins.items():
            plugin_start = time.time()
            try:
                if hasattr(obj, "on_pubmsg"):
                    handled = obj.on_pubmsg(connection, event, msg, username)
                    
                    # Update stats
                    plugin_time = time.time() - plugin_start
                    stats = self._plugin_stats[name]
                    stats["calls"] += 1
                    stats["total_time"] += plugin_time
                    
                    if handled:
                        return True
                        
            except Exception as e:
                plugin_time = time.time() - plugin_start
                stats = self._plugin_stats[name]
                stats["calls"] += 1
                stats["total_time"] += plugin_time
                stats["errors"] += 1
                stats["last_error"] = str(e)
                print(f"[plugins] on_pubmsg error in {name}: {e}", file=sys.stderr)
        
        return False

    def get_stats(self):
        """Return plugin performance statistics."""
        return self._plugin_stats.copy()

# ---------- connection manager ----------
class ConnectionManager:
    """Handles connection state and reconnection logic."""
    
    def __init__(self, bot):
        self.bot = bot
        self.connected = False
        self.last_activity = time.time()
        self.ping_timer = None
        
    def start_ping_monitor(self):
        """Monitor connection health."""
        if self.ping_timer:
            self.ping_timer.cancel()
        self.ping_timer = threading.Timer(300.0, self._check_connection)  # 5 minutes
        self.ping_timer.start()
        
    def _check_connection(self):
        """Send periodic pings to keep connection alive."""
        if self.connected:
            try:
                self.bot.connection.ping("keepalive")
                self.start_ping_monitor()  # Schedule next ping
            except Exception:
                print("[connection] ping failed", file=sys.stderr)
                
    def mark_activity(self):
        """Mark recent activity to prevent unnecessary pings."""
        self.last_activity = time.time()

# ---------- the enhanced butler ----------
class Jeeves(SingleServerIRCBot):
    def __init__(self, server, port, channel, nickname, username=None, password=None):
        ssl_factory = Factory(wrapper=ssl.wrap_socket)
        super().__init__([(server, port)], nickname, nickname, connect_factory=ssl_factory)
        
        self.server = server
        self.port = port
        self.primary_channel = channel
        self.nickname = nickname

        # Auth configuration
        env_user = os.getenv("JEEVES_USER", "").strip()
        env_pass = os.getenv("JEEVES_PASS", "").strip()
        self.sasl_user = (username or env_user).strip()
        self.sasl_pass = (password or env_pass).strip()
        self.nickserv_pass = os.getenv("JEEVES_NICKSERV_PASS", "").strip()
        self.auth_debug = os.getenv("JEEVES_AUTH_DEBUG", "0").strip().lower() in ("1","true","yes","on")

        # CAP/SASL state
        self._cap_in_progress = False
        self._sasl_try = bool(self.sasl_user and self.sasl_pass)
        self._sasl_done = False

        # Enhanced components
        self.pm = PluginManager(self)
        self.conn_manager = ConnectionManager(self)

        # Channel management
        chans_env = os.getenv("JEEVES_CHANNELS", "").strip()
        self.start_channels = (
            {channel} if not chans_env 
            else {c.strip() for c in chans_env.split(",") if c.strip()}
        )
        if not self.start_channels:
            self.start_channels = {channel}
        self.joined_channels = set()

        # Constants for plugins
        self.JEEVES_NAME_RE = JEEVES_NAME_RE
        self._scheduler_started = False

        # Rate limiting for bot responses
        self._last_response_time = {}
        self._response_cooldown = 1.0  # 1 second between responses per user

    # ----- enhanced helpers for plugins -----
    def get_module_state(self, name): 
        return self.pm.get_state(name)
    
    def update_module_state(self, name, updates):
        """Efficient way for plugins to update their state."""
        self.pm.update_module_state(name, updates)
    
    def save(self): 
        state_manager.force_save()
    
    def say(self, text, rate_limit=True): 
        if rate_limit and not self._check_rate_limit("global"):
            return
        self.connection.privmsg(self.primary_channel, text)
    
    def say_to(self, room, text, rate_limit=True): 
        if rate_limit and not self._check_rate_limit(f"room:{room}"):
            return
        self.connection.privmsg(room, text)
    
    def privmsg(self, nick, text, rate_limit=True): 
        if rate_limit and not self._check_rate_limit(f"user:{nick}"):
            return
        self.connection.privmsg(nick, text)

    def _check_rate_limit(self, key):
        """Check if we can send a message without hitting rate limits."""
        now = time.time()
        if now - self._last_response_time.get(key, 0) < self._response_cooldown:
            return False
        self._last_response_time[key] = now
        return True

    # Enhanced profile management with caching
    def _get_profiles(self):
        return state_manager.get_state().get("profiles", {})

    def set_profile(self, nick, *, title=None, pronouns=None):
        nick_key = nick.lower()
        profiles = self._get_profiles()
        prof = profiles.get(nick_key, {})
        
        if title is not None: 
            prof["title"] = title
        if pronouns is not None: 
            prof["pronouns"] = pronouns
        prof["set_at"] = datetime.now(UTC).isoformat()
        
        profiles[nick_key] = prof
        state_manager.update_state({"profiles": profiles})

    def title_for(self, nick):
        prof = self._get_profiles().get(nick.lower(), {})
        t = prof.get("title")
        return t if t in ("sir", "madam") else "Mx."

    def pronouns_for(self, nick):
        return self._get_profiles().get(nick.lower(), {}).get("pronouns", "they/them")

    def is_admin(self, nick: str) -> bool:
        admin_nicks = get_admin_nicks()  # Dynamic admin list
        return nick.lower() in admin_nicks if admin_nicks else False

    # ----- enhanced scheduler -----
    def _ensure_scheduler_thread(self):
        if self._scheduler_started:
            return
        self._scheduler_started = True
        
        def loop():
            while True:
                try:
                    schedule.run_pending()
                except Exception as e:
                    print(f"[schedule] error: {e}", file=sys.stderr)
                time.sleep(1)
                
        t = threading.Thread(target=loop, name="jeeves-scheduler", daemon=True)
        t.start()

    # ----- connection methods -----
    def _whois_self(self):
        try:
            print(f"[whois] WHOIS {self.nickname}", file=sys.stderr)
            self.connection.whois([self.nickname])
        except Exception:
            print("[whois] failed to send WHOIS", file=sys.stderr)

    # CAP/SASL methods (unchanged but could be optimized)
    def _cap_ls(self):
        self._cap_in_progress = True
        print("[cap] LS 302", file=sys.stderr)
        self.connection.send_raw("CAP LS 302")

    def _cap_req_sasl(self):
        print(f"[cap] REQ sasl (user='{self.sasl_user or '<empty>'}')", file=sys.stderr)
        self.connection.send_raw("CAP REQ :sasl")

    def _send_sasl_plain(self):
        print(f"[sasl] AUTHENTICATE PLAIN (user='{self.sasl_user or '<empty>'}')", file=sys.stderr)
        self.connection.send_raw("AUTHENTICATE PLAIN")

    def _send_sasl_blob(self):
        blob = f"{self.sasl_user}\0{self.sasl_user}\0{self.sasl_pass}".encode("utf-8")
        b64 = base64.b64encode(blob).decode("ascii")
        print(f"[sasl] sending creds for user='{self.sasl_user}' ({len(b64)}b)", file=sys.stderr)
        for i in range(0, len(b64), 400):
            self.connection.send_raw("AUTHENTICATE " + b64[i:i+400])
        if len(b64) % 400 == 0:
            self.connection.send_raw("AUTHENTICATE +")

    def _maybe_identify_nickserv(self):
        if self.nickserv_pass and self.sasl_user:
            try:
                print(f"[nickserv] IDENTIFY user='{self.sasl_user}'", file=sys.stderr)
                self.connection.privmsg("NickServ", f"IDENTIFY {self.sasl_user} {self.nickserv_pass}")
            except Exception:
                print("[nickserv] failed to send IDENTIFY", file=sys.stderr)

    # ----- IRC event handlers -----
    def on_connect(self, connection, event):
        print("[boot] on_connect", file=sys.stderr)
        self.conn_manager.connected = True
        if self._sasl_try:
            self._cap_ls()

    def on_disconnect(self, connection, event):
        print("[boot] on_disconnect", file=sys.stderr)
        self.conn_manager.connected = False
        self.joined_channels.clear()

    def on_cap(self, connection, event):
        args = event.arguments or []
        verb = (args[0] or "").upper()
        rest = " ".join(args[1:]).lower()
        print(f"[cap] {verb} {rest}", file=sys.stderr)

        if verb == "LS":
            if "sasl" in rest and self._sasl_try:
                self._cap_req_sasl()
            else:
                print("[cap] no sasl listed; CAP END", file=sys.stderr)
                connection.send_raw("CAP END")
                self._cap_in_progress = False
                self._maybe_identify_nickserv()
            return

        if verb == "ACK" and "sasl" in rest and self._sasl_try:
            self._send_sasl_plain()
            return

        if verb == "NAK":
            print("[cap] NAK; CAP END", file=sys.stderr)
            connection.send_raw("CAP END")
            self._cap_in_progress = False
            self._maybe_identify_nickserv()

    def on_authenticate(self, connection, event):
        print(f"[sasl] server AUTH {event.arguments}", file=sys.stderr)
        if not self._sasl_try:
            return
        if event.arguments and event.arguments[0] == "+":
            self._send_sasl_blob()

    # SASL result handlers
    def on_903(self, connection, event):
        print("[sasl] success (903); CAP END", file=sys.stderr)
        if self._cap_in_progress:
            connection.send_raw("CAP END")
            self._cap_in_progress = False

    def on_904(self, connection, event):
        print("[sasl] fail (904); CAP END", file=sys.stderr)
        if self._cap_in_progress:
            connection.send_raw("CAP END")
            self._cap_in_progress = False
        self._maybe_identify_nickserv()

    def on_905(self, connection, event):
        print("[sasl] fail (905); CAP END", file=sys.stderr)
        if self._cap_in_progress:
            connection.send_raw("CAP END")
            self._cap_in_progress = False
        self._maybe_identify_nickserv()

    def on_906(self, connection, event):
        print("[sasl] mechanism not available (906); CAP END", file=sys.stderr)
        if self._cap_in_progress:
            connection.send_raw("CAP END")
            self._cap_in_progress = False
        self._maybe_identify_nickserv()

    def on_907(self, connection, event):
        print("[sasl] already authenticated (907); CAP END", file=sys.stderr)
        if self._cap_in_progress:
            connection.send_raw("CAP END")
            self._cap_in_progress = False

    # WHOIS response handlers
    def on_330(self, connection, event):
        args = event.arguments or []
        if len(args) >= 2:
            nick, account = args[0], args[1]
            print(f"[whois] {nick} is logged in as {account} (330)", file=sys.stderr)
            if self.auth_debug:
                self.say_to(self.primary_channel, f"WHOIS: {nick} is logged in as {account}.")

    def on_318(self, connection, event):
        args = event.arguments or []
        print(f"[whois] end of WHOIS: {' '.join(args)} (318)", file=sys.stderr)

    def on_307(self, connection, event):
        args = event.arguments or []
        nick = args[0] if args else self.nickname
        print(f"[whois] {nick} has identified (307)", file=sys.stderr)
        if self.auth_debug:
            self.say_to(self.primary_channel, f"WHOIS: {nick} is identified (307).")

    def on_welcome(self, connection, event):
        print("[boot] on_welcome", file=sys.stderr)
        self.conn_manager.start_ping_monitor()
        
        if self.auth_debug:
            threading.Timer(5.0, self._whois_self).start()
        if not self._sasl_try and self.nickserv_pass:
            threading.Timer(2.0, self._maybe_identify_nickserv).start()

        # Join channels
        for room in sorted(self.start_channels):
            try:
                connection.join(room)
            except Exception as e:
                print(f"[join] failed to join {room}: {e}", file=sys.stderr)

        # Set bot mode if supported
        try:
            for room in self.start_channels:
                connection.mode(room, "+B")
        except Exception:
            pass

        # Load plugins and start scheduler
        self.pm.load_all()
        self._ensure_scheduler_thread()

    def on_join(self, connection, event):
        room = event.target
        nick = event.source.split('!')[0]
        if nick == self.nickname:
            self.joined_channels.add(room)

    def on_part(self, connection, event):
        room = event.target
        nick = event.source.split('!')[0]
        if nick == self.nickname and room in self.joined_channels:
            self.joined_channels.discard(room)

    def on_pong(self, connection, event):
        """Handle pong responses."""
        self.conn_manager.mark_activity()

    def on_pubmsg(self, connection, event):
        self.conn_manager.mark_activity()
        
        raw = event.arguments[0]
        msg = raw if isinstance(raw, str) else raw.decode("utf-8", errors="ignore")
        username = event.source.split('!')[0]

        # Enhanced admin commands
        if self.is_admin(username):
            if msg.strip().lower() == "!reload":
                try:
                    self.say("Very good; reloading my habits.")
                    ok = self.pm.load_all()
                    self.say(
                        f"Refreshed and ready, {self.title_for(username)}."
                        if ok else "Reload aborted; retaining the previous configuration."
                    )
                except Exception as e:
                    self.say("My apologies; an unexpected error occurred while retying my cravat.")
                    print(f"[reload] error: {e}", file=sys.stderr)
                return

            elif msg.strip().lower() == "!authcheck":
                self.say("Very good; inquiring of the clerks.")
                self._whois_self()
                return
                
            elif msg.strip().lower() == "!stats":
                stats = self.pm.get_stats()
                if stats:
                    lines = []
                    for name, data in stats.items():
                        avg_time = (data["total_time"] / data["calls"]) * 1000 if data["calls"] > 0 else 0
                        lines.append(f"{name}: {data['calls']} calls, {avg_time:.1f}ms avg, {data['errors']} errors")
                    self.say(f"Plugin stats: {'; '.join(lines)}")
                else:
                    self.say("No plugin statistics available.")
                return

        # Let plugins handle the message
        if self.pm.dispatch_pubmsg(connection, event, msg, username):
            return

# ----- enhanced signal handling -----
def handle_sighup(signum, frame, bot_ref):
    try:
        bot = bot_ref[0]
        if bot and bot.conn_manager.connected:
            bot.connection.privmsg(bot.primary_channel, "Pardon me; refreshing my books.")
            bot.pm.load_all()
    except Exception as e:
        print(f"[sighup] error: {e}", file=sys.stderr)

def handle_sigterm(signum, frame, bot_ref):
    """Graceful shutdown."""
    try:
        print("[shutdown] SIGTERM received, shutting down gracefully...", file=sys.stderr)
        bot = bot_ref[0]
        if bot:
            if bot.conn_manager.connected:
                bot.connection.privmsg(bot.primary_channel, "I shall return shortly.")
                bot.connection.quit("Graceful shutdown")
            state_manager.force_save()
        sys.exit(0)
    except Exception as e:
        print(f"[shutdown] error: {e}", file=sys.stderr)
        sys.exit(1)

# ----- main runner with enhanced error handling -----
def main():
    SERVER = os.getenv("JEEVES_SERVER", "")
    PORT = int(os.getenv("JEEVES_PORT", "6667"))
    CHANNEL = os.getenv("JEEVES_CHANNEL", "")
    NICKNAME = os.getenv("JEEVES_NICK", "Jeeves")
    SASL_USERNAME = os.getenv("JEEVES_USER", "")
    SASL_PASSWORD = os.getenv("JEEVES_PASS", "")

    if not all([SERVER, CHANNEL]):
        print("Error: JEEVES_SERVER and JEEVES_CHANNEL must be set", file=sys.stderr)
        sys.exit(1)

    print(f"[boot] cwd={os.getcwd()}", file=sys.stderr)
    print(f"[boot] server={SERVER} port={PORT} nick={NICKNAME}", file=sys.stderr)
    print(f"[boot] sasl_user={'<set>' if SASL_USERNAME else '<empty>'}", file=sys.stderr)

    bot_ref = [None]
    retry_count = 0
    max_retries = 10
    
    while retry_count < max_retries:
        try:
            if bot_ref[0] is None:
                bot_ref[0] = Jeeves(SERVER, PORT, CHANNEL, NICKNAME, SASL_USERNAME, SASL_PASSWORD)
                signal.signal(signal.SIGHUP, lambda s, f: handle_sighup(s, f, bot_ref))
                signal.signal(signal.SIGTERM, lambda s, f: handle_sigterm(s, f, bot_ref))
                signal.signal(signal.SIGINT, lambda s, f: handle_sigterm(s, f, bot_ref))
                
                print(f"[boot] starting bot (attempt {retry_count + 1})", file=sys.stderr)
                bot_ref[0].start()
                retry_count = 0  # Reset on successful connection
                
            time.sleep(1)
            
        except KeyboardInterrupt:
            print("[boot] keyboard interrupt", file=sys.stderr)
            handle_sigterm(signal.SIGINT, None, bot_ref)
            
        except Exception as e:
            print(f"[core] bot crashed: {e}", file=sys.stderr)
            retry_count += 1
            bot_ref[0] = None
            
            if retry_count >= max_retries:
                print(f"[core] max retries ({max_retries}) exceeded, giving up", file=sys.stderr)
                break
                
            backoff = min(300, 5 * (2 ** retry_count))  # Exponential backoff, max 5 minutes
            print(f"[core] retrying in {backoff} seconds (attempt {retry_count}/{max_retries})", file=sys.stderr)
            time.sleep(backoff)

    # Ensure state is saved on exit
    state_manager.force_save()

if __name__ == "__main__":
    main()
