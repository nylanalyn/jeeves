import copy
import re
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from modules.wordle import Wordle
from modules.house import House


class FakeConnection:
    def __init__(self):
        self.messages = []

    def privmsg(self, target, text):
        self.messages.append((target, text))


class FakeUsersModule:
    def __init__(self, user_map):
        self.user_map = user_map

    def get_state(self, key=None, default=None):
        if key == "user_map":
            return self.user_map
        return default


class FakeBot:
    def __init__(self, root, words_file, dict_file, state=None, joined_channels=None, admins=None):
        self.ROOT = Path(root)
        self.config = {
            "wordle": {
                "allowed_channels": ["#test"],
                "max_attempts_per_user": 3,
                "word_list_file": str(words_file),
                "dictionary_file": str(dict_file),
            }
        }
        self.joined_channels = set(joined_channels if joined_channels is not None else ["#test"])
        self.admins = set(admins or [])
        self.module_states = {"wordle": copy.deepcopy(state or {})}
        self.debug_messages = []
        self.user_ids = {}
        self.user_map = {}
        self.pm = SimpleNamespace(plugins={"users": FakeUsersModule(self.user_map)})

    def get_module_state(self, name):
        return copy.deepcopy(self.module_states.get(name, {}))

    def update_module_state(self, name, state):
        self.module_states[name] = copy.deepcopy(state)

    def log_debug(self, message):
        self.debug_messages.append(message)

    def get_user_id(self, username):
        key = username.lower()
        user_id = self.user_ids.setdefault(key, f"user:{key}")
        self.user_map[user_id] = {"canonical_nick": username}
        return user_id

    def title_for(self, username):
        return f"Sir {username}"

    def is_admin(self, source):
        nick = getattr(source, "nick", str(source))
        return nick in self.admins


class WordleHarness:
    def __init__(self, words, dictionary=None, state=None, joined_channels=None, admins=None):
        self.tempdir = tempfile.TemporaryDirectory()
        root = Path(self.tempdir.name)
        self.words_file = root / "words.txt"
        self.dict_file = root / "dict.txt"
        self.words_file.write_text("\n".join(words) + "\n", encoding="utf-8")
        dictionary = dictionary or []
        self.dict_file.write_text("\n".join(dictionary) + "\n", encoding="utf-8")
        self.bot = FakeBot(
            root,
            self.words_file,
            self.dict_file,
            state=state,
            joined_channels=joined_channels,
            admins=admins,
        )
        self.module = Wordle(self.bot)
        self.connection = FakeConnection()

    def close(self):
        self.tempdir.cleanup()

    def event(self, username="Alice", channel="#test"):
        return SimpleNamespace(target=channel, source=SimpleNamespace(nick=username))

    def dispatch(self, message, username="Alice", channel="#test"):
        event = self.event(username=username, channel=channel)
        handled = self.module._dispatch_commands(self.connection, event, message, username)
        return handled

    @property
    def replies(self):
        return [message for _, message in self.connection.messages]


class TestWordleEvaluation(unittest.TestCase):
    def test_duplicate_letters_follow_standard_wordle_rules(self):
        self.assertEqual(
            Wordle._evaluate_guess("teller", "letter"),
            ["present", "correct", "present", "absent", "correct", "correct"],
        )
        self.assertEqual(
            Wordle._evaluate_guess("aahing", "abacus"),
            ["correct", "present", "absent", "absent", "absent", "absent"],
        )

    def test_compute_discovered_does_not_mark_known_letters_absent(self):
        harness = WordleHarness(
            words=["letter"],
            dictionary=["teller"],
        )
        try:
            today = {
                "word": "letter",
                "guesses": {"user:alice": ["teller"]},
            }
            discovered = harness.module._compute_discovered(today)
        finally:
            harness.close()

        self.assertEqual(discovered["correct"], [None, "e", None, None, "e", "r"])
        self.assertEqual(discovered["present"], ["l", "t"])
        self.assertNotIn("l", discovered["absent"])
        self.assertNotIn("t", discovered["absent"])


