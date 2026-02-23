"""Arbitrage engine"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from ..analytics.flip_finder import find_flip_opportunities
from ..analytics.price_stats import compute_price_stats
from ..etl.models import ListingCanonical
from ._runner import run_idle_service

logger = logging.getLogger(__name__)

SERVICE_NAME = "flip_finder"


def _default_listings() -> Sequence[ListingCanonical]:
    now = datetime.now(timezone.utc)
    return [
        ListingCanonical(
            listing_id="flip-1",
            item_id="item-1",
            price=25.0,
            currency="Chaos",
            seller="demo",
            timestamp=now,
            fp_exact="exact",
            fp_loose="loose",
        ),
        ListingCanonical(
            listing_id="flip-2",
            item_id="item-2",
            price=5.0,
            currency="Chaos",
            seller="demo",
            timestamp=now,
            fp_exact="exact2",
            fp_loose="loose2",
        ),
    ]


def _load_listings(path: Path | None) -> Sequence[ListingCanonical]:
    if path and path.exists():
        try:
            data = json.loads(path.read_text())
            now = datetime.now(timezone.utc)
            return [
                ListingCanonical(
                    listing_id=item.get("listing_id", "unknown"),
                    item_id=item.get("item_id", "unknown"),
                    price=float(item.get("price", 0.0)),
                    currency=item.get("currency", "Chaos"),
                    seller=item.get("seller", "unknown"),
                    timestamp=now,
                    fp_exact=item.get("fp_exact", "fp"),
                    fp_loose=item.get("fp_loose", "fp"),
                )
                for item in data
            ]
        except json.JSONDecodeError:
            logger.warning("Failed to parse %s, falling back to defaults", path)
    return _default_listings()


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the flip finder service")
    parser.add_argument("--input", type=Path, help="JSON array of listing snapshots")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    listings = _load_listings(args.input)
    stats = compute_price_stats([listing.price for listing in listings])
    flips = find_flip_opportunities(list(listings), stats)
    logger.info("Detected %s flips from %s listings", len(flips), len(listings))

    if args.dry_run:
        logger.info("Flips: %s", [flip.listing_id for flip in flips])
        return

    run_idle_service(SERVICE_NAME)
