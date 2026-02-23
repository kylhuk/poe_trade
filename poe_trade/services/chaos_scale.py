"""Chaos normalization + stats"""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from ..config import settings as config_settings
from ..analytics.chaos_scale import ChaosScaleEngine
from ..etl.models import CurrencySnapshot
from ._runner import run_idle_service

logger = logging.getLogger(__name__)

SERVICE_NAME = "chaos_scale"


def _default_snapshots() -> Sequence[CurrencySnapshot]:
    timestamp = datetime.now(timezone.utc)
    return [
        CurrencySnapshot(currency="Chaos", chaos_value=1.0, timestamp=timestamp),
        CurrencySnapshot(currency="Divine", chaos_value=132.0, timestamp=timestamp),
        CurrencySnapshot(currency="Exalted", chaos_value=150.0, timestamp=timestamp),
    ]


def _load_snapshots(path: Path | None) -> Sequence[CurrencySnapshot]:
    if path and path.exists():
        try:
            data = json.loads(path.read_text())
            return [
                CurrencySnapshot(currency=item.get("currency", "Chaos"), chaos_value=float(item.get("chaos_value", 1.0)), timestamp=datetime.now(timezone.utc))
                for item in data
            ]
        except json.JSONDecodeError:
            logger.warning("Failed to parse %s, falling back to defaults", path)
    return _default_snapshots()


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the chaos scale service")
    parser.add_argument("--input", type=Path, help="JSON array of currency snapshots")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    cfg = config_settings.get_settings()
    port = cfg.service_ports.get(SERVICE_NAME, None)
    logger.info("%s starting on port %s (clickhouse=%s) realms=%s leagues=%s", SERVICE_NAME, port, cfg.clickhouse_url, cfg.realms, cfg.leagues)

    snapshots = _load_snapshots(args.input)
    engine = ChaosScaleEngine.from_snapshots(snapshots)
    sample = 12.5
    normalized = engine.normalize_listing(sample, "Divine")
    logger.info("Normalized %s Divine to %.2f chaos using snapshots %s", sample, normalized, [asdict(snapshot) for snapshot in snapshots])

    if args.dry_run:
        logger.info("Dry-run: skipping idle loop for %s", SERVICE_NAME)
        return

    run_idle_service(SERVICE_NAME)