class TestWordleCommands(unittest.TestCase):
    def test_status_initializes_today_and_restart_reuses_selected_word(self):
        harness = WordleHarness(words=["anchor"], dictionary=[])
        try:
            with patch("modules.wordle.random.choice", side_effect=lambda words: words[0]):
                self.assertTrue(harness.dispatch("!word"))

            self.assertIn("Today's word: _ _ _ _ _ _", harness.replies[-1])
            state = harness.bot.module_states["wordle"]
            self.assertEqual(state["today"]["word"], "anchor")
            self.assertEqual(state["used_words"], ["anchor"])

            restarted = WordleHarness(words=["anchor"], dictionary=[], state=state)
            try:
                self.assertTrue(restarted.dispatch("!word"))
                self.assertEqual(restarted.bot.module_states["wordle"]["used_words"], ["anchor"])
                self.assertEqual(restarted.bot.module_states["wordle"]["today"]["word"], "anchor")
            finally:
                restarted.close()
        finally:
            harness.close()

    def test_guess_flow_attempt_limit_and_solved_state(self):
        harness = WordleHarness(
            words=["anchor"],
            dictionary=["castle", "police", "abacus", "anchor"],
        )
        try:
            with patch("modules.wordle.random.choice", side_effect=lambda words: words[0]):
                self.assertTrue(harness.dispatch("!word castle", username="Alice"))
            self.assertIn("The word contains", harness.replies[-1])
            self.assertIn("a, c", harness.replies[-1])

            self.assertTrue(harness.dispatch("!word police", username="Alice"))
            self.assertTrue(harness.dispatch("!word abacus", username="Alice"))
            self.assertTrue(harness.dispatch("!word anchor", username="Alice"))
            self.assertIn("exhausted your 3 attempts", harness.replies[-1])
            self.assertFalse(harness.bot.module_states["wordle"]["today"]["solved"])

            self.assertTrue(harness.dispatch("!word anchor", username="Bob"))
            self.assertEqual(
                harness.replies[-1],
                "Today's word was: ANCHOR. Well deduced, Sir Bob! Try again tomorrow.",
            )
            today = harness.bot.module_states["wordle"]["today"]
            self.assertTrue(today["solved"])
            self.assertEqual(today["solved_by"], "user:bob")

            self.assertTrue(harness.dispatch("!word", username="Charlie"))
            self.assertIn("Today's word was: ANCHOR", harness.replies[-1])
            self.assertIn("Try again tomorrow", harness.replies[-1])

            stats = harness.bot.module_states["wordle"]["stats"]
            self.assertEqual(stats["user:alice"], {"wins": 0, "games_played": 1})
            self.assertEqual(stats["user:bob"], {"wins": 1, "games_played": 1})
        finally:
            harness.close()

    def test_invalid_length_and_unknown_words_are_rejected(self):
        harness = WordleHarness(words=["anchor"], dictionary=["anchor"])
        try:
            self.assertTrue(harness.dispatch("!word abc", username="Alice"))
            self.assertEqual(harness.replies[-1], "A six-letter word is required, if you please, sir.")

            self.assertTrue(harness.dispatch("!word zzzzzz", username="Alice"))
            self.assertEqual(harness.replies[-1], "I'm afraid that word isn't in my dictionary, sir.")
            self.assertIsNone(harness.bot.module_states["wordle"]["today"])
        finally:
            harness.close()

    def test_unsolved_word_carries_over_with_fresh_attempts_and_known_clues(self):
        state = {
            "used_words": ["anchor"],
            "today": {
                "date": "2000-01-01",
                "word": "anchor",
                "solved": False,
                "solved_by": None,
                "guesses": {"user:alice": ["castle", "police", "abacus"]},
                "discovered": {"correct": ["a", None, None, None, None, None], "present": ["c"], "absent": ["e"]},
            },
            "stats": {},
        }
        harness = WordleHarness(words=["anchor", "castle"], dictionary=[], state=state)
        try:
            with patch("modules.wordle.random.choice", side_effect=lambda words: words[0]):
                today = harness.module._ensure_today()
            self.assertEqual(today["word"], "anchor")
            self.assertEqual(today["guesses"], {})
            self.assertEqual(today["discovered"]["correct"], ["a", None, None, None, None, None])
            self.assertEqual(today["discovered"]["present"], ["c"])
            self.assertEqual(today["discovered"]["absent"], ["e"])
            self.assertEqual(harness.bot.module_states["wordle"]["used_words"], ["anchor"])
            self.assertIsNone(harness.bot.module_states["wordle"]["yesterday"])

            self.assertTrue(harness.dispatch("!word anchor", username="Alice"))
            self.assertIn("Well deduced", harness.replies[-1])
        finally:
            harness.close()

    def test_solved_word_advances_to_new_word_next_day(self):
        state = {
            "used_words": ["anchor"],
            "today": {
                "date": "2000-01-01",
                "word": "anchor",
                "solved": True,
                "solved_by": "user:alice",
                "guesses": {"user:alice": ["anchor"]},
                "discovered": {"correct": list("anchor"), "present": [], "absent": []},
            },
            "stats": {},
        }
        harness = WordleHarness(words=["anchor", "castle"], dictionary=[], state=state)
        try:
            with patch("modules.wordle.random.choice", side_effect=lambda words: words[0]):
                today = harness.module._ensure_today()
            self.assertEqual(today["word"], "castle")
            self.assertEqual(harness.bot.module_states["wordle"]["used_words"], ["anchor", "castle"])
            self.assertEqual(
                harness.bot.module_states["wordle"]["yesterday"],
                {
                    "date": "2000-01-01",
                    "word": "anchor",
                    "solved": True,
                    "solved_by": "user:alice",
                },
            )
        finally:
            harness.close()

    def test_status_after_guess_shows_community_discoveries(self):
        harness = WordleHarness(words=["anchor"], dictionary=["castle"])
        try:
            with patch("modules.wordle.random.choice", side_effect=lambda words: words[0]):
                harness.dispatch("!word castle", username="Alice")
            harness.dispatch("!word", username="Bob")
            self.assertIn("Letters present: a, c", harness.replies[-1])
            for absent in ["e", "l", "s", "t"]:
                self.assertIn(absent, harness.replies[-1])
        finally:
            harness.close()

    def test_stats_and_top_commands(self):
        state = {
            "used_words": [],
            "today": None,
            "stats": {
                "user:alice": {"wins": 2, "games_played": 3},
                "user:bob": {"wins": 5, "games_played": 9},
            },
        }
        harness = WordleHarness(words=["anchor"], dictionary=[], state=state)
        try:
            harness.bot.get_user_id("Alice")
            harness.bot.get_user_id("Bob")
            self.assertTrue(harness.dispatch("!word stats", username="Alice"))
            self.assertIn("2 wins in 3 games (67%)", harness.replies[-1])

            self.assertTrue(harness.dispatch("!word top", username="Alice"))
            self.assertIn("Bob (5)", harness.replies[-1])
            self.assertIn("Alice (2)", harness.replies[-1])
        finally:
            harness.close()

    def test_house_status_reports_current_and_yesterday_wordle(self):
        state = {
            "used_words": ["anchor"],
            "today": {
                "date": "2000-01-01",
                "word": "anchor",
                "solved": False,
                "solved_by": None,
                "guesses": {},
                "discovered": {"correct": [None] * 6, "present": [], "absent": []},
            },
            "yesterday": {"date": "1999-12-31", "word": "castle"},
            "stats": {},
        }
        harness = WordleHarness(words=["anchor", "police"], dictionary=[], state=state)
        try:
            today = harness.module.get_state("today")
            today["date"] = harness.module._today_date()
            harness.module.set_state("today", today)
            harness.module.save_state()

            self.assertEqual(
                harness.module.house_status("#test"),
                "Wordle: currently not solved. Yesterday's word was CASTLE.",
            )

            today = harness.module.get_state("today")
            today["solved"] = True
            today["word"] = "police"
            harness.module.set_state("today", today)
            harness.module.save_state()

            self.assertEqual(
                harness.module.house_status("#test"),
                "Wordle: solved; the word was POLICE. Yesterday's word was CASTLE.",
            )
        finally:
            harness.close()

    def test_house_command_includes_wordle_status_when_loaded(self):
        state = {
            "used_words": ["anchor"],
            "today": {
                "date": "2000-01-01",
                "word": "anchor",
                "solved": False,
                "solved_by": None,
                "guesses": {},
                "discovered": {"correct": [None] * 6, "present": [], "absent": []},
            },
            "yesterday": {"date": "1999-12-31", "word": "castle"},
            "stats": {},
        }
        harness = WordleHarness(words=["anchor", "police"], dictionary=[], state=state)
        try:
            today = harness.module.get_state("today")
            today["date"] = harness.module._today_date()
            harness.module.set_state("today", today)
            harness.module.save_state()

            harness.bot.pm.plugins.update(
                {
                    "birthday": SimpleNamespace(house_status=lambda channel: "Birthdays: next one in 7 days."),
                    "fishing": SimpleNamespace(house_status=lambda channel: "Fishing: 31 fishers, 20 lines out."),
                    "fortune": SimpleNamespace(house_status=lambda channel: "Fortunes: 681 available."),
                    "hunt": SimpleNamespace(house_status=lambda channel: "Hunt: 151 guests have animal records."),
                    "karma": SimpleNamespace(house_status=lambda channel: "Karma: 165 people scored."),
                    "memos": SimpleNamespace(house_status=lambda channel: "Memos: 19 pending."),
                    "wordle": harness.module,
                }
            )
            house = House(harness.bot)
            connection = FakeConnection()

            handled = house._cmd_house(connection, harness.event(), "!house", "Alice", None)

            self.assertTrue(handled)
            self.assertEqual(len(connection.messages), 1)
            report = connection.messages[0][1]
            self.assertIn("Wordle: currently not solved. Yesterday's word was CASTLE.", report)
            self.assertIn("Birthdays: next one in 7 days.", report)
            self.assertIn("Memos: 19 pending.", report)
            self.assertNotIn("Hunt: 151 guests have animal records.", report)
            self.assertNotIn("Karma: 165 people scored.", report)
        finally:
            harness.close()

    def test_admin_new_day_is_gated_and_forces_new_word(self):
        harness = WordleHarness(
            words=["anchor", "castle"],
            dictionary=[],
            admins=["Admin"],
        )
        try:
            with patch("modules.wordle.random.choice", side_effect=lambda words: words[0]):
                self.assertTrue(harness.dispatch("!word", username="Alice"))
                self.assertTrue(harness.dispatch("!word new", username="Alice"))
                self.assertIn("reserved for the master", harness.replies[-1])
                self.assertEqual(harness.bot.module_states["wordle"]["today"]["word"], "anchor")

                self.assertTrue(harness.dispatch("!word new", username="Admin"))
            self.assertEqual(harness.replies[-1], "As you wish. A fresh Wordle has been laid out for the household.")
            self.assertEqual(harness.bot.module_states["wordle"]["today"]["word"], "castle")
        finally:
            harness.close()

    def test_joined_channel_check_suppresses_response(self):
        harness = WordleHarness(words=["anchor"], dictionary=[], joined_channels=[])
        try:
            self.assertFalse(harness.dispatch("!word", username="Alice"))
            self.assertEqual(harness.replies, [])
        finally:
            harness.close()


if __name__ == "__main__":
    unittest.main()
