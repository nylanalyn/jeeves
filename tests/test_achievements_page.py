import unittest

from web.stats.templates import render_achievements_page


class TestAchievementsPage(unittest.TestCase):
    def test_hides_undiscovered_achievements(self) -> None:
        stats = {
            "users": {"u1": {"canonical_nick": "Alice"}},
            "achievements": {
                "user_achievements": {
                    "u1": {"unlocked": ["unlucky"]},
                },
                "global_first_unlocks": {},
            },
        }

        html = render_achievements_page(stats)

        self.assertIn("Unlucky", html)
        self.assertNotIn("Quest Novice", html)

    def test_shows_empty_state_when_none_discovered(self) -> None:
        stats = {
            "users": {},
            "achievements": {
                "user_achievements": {},
                "global_first_unlocks": {},
            },
        }

        html = render_achievements_page(stats)

        self.assertIn("No achievements discovered yet.", html)
        self.assertNotIn("Unlucky", html)


if __name__ == "__main__":
    unittest.main()

