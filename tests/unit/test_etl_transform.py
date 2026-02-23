from __future__ import annotations

import json
import unittest
from dataclasses import asdict

from poe_trade.etl.parser import parse_bronze_row
from poe_trade.etl.pipeline import run_etl_pipeline


def make_sample_row() -> dict[str, object]:
    item_payload = {
        "id": "item-001",
        "name": "Test Sword",
        "typeLine": "Sword",
        "frameType": 2,
        "ilvl": 85,
        "corrupted": False,
        "properties": [{"name": "Quality", "value": "+20%"}],
        "sockets": [{"group": 0}, {"group": 0}],
        "links": 2,
        "influences": {"shaper": True, "elder": False},
        "flags": ["identified"],
        "explicitMods": [{"id": "explicit-1", "tier": 1}],
        "implicitMods": [{"id": "implicit-1", "tier": 0}],
        "listing": {
            "price": {"amount": 45, "currency": "Chaos"},
            "seller": {"id": "seller-123", "meta": "rank1"},
            "listed_at": "2025-01-01T00:00:00Z",
        },
    }
    stash_payload = {
        "league": "MockLeague",
        "stash_id": "stash-alpha",
        "items": [item_payload],
    }
    return {
        "ingested_at": "2025-01-01T00:00:00Z",
        "realm": "pc",
        "league": "MockLeague",
        "stash_id": "stash-alpha",
        "payload_json": json.dumps(stash_payload, ensure_ascii=False),
    }


class TestETLTransform(unittest.TestCase):
    def test_schema_keys_present_for_canonical_rows(self):
        row = make_sample_row()
        result = run_etl_pipeline([row])
        self.assertEqual(result.metrics.get("total_rows"), 1)
        self.assertEqual(result.metrics.get("parseable_price_pct"), 1.0)
        self.assertEqual(len(result.items), 1)
        self.assertEqual(len(result.listings), 1)

        item_keys = set(asdict(result.items[0]).keys())
        expected_item_keys = {
            "item_uid",
            "source",
            "captured_at",
            "league",
            "base_type",
            "rarity",
            "ilvl",
            "corrupted",
            "quality",
            "sockets",
            "links",
            "influences",
            "modifier_ids",
            "modifier_tiers",
            "flags",
            "fp_exact",
            "fp_loose",
            "payload_json",
        }
        self.assertEqual(item_keys, expected_item_keys)
        self.assertEqual(result.items[0].flags, ["identified"])

        listing_keys = set(asdict(result.listings[0]).keys())
        expected_listing_keys = {
            "listing_uid",
            "item_uid",
            "listed_at",
            "league",
            "price_amount",
            "price_currency",
            "price_chaos",
            "seller_id",
            "seller_meta",
            "last_seen_at",
            "fp_loose",
            "payload_json",
        }
        self.assertEqual(listing_keys, expected_listing_keys)

    def test_deterministic_fingerprint_for_repeat_rows(self):
        row = make_sample_row()
        parsed_once = parse_bronze_row(row)
        parsed_again = parse_bronze_row(row)
        self.assertEqual(len(parsed_once), len(parsed_again))
        self.assertEqual(parsed_once[0][0].fp_exact, parsed_again[0][0].fp_exact)
        self.assertEqual(parsed_once[0][1].fp_loose, parsed_again[0][1].fp_loose)
        self.assertEqual(parsed_once[0][1].payload_json, parsed_again[0][1].payload_json)

    def test_invalid_prices_are_counted(self):
        row = make_sample_row()
        payload = json.loads(row["payload_json"])
        payload["items"][0]["listing"]["price"]["amount"] = 0
        row["payload_json"] = json.dumps(payload, ensure_ascii=False)

        result = run_etl_pipeline([row])
        self.assertEqual(result.metrics.get("invalid_price_count"), 1)
        self.assertEqual(result.metrics.get("parseable_price_pct"), 0.0)
        self.assertEqual(len(result.listings), 0)

    def test_dedupe_by_ids_preserves_metrics(self):
        row = make_sample_row()
        duplicate = dict(row)
        result = run_etl_pipeline([row, duplicate])
        self.assertEqual(result.metrics.get("total_rows"), 2)
        self.assertEqual(result.metrics.get("parsed_rows"), 2)
        self.assertEqual(result.metrics.get("invalid_price_count"), 0)
        self.assertLessEqual(result.metrics.get("parseable_price_pct"), 1.0)
        self.assertEqual(result.metrics.get("parseable_price_pct"), 0.5)
        self.assertEqual(len(result.items), 1)
        self.assertEqual(len(result.listings), 1)


if __name__ == "__main__":
    unittest.main()
