#!/usr/bin/env python3
# jeeves.py — modular IRC butler core (SASL + debug + modular plugins)

import os, sys, time, json, re, ssl, signal, threading, traceback, importlib.util, base64
from pathlib import Path
from datetime import datetime, timezone
from irc.bot import SingleServerIRCBot
from irc.connection import Factory
import schedule  # modules may schedule; we run the loop here

# ---------- constants & paths ----------
UTC = timezone.utc
ROOT = Path(__file__).resolve().parent
STATE_PATH = ROOT / "state.json"
MODULES_DIR = ROOT / "modules"
MODULES_DIR.mkdir(exist_ok=True)  # ensure it exists (prevents startup noise)

# Admin list (comma-separated; case-insensitive). If empty → locked down (no one is admin).
ADMIN_NICKS = {n.strip().lower() for n in os.getenv("JEEVES_ADMINS", "").split(",") if n.strip()}

# Addressable names (tab-complete friendly) exposed to plugins
JEEVES_NAME_RE = r"(?:jeeves|jeevesbot)"

# ---------- state i/o ----------
def load_state():
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text())
        except Exception:
            print(f"[state] could not parse {STATE_PATH}:\n{traceback.format_exc()}", file=sys.stderr)
    return {"modules": {}, "profiles": {}}

def save_state(state):
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True))
    tmp.replace(STATE_PATH)

# ---------- plugin manager ----------
class PluginManager:
    def __init__(self, bot):
        self.bot = bot
        self.plugins = {}  # active plugin objects
        self.modules = {}  # active imported module objects

    def get_state(self, name):
        mods = self.bot.state.setdefault("modules", {})
        return mods.setdefault(name, {})

    def _import_file(self, path: Path):
        name = path.stem
        spec = importlib.util.spec_from_file_location(f"jeeves.modules.{name}", str(path))
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

    def load_all(self):
        """Atomic reload. Only load top-level *.py in modules/, ignore __pycache__/ etc."""
        import importlib
        importlib.invalidate_caches()

        temp_plugins, temp_modules, errors = {}, {}, []

        # enumerate only immediate children that are real .py files
        try:
            files = []
            for p in MODULES_DIR.iterdir():
                if not p.is_file():
                    continue
                if p.suffix != ".py":
                    continue
                if p.name.startswith("_"):
                    continue
                if not p.parent.samefile(MODULES_DIR):
                    continue
                files.append(p)
        except Exception:
            errors.append(f"[plugins] cannot list modules directory:\n{traceback.format_exc()}")

        for py in sorted(files):
            try:
                name, mod = self._import_file(py)
                if not hasattr(mod, "setup"):
                    continue
                obj = mod.setup(self.bot)  # pass bot
                temp_modules[name] = mod
                temp_plugins[name]  = obj
            except Exception:
                errors.append(f"[plugins] failed to load {py.name}:\n{traceback.format_exc()}")

        if errors:
            # Quiet failure: do not chat in-channel before joins; just log.
            for err in errors:
                print(err, file=sys.stderr)
            return False

        # swap in the new set
        self.unload_all()
        self.modules = temp_modules
        self.plugins = temp_plugins

        # call on_load hooks (non-fatal if they error)
        for name, obj in self.plugins.items():
            try:
                if hasattr(obj, "on_load"):
                    obj.on_load()
                print(f"[plugins] loaded {name}")
            except Exception:
                print(f"[plugins] on_load error in {name}:\n{traceback.format_exc()}", file=sys.stderr)
        return True

    def dispatch_pubmsg(self, connection, event, msg, username):
        for name, obj in self.plugins.items():
            try:
                if hasattr(obj, "on_pubmsg"):
                    handled = obj.on_pubmsg(connection, event, msg, username)
                    if handled:
                        return True
            except Exception:
                print(f"[plugins] on_pubmsg error in {name}:\n{traceback.format_exc()}", file=sys.stderr)
        return False

