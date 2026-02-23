from __future__ import annotations

import unittest
from datetime import datetime, timezone

from poe_trade.analytics.stash_pricer import StashPriceSuggestion


class TestStashPriceSuggestion(unittest.TestCase):
    def test_row_includes_timestamps(self):
        created = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
        updated = datetime(2025, 1, 2, 12, 0, tzinfo=timezone.utc)
        suggestion = StashPriceSuggestion(
            snapshot_id="snapshot-1",
            item_uid="item-1",
            league="Standard",
            est_price_chaos=20.0,
            list_price_chaos=15.0,
            confidence=0.75,
            reason_codes=("below_estimate", "high_confidence"),
            details="test",
            created_at=created,
            updated_at=updated,
        )
        row = suggestion.to_row()
        self.assertEqual(row["created_at"], created)
        self.assertEqual(row["updated_at"], updated)
        self.assertEqual(row["reason_codes"], ["below_estimate", "high_confidence"])
        self.assertEqual(row["confidence"], 0.75)


if __name__ == "__main__":
    unittest.main()
