# tests/test_caw.py
import re
import threading
import time
import types
import sys
import unittest


def _install_stubs():
    for mod_name in ["irc", "irc.bot", "irc.connection"]:
        if mod_name not in sys.modules:
            sys.modules[mod_name] = types.ModuleType(mod_name)
    if "irc.bot" in sys.modules:
        sys.modules["irc.bot"].SingleServerIRCBot = object
    if "irc.connection" in sys.modules:
        sys.modules["irc.connection"].Factory = lambda *a, **kw: None
    if "schedule" not in sys.modules:
        sched = types.ModuleType("schedule")
        sched.every = lambda *a, **kw: sched
        sched.seconds = sched
        sched.do = lambda *a, **kw: None
        sched.get_jobs = lambda: []
        sched.cancel_job = lambda j: None
        sched.CancelJob = object()
        sys.modules["schedule"] = sched


_install_stubs()

from modules.caw import Caw  # noqa: E402


def _make_caw():
    """Build a Caw instance with all bot/state calls stubbed out."""
    c = Caw.__new__(Caw)
    c._state_cache = {"last_response_time": 0.0}
    c._state_lock = threading.RLock()
    c._state_dirty = False

    c.RE_CAW = re.compile(r'\bCAW\b', re.IGNORECASE)

    c._replies = []
    c.safe_reply = lambda conn, evt, text: c._replies.append(text)
    c.save_state = lambda force=False: None
    c.is_enabled = lambda target: True
    c.get_config_value = lambda key, target, default: default

    class _BotStub:
        def title_for(self, username):
            return f"Sir {username}"

    c.bot = _BotStub()
    return c


def _make_event(target="#test"):
    return types.SimpleNamespace(target=target)


class TestCawTriggers(unittest.TestCase):
    def test_uppercase_caw_triggers_response(self):
        c = _make_caw()
        result = c.on_ambient_message(None, _make_event(), "CAW", "alice")
        self.assertTrue(result)
        self.assertEqual(len(c._replies), 1)

    def test_lowercase_caw_triggers_response(self):
        c = _make_caw()
        result = c.on_ambient_message(None, _make_event(), "caw", "alice")
        self.assertTrue(result)
        self.assertEqual(len(c._replies), 1)

    def test_mixed_case_caw_triggers_response(self):
        c = _make_caw()
        result = c.on_ambient_message(None, _make_event(), "Caw", "alice")
        self.assertTrue(result)
        self.assertEqual(len(c._replies), 1)

    def test_bang_caw_triggers_response(self):
        c = _make_caw()
        result = c.on_ambient_message(None, _make_event(), "!caw", "alice")
        self.assertTrue(result)
        self.assertEqual(len(c._replies), 1)

    def test_bang_caw_uppercase_triggers_response(self):
        c = _make_caw()
        result = c.on_ambient_message(None, _make_event(), "!CAW", "alice")
        self.assertTrue(result)
        self.assertEqual(len(c._replies), 1)

    def test_caw_embedded_in_word_does_not_trigger(self):
        """'cawing' should not match the whole-word CAW pattern."""
        c = _make_caw()
        result = c.on_ambient_message(None, _make_event(), "the crow was cawing away", "alice")
        self.assertFalse(result)
        self.assertEqual(len(c._replies), 0)

    def test_bang_caw_embedded_in_word_does_not_trigger(self):
        """!cawing should not match - the word boundary applies to the bang form too."""
        c = _make_caw()
        result = c.on_ambient_message(None, _make_event(), "!cawing", "alice")
        self.assertFalse(result)
        self.assertEqual(len(c._replies), 0)

    def test_unrelated_message_does_not_trigger(self):
        c = _make_caw()
        result = c.on_ambient_message(None, _make_event(), "hello there", "alice")
        self.assertFalse(result)
        self.assertEqual(len(c._replies), 0)

    def test_caw_mid_sentence_triggers_response(self):
        """CAW as a standalone word within a sentence should still trigger."""
        c = _make_caw()
        result = c.on_ambient_message(None, _make_event(), "goes like CAW into the void", "alice")
        self.assertTrue(result)
        self.assertEqual(len(c._replies), 1)


class TestCawCooldown(unittest.TestCase):
    def test_cooldown_prevents_immediate_second_response(self):
        c = _make_caw()
        c.on_ambient_message(None, _make_event(), "CAW", "alice")
        result = c.on_ambient_message(None, _make_event(), "CAW", "alice")
        self.assertFalse(result)
        self.assertEqual(len(c._replies), 1)

    def test_response_fires_after_cooldown_expires(self):
        c = _make_caw()
        c.on_ambient_message(None, _make_event(), "CAW", "alice")
        # Manually push last_response_time into the past
        c._state_cache["last_response_time"] = time.time() - 10.0
        result = c.on_ambient_message(None, _make_event(), "CAW", "alice")
        self.assertTrue(result)
        self.assertEqual(len(c._replies), 2)

    def test_disabled_channel_does_not_respond(self):
        c = _make_caw()
        c.is_enabled = lambda target: False
        result = c.on_ambient_message(None, _make_event(), "CAW", "alice")
        self.assertFalse(result)
        self.assertEqual(len(c._replies), 0)


class TestCawResponseContent(unittest.TestCase):
    def test_response_contains_title(self):
        c = _make_caw()
        c.on_ambient_message(None, _make_event(), "CAW", "alice")
        self.assertIn("Sir alice", c._replies[0])

    def test_response_is_nonempty_string(self):
        c = _make_caw()
        c.on_ambient_message(None, _make_event(), "CAW", "alice")
        self.assertIsInstance(c._replies[0], str)
        self.assertGreater(len(c._replies[0]), 0)


if __name__ == "__main__":
    unittest.main()
