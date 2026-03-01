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


class TestAnnualReset(unittest.TestCase):
    def _make_fishing_with_players(self):
        players = {
            "alice": {
                "level": 9, "furthest_cast": 5000.0,
                "rare_catches": [{}] * 20, "total_fish": 100,
                "xp": 0, "total_casts": 0, "biggest_fish": 0.0,
                "biggest_fish_name": None, "lines_broken": 0,
                "junk_collected": 0, "catches": {}, "catches_by_location": {},
                "locations_fished": [], "xp_boost_catches": 0,
                "force_rare_legendary": False, "artifact": None, "junk_curse_date": None,
            },
            "bob": {
                "level": 3, "furthest_cast": 100.0,
                "rare_catches": [], "total_fish": 10,
                "xp": 0, "total_casts": 0, "biggest_fish": 0.0,
                "biggest_fish_name": None, "lines_broken": 0,
                "junk_collected": 0, "catches": {}, "catches_by_location": {},
                "locations_fished": [], "xp_boost_catches": 0,
                "force_rare_legendary": False, "artifact": None, "junk_curse_date": None,
            },
        }
        state = {
            "players": players,
            "active_casts": {"alice": {"timestamp": "2025-01-01T00:00:00+00:00"}},
            "active_event": {"type": "test"},
        }
        f = _make_fishing(state)
        # Stub out bot and safe_say so reset doesn't crash
        class _BotStub:
            def get_module_state(self, name): return {"user_map": {}}
            joined_channels = ["#test"]
            config = {"fishing": {}}
        f.bot = _BotStub()
        f._messages_sent = []
        f.safe_say = lambda msg, target=None: f._messages_sent.append(msg)
        f.save_state = lambda force=False: None
        return f

    def test_reset_updates_fishing_champions(self):
        f = self._make_fishing_with_players()
        f._run_annual_reset(2025)
        champions = f.get_state("fishing_champions", {})
        self.assertEqual(champions["year"], 2025)
        self.assertEqual(champions["traveler"], "alice")
        self.assertEqual(champions["caster"], "alice")
        self.assertEqual(champions["collector"], "alice")

    def test_reset_stores_snapshot_stats(self):
        f = self._make_fishing_with_players()
        f._run_annual_reset(2025)
        champions = f.get_state("fishing_champions", {})
        self.assertEqual(champions["traveler_level"], 9)
        self.assertEqual(champions["traveler_location"], "The Void")
        self.assertAlmostEqual(champions["caster_distance"], 5000.0, places=1)
        self.assertEqual(champions["collector_count"], 20)

    def test_reset_wipes_players(self):
        f = self._make_fishing_with_players()
        f._run_annual_reset(2025)
        self.assertEqual(f.get_state("players", {}), {})

    def test_reset_clears_active_casts(self):
        f = self._make_fishing_with_players()
        f._run_annual_reset(2025)
        self.assertEqual(f.get_state("active_casts", {}), {})

    def test_reset_clears_active_event(self):
        f = self._make_fishing_with_players()
        f._run_annual_reset(2025)
        self.assertIsNone(f.get_state("active_event"))

    def test_reset_sends_announcement(self):
        f = self._make_fishing_with_players()
        f._run_annual_reset(2025)
        self.assertTrue(len(f._messages_sent) > 0)
        combined = " ".join(f._messages_sent)
        self.assertIn("RESET", combined)


