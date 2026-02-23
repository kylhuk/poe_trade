from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from poe_trade.analytics.session_ledger import SessionSnapshot, summarize_session


class TestSessionLedger(unittest.TestCase):
    def test_farming_session_row(self):
        now = datetime.now(timezone.utc)
        snapshot = SessionSnapshot(
            session_id="s1",
            realm="pc",
            league="Standard",
            start_snapshot="alpha",
            end_snapshot="omega",
            start_value=100.0,
            end_value=200.0,
            start_time=now - timedelta(hours=2),
            end_time=now,
            tag="map",
            notes="test",
        )
        row = summarize_session(snapshot).to_row()
        self.assertEqual(row["session_id"], "s1")
        self.assertAlmostEqual(row["profit_chaos"], 100.0)
        self.assertAlmostEqual(row["profit_per_hour"], 50.0, places=2)
        self.assertEqual(row["tag"], "map")


if __name__ == "__main__":
    unittest.main()
