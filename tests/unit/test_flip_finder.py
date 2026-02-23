from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone

from poe_trade.analytics.flip_finder import find_flip_opportunities
from poe_trade.etl.models import ListingCanonical


class TestFlipFinder(unittest.TestCase):
    def _build_listing(self, listing_uid: str, price: float) -> ListingCanonical:
        now = datetime.now(timezone.utc)
        return ListingCanonical(
            listing_uid=listing_uid,
            item_uid="item-1",
            listed_at=now,
            league="Standard",
            price_amount=price,
            price_currency="Chaos",
            price_chaos=price,
            seller_id="seller",
            seller_meta="meta",
            last_seen_at=now,
            fp_loose="fp",
            payload_json="{}",
        )

    def test_detects_underpriced_listing(self):
        listing = self._build_listing("flip-1", 5.0)
        stats = {
            "p25": 20.0,
            "p50": 25.0,
            "p75": 30.0,
            "liquidity_score": 3.0,
        }
        opportunities = find_flip_opportunities([listing], stats)
        self.assertEqual(len(opportunities), 1)
        self.assertEqual(opportunities[0].league, "Standard")
        self.assertIn("fp", opportunities[0].metadata.values())

    def test_honors_price_overrides_for_detection(self):
        listing = self._build_listing("flip-override", 10.0)
        stats = {
            "p25": 50.0,
            "p50": 60.0,
            "p75": 70.0,
            "liquidity_score": 1.0,
        }
        overrides = {listing.listing_uid: 15.0}
        opportunities = find_flip_opportunities([listing], stats, price_overrides=overrides)
        self.assertEqual(len(opportunities), 1)
        self.assertEqual(opportunities[0].buy_max, 15.0)

    def test_to_row_serializes_metadata_and_times(self):
        listing = self._build_listing("flip-serialize", 5.0)
        stats = {"p25": 10.0, "p50": 20.0, "p75": 30.0, "liquidity_score": 2.0}
        opportunities = find_flip_opportunities([listing], stats)
        self.assertEqual(len(opportunities), 1)
        row = opportunities[0].to_row()
        self.assertIsInstance(row["detected_at"], datetime)
        self.assertIsInstance(row["expiry_ts"], datetime)
        metadata = json.loads(row["metadata"])
        self.assertEqual(metadata["listing_uid"], "flip-serialize")
        self.assertIn("fp_loose", metadata)


if __name__ == "__main__":
    unittest.main()
