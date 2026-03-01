import threading
import unittest
import types
import sys


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
    # Stub out achievement_hooks
    if "modules.achievement_hooks" not in sys.modules:
        ah = types.ModuleType("modules.achievement_hooks")
        ah.record_achievement = lambda *a, **kw: None
        ah.record_fishing_level = lambda *a, **kw: None
        sys.modules["modules.achievement_hooks"] = ah


_install_stubs()

from modules.fishing import Fishing  # noqa: E402


def _make_fishing(state=None):
    f = Fishing.__new__(Fishing)
    f._state_cache = state.copy() if state else {}
    f._state_lock = threading.RLock()
    f._state_dirty = False
    return f


def _player(level=0, furthest_cast=0.0, rare_catches=None, total_fish=0):
    return {
        "level": level,
        "furthest_cast": furthest_cast,
        "rare_catches": rare_catches or [],
        "total_fish": total_fish,
    }


class TestComputeAnnualChampions(unittest.TestCase):
    def test_returns_null_champions_when_no_players(self):
        result = Fishing._compute_annual_champions({})
        self.assertIsNone(result["traveler"])
        self.assertIsNone(result["caster"])
        self.assertIsNone(result["collector"])

    def test_traveler_is_highest_level(self):
        players = {
            "alice": _player(level=9),
            "bob": _player(level=5),
        }
        result = Fishing._compute_annual_champions(players)
        self.assertEqual(result["traveler"], "alice")

    def test_caster_is_highest_furthest_cast(self):
        players = {
            "alice": _player(furthest_cast=100.0),
            "bob": _player(furthest_cast=4999.9),
        }
        result = Fishing._compute_annual_champions(players)
        self.assertEqual(result["caster"], "bob")

    def test_collector_is_most_rare_catches(self):
        players = {
            "alice": _player(rare_catches=[{"name": "Fish"}] * 3),
            "bob": _player(rare_catches=[{"name": "Fish"}] * 10),
        }
        result = Fishing._compute_annual_champions(players)
        self.assertEqual(result["collector"], "bob")

    def test_traveler_tiebreak_by_total_fish(self):
        players = {
            "alice": _player(level=9, total_fish=50),
            "bob": _player(level=9, total_fish=100),
        }
        result = Fishing._compute_annual_champions(players)
        self.assertEqual(result["traveler"], "bob")

    def test_caster_tiebreak_by_total_fish(self):
        players = {
            "alice": _player(furthest_cast=500.0, total_fish=10),
            "bob": _player(furthest_cast=500.0, total_fish=99),
        }
        result = Fishing._compute_annual_champions(players)
        self.assertEqual(result["caster"], "bob")

    def test_collector_tiebreak_by_total_fish(self):
        players = {
            "alice": _player(rare_catches=[{}] * 5, total_fish=5),
            "bob": _player(rare_catches=[{}] * 5, total_fish=20),
        }
        result = Fishing._compute_annual_champions(players)
        self.assertEqual(result["collector"], "bob")

    def test_collector_ignores_players_with_no_rare_catches(self):
        players = {
            "alice": _player(rare_catches=[]),
            "bob": _player(rare_catches=[]),
        }
        result = Fishing._compute_annual_champions(players)
        self.assertIsNone(result["collector"])

    def test_all_three_can_be_same_player(self):
        players = {
            "alice": _player(level=9, furthest_cast=9999.0, rare_catches=[{}] * 20, total_fish=100),
        }
        result = Fishing._compute_annual_champions(players)
        self.assertEqual(result["traveler"], "alice")
        self.assertEqual(result["caster"], "alice")
        self.assertEqual(result["collector"], "alice")


if __name__ == "__main__":
    unittest.main()
