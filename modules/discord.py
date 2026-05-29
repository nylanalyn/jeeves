"""
Discord admin bridge endpoint for Jeeves.

This module does not connect to Discord directly. It exposes the same local
HTTP admin API used by ircbot_core's shared discord_admin.py router, so the
existing router can call Jeeves with commands like:

    jeeves status
    jeeves modules

Config (add to config.yaml):
    discord:
      enabled: true
      host: "127.0.0.1"
      port: 9110
      token: "${JEEVES_ADMIN_TOKEN}"
"""

from __future__ import annotations

import hmac
import json
import os
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from .base import SimpleCommandModule


def setup(bot: Any) -> "Discord":
    return Discord(bot)


class Discord(SimpleCommandModule):
    name = "discord"
    version = "1.0.0"
    description = "Local Discord-router admin API for Jeeves."

    def __init__(self, bot: Any) -> None:
        super().__init__(bot)
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._event_lock = threading.RLock()
        self._events: list[dict[str, Any]] = []
        self._next_event_id = 1
        self._start_api()

    def _register_commands(self) -> None:
        pass

    def on_unload(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None

    def on_config_reload(self, new_config: dict[str, Any]) -> None:
        cfg = self._discord_config()
        if not cfg.get("enabled", False):
            self.on_unload()
        elif self._server is None:
            self._start_api()

    # --- Startup ---------------------------------------------------------

    def _discord_config(self) -> dict[str, Any]:
        # Prefer a discord section because the module is named discord.py. Accept
        # admin_api too so Jeeves can mirror ircbot_core personality configs.
        discord_cfg = self.bot.config.get("discord", {})
        admin_api_cfg = self.bot.config.get("admin_api", {})
        if discord_cfg.get("enabled", False) or not admin_api_cfg:
            return discord_cfg
        return admin_api_cfg

    def _start_api(self) -> None:
        cfg = self._discord_config()
        if not cfg.get("enabled", False):
            self.log_debug("[discord] admin API disabled")
            return

        token = str(cfg.get("token", "")).strip()
        if not token:
            self.log_debug("[discord] token missing; admin API disabled")
            return

        host = str(cfg.get("host", "127.0.0.1"))
        port = int(cfg.get("port", 9110))
        handler = self._make_handler()

        try:
            self._server = ThreadingHTTPServer((host, port), handler)
        except OSError as e:
            self.log_debug(f"[discord] failed to bind {host}:{port}: {e}")
            return

        self._thread = threading.Thread(
            target=self._server.serve_forever,
            daemon=True,
            name="discord-admin-api",
        )
        self._thread.start()
        self.log_debug(f"[discord] admin API listening on http://{host}:{port}")

    # --- HTTP API --------------------------------------------------------

    def _make_handler(self) -> type[BaseHTTPRequestHandler]:
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "JeevesDiscordAdmin/1.0"

            def log_message(self, fmt: str, *args: Any) -> None:
                bridge.log_debug(f"[discord] {self.address_string()} - {fmt % args}")

            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                if parsed.path == "/health":
                    self._send_json({"ok": True})
                    return
                if parsed.path == "/v1/events":
                    if not self._authorized():
                        return
                    qs = parse_qs(parsed.query)
                    since = None
                    if qs.get("since", [""])[0]:
                        try:
                            since = int(qs["since"][0])
                        except ValueError:
                            self._send_json({"error": "since must be an integer"}, HTTPStatus.BAD_REQUEST)
                            return
                    self._send_json({"events": bridge._get_events_since(since)})
                    return
                self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)

            def do_POST(self) -> None:
                parsed = urlparse(self.path)
                if parsed.path != "/v1/command":
                    self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
                    return
                if not self._authorized():
                    return

                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    payload = json.loads(self.rfile.read(length) or b"{}")
                except Exception:
                    self._send_json({"error": "invalid json"}, HTTPStatus.BAD_REQUEST)
                    return

                command = str(payload.get("command", "")).strip()
                args = str(payload.get("args", "")).strip()
                if not command:
                    self._send_json({"error": "command is required"}, HTTPStatus.BAD_REQUEST)
                    return

                try:
                    messages = bridge._execute(command, args)
                except Exception as e:
                    bridge.log_debug(f"[discord] command failed: {e}")
                    self._send_json({"error": repr(e)}, HTTPStatus.INTERNAL_SERVER_ERROR)
                    return
                self._send_json({"messages": messages or ["ok."]})

            def _authorized(self) -> bool:
                token = str(bridge._discord_config().get("token", "")).strip()
                expected = f"Bearer {token}"
                if hmac.compare_digest(self.headers.get("Authorization", ""), expected):
                    return True
                self._send_json({"error": "unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return False

            def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(int(status))
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        return Handler

    # --- Command dispatch ------------------------------------------------

    @property
    def _builtin_routes(self) -> dict[str, tuple[Callable[[str], str], str]]:
        return {
            "modules": (lambda a: self._cmd_modules(), "list loaded modules"),
            "reload": (lambda a: self._cmd_reload(), "reload all modules"),
            "load": (self._cmd_load, "load <module>"),
            "unload": (self._cmd_unload, "unload <module>"),
            "join": (self._cmd_join, "join <#channel>"),
            "part": (self._cmd_part, "part <#channel> [msg]"),
            "say": (self._cmd_say, "say <#channel> <message>"),
            "debug": (self._cmd_debug, "debug <on|off> [module]"),
            "config": (self._cmd_config, "config reload"),
            "kill": (lambda a: self._cmd_kill(), "shut down the bot"),
            "status": (lambda a: self._cmd_status(), "connection status"),
            "help": (lambda a: self._cmd_help(), "this message"),
        }

    def _plugin_commands(self) -> dict[str, tuple[Callable[[str], str], str]]:
        cmds: dict[str, tuple[Callable[[str], str], str]] = {}
        for plugin in self.bot.pm.plugins.values():
            contrib = getattr(plugin, "matrix_admin_commands", None)
            if isinstance(contrib, dict):
                for key, value in contrib.items():
                    normalized = self._normalize_command_text(str(key))
                    cmds[normalized] = value
        return cmds

    def _execute(self, command: str, args: str = "") -> list[str]:
        text = self._normalize_command_text(f"{command} {args}".strip())
        parts = text.split(None, 1)
        cmd = parts[0].lower()
        remaining = parts[1].strip() if len(parts) > 1 else ""

        builtin = self._builtin_routes.get(cmd)
        if builtin:
            handler, _ = builtin
            return self._reply(handler(remaining))

        plugin_cmds = self._plugin_commands()
        for key in sorted(plugin_cmds.keys(), key=len, reverse=True):
            key_lower = key.lower()
            if text.lower() == key_lower or text.lower().startswith(key_lower + " "):
                handler, _ = plugin_cmds[key]
                plugin_args = text[len(key):].strip()
                return self._reply(handler(plugin_args))

        return [f"Unknown command: {cmd}. Send help for available commands."]

    @staticmethod
    def _normalize_command_text(text: str) -> str:
        return text.strip().lstrip("!").strip()

    @staticmethod
    def _reply(result: Any) -> list[str]:
        if result is None:
            return []
        if isinstance(result, list):
            return [str(item) for item in result]
        return [str(result)]

    # --- Events ----------------------------------------------------------

    def _record_event(self, message: str) -> None:
        with self._event_lock:
            self._events.append({"id": self._next_event_id, "message": message})
            self._next_event_id += 1
            self._events = self._events[-500:]

    def _get_events_since(self, since: int | None = None) -> list[dict[str, Any]]:
        with self._event_lock:
            if since is None:
                return list(self._events)
            return [event for event in self._events if int(event["id"]) > since]

    # --- Command handlers -----------------------------------------------

    def _cmd_modules(self) -> str:
        loaded = sorted(self.bot.pm.plugins.keys())
        return f"Loaded modules ({len(loaded)}): {', '.join(loaded)}"

    def _cmd_reload(self) -> str:
        loaded = self.bot.core_reload_plugins()
        return f"Modules reloaded: {', '.join(sorted(loaded))}"

    def _cmd_load(self, args: str) -> str:
        module_name = args.strip()
        if not module_name:
            return "Usage: load <module_name>"
        if self.bot.pm.load_module(module_name):
            return f"Module '{module_name}' loaded."
        return f"Failed to load '{module_name}'. Check debug.log."

    def _cmd_unload(self, args: str) -> str:
        module_name = args.strip()
        if not module_name:
            return "Usage: unload <module_name>"
        if self.bot.pm.unload_module(module_name):
            return f"Module '{module_name}' unloaded."
        return f"Failed to unload '{module_name}'."

    def _cmd_join(self, args: str) -> str:
        room = args.strip()
        if not room:
            return "Usage: join <#channel>"
        self.bot.connection.join(room)
        return f"Joined {room}."

    def _cmd_part(self, args: str) -> str:
        parts = args.split(None, 1)
        if not parts:
            return "Usage: part <#channel> [message]"
        room = parts[0]
        msg = parts[1] if len(parts) > 1 else "Leaving per request."
        if room in self.bot.joined_channels:
            self.bot.connection.part(room, msg)
            return f"Left {room}."
        return f"Not in {room}."

    def _cmd_say(self, args: str) -> str:
        parts = args.split(None, 1)
        if len(parts) < 2:
            return "Usage: say <#channel> <message>"
        channel, message = parts[0], parts[1]
        message = message.replace("\r", "").replace("\n", " ")
        if not self.bot.connection.is_connected():
            return "Not connected to IRC."
        self.bot.connection.privmsg(channel, message)
        return f"Sent to {channel}: {message}"

    def _cmd_debug(self, args: str) -> str:
        parts = args.split()
        if not parts:
            return "Usage: debug <on|off> [module_name]"

        if len(parts) == 1:
            state_bool = parts[0].lower() in ("on", "true", "1", "enable")
            self.bot.set_debug_mode(state_bool)
            return f"Debug mode is now {'ON' if state_bool else 'OFF'}."

        if len(parts) == 2:
            module_name, state = parts[0], parts[1]
            state_bool = state.lower() in ("on", "true", "1", "enable")
            if module_name not in self.bot.pm.plugins:
                return f"Module '{module_name}' is not loaded."
            self.bot.set_module_debug(module_name, state_bool)
            return f"Debug for '{module_name}' is now {'ON' if state_bool else 'OFF'}."

        return "Usage: debug <on|off> or debug <module_name> <on|off>"

    def _cmd_config(self, args: str) -> str:
        if args.strip().lower() != "reload":
            return "Usage: config reload"
        if self.bot.core_reload_config():
            return "Configuration reloaded from config.yaml."
        return "Failed to reload configuration."

    def _cmd_kill(self) -> str:
        self._record_event("Jeeves is shutting down via Discord admin API.")
        self.bot.connection.quit("Killed via Discord.")
        threading.Timer(0.2, lambda: os._exit(42)).start()
        return "Shutting down Jeeves..."

    def _cmd_status(self) -> str:
        connected = self.bot.connection.is_connected()
        channels = ", ".join(sorted(self.bot.joined_channels)) or "(none)"
        module_count = len(self.bot.pm.plugins)
        debug = "ON" if self.bot.debug_mode else "OFF"
        return (
            "discord: connected via shared router\n"
            f"IRC: {'connected' if connected else 'disconnected'}\n"
            f"Channels: {channels}\n"
            f"Modules loaded: {module_count}\n"
            f"Debug: {debug}"
        )

    def _cmd_help(self) -> str:
        lines = ["Jeeves admin commands via Discord:"]
        for cmd, (_, desc) in sorted(self._builtin_routes.items()):
            lines.append(f"{cmd} - {desc}")

        plugin_cmds = self._plugin_commands()
        if plugin_cmds:
            lines.append("")
            lines.append("Module commands:")
            for cmd, (_, desc) in sorted(plugin_cmds.items()):
                lines.append(f"{cmd} - {desc}")

        return "\n".join(lines)
