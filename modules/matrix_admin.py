"""
Matrix admin bridge for Jeeves.

Polls a Matrix room for commands and executes them with full admin/super-admin
privileges — no IRC identity check needed, as Matrix access implies ownership.

Config (add to config.yaml under a `matrix:` key):
    matrix:
      homeserver: "https://matrix.example.com"
      room_id: "!roomid:example.com"
      access_token: "${MATRIX_ACCESS_TOKEN}"   # preferred
      # OR
      username: "${MATRIX_USERNAME}"
      password: "${MATRIX_PASSWORD}"
      admin_user: "@you:example.com"           # optional allowlist (single user)
"""

from typing import Any
import re
import sys
import json
import time
import threading
import logging

import requests
from urllib.parse import quote as urlquote

from .base import SimpleCommandModule

logger = logging.getLogger(__name__)


def setup(bot: Any) -> "MatrixAdmin":
    return MatrixAdmin(bot)


class MatrixAdmin(SimpleCommandModule):
    name = "matrix_admin"
    version = "1.0.0"
    description = "Matrix admin bridge — control Jeeves from a Matrix room."

    def __init__(self, bot: Any) -> None:
        super().__init__(bot)
        self._access_token: str = ""
        self._since: str = ""
        self._txn_id: int = int(time.time() * 1000)
        self._poll_thread: threading.Thread | None = None
        self._start_matrix()

    def _register_commands(self) -> None:
        pass  # No IRC commands — all interaction is via Matrix

    # ── Startup ───────────────────────────────────────────────

    def _start_matrix(self) -> None:
        cfg = self._matrix_config()
        if not cfg.get("homeserver") or not cfg.get("room_id"):
            self.log_debug("[matrix_admin] homeserver or room_id not configured — bridge disabled")
            return

        self._login()
        if not self._access_token:
            self.log_debug("[matrix_admin] no access token — bridge disabled")
            return

        self._poll_thread = threading.Thread(
            target=self._poll_loop, daemon=True, name="matrix-admin-poll"
        )
        self._poll_thread.start()
        self.log_debug("[matrix_admin] poll thread started")

    def on_unload(self) -> None:
        pass  # daemon thread will die with the process

    # ── Config helper ─────────────────────────────────────────

    def _matrix_config(self) -> dict:
        return self.bot.config.get("matrix", {})

    # ── Auth ──────────────────────────────────────────────────

    def _login(self) -> None:
        cfg = self._matrix_config()
        homeserver = cfg.get("homeserver", "").rstrip("/")

        token = cfg.get("access_token", "")
        if token:
            self._access_token = token
            self.log_debug("[matrix_admin] using pre-configured access token")
            return

        username = cfg.get("username", "")
        password = cfg.get("password", "")
        if not username or not password:
            self.log_debug("[matrix_admin] no credentials configured")
            return

        try:
            resp = requests.post(
                f"{homeserver}/_matrix/client/v3/login",
                json={"type": "m.login.password", "user": username, "password": password},
                timeout=10,
            )
            resp.raise_for_status()
            self._access_token = resp.json()["access_token"]
            self.log_debug("[matrix_admin] password login successful")
        except Exception as e:
            self.log_debug(f"[matrix_admin] login failed: {e}")

    # ── Send ──────────────────────────────────────────────────

    def _send(self, message: str) -> None:
        cfg = self._matrix_config()
        homeserver = cfg.get("homeserver", "").rstrip("/")
        room_id = cfg.get("room_id", "")
        if not homeserver or not room_id or not self._access_token:
            return

        self._txn_id += 1
        encoded_room = urlquote(room_id, safe="")
        try:
            resp = requests.put(
                f"{homeserver}/_matrix/client/v3/rooms/{encoded_room}/send/m.room.message/{self._txn_id}",
                headers={"Authorization": f"Bearer {self._access_token}"},
                json={"msgtype": "m.text", "body": message},
                timeout=10,
            )
            resp.raise_for_status()
        except requests.exceptions.RequestException as e:
            self.log_debug(f"[matrix_admin] send failed: {e}")

    # ── Poll loop ─────────────────────────────────────────────

    def _poll_loop(self) -> None:
        cfg = self._matrix_config()
        homeserver = cfg.get("homeserver", "").rstrip("/")
        room_id = cfg.get("room_id", "")
        admin_user = cfg.get("admin_user", "")
        bot_username = cfg.get("username", "")

        headers = {"Authorization": f"Bearer {self._access_token}"}

        # Initial sync — skip old messages
        try:
            resp = requests.get(
                f"{homeserver}/_matrix/client/v3/sync",
                headers=headers,
                params={"timeout": 0, "filter": json.dumps({"room": {"timeline": {"limit": 0}}})},
                timeout=15,
            )
            resp.raise_for_status()
            self._since = resp.json().get("next_batch", "")
            self.log_debug("[matrix_admin] initial sync complete")
        except Exception as e:
            self.log_debug(f"[matrix_admin] initial sync failed: {e}")

        backoff = 5
        while True:
            try:
                params: dict = {"timeout": 30000}
                if self._since:
                    params["since"] = self._since

                resp = requests.get(
                    f"{homeserver}/_matrix/client/v3/sync",
                    headers=headers,
                    params=params,
                    timeout=35,
                )
                resp.raise_for_status()
                data = resp.json()
                self._since = data.get("next_batch", self._since)
                backoff = 5

                # Accept any pending invites
                for invited_room in data.get("rooms", {}).get("invite", {}):
                    self.log_debug(f"[matrix_admin] accepting invite to {invited_room}")
                    try:
                        requests.post(
                            f"{homeserver}/_matrix/client/v3/join/{urlquote(invited_room, safe='')}",
                            headers=headers,
                            timeout=10,
                        ).raise_for_status()
                        self.log_debug(f"[matrix_admin] joined {invited_room}")
                    except Exception as e:
                        self.log_debug(f"[matrix_admin] failed to join {invited_room}: {e}")

                joined = data.get("rooms", {}).get("join", {})
                room_data = joined.get(room_id, {})
                for event in room_data.get("timeline", {}).get("events", []):
                    if event.get("type") != "m.room.message":
                        continue
                    content = event.get("content", {})
                    if content.get("msgtype") != "m.text":
                        continue
                    sender = event.get("sender", "")
                    # Skip our own messages
                    if bot_username and sender.startswith(f"@{bot_username}:"):
                        continue
                    # Enforce allowlist if configured
                    if admin_user and sender != admin_user:
                        continue
                    text = content.get("body", "").strip()
                    if text.startswith("!"):
                        self._dispatch(text)

            except requests.exceptions.RequestException as e:
                self.log_debug(f"[matrix_admin] sync error: {e}")
                time.sleep(backoff)
                backoff = min(backoff * 2, 60)
            except Exception as e:
                self.log_debug(f"[matrix_admin] unexpected poll error: {e}")
                time.sleep(backoff)
                backoff = min(backoff * 2, 60)

    # ── Command dispatch ──────────────────────────────────────

    # Built-in commands: { "!cmd": (handler, description) }
    # Handler signature: (args: str) -> None
    @property
    def _builtin_routes(self) -> dict:
        return {
            "!modules":      (lambda a: self._cmd_modules(),          "list loaded modules"),
            "!reload":       (lambda a: self._cmd_reload(),           "reload all modules"),
            "!load":         (lambda a: self._cmd_load(a),            "!load <module>"),
            "!unload":       (lambda a: self._cmd_unload(a),          "!unload <module>"),
            "!join":         (lambda a: self._cmd_join(a),            "!join <#channel>"),
            "!part":         (lambda a: self._cmd_part(a),            "!part <#channel> [msg]"),
            "!say":          (lambda a: self._cmd_say(a),             "!say <#channel> <message>"),
            "!debug":        (lambda a: self._cmd_debug(a),           "!debug <on|off> [module]"),
            "!config":       (lambda a: self._cmd_config(a),          "!config reload"),
            "!kill":         (lambda a: self._cmd_kill(),             "shut down the bot"),
            "!status":       (lambda a: self._cmd_status(),           "connection status"),
            "!help":         (lambda a: self._cmd_help(),             "this message"),
        }

    def _plugin_commands(self) -> dict:
        """Collect matrix_admin_commands from all loaded plugins.

        Each plugin may expose:
            matrix_admin_commands = {
                "!cmd prefix": (handler_fn, "description"),
                ...
            }
        where handler_fn(args: str) -> str returns the reply text.
        """
        cmds: dict = {}
        for plugin in self.bot.pm.plugins.values():
            contrib = getattr(plugin, "matrix_admin_commands", None)
            if isinstance(contrib, dict):
                cmds.update(contrib)
        return cmds

    def _dispatch(self, text: str) -> None:
        text_lower = text.lower()

        # Built-ins: single-word match on first token
        parts = text.split(None, 1)
        cmd = parts[0].lower()
        args = parts[1].strip() if len(parts) > 1 else ""

        builtin = self._builtin_routes.get(cmd)
        if builtin:
            handler, _ = builtin
            try:
                handler(args)
            except Exception as e:
                self.log_debug(f"[matrix_admin] command error ({cmd}): {e}")
                self._send(f"Error executing {cmd}: {e}")
            return

        # Plugin commands: longest-prefix match (supports multi-word keys)
        plugin_cmds = self._plugin_commands()
        for key in sorted(plugin_cmds.keys(), key=len, reverse=True):
            key_lower = key.lower()
            if text_lower == key_lower or text_lower.startswith(key_lower + " "):
                remaining = text[len(key):].strip()
                handler, _ = plugin_cmds[key]
                try:
                    result = handler(remaining)
                    if result:
                        self._send(result)
                except Exception as e:
                    self.log_debug(f"[matrix_admin] plugin command error ({key}): {e}")
                    self._send(f"Error executing {key}: {e}")
                return

        self._send(f"Unknown command: {cmd}. Send !help for available commands.")

    # ── Command handlers ──────────────────────────────────────

    def _cmd_modules(self) -> None:
        loaded = sorted(self.bot.pm.plugins.keys())
        self._send(f"Loaded modules ({len(loaded)}): {', '.join(loaded)}")

    def _cmd_reload(self) -> None:
        loaded = self.bot.core_reload_plugins()
        self._send(f"Modules reloaded: {', '.join(sorted(loaded))}")

    def _cmd_load(self, args: str) -> None:
        module_name = args.strip()
        if not module_name:
            self._send("Usage: !load <module_name>")
            return
        if self.bot.pm.load_module(module_name):
            self._send(f"Module '{module_name}' loaded.")
        else:
            self._send(f"Failed to load '{module_name}'. Check debug.log.")

    def _cmd_unload(self, args: str) -> None:
        module_name = args.strip()
        if not module_name:
            self._send("Usage: !unload <module_name>")
            return
        if self.bot.pm.unload_module(module_name):
            self._send(f"Module '{module_name}' unloaded.")
        else:
            self._send(f"Failed to unload '{module_name}'.")

    def _cmd_join(self, args: str) -> None:
        room = args.strip()
        if not room:
            self._send("Usage: !join <#channel>")
            return
        self.bot.connection.join(room)
        self._send(f"Joined {room}.")

    def _cmd_part(self, args: str) -> None:
        parts = args.split(None, 1)
        if not parts:
            self._send("Usage: !part <#channel> [message]")
            return
        room = parts[0]
        msg = parts[1] if len(parts) > 1 else "Leaving per request."
        if room in self.bot.joined_channels:
            self.bot.connection.part(room, msg)
            self._send(f"Left {room}.")
        else:
            self._send(f"Not in {room}.")

    def _cmd_say(self, args: str) -> None:
        parts = args.split(None, 1)
        if len(parts) < 2:
            self._send("Usage: !say <#channel> <message>")
            return
        channel, message = parts[0], parts[1]
        message = message.replace("\r", "").replace("\n", " ")
        if not self.bot.connection.is_connected():
            self._send("Not connected to IRC.")
            return
        self.bot.connection.privmsg(channel, message)
        self._send(f"Sent to {channel}: {message}")

    def _cmd_debug(self, args: str) -> None:
        parts = args.split()
        if not parts:
            self._send("Usage: !debug <on|off> [module_name]")
            return

        if len(parts) == 1:
            state_bool = parts[0].lower() in ("on", "true", "1", "enable")
            self.bot.set_debug_mode(state_bool)
            self._send(f"Debug mode is now {'ON' if state_bool else 'OFF'}.")
        elif len(parts) == 2:
            module_name, state = parts[0], parts[1]
            state_bool = state.lower() in ("on", "true", "1", "enable")
            if module_name not in self.bot.pm.plugins:
                self._send(f"Module '{module_name}' is not loaded.")
                return
            self.bot.set_module_debug(module_name, state_bool)
            self._send(f"Debug for '{module_name}' is now {'ON' if state_bool else 'OFF'}.")
        else:
            self._send("Usage: !debug <on|off> or !debug <module_name> <on|off>")

    def _cmd_config(self, args: str) -> None:
        if args.strip().lower() == "reload":
            if self.bot.core_reload_config():
                self._send("Configuration reloaded from config.yaml.")
            else:
                self._send("Failed to reload configuration.")
        else:
            self._send("Usage: !config reload")

    def _cmd_kill(self) -> None:
        self._send("Shutting down Jeeves...")
        self.bot.connection.quit("Killed via Matrix.")
        sys.exit(42)

    def _cmd_status(self) -> None:
        connected = self.bot.connection.is_connected()
        channels = ", ".join(sorted(self.bot.joined_channels)) or "(none)"
        module_count = len(self.bot.pm.plugins)
        debug = "ON" if self.bot.debug_mode else "OFF"
        self._send(
            f"IRC: {'connected' if connected else 'disconnected'}\n"
            f"Channels: {channels}\n"
            f"Modules loaded: {module_count}\n"
            f"Debug: {debug}"
        )

    def _cmd_help(self) -> None:
        lines = ["Jeeves admin commands via Matrix:"]
        for cmd, (_, desc) in sorted(self._builtin_routes.items()):
            lines.append(f"{cmd} — {desc}")

        plugin_cmds = self._plugin_commands()
        if plugin_cmds:
            lines.append("")
            lines.append("Module commands:")
            for cmd, (_, desc) in sorted(plugin_cmds.items()):
                lines.append(f"{cmd} — {desc}")

        self._send("\n".join(lines))
