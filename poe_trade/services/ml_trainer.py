from __future__ import annotations

import argparse
import json
import logging
import os
import time
from collections.abc import Sequence
from pathlib import Path

from poe_trade.config import settings as config_settings
from poe_trade.db import ClickHouseClient
from poe_trade.ml import workflows
from poe_trade.ml.v3 import train as v3_train

SERVICE_NAME = "ml_trainer"


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _write_status(payload: dict[str, object]) -> None:
    status_path = Path(".sisyphus/state/qa/ml-trainer-last-run.json")
    status_path.parent.mkdir(parents=True, exist_ok=True)
    _ = status_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog=SERVICE_NAME, description="Run autonomous ML trainer service"
    )
    _ = parser.add_argument("--league", default=None)
    _ = parser.add_argument("--dataset-table", default="poe_trade.ml_price_dataset_v2")
    _ = parser.add_argument("--model-dir", default="artifacts/ml/mirage_v2")
    _ = parser.add_argument("--once", action="store_true")
    _ = parser.add_argument("--interval-seconds", type=int, default=None)
    args = parser.parse_args(argv)

    _configure_logging()
    cfg = config_settings.get_settings()
    if not cfg.ml_automation_enabled:
        logging.getLogger(__name__).info("%s disabled", SERVICE_NAME)
        return 0
    workflows._ensure_non_legacy_dataset_table(str(args.dataset_table))
    workflows._ensure_non_legacy_model_dir(str(args.model_dir))
    league = args.league or cfg.ml_automation_league
    interval = args.interval_seconds or cfg.ml_automation_interval_seconds
    v3_enabled = str(os.getenv("POE_ML_V3_TRAINER_ENABLED", "0")).strip() in {
        "1",
        "true",
        "yes",
        "on",
    }
    client = ClickHouseClient.from_env(cfg.clickhouse_url)
    try:
        workflows.warmup_active_models(client, league=league)
    except Exception as exc:
        logging.getLogger(__name__).warning(
            "ml trainer warmup failed for league=%s: %s",
            league,
            exc,
        )
    try:
        rollout = workflows.rollout_controls(client, league=league)
    except Exception as exc:
        logging.getLogger(__name__).warning(
            "ml trainer rollout read failed for league=%s: %s",
            league,
            exc,
        )
        rollout = {}

    while True:
        if v3_enabled:
            v3_result = v3_train.train_all_routes_v3(
                client,
                league=league,
                model_dir=str(args.model_dir),
            )
            result = {
                "status": "completed",
                "stop_reason": "v3_train_cycle",
                "active_model_version": "v3",
                "v3": v3_result,
            }
        else:
            result = workflows.train_loop(
                client,
                league=league,
                dataset_table=str(args.dataset_table),
                model_dir=str(args.model_dir),
                max_iterations=cfg.ml_automation_max_iterations,
                max_wall_clock_seconds=cfg.ml_automation_max_wall_clock_seconds,
                no_improvement_patience=cfg.ml_automation_no_improvement_patience,
                min_mdape_improvement=cfg.ml_automation_min_mdape_improvement,
                resume=False,
            )
        try:
            rollout = workflows.rollout_controls(client, league=league)
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "ml trainer rollout refresh failed for league=%s: %s",
                league,
                exc,
            )
        _write_status({"league": league, "result": result, "rollout": rollout})
        logging.getLogger(__name__).info(
            "ml trainer cycle status=%s stop_reason=%s",
            result.get("status"),
            result.get("stop_reason"),
        )
        if args.once:
            return 0
        time.sleep(max(interval, 1))


if __name__ == "__main__":
    raise SystemExit(main())
