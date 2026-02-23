from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Sequence

from .models import ItemCanonical, ListingCanonical
from .parser import parse_bronze_row


class ETLPipelineResult:
    def __init__(self, items: Sequence[ItemCanonical], listings: Sequence[ListingCanonical], metrics: Mapping[str, object]) -> None:
        self.items = list(items)
        self.listings = list(listings)
        self.metrics = dict(metrics)


def run_etl_pipeline(rows: Iterable[Mapping[str, object]]) -> ETLPipelineResult:
    total_rows = 0
    parsed_rows = 0
    invalid_price_count = 0
    items: list[ItemCanonical] = []
    listings: list[ListingCanonical] = []
    seen_item_ids: set[str] = set()
    seen_listing_ids: set[str] = set()

    for row in rows:
        total_rows += 1
        try:
            parsed_pairs = parse_bronze_row(row)
        except ValueError:
            continue
        for item, listing in parsed_pairs:
            parsed_rows += 1
            if listing.price_amount <= 0:
                invalid_price_count += 1
                continue
            if item.item_uid in seen_item_ids or listing.listing_uid in seen_listing_ids:
                continue
            seen_item_ids.add(item.item_uid)
            seen_listing_ids.add(listing.listing_uid)
            items.append(item)
            listings.append(listing)

    priceable_candidates = max(parsed_rows - invalid_price_count, 0)
    metrics = {
        "total_rows": total_rows,
        "parsed_rows": parsed_rows,
        "parseable_price_pct": len(listings) / max(priceable_candidates, 1),
        "invalid_price_count": invalid_price_count,
    }
    return ETLPipelineResult(items=items, listings=listings, metrics=metrics)
