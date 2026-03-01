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

    def test_traveler_requires_level_above_zero(self):
        players = {
            "alice": _player(level=0, total_fish=100),
        }
        result = Fishing._compute_annual_champions(players)
        self.assertIsNone(result["traveler"])

    def test_all_three_can_be_same_player(self):
        players = {
            "alice": _player(level=9, furthest_cast=9999.0, rare_catches=[{}] * 20, total_fish=100),
        }
        result = Fishing._compute_annual_champions(players)
        self.assertEqual(result["traveler"], "alice")
        self.assertEqual(result["caster"], "alice")
        self.assertEqual(result["collector"], "alice")


class TestGetChampionBonuses(unittest.TestCase):
    def test_no_champions_returns_zero_bonuses(self):
        f = _make_fishing({"fishing_champions": {}})
        bonuses = f._get_champion_bonuses("alice")
        self.assertEqual(bonuses["xp"], 0.0)
        self.assertEqual(bonuses["distance"], 0.0)
        self.assertEqual(bonuses["rarity"], 0.0)

    def test_traveler_gets_xp_bonus(self):
        f = _make_fishing({"fishing_champions": {"traveler": "alice"}})
        bonuses = f._get_champion_bonuses("alice")
        self.assertEqual(bonuses["xp"], 0.20)
        self.assertEqual(bonuses["distance"], 0.0)

    def test_caster_gets_distance_bonus(self):
        f = _make_fishing({"fishing_champions": {"caster": "bob"}})
        bonuses = f._get_champion_bonuses("bob")
        self.assertEqual(bonuses["distance"], 0.20)

    def test_collector_gets_rarity_bonus(self):
        f = _make_fishing({"fishing_champions": {"collector": "carol"}})
        bonuses = f._get_champion_bonuses("carol")
        self.assertEqual(bonuses["rarity"], 0.20)

    def test_player_can_hold_multiple_titles(self):
        f = _make_fishing({"fishing_champions": {
            "traveler": "alice", "caster": "alice", "collector": "alice"
        }})
        bonuses = f._get_champion_bonuses("alice")
        self.assertEqual(bonuses["xp"], 0.20)
        self.assertEqual(bonuses["distance"], 0.20)
        self.assertEqual(bonuses["rarity"], 0.20)

    def test_non_champion_gets_zero_bonuses(self):
        f = _make_fishing({"fishing_champions": {"traveler": "alice"}})
        bonuses = f._get_champion_bonuses("bob")
        self.assertEqual(bonuses["xp"], 0.0)


class TestGetFishingSuffix(unittest.TestCase):
    def test_no_champions_returns_empty(self):
        f = _make_fishing({"fishing_champions": {}})
        self.assertEqual(f.get_fishing_suffix_for_user("alice"), "")

    def test_traveler_returns_suffix(self):
        f = _make_fishing({"fishing_champions": {"traveler": "alice"}})
        self.assertEqual(f.get_fishing_suffix_for_user("alice"), "the Traveler")

    def test_caster_returns_suffix(self):
        f = _make_fishing({"fishing_champions": {"caster": "alice"}})
        self.assertEqual(f.get_fishing_suffix_for_user("alice"), "the Caster")

    def test_collector_returns_suffix(self):
        f = _make_fishing({"fishing_champions": {"collector": "alice"}})
        self.assertEqual(f.get_fishing_suffix_for_user("alice"), "the Collector")

    def test_multiple_titles_join_in_order(self):
        f = _make_fishing({"fishing_champions": {
            "traveler": "alice", "caster": "alice", "collector": "alice"
        }})
        result = f.get_fishing_suffix_for_user("alice")
        self.assertEqual(result, "the Traveler the Caster the Collector")

    def test_non_champion_returns_empty(self):
        f = _make_fishing({"fishing_champions": {"traveler": "bob"}})
        self.assertEqual(f.get_fishing_suffix_for_user("alice"), "")

    def test_no_fishing_champions_state_returns_empty(self):
        f = _make_fishing({})
        self.assertEqual(f.get_fishing_suffix_for_user("alice"), "")


class TestCasterBonus(unittest.TestCase):
    def test_no_champion_bonus_no_change(self):
        from modules.fishing import LOCATIONS
        puddle = LOCATIONS[0]  # max_distance=5
        # Without bonus, distance is in [1.5, 3.5] (0.3–0.7 * 5 for level 0)
        # With 0.0 bonus it should not exceed 5.0
        distance = Fishing._get_cast_distance(0, puddle, 0.0, 0.0)
        self.assertLessEqual(distance, 5.0)

    def test_caster_bonus_increases_distance(self):
        import random
        from modules.fishing import LOCATIONS
        void = LOCATIONS[9]  # max_distance=5000
        random.seed(42)
        without = Fishing._get_cast_distance(9, void, 0.0, 0.0)
        random.seed(42)
        with_bonus = Fishing._get_cast_distance(9, void, 0.0, 0.20)
        self.assertGreater(with_bonus, without)

    def test_caster_bonus_is_multiplicative(self):
        import random
        from modules.fishing import LOCATIONS
        void = LOCATIONS[9]
        random.seed(42)
        base = Fishing._get_cast_distance(9, void, 0.0, 0.0)
        random.seed(42)
        with_bonus = Fishing._get_cast_distance(9, void, 0.0, 0.20)
        self.assertAlmostEqual(with_bonus, base * 1.20, places=1)


class TestCollectorBonus(unittest.TestCase):
    def test_select_rarity_accepts_champion_rarity_boost(self):
        f = _make_fishing({})
        # Should not raise with 4th argument
        result = f._select_rarity(20.0, None, 0.0, 0.20)
        self.assertIn(result, ["common", "uncommon", "rare", "legendary"])

    def test_collector_boost_shifts_weights_toward_rare(self):
        """With max wait and collector boost, rare/legendary should dominate."""
        import random
        f = _make_fishing({})
        random.seed(0)
        results_with = [f._select_rarity(20.0, None, 0.0, 0.20) for _ in range(200)]
        random.seed(0)
        results_without = [f._select_rarity(20.0, None, 0.0, 0.0) for _ in range(200)]
        rare_with = sum(1 for r in results_with if r in ("rare", "legendary"))
        rare_without = sum(1 for r in results_without if r in ("rare", "legendary"))
        self.assertGreater(rare_with, rare_without)


if __name__ == "__main__":
    unittest.main()