# ---------- the butler ----------
class Jeeves(SingleServerIRCBot):
    def __init__(self, server, port, channel, nickname, username=None, password=None):
        ssl_factory = Factory(wrapper=ssl.wrap_socket)
        super().__init__([(server, port)], nickname, nickname, connect_factory=ssl_factory)
        self.server = server
        self.port = port
        self.primary_channel = channel  # keep a "home" room
        self.nickname = nickname

        # auth / services (allow ctor args to override env for tests)
        env_user = os.getenv("JEEVES_USER", "").strip()
        env_pass = os.getenv("JEEVES_PASS", "").strip()
        self.sasl_user = (username or env_user).strip()
        self.sasl_pass = (password or env_pass).strip()
        self.nickserv_pass = os.getenv("JEEVES_NICKSERV_PASS", "").strip()  # optional fallback
        self.auth_debug = os.getenv("JEEVES_AUTH_DEBUG", "0").strip().lower() in ("1","true","yes","on")

        # CAP/SASL state
        self._cap_in_progress = False
        self._sasl_try = bool(self.sasl_user and self.sasl_pass)
        self._sasl_done = False

        # state & plugins
        self.state = load_state()
        self.pm = PluginManager(self)

        # channels: support single env or comma-separated list
        chans_env = os.getenv("JEEVES_CHANNELS", "").strip()
        self.start_channels = (
            {channel}
            if not chans_env else {c.strip() for c in chans_env.split(",") if c.strip()}
        )
        if not self.start_channels:
            self.start_channels = {channel}
        self.joined_channels = set()  # will be filled by on_join events

        # Expose constants for plugins
        self.JEEVES_NAME_RE = JEEVES_NAME_RE

        # start a simple scheduler loop once connected
        self._scheduler_started = False

    # ----- shared helpers for plugins -----
    def get_module_state(self, name): return self.pm.get_state(name)
    def save(self): save_state(self.state)
    def say(self, text): self.connection.privmsg(self.primary_channel, text)
    def say_to(self, room, text): self.connection.privmsg(room, text)
    def privmsg(self, nick, text): self.connection.privmsg(nick, text)  # real PMs now

    # store/read profiles case-insensitively
    def set_profile(self, nick, *, title=None, pronouns=None):
        nick_key = nick.lower()
        prof = self.state.setdefault("profiles", {}).get(nick_key, {})
        if title is not None: prof["title"] = title
        if pronouns is not None: prof["pronouns"] = pronouns
        prof["set_at"] = datetime.now(UTC).isoformat()
        self.state["profiles"][nick_key] = prof
        self.save()

    def title_for(self, nick):
        prof = self.state.get("profiles", {}).get(nick.lower(), {})
        t = prof.get("title")
        return t if t in ("sir", "madam") else "Mx."

    def pronouns_for(self, nick):
        return self.state.get("profiles", {}).get(nick.lower(), {}).get("pronouns", "they/them")

    def is_admin(self, nick: str) -> bool:
        return nick.lower() in ADMIN_NICKS if ADMIN_NICKS else False

    # ----- scheduler thread -----
    def _ensure_scheduler_thread(self):
        if self._scheduler_started:
            return
        self._scheduler_started = True
        def loop():
            while True:
                try:
                    schedule.run_pending()
                except Exception:
                    print(f"[schedule] error:\n{traceback.format_exc()}", file=sys.stderr)
                time.sleep(1)
        t = threading.Thread(target=loop, name="jeeves-scheduler", daemon=True)
        t.start()

    # ----- WHOIS / auth helpers -----
    def _whois_self(self):
        try:
            print(f"[whois] WHOIS {self.nickname}", file=sys.stderr)
            self.connection.whois([self.nickname])
        except Exception:
            print("[whois] failed to send WHOIS", file=sys.stderr)

    # ----- CAP / SASL helpers -----
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

    # ----- IRC lifecycle -----
    def on_connect(self, connection, event):
        print("[boot] on_connect", file=sys.stderr)
        if self._sasl_try:
            self._cap_ls()

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
                # optional fallback
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
            return

    def on_authenticate(self, connection, event):
        print(f"[sasl] server AUTH {event.arguments}", file=sys.stderr)
        if not self._sasl_try:
            return
        if event.arguments and event.arguments[0] == "+":
            self._send_sasl_blob()

    # SASL numerics: 903 success; 904/905 fail; 906/907 mech issues
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

    # WHOIS numerics (debugging)
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
        if self.auth_debug:
            threading.Timer(5.0, self._whois_self).start()
        # If we're not attempting SASL but we have a NickServ password, identify now.
        if not self._sasl_try and self.nickserv_pass:
            threading.Timer(2.0, self._maybe_identify_nickserv).start()
        # Join all configured rooms
        for room in sorted(self.start_channels):
            try:
                connection.join(room)
            except Exception:
                print(f"[join] failed to join {room}", file=sys.stderr)

        # be a good bot where supported
        try:
            for room in self.start_channels:
                connection.mode(room, "+B")
        except Exception:
            pass

        # load plugins + start scheduler loop
        self.pm.load_all()
        self._ensure_scheduler_thread()

    # Keep joined_channels accurate for admin module (!join/!part)
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

    def on_pubmsg(self, connection, event):
        raw = event.arguments[0]
        msg = raw if isinstance(raw, str) else raw.decode("utf-8", errors="ignore")
        username = event.source.split('!')[0]

        # admin: !reload
        if msg.strip().lower() == "!reload" and self.is_admin(username):
            try:
                self.say("Very good; reloading my habits.")
                ok = self.pm.load_all()
                self.say(
                    f"Refreshed and ready, {self.title_for(username)}."
                    if ok else "Reload aborted; retaining the previous configuration."
                )
            except Exception:
                self.say("My apologies; an unexpected error occurred while retying my cravat.")
                print(f"[reload] error:\n{traceback.format_exc()}", file=sys.stderr)
            return

        # admin: !authcheck → WHOIS the bot
        if msg.strip().lower() == "!authcheck" and self.is_admin(username):
            self.say("Very good; inquiring of the clerks.")
            self._whois_self()
            return

        # let plugins try first
        if self.pm.dispatch_pubmsg(connection, event, msg, username):
            return

        # friendly default if addressed as a question
        #if re.search(rf"\b{self.JEEVES_NAME_RE}\b", msg, re.IGNORECASE) and re.search(r"\?\s*$", msg):
        #    connection.privmsg(event.target, f"{username}, Indeed, {self.title_for(username)}.")

