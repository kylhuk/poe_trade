from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from typing import Mapping

from poe_trade.analytics.pipeline import orchestrate_analytics
from poe_trade.etl.models import CurrencySnapshot
from poe_trade.analytics.session_ledger import SessionSnapshot


def _build_listing_row(listing_uid: str, amount: float, currency: str, league: str = "Standard", realm: str = "pc") -> Mapping[str, object]:
    now = datetime.now(timezone.utc)
    return {
        "payload_json": {
            "stash_id": f"stash-{listing_uid}",
            "items": [
                {
                    "id": listing_uid,
                    "listing_id": listing_uid,
                    "listing": {
                        "listing_id": listing_uid,
                        "price": {"amount": amount, "currency": currency},
                        "seller": {
                            "id": f"seller-{listing_uid}",
                            "accountName": f"seller-{listing_uid}",
                            "meta": "",
                        },
                    },
                    "typeLine": "Test Sword",
                    "baseType": "Sword",
                    "rarity": "rare",
                }
            ],
        },
        "league": league,
        "realm": realm,
        "stash_id": f"stash-{listing_uid}",
        "ingested_at": now.isoformat(),
    }


class TestPipelineOrchestration(unittest.TestCase):
    def test_orchestrate_returns_all_sections(self):
        rows = [_build_listing_row("listing-1", 10.0, "Chaos")]
        snapshot = CurrencySnapshot(currency="Chaos", chaos_value=1.0, timestamp=datetime.now(timezone.utc))
        now = datetime.now(timezone.utc)
        session = SessionSnapshot(
            session_id="session-1",
            realm="pc",
            league="Standard",
            start_snapshot="alpha",
            end_snapshot="omega",
            start_value=10.0,
            end_value=20.0,
            start_time=now - timedelta(hours=1),
            end_time=now,
        )
        result = orchestrate_analytics(rows, [snapshot], [session])
        self.assertIsInstance(result.price_stats, dict)
        self.assertGreaterEqual(len(result.listings), 1)
        self.assertIsInstance(result.strategy_results, list)
        self.assertEqual(len(result.strategy_results), 12)
        first_strategy = result.strategy_results[0]
        self.assertIn("strategy_id", first_strategy)
        self.assertIn("claim_summary", first_strategy)
        self.assertIn("kpi_summary", first_strategy)
        self.assertIn("kpi_targets", first_strategy)

    def test_price_stats_use_chaos_normalized_values(self):
        now = datetime.now(timezone.utc)
        rows = [
            _build_listing_row("listing-chaos", 10.0, "Chaos"),
            _build_listing_row("listing-exalted", 0.75, "Exalted"),
            _build_listing_row("listing-divine", 1.2, "Divine"),
        ]
        snapshots = [
            CurrencySnapshot(currency="Chaos", chaos_value=1.0, timestamp=now),
            CurrencySnapshot(currency="Exalted", chaos_value=120.0, timestamp=now),
            CurrencySnapshot(currency="Divine", chaos_value=125.0, timestamp=now),
        ]
        result = orchestrate_analytics(rows, snapshots, [])
        self.assertEqual(result.price_stats["p50"], 90.0)
        self.assertEqual(result.price_stats["spread"], 140.0)
        listings_by_id = {listing["listing_id"]: listing for listing in result.listings}
        self.assertEqual(listings_by_id["listing-chaos"]["price_chaos"], 10.0)
        self.assertEqual(listings_by_id["listing-exalted"]["price_chaos"], 90.0)
        self.assertEqual(listings_by_id["listing-divine"]["price_chaos"], 150.0)
        self.assertEqual(len(result.strategy_results), 12)
        self.assertIn("strategy_id", result.strategy_results[0])


if __name__ == "__main__":
    unittest.main()
