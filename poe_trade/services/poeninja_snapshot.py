from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Sequence

from ..config import settings as config_settings
from ..db import ClickHouseClient
from ..ml import workflows as ml_workflows


LOGGER = logging.getLogger(__name__)
SERVICE_NAME = "poeninja_snapshot"
MIN_REBUILD_INTERVAL_SECONDS = 1800


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog=SERVICE_NAME,
        description="Ingest PoeNinja raw snapshot data for incremental derivation",
    )
    parser.add_argument(
        "--league",
        help="League label (default from config)",
    )
    parser.add_argument(
        "--snapshot-table",
        default="poe_trade.raw_poeninja_currency_overview",
        help="Table for raw PoeNinja currency snapshot (default: poe_trade.raw_poeninja_currency_overview)",
    )
    parser.add_argument(
        "--interval-seconds",
        type=float,
        help="Polling interval in seconds (default from config or 900)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one pipeline cycle and exit",
    )
    parser.add_argument(
        "--full-rebuild-backfill",
        action="store_true",
        help="Deprecated no-op flag retained for compatibility",
    )
    args = parser.parse_args(argv)

    _configure_logging()
    cfg = config_settings.get_settings()

    # Check if enabled
    if not getattr(cfg, "poe_enable_poeninja_snapshot", True):
        LOGGER.info("%s disabled via POE_ENABLE_POENINJA_SNAPSHOT=false", SERVICE_NAME)
        return 0

    # Determine league
    league = (
        args.league
        or getattr(cfg, "poe_poeninja_snapshot_league", None)
        or cfg.ml_automation_league
    )
    if not league:
        LOGGER.error(
            "No league configured. Set POE_POENINJA_SNAPSHOT_LEAGUE or POE_ML_AUTOMATION_LEAGUE"
        )
        return 1

    # Determine interval
    interval = args.interval_seconds or getattr(
        cfg, "poe_ml_dataset_rebuild_interval_seconds", 900
    )
    if not args.once and interval < MIN_REBUILD_INTERVAL_SECONDS:
        LOGGER.warning(
            "%s interval %ss below floor %ss; clamping",
            SERVICE_NAME,
            interval,
            MIN_REBUILD_INTERVAL_SECONDS,
        )
        interval = MIN_REBUILD_INTERVAL_SECONDS

    LOGGER.info(
        "%s starting league=%s once=%s interval=%ss",
        SERVICE_NAME,
        league,
        args.once,
        interval,
    )

    # Initialize ClickHouse client
    ck_client = ClickHouseClient.from_env(cfg.clickhouse_url)

    # Ensure state directory exists
    state_dir = Path(".sisyphus/state")
    state_dir.mkdir(parents=True, exist_ok=True)
    status_file = state_dir / f"{SERVICE_NAME}-last-run.json"

    try:
        while True:
            start_time = time.time()
            LOGGER.info("%s: Starting pipeline cycle", SERVICE_NAME)

            # Step 1: Snapshot PoeNinja currency data
            LOGGER.info("Step 1: Snapshot PoeNinja currency")
            snapshot_result = ml_workflows.snapshot_poeninja(
                ck_client,
                league=league,
                output_table=args.snapshot_table,
                max_iterations=1,
            )
            snapshot_rows = snapshot_result.get("rows_written", 0)
            LOGGER.info("Snapshot complete: %d rows", snapshot_rows)
            if args.full_rebuild_backfill:
                LOGGER.warning(
                    "--full-rebuild-backfill is deprecated and ignored; poeninja_snapshot now performs snapshot-only ingest"
                )

            # Write status
            elapsed = time.time() - start_time
            status = {
                "timestamp": datetime.now(UTC).isoformat(),
                "league": league,
                "snapshot_mode": "steady_state_snapshot_only",
                "downstream_derivation_owner": "ml_v3",
                "downstream_rebuild_triggered": False,
                "snapshot_rows": snapshot_rows,
                "fx_rows": 0,
                "labels_rows": 0,
                "events_rows": 0,
                "dataset_rows": 0,
                "comps_rows": 0,
                "serving_profile_rows": 0,
                "serving_profile_as_of_ts": "",
                "rebuild_window": {},
                "previous_rebuild_window_id": "",
                "rebuild_skipped": True,
                "rebuild_skip_reason": "steady_state_snapshot_only",
                "elapsed_seconds": round(elapsed, 2),
            }
            with open(status_file, "w") as f:
                json.dump(status, f, indent=2)

            LOGGER.info("%s: Cycle complete in %.2fs", SERVICE_NAME, elapsed)

            if args.once:
                LOGGER.info("%s: --once specified, exiting", SERVICE_NAME)
                break

            time.sleep(interval)

    except KeyboardInterrupt:
        LOGGER.info("%s: Interrupted, shutting down", SERVICE_NAME)
        return 0
    except Exception as e:
        LOGGER.exception("%s: Fatal error", SERVICE_NAME)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
