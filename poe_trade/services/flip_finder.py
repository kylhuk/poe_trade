"""Arbitrage engine"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from ..analytics.flip_finder import find_flip_opportunities
from ..analytics.price_stats import compute_price_stats
from ..etl.models import ListingCanonical
from ._runner import run_idle_service

logger = logging.getLogger(__name__)

SERVICE_NAME = "flip_finder"


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _default_listings() -> Sequence[ListingCanonical]:
    now = datetime.now(timezone.utc)
    return [
        ListingCanonical(
            listing_uid="flip-1",
            item_uid="item-1",
            listed_at=now,
            league="Synthesis",
            price_amount=25.0,
            price_currency="Chaos",
            price_chaos=25.0,
            seller_id="demo",
            seller_meta="demo",
            last_seen_at=now,
            fp_loose="loose",
            payload_json="{}",
        ),
        ListingCanonical(
            listing_uid="flip-2",
            item_uid="item-2",
            listed_at=now,
            league="Synthesis",
            price_amount=5.0,
            price_currency="Chaos",
            price_chaos=5.0,
            seller_id="demo",
            seller_meta="demo",
            last_seen_at=now,
            fp_loose="loose2",
            payload_json="{}",
        ),
    ]


def _load_listings(path: Path | None) -> Sequence[ListingCanonical]:
    if path and path.exists():
        try:
            data = json.loads(path.read_text())
            now = datetime.now(timezone.utc)
            rows: list[ListingCanonical] = []
            for idx, item in enumerate(data):
                price_amount = _to_float(item.get("price"))
                price_chaos = _to_float(item.get("price_chaos"), price_amount)
                rows.append(
                    ListingCanonical(
                        listing_uid=
                        item.get("listing_uid")
                        or item.get("listing_id")
                        or f"listing-{idx}",
                        item_uid=item.get("item_uid") or item.get("item_id") or "unknown",
                        listed_at=now,
                        league=item.get("league") or "Synthesis",
                        price_amount=price_amount,
                        price_currency=item.get("currency") or "Chaos",
                        price_chaos=price_chaos,
                        seller_id=item.get("seller_id")
                        or item.get("seller")
                        or "unknown",
                        seller_meta=item.get("seller_meta") or "",
                        last_seen_at=now,
                        fp_loose=item.get("fp_loose") or item.get("fp_exact") or "fp",
                        payload_json=json.dumps(item, ensure_ascii=False),
                    )
                )
            if rows:
                return rows
        except json.JSONDecodeError:
            logger.warning("Failed to parse %s, falling back to defaults", path)
    return _default_listings()


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the flip finder service")
    parser.add_argument("--input", type=Path, help="JSON array of listing snapshots")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    listings = _load_listings(args.input)
    stats = compute_price_stats([listing.price_chaos for listing in listings])
    flips = find_flip_opportunities(list(listings), stats)
    logger.info("Detected %s flips from %s listings", len(flips), len(listings))

    if args.dry_run:
        logger.info(
            "Flips: %s",
            [flip.metadata.get("listing_uid", "unknown") for flip in flips],
        )
        return

    run_idle_service(SERVICE_NAME)
