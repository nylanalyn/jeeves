import json
import unittest
from unittest.mock import Mock, patch

from modules.matrix_admin import MatrixAdmin


def _make_matrix_admin():
    admin = MatrixAdmin.__new__(MatrixAdmin)
    admin._since = ""
    admin._started_at_ms = 1000
    admin._debug_messages = []
    admin.log_debug = admin._debug_messages.append
    return admin


class TestMatrixAdminStartupSync(unittest.TestCase):
    def test_initial_sync_records_next_batch_and_uses_empty_timeline_filter(self):
        admin = _make_matrix_admin()
        response = Mock()
        response.json.return_value = {"next_batch": "s123"}

        with patch("modules.matrix_admin.requests.get", return_value=response) as get:
            self.assertTrue(
                admin._initial_sync("https://matrix.example", {"Authorization": "Bearer t"})
            )

        self.assertEqual(admin._since, "s123")
        params = get.call_args.kwargs["params"]
        self.assertEqual(params["timeout"], 0)
        self.assertEqual(
            json.loads(params["filter"]),
            {"room": {"timeline": {"limit": 0}}},
        )

    def test_initial_sync_fails_without_next_batch(self):
        admin = _make_matrix_admin()
        response = Mock()
        response.json.return_value = {}

        with patch("modules.matrix_admin.requests.get", return_value=response):
            self.assertFalse(admin._initial_sync("https://matrix.example", {}))

        self.assertEqual(admin._since, "")
        self.assertIn(
            "[matrix_admin] initial sync missing next_batch",
            admin._debug_messages,
        )

    def test_fresh_event_rejects_backfilled_events_before_module_start(self):
        admin = _make_matrix_admin()

        self.assertFalse(admin._is_fresh_event({"origin_server_ts": 999}))
        self.assertTrue(admin._is_fresh_event({"origin_server_ts": 1000}))
        self.assertTrue(admin._is_fresh_event({"origin_server_ts": 1001}))

    def test_fresh_event_rejects_events_without_matrix_timestamp(self):
        admin = _make_matrix_admin()

        self.assertFalse(admin._is_fresh_event({}))
        self.assertFalse(admin._is_fresh_event({"origin_server_ts": "1001"}))


if __name__ == "__main__":
    unittest.main()
