import re
import unittest
from types import SimpleNamespace

from modules.memos import Memos


class ConnectionStub:
    def __init__(self):
        self.messages = []

    def privmsg(self, target, text):
        self.messages.append((target, text))


class UsersStub:
    def __init__(self, user_map):
        self.user_map = user_map

    def get_state(self, key=None, default=None):
        if key == "user_map":
            return self.user_map
        return default


class BotStub:
    def __init__(self, state=None, admins=None):
        self.config = {"memos": {"allowed_channels": ["#test"]}}
        self.primary_channel = "#test"
        self._states = {"memos": state or {}}
        self.admins = set(admins or {"Admin"})
        self.user_ids = {
            "alice": "user:alice",
            "bob": "user:bob",
            "yourmom": "user:yourmom",
        }
        self.user_map = {
            "user:alice": {"canonical_nick": "Alice"},
            "user:bob": {"canonical_nick": "Bob"},
            "user:yourmom": {"canonical_nick": "yourmom"},
        }
        self.pm = SimpleNamespace(plugins={"users": UsersStub(self.user_map)})
        self.debug_messages = []

    def get_module_state(self, name):
        return self._states.setdefault(name, {}).copy()

    def update_module_state(self, name, state):
        self._states[name] = state.copy()

    def get_user_id(self, username):
        return self.user_ids.setdefault(username.lower(), f"user:{username.lower()}")

    def title_for(self, username):
        return f"Sir {username}"

    def is_admin(self, source):
        nick = getattr(source, "nick", str(source))
        return nick in self.admins

    def get_utc_time(self):
        return "2026-05-10T12:00:00Z"

    def pronouns_for(self, username):
        return "they/them"

    def log_debug(self, message):
        self.debug_messages.append(message)


def event(username="Admin", target="#test"):
    return SimpleNamespace(target=target, source=SimpleNamespace(nick=username))


def make_memos():
    state = {
        "pending": {
            "#test": {
                "user:alice": [
                    {"from": "Bob", "text": "first memo", "when": "2026-05-01T09:00:00Z"},
                    {"from": "Carol", "text": "second memo", "when": "2026-05-02T09:00:00Z"},
                ],
                "user:yourmom": [
                    {"from": "Alice", "text": "wrong target", "when": "2026-05-03T09:00:00Z"},
                ],
            },
            "#other": {
                "user:bob": [
                    {"from": "Alice", "text": "other channel", "when": "2026-05-04T09:00:00Z"},
                ],
            },
        }
    }
    bot = BotStub(state)
    memos = Memos(bot)
    bot.pm.plugins["memos"] = memos
    connection = ConnectionStub()
    bot.connection = connection
    return bot, memos, connection


def dispatch(memos, connection, message, username="Admin"):
    return memos._dispatch_commands(connection, event(username=username), message, username)


def memo_ids_from_messages(messages):
    ids = []
    for _, text in messages:
        ids.extend(re.findall(r"\b[0-9a-f]{10}\b", text))
    return ids


class TestMemoAdminCommands(unittest.TestCase):
    def test_admin_summary_and_list_privately_show_pending_memo_ids(self):
        _, memos, connection = make_memos()

        self.assertTrue(dispatch(memos, connection, "!memos admin summary"))
        self.assertEqual(
            connection.messages[-1],
            (
                "#test",
                "4 pending memo(s). By channel: #other: 1, #test: 3. Top recipients: Alice: 2, Bob: 1, yourmom: 1.",
            ),
        )

        self.assertTrue(dispatch(memos, connection, "!memos admin list #test 2"))
        self.assertEqual(connection.messages[1][0], "#test")
        private_lines = [message for target, message in connection.messages if target == "Admin"]
        self.assertEqual(len(private_lines), 3)
        self.assertIn("#test -> Alice from Bob", private_lines[0])
        self.assertIn("#test -> Alice from Carol", private_lines[1])
        self.assertTrue(private_lines[2].startswith("...and 1 more"))
        self.assertGreaterEqual(len(memo_ids_from_messages(connection.messages)), 2)

    def test_admin_show_and_clear_one_memo_by_id(self):
        bot, memos, connection = make_memos()
        memo_id = next(entry["id"] for entry in memos._iter_pending_memos() if entry["text"] == "first memo")

        self.assertTrue(dispatch(memos, connection, f"!memos admin show {memo_id}"))
        self.assertEqual(connection.messages[-2], ("#test", "Sir Admin, I have sent that memo privately."))
        self.assertEqual(connection.messages[-1][0], "Admin")
        self.assertIn("first memo", connection.messages[-1][1])

        self.assertTrue(dispatch(memos, connection, f"!memos admin clear {memo_id}"))
        self.assertEqual(connection.messages[-1], ("#test", f"Cleared memo {memo_id} for Alice in #test."))
        pending = bot._states["memos"]["pending"]
        self.assertEqual(len(pending["#test"]["user:alice"]), 1)
        self.assertEqual(pending["#test"]["user:alice"][0]["text"], "second memo")

    def test_admin_clear_recipient_removes_wrong_target_bucket(self):
        bot, memos, connection = make_memos()

        self.assertTrue(dispatch(memos, connection, "!memos admin clear-recipient yourmom #test"))
        self.assertEqual(connection.messages[-1], ("#test", "Cleared 1 pending memo(s) for yourmom in #test."))
        self.assertNotIn("user:yourmom", bot._states["memos"]["pending"]["#test"])

    def test_non_admin_cannot_use_memo_admin_commands(self):
        bot, memos, connection = make_memos()

        self.assertTrue(dispatch(memos, connection, "!memos admin summary", username="Alice"))
        self.assertEqual(
            connection.messages[-1],
            (
                "#test",
                "I'm terribly sorry, Alice, but that command is reserved for the master of the house.",
            ),
        )
        self.assertTrue(bot._states["memos"]["pending"]["#test"]["user:yourmom"])

    def test_matrix_admin_commands_share_same_memo_admin_behaviour(self):
        _, memos, _ = make_memos()
        commands = memos.matrix_admin_commands
        memo_id = next(entry["id"] for entry in memos._iter_pending_memos() if entry["text"] == "first memo")

        self.assertIn("4 pending memo(s)", commands["!memos admin summary"][0](""))
        self.assertIn("#test -> Alice from Bob", commands["!memos admin list"][0]("#test 1"))
        self.assertIn("first memo", commands["!memos admin show"][0](memo_id))
        self.assertEqual(commands["!memos admin clear"][0](memo_id), f"Cleared memo {memo_id} for Alice in #test.")
        self.assertEqual(
            commands["!memos admin clear-recipient"][0]("yourmom #test"),
            "Cleared 1 pending memo(s) for yourmom in #test.",
        )


if __name__ == "__main__":
    unittest.main()
