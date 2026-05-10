import time
from types import SimpleNamespace

from modules.hints import Hints
from modules.house import House
from modules.welcome import Welcome


class BotStub:
    def __init__(self, plugins=None):
        self.config = {}
        self.primary_channel = "#test"
        self.pm = SimpleNamespace(plugins=plugins or {})
        self._states = {}

    def get_module_state(self, name):
        return self._states.setdefault(name, {})

    def update_module_state(self, name, updates):
        self._states.setdefault(name, {}).update(updates)

    def get_user_id(self, username):
        return username.lower()

    def title_for(self, username):
        return username

    def is_admin(self, source):
        return False


class ConnectionStub:
    def __init__(self):
        self.messages = []

    def privmsg(self, target, text):
        self.messages.append((target, text))


def event(target="#test", source="Alice!user@example.test"):
    return SimpleNamespace(target=target, source=source)


class StatusPlugin:
    def house_status(self, channel):
        return f"Status for {channel}."

    def welcome_summary(self, channel):
        return f"Welcome for {channel}."


class HintPlugin:
    def contextual_hint(self, msg, username, channel):
        if "weather" in msg:
            return "Use !weather after setting !location."
        return None


def test_house_collects_loaded_module_status():
    bot = BotStub({"sample": StatusPlugin()})
    house = House(bot)
    bot.pm.plugins["house"] = house
    connection = ConnectionStub()

    handled = house._cmd_house(connection, event(), "!house", "Alice", None)

    assert handled
    assert connection.messages == [
        ("#test", "Household report: Status for #test.")
    ]


def test_house_falls_back_to_loaded_services_when_no_status_hooks():
    bot = BotStub({"fortune": object()})
    house = House(bot)
    bot.pm.plugins["house"] = house
    connection = ConnectionStub()

    house._cmd_house(connection, event(), "!house", "Alice", None)

    assert "Available services include fortune." in connection.messages[0][1]


def test_house_excludes_hunt_and_karma_from_status_and_fallback_services():
    bot = BotStub(
        {
            "hunt": StatusPlugin(),
            "karma": StatusPlugin(),
            "memos": StatusPlugin(),
            "fortune": object(),
        }
    )
    house = House(bot)
    bot.pm.plugins["house"] = house
    connection = ConnectionStub()

    house._cmd_house(connection, event(), "!house", "Alice", None)

    report = connection.messages[0][1]
    assert "Memos" in report or "Status for #test." in report
    assert "Hunt" not in report
    assert "Karma" not in report
    assert "karma" not in house._loaded_services_line()
    assert "hunt" not in house._loaded_services_line()

def test_welcome_collects_loaded_module_summaries_privately():
    bot = BotStub({"sample": StatusPlugin()})
    welcome = Welcome(bot)
    bot.pm.plugins["welcome"] = welcome
    connection = ConnectionStub()
    bot.connection = connection

    handled = welcome._cmd_welcome(connection, event(), "!welcome", "Alice", SimpleNamespace(group=lambda index: None))

    assert handled
    assert ("#test", "I have sent you a brief welcome privately, Alice.") in connection.messages
    assert ("Alice", "- Welcome for #test.") in connection.messages


def test_hints_uses_loaded_module_hooks_and_records_cooldown():
    bot = BotStub({"hint_source": HintPlugin()})
    hints = Hints(bot)
    bot.pm.plugins["hints"] = hints
    connection = ConnectionStub()

    handled = hints.on_ambient_message(connection, event(), "what about weather", "Alice")

    assert handled is False
    assert connection.messages == [
        ("#test", "A brief note, if I may: Use !weather after setting !location.")
    ]
    assert bot.get_module_state("hints")["last_channel_hint"]["#test"] <= time.time()


def test_hints_respects_channel_cooldown():
    bot = BotStub({"hint_source": HintPlugin()})
    bot._states["hints"] = {
        "last_channel_hint": {"#test": time.time()},
        "last_user_hint": {},
    }
    hints = Hints(bot)
    bot.pm.plugins["hints"] = hints
    connection = ConnectionStub()

    hints.on_ambient_message(connection, event(), "what about weather", "Alice")

    assert connection.messages == []