class TestFishingChampionsCommand(unittest.TestCase):
    """Tests for _cmd_fishing_champions."""

    def _make_champions_fishing(self, state=None, user_map=None):
        """Build a Fishing instance wired up for _cmd_fishing_champions tests."""
        f = _make_fishing(state)

        class _BotStub:
            config = {"fishing": {}}

            def get_module_state(self, name):
                return {"user_map": user_map or {}}

        f.bot = _BotStub()
        f._replies = []
        f.safe_reply = lambda conn, evt, text: f._replies.append(text)
        return f

    def _make_event(self, target="#fishing"):
        evt = types.SimpleNamespace(target=target)
        return evt

    def _call_cmd(self, f, state=None):
        """Invoke _cmd_fishing_champions with dummy connection/event/msg/username/match."""
        conn = object()
        event = self._make_event()
        f._cmd_fishing_champions(conn, event, "!champions", "testuser", None)

    # ------------------------------------------------------------------
    # Test 1: no champions yet (fishing_champions state is None / absent)
    # ------------------------------------------------------------------

    def test_no_champions_replies_with_first_reset_message(self):
        f = self._make_champions_fishing(state={})
        self._call_cmd(f)
        self.assertEqual(len(f._replies), 1)
        self.assertIn("No champions yet", f._replies[0])
        self.assertIn("April 1st", f._replies[0])

    def test_no_champions_when_state_key_missing(self):
        """fishing_champions key not present at all → no-champions message."""
        f = self._make_champions_fishing(state={})
        self._call_cmd(f)
        self.assertIn("first reset", f._replies[0])

    def test_no_champions_when_all_slots_null(self):
        """fishing_champions exists but all slots are None → treated as no champions."""
        f = self._make_champions_fishing(state={
            "fishing_champions": {
                "year": 2025,
                "traveler": None,
                "caster": None,
                "collector": None,
            }
        })
        self._call_cmd(f)
        self.assertEqual(len(f._replies), 1)
        self.assertIn("No champions yet", f._replies[0])

    # ------------------------------------------------------------------
    # Test 2: champions exist with snapshot stats
    # ------------------------------------------------------------------

    def test_champions_with_snapshot_stats_formats_traveler(self):
        """Snapshot traveler_level and traveler_location appear in output."""
        f = self._make_champions_fishing(
            state={
                "fishing_champions": {
                    "year": 2025,
                    "traveler": "alice",
                    "caster": None,
                    "collector": None,
                    "traveler_level": 9,
                    "traveler_location": "The Void",
                }
            },
            user_map={"alice": {"canonical_nick": "Alice"}},
        )
        self._call_cmd(f)
        self.assertEqual(len(f._replies), 1)
        reply = f._replies[0]
        self.assertIn("the Traveler", reply)
        self.assertIn("Alice", reply)
        self.assertIn("level 9", reply)
        self.assertIn("The Void", reply)

    def test_champions_with_snapshot_stats_formats_caster(self):
        """Snapshot caster_distance appears formatted with one decimal place."""
        f = self._make_champions_fishing(
            state={
                "fishing_champions": {
                    "year": 2025,
                    "traveler": None,
                    "caster": "bob",
                    "collector": None,
                    "caster_distance": 4999.5,
                }
            },
            user_map={"bob": {"canonical_nick": "Bob"}},
        )
        self._call_cmd(f)
        reply = f._replies[0]
        self.assertIn("the Caster", reply)
        self.assertIn("Bob", reply)
        self.assertIn("4999.5m", reply)

    def test_champions_with_snapshot_stats_formats_collector(self):
        """Snapshot collector_count appears in output."""
        f = self._make_champions_fishing(
            state={
                "fishing_champions": {
                    "year": 2025,
                    "traveler": None,
                    "caster": None,
                    "collector": "carol",
                    "collector_count": 17,
                }
            },
            user_map={"carol": {"canonical_nick": "Carol"}},
        )
        self._call_cmd(f)
        reply = f._replies[0]
        self.assertIn("the Collector", reply)
        self.assertIn("Carol", reply)
        self.assertIn("17", reply)
        self.assertIn("rare/legendary", reply)

    def test_snapshot_fallback_to_live_player_data_for_traveler(self):
        """When snapshot stats are absent, live player data is used instead."""
        f = self._make_champions_fishing(
            state={
                "fishing_champions": {
                    "year": 2025,
                    "traveler": "alice",
                    "caster": None,
                    "collector": None,
                    # no traveler_level or traveler_location snapshot
                },
                "players": {
                    "alice": {"level": 7, "furthest_cast": 0.0, "rare_catches": [], "total_fish": 0},
                },
            },
            user_map={"alice": {"canonical_nick": "Alice"}},
        )
        self._call_cmd(f)
        reply = f._replies[0]
        self.assertIn("level 7", reply)
        # Level 7 maps to Mars in LOCATIONS
        self.assertIn("Mars", reply)

    def test_snapshot_fallback_to_live_player_data_for_caster(self):
        """When caster_distance snapshot is absent, live furthest_cast is used."""
        f = self._make_champions_fishing(
            state={
                "fishing_champions": {
                    "year": 2025,
                    "traveler": None,
                    "caster": "bob",
                    "collector": None,
                    # no caster_distance snapshot
                },
                "players": {
                    "bob": {"level": 3, "furthest_cast": 123.4, "rare_catches": [], "total_fish": 0},
                },
            },
            user_map={"bob": {"canonical_nick": "Bob"}},
        )
        self._call_cmd(f)
        reply = f._replies[0]
        self.assertIn("123.4m", reply)

    def test_snapshot_fallback_to_live_player_data_for_collector(self):
        """When collector_count snapshot is absent, len(rare_catches) is used."""
        f = self._make_champions_fishing(
            state={
                "fishing_champions": {
                    "year": 2025,
                    "traveler": None,
                    "caster": None,
                    "collector": "carol",
                    # no collector_count snapshot
                },
                "players": {
                    "carol": {
                        "level": 0, "furthest_cast": 0.0,
                        "rare_catches": [{}] * 5, "total_fish": 5,
                    },
                },
            },
            user_map={"carol": {"canonical_nick": "Carol"}},
        )
        self._call_cmd(f)
        reply = f._replies[0]
        self.assertIn("5", reply)

    # ------------------------------------------------------------------
    # Test 3: null champion slot is omitted gracefully
    # ------------------------------------------------------------------

    def test_null_caster_slot_is_omitted(self):
        """When caster is None, the Caster line does not appear in output."""
        f = self._make_champions_fishing(
            state={
                "fishing_champions": {
                    "year": 2025,
                    "traveler": "alice",
                    "caster": None,
                    "collector": None,
                    "traveler_level": 9,
                    "traveler_location": "The Void",
                }
            },
            user_map={"alice": {"canonical_nick": "Alice"}},
        )
        self._call_cmd(f)
        reply = f._replies[0]
        self.assertNotIn("the Caster", reply)
        self.assertIn("the Traveler", reply)

    def test_null_traveler_slot_is_omitted(self):
        """When traveler is None, the Traveler line does not appear in output."""
        f = self._make_champions_fishing(
            state={
                "fishing_champions": {
                    "year": 2025,
                    "traveler": None,
                    "caster": "bob",
                    "collector": None,
                    "caster_distance": 500.0,
                }
            },
            user_map={"bob": {"canonical_nick": "Bob"}},
        )
        self._call_cmd(f)
        reply = f._replies[0]
        self.assertNotIn("the Traveler", reply)
        self.assertIn("the Caster", reply)

    def test_null_collector_slot_is_omitted(self):
        """When collector is None, the Collector line does not appear in output."""
        f = self._make_champions_fishing(
            state={
                "fishing_champions": {
                    "year": 2025,
                    "traveler": None,
                    "caster": "bob",
                    "collector": None,
                    "caster_distance": 500.0,
                }
            },
            user_map={"bob": {"canonical_nick": "Bob"}},
        )
        self._call_cmd(f)
        reply = f._replies[0]
        self.assertNotIn("the Collector", reply)

    # ------------------------------------------------------------------
    # Test 4: year is displayed in output
    # ------------------------------------------------------------------

    def test_year_appears_in_output(self):
        """The champions year is included in the reply header."""
        f = self._make_champions_fishing(
            state={
                "fishing_champions": {
                    "year": 2024,
                    "traveler": "alice",
                    "caster": None,
                    "collector": None,
                    "traveler_level": 5,
                    "traveler_location": "Deep Sea",
                }
            },
            user_map={"alice": {"canonical_nick": "Alice"}},
        )
        self._call_cmd(f)
        self.assertIn("2024", f._replies[0])

    def test_year_question_mark_when_missing(self):
        """When year key is absent from champions dict, '?' is displayed."""
        f = self._make_champions_fishing(
            state={
                "fishing_champions": {
                    # no 'year' key
                    "traveler": "alice",
                    "caster": None,
                    "collector": None,
                    "traveler_level": 5,
                    "traveler_location": "Deep Sea",
                }
            },
            user_map={"alice": {"canonical_nick": "Alice"}},
        )
        self._call_cmd(f)
        self.assertIn("?", f._replies[0])

    # ------------------------------------------------------------------
    # Test 5: user_map lookup for display names
    # ------------------------------------------------------------------

    def test_user_map_lookup_uses_canonical_nick(self):
        """canonical_nick from user_map is used as display name."""
        f = self._make_champions_fishing(
            state={
                "fishing_champions": {
                    "year": 2025,
                    "traveler": "uid_xyz",
                    "caster": None,
                    "collector": None,
                    "traveler_level": 3,
                    "traveler_location": "River",
                }
            },
            user_map={"uid_xyz": {"canonical_nick": "FancyNick"}},
        )
        self._call_cmd(f)
        self.assertIn("FancyNick", f._replies[0])
        self.assertNotIn("uid_xyz", f._replies[0])

    def test_user_map_falls_back_to_uid_when_not_found(self):
        """When uid is not in user_map, the uid itself is used as display name."""
        f = self._make_champions_fishing(
            state={
                "fishing_champions": {
                    "year": 2025,
                    "traveler": "unknown_uid",
                    "caster": None,
                    "collector": None,
                    "traveler_level": 2,
                    "traveler_location": "Lake",
                }
            },
            user_map={},  # empty — no entry for unknown_uid
        )
        self._call_cmd(f)
        self.assertIn("unknown_uid", f._replies[0])

    def test_all_three_champions_appear_in_single_reply(self):
        """All three champion slots appear together, pipe-separated."""
        f = self._make_champions_fishing(
            state={
                "fishing_champions": {
                    "year": 2025,
                    "traveler": "alice",
                    "caster": "bob",
                    "collector": "carol",
                    "traveler_level": 9,
                    "traveler_location": "The Void",
                    "caster_distance": 4999.0,
                    "collector_count": 20,
                }
            },
            user_map={
                "alice": {"canonical_nick": "Alice"},
                "bob": {"canonical_nick": "Bob"},
                "carol": {"canonical_nick": "Carol"},
            },
        )
        self._call_cmd(f)
        self.assertEqual(len(f._replies), 1)
        reply = f._replies[0]
        self.assertIn("the Traveler", reply)
        self.assertIn("the Caster", reply)
        self.assertIn("the Collector", reply)
        self.assertIn("|", reply)


if __name__ == "__main__":
    unittest.main()
