import json
import tempfile
import unittest
from pathlib import Path

from web.stats.data_loader import JeevesStatsLoader


class TestAchievementsLoader(unittest.TestCase):
    def test_loader_reads_achievements_from_state_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir)

            # Simulate older deployments where achievements are stored in state.json.
            state_payload = {
                "modules": {
                    "achievements": {
                        "user_achievements": {"u1": {"unlocked": ["quest_novice"]}},
                        "global_first_unlocks": {"quest_novice": {"user_id": "u1"}},
                    }
                }
            }
            (config_path / "state.json").write_text(json.dumps(state_payload), encoding="utf-8")

            loader = JeevesStatsLoader(config_path)
            achievements = loader.load_achievements_stats()

            self.assertIn("u1", achievements["user_achievements"])
            self.assertIn("quest_novice", achievements["global_first_unlocks"])

    def test_stats_json_overrides_state_json_when_both_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir)

            (config_path / "state.json").write_text(
                json.dumps({"modules": {"achievements": {"user_achievements": {"u1": {"unlocked": ["a"]}}}}}),
                encoding="utf-8",
            )
            (config_path / "stats.json").write_text(
                json.dumps({"modules": {"achievements": {"user_achievements": {"u1": {"unlocked": ["b"]}}}}}),
                encoding="utf-8",
            )

            loader = JeevesStatsLoader(config_path)
            achievements = loader.load_achievements_stats()

            self.assertEqual(achievements["user_achievements"]["u1"]["unlocked"], ["b"])


if __name__ == "__main__":
    unittest.main()

