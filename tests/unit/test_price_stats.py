from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone

from poe_trade.analytics.price_stats import PriceStatsRow, compute_price_stats


class TestPriceStats(unittest.TestCase):
    def test_percentiles_and_row(self):
        prices = [10.0, 20.0, 30.0, 40.0, 50.0]
        stats = compute_price_stats(prices)
        self.assertEqual(stats["p10"], 10.0)
        self.assertEqual(stats["p50"], 30.0)
        self.assertEqual(stats["p90"], 50.0)
        self.assertEqual(stats["spread"], 40.0)
        self.assertEqual(stats["listing_count"], 5)
        bucket = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
        row = PriceStatsRow.from_prices(
            "standard", "fp", bucket, prices, metadata={"stage": "test"}
        )
        row_data = row.to_row()
        self.assertEqual(row_data["league"], "standard")
        self.assertEqual(row_data["listing_count"], 5)
        self.assertEqual(row_data["liquidity_score"], 5.0)
        self.assertIn("p25", row_data)
        self.assertEqual(row_data["median_price"], stats["p50"])
        self.assertEqual(row_data["time_bucket"], bucket)
        metadata = str(row_data["metadata"])
        self.assertEqual(json.loads(metadata), {"stage": "test"})


if __name__ == "__main__":
    unittest.main()
