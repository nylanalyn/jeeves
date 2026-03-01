import unittest

import sys
import types


def _install_dependency_stubs():
    if "irc" not in sys.modules:
        irc_module = types.ModuleType("irc")
        irc_bot_module = types.ModuleType("irc.bot")
        irc_connection_module = types.ModuleType("irc.connection")

        class SingleServerIRCBot:
            pass

        class Factory:
            def __init__(self, *args, **kwargs):
                pass

        irc_bot_module.SingleServerIRCBot = SingleServerIRCBot
        irc_connection_module.Factory = Factory

        sys.modules["irc"] = irc_module
        sys.modules["irc.bot"] = irc_bot_module
        sys.modules["irc.connection"] = irc_connection_module

    if "schedule" not in sys.modules:
        schedule_module = types.ModuleType("schedule")

        def run_pending():
            return None

        schedule_module.run_pending = run_pending
        sys.modules["schedule"] = schedule_module


_install_dependency_stubs()

from jeeves import Jeeves


class _CourtesyStub:
    def __init__(self, profile):
        self._profile = profile

    def _get_user_profile(self, user_id):
        return self._profile


class _QuestStub:
    def __init__(self, suffix):
        self._suffix = suffix

    def get_legend_suffix_for_user(self, user_id):
        return self._suffix


class _FishingStub:
    def __init__(self, suffix):
        self._suffix = suffix

    def get_fishing_suffix_for_user(self, user_id):
        return self._suffix


class _PluginManagerStub:
    def __init__(self, plugins):
        self.plugins = plugins


def _make_bot(*, courtesy_profile=None, quest_suffix=None, fishing_suffix=None):
    bot = Jeeves.__new__(Jeeves)
    plugins = {}
    if courtesy_profile is not None:
        plugins["courtesy"] = _CourtesyStub(courtesy_profile)
    if quest_suffix is not None:
        plugins["quest"] = _QuestStub(quest_suffix)
    if fishing_suffix is not None:
        plugins["fishing"] = _FishingStub(fishing_suffix)
    bot.pm = _PluginManagerStub(plugins)
    def _get_user_id(nick):
        return f"user-id-for:{nick}"
    bot.get_user_id = _get_user_id
    return bot


class TestTitleFor(unittest.TestCase):
    def test_title_for_defaults_to_nick(self):
        bot = _make_bot()
        self.assertEqual(bot.title_for("Alice"), "Alice")

    def test_title_for_uses_sir_and_madam(self):
        bot = _make_bot(courtesy_profile={"title": "sir"})
        self.assertEqual(bot.title_for("Alice"), "Sir")

        bot = _make_bot(courtesy_profile={"title": "madam"})
        self.assertEqual(bot.title_for("Alice"), "Madam")

    def test_title_for_uses_custom_titles(self):
        bot = _make_bot(courtesy_profile={"title": "archmage"})
        self.assertEqual(bot.title_for("Alice"), "Archmage")

    def test_title_for_neutral_preserves_nick(self):
        bot = _make_bot(courtesy_profile={"title": "neutral"})
        self.assertEqual(bot.title_for("Alice"), "Alice")

    def test_title_for_appends_quest_suffix(self):
        bot = _make_bot(courtesy_profile={"title": "archmage"}, quest_suffix="the Brave")
        self.assertEqual(bot.title_for("Alice"), "Archmage the Brave")


class TestTitleForFishingSuffix(unittest.TestCase):
    def test_fishing_suffix_appended_to_nick(self):
        bot = _make_bot(fishing_suffix="the Traveler")
        self.assertEqual(bot.title_for("Alice"), "Alice the Traveler")

    def test_fishing_suffix_appended_after_quest_suffix(self):
        bot = _make_bot(quest_suffix="(Legend)", fishing_suffix="the Collector")
        self.assertEqual(bot.title_for("Alice"), "Alice (Legend) the Collector")

    def test_fishing_suffix_appended_after_courtesy_and_quest(self):
        bot = _make_bot(
            courtesy_profile={"title": "archmage"},
            quest_suffix="(Legend)",
            fishing_suffix="the Traveler the Caster",
        )
        self.assertEqual(bot.title_for("Alice"), "Archmage (Legend) the Traveler the Caster")

    def test_empty_fishing_suffix_not_appended(self):
        bot = _make_bot(fishing_suffix="")
        self.assertEqual(bot.title_for("Alice"), "Alice")

    def test_no_fishing_module_no_change(self):
        bot = _make_bot()
        self.assertEqual(bot.title_for("Alice"), "Alice")


if __name__ == "__main__":
    unittest.main()
