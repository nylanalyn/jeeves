import tempfile
import unittest
from pathlib import Path

from web.stats.data_loader import JeevesStatsLoader, StatsAggregator
from web.stats.config import filter_channels


class TestActivityStats(unittest.TestCase):
    def test_loader_missing_stats_file_returns_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir)
            loader = JeevesStatsLoader(config_path)
            stats = loader.load_all()

            self.assertIn("activity", stats)
            self.assertIn("global", stats["activity"])
            self.assertEqual(len(stats["activity"]["global"]["grid"]), 7 * 24)
            self.assertEqual(stats["activity"]["global"]["total"], 0)

    def test_aggregator_user_lookup_and_top_hours(self) -> None:
        fake_stats = {
            "users": {
                "u1": {"canonical_nick": "Alice", "seen_nicks": ["alice", "alice_away"]},
            },
            "activity": {
                "global": {"grid": [0] * (7 * 24), "total": 0},
                "channels": {},
                "users": {
                    "u1": {"grid": [0] * (7 * 24), "total": 0},
                },
            },
            "quest": {},
            "hunt": {},
            "duel": {},
            "adventure": {},
            "roadtrip": {},
            "absurdia": {},
            "karma": {},
            "coffee": {},
            "bell": {},
            "achievements": {},
        }

        # Set some activity for hour 13 across multiple days.
        for dow in range(7):
            fake_stats["activity"]["users"]["u1"]["grid"][(dow * 24) + 13] = dow + 1
            fake_stats["activity"]["users"]["u1"]["total"] += dow + 1

        agg = StatsAggregator(fake_stats)
        self.assertEqual(agg.find_user_id("alice"), "u1")
        self.assertEqual(agg.find_user_id("ALICE_AWAY"), "u1")
        self.assertEqual(agg.find_user_id("u1"), "u1")
        self.assertIsNone(agg.find_user_id("missing"))

        bucket = agg.get_activity_bucket_user("u1")
        top_hours = agg.get_top_hours(bucket, limit=3)
        self.assertEqual(top_hours[0][0], 13)
        self.assertGreater(top_hours[0][1], 0)

    def test_channel_filtering(self) -> None:
        available = ["#a", "#b", "#c"]
        self.assertEqual(filter_channels(available, visible_channels=None, hidden_channels=["#b"]), ["#a", "#c"])
        self.assertEqual(filter_channels(available, visible_channels=["#c", "#a"], hidden_channels=[]), ["#c", "#a"])
        self.assertEqual(filter_channels(available, visible_channels=["#missing", "#a"], hidden_channels=["#a"]), [])


if __name__ == "__main__":
    unittest.main()
