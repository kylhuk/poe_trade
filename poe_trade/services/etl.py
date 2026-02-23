"""Raw to canonical ETL"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Sequence

from ..config import settings as config_settings
from ..etl.pipeline import run_etl_pipeline
from ._runner import run_idle_service

logger = logging.getLogger(__name__)

SERVICE_NAME = "etl"


def _default_rows() -> Sequence[dict]:
    return [
        {
            "stash_id": "demo-stash",
            "item": {
                "name": "Whispering Essence",
                "base_type": "Essence",
                "rarity": "unique",
                "properties": {
                    "tier": 1,
                },
            },
            "listing": {
                "id": "listing-1",
                "price": {
                    "amount": 20,
                    "currency": "Chaos",
                },
                "seller": "demo",
                "timestamp": "2026-02-22T00:00:00Z",
            },
        },
    ]


def _load_rows(path: Path | None) -> Sequence[dict]:
    if path and path.exists():
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            logger.warning("Failed to parse %s, falling back to sample rows", path)
    return _default_rows()


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the ETL service")
    parser.add_argument(
        "--input",
        type=Path,
        help="Path to a JSON array of bronze rows to parse",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    cfg = config_settings.get_settings()
    port = cfg.service_ports.get(SERVICE_NAME, None)
    logger.info("%s starting on port %s (clickhouse=%s) realms=%s leagues=%s", SERVICE_NAME, port, cfg.clickhouse_url, cfg.realms, cfg.leagues)

    rows = _load_rows(args.input)
    result = run_etl_pipeline(rows)
    logger.info("ETL parsed %s rows, metrics=%s", len(rows), result.metrics)

    if args.dry_run:
        logger.info("Dry-run detected; skipping idle loop")
        return

    run_idle_service(SERVICE_NAME)