# ----- SIGHUP reload handler -----
def handle_sighup(signum, frame, bot_ref):
    try:
        bot = bot_ref[0]
        if bot:
            bot.connection.privmsg(bot.primary_channel, "Pardon me; refreshing my books.")
            bot.pm.load_all()
    except Exception:
        print(f"[sighup] error:\n{traceback.format_exc()}", file=sys.stderr)

# ----- main runner -----
def main():
    SERVER = os.getenv("JEEVES_SERVER", "")
    PORT = int(os.getenv("JEEVES_PORT", ""))
    CHANNEL = os.getenv("JEEVES_CHANNEL", "")
    NICKNAME = os.getenv("JEEVES_NICK", "")
    SASL_USERNAME = os.getenv("JEEVES_USER", "")
    SASL_PASSWORD = os.getenv("JEEVES_PASS", "")

    print(f"[boot] cwd={os.getcwd()}", file=sys.stderr)
    print(f"[boot] server={SERVER} port={PORT} nick={NICKNAME}", file=sys.stderr)
    print(f"[boot] sasl_user={'<set>' if SASL_USERNAME else '<empty>'}", file=sys.stderr)

    bot_ref = [None]
    while True:
        try:
            if bot_ref[0] is None:
                bot_ref[0] = Jeeves(SERVER, PORT, CHANNEL, NICKNAME, SASL_USERNAME, SASL_PASSWORD)
                signal.signal(signal.SIGHUP, lambda s, f: handle_sighup(s, f, bot_ref))
                bot_ref[0].start()
            time.sleep(1)
        except Exception as e:
            print(f"[core] bot crashed: {e}\n{traceback.format_exc()}", file=sys.stderr)
            bot_ref[0] = None
            time.sleep(5)

if __name__ == "__main__":
    main()

