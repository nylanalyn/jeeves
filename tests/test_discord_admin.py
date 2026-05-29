import importlib
import unittest
from types import SimpleNamespace


discord_module = importlib.import_module("modules.discord")
Discord = discord_module.Discord


class ConnectionStub:
    def __init__(self):
        self.sent = []
        self.joined = []
        self.parted = []
        self.quit_message = None
        self.connected = True

    def is_connected(self):
        return self.connected

    def privmsg(self, target, message):
        self.sent.append((target, message))

    def join(self, channel):
        self.joined.append(channel)

    def part(self, channel, message):
        self.parted.append((channel, message))

    def quit(self, message):
        self.quit_message = message


class PluginStub:
    @property
    def matrix_admin_commands(self):
        return {
            "!quest challenge list": (lambda args: f"challenges {args}".strip(), "list challenges"),
        }


class BotStub:
    def __init__(self):
        self.config = {"discord": {"enabled": False}}
        self.connection = ConnectionStub()
        self.joined_channels = {"#test"}
        self.debug_mode = False
        self.pm = SimpleNamespace(plugins={"plugin": PluginStub()})
        self.loaded = ["admin", "discord", "quest"]
        self.debug_messages = []

    def core_reload_plugins(self):
        return self.loaded

    def core_reload_config(self):
        return True

    def set_debug_mode(self, status):
        self.debug_mode = status

    def set_module_debug(self, module_name, status):
        self.module_debug = (module_name, status)

    def log_debug(self, message):
        self.debug_messages.append(message)


def make_discord_admin():
    admin = Discord.__new__(Discord)
    admin.bot = BotStub()
    admin._event_lock = discord_module.threading.RLock()
    admin._events = []
    admin._next_event_id = 1
    return admin


class TestDiscordAdminCommands(unittest.TestCase):
    def test_builtin_status_and_modules_match_router_command_shape(self):
        admin = make_discord_admin()

        status = admin._execute("status")
        modules = admin._execute("modules")

        self.assertIn("discord: connected via shared router", status[0])
        self.assertIn("IRC: connected", status[0])
        self.assertEqual(modules, ["Loaded modules (1): plugin"])

    def test_say_sanitizes_and_sends_to_irc(self):
        admin = make_discord_admin()

        result = admin._execute("say", "#test hello\r\nworld")

        self.assertEqual(result, ["Sent to #test: hello world"])
        self.assertEqual(admin.bot.connection.sent, [("#test", "hello world")])

    def test_plugin_matrix_admin_commands_work_without_bang_prefix(self):
        admin = make_discord_admin()

        result = admin._execute("quest", "challenge list all")

        self.assertEqual(result, ["challenges all"])

    def test_event_polling_returns_only_newer_events(self):
        admin = make_discord_admin()
        admin._record_event("one")
        admin._record_event("two")

        self.assertEqual([e["message"] for e in admin._get_events_since(1)], ["two"])

    def test_admin_api_config_is_used_when_default_discord_config_is_disabled(self):
        admin = make_discord_admin()
        admin.bot.config = {
            "discord": {"enabled": False},
            "admin_api": {"enabled": True, "host": "127.0.0.1", "port": 9111, "token": "t"},
        }

        self.assertEqual(admin._discord_config()["port"], 9111)


if __name__ == "__main__":
    unittest.main()
