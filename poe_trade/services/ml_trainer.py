from __future__ import annotations

import argparse
import json
import logging
import os
import time
from collections.abc import Sequence
from datetime import datetime, timedelta
from pathlib import Path

from poe_trade.config import settings as config_settings
from poe_trade.db import ClickHouseClient
from poe_trade.ml import workflows
from poe_trade.ml.v3 import backfill as v3_backfill
from poe_trade.ml.v3 import eval as v3_eval
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


def _query_rows(client: ClickHouseClient, query: str) -> list[dict[str, object]]:
    payload = client.execute(query).strip()
    if not payload:
        return []
    return [json.loads(line) for line in payload.splitlines() if line.strip()]


def _refresh_v3_training_examples(
    client: ClickHouseClient, *, league: str
) -> dict[str, object]:
    source_rows = _query_rows(
        client,
        " ".join(
            [
                "SELECT max(observed_at) AS latest_source_at",
                "FROM poe_trade.silver_v3_item_observations",
                f"WHERE league = '{league}'",
                "FORMAT JSONEachRow",
            ]
        ),
    )
    train_rows = _query_rows(
        client,
        " ".join(
            [
                "SELECT max(as_of_ts) AS latest_training_at",
                "FROM poe_trade.ml_v3_training_examples",
                f"WHERE league = '{league}'",
                "FORMAT JSONEachRow",
            ]
        ),
    )
    latest_source_at = str(
        (source_rows[0] if source_rows else {}).get("latest_source_at") or ""
    )
    latest_training_at = str(
        (train_rows[0] if train_rows else {}).get("latest_training_at") or ""
    )
    if not latest_source_at:
        return {
            "latest_source_at": None,
            "latest_training_at": latest_training_at or None,
            "replayed_days": [],
        }

    source_day = latest_source_at.split(" ", 1)[0]
    training_day = latest_training_at.split(" ", 1)[0] if latest_training_at else ""
    replayed_days: list[str] = []
    if not training_day or source_day >= training_day:
        start_rows = _query_rows(
            client,
            " ".join(
                [
                    "SELECT min(toDate(observed_at)) AS first_day",
                    "FROM poe_trade.silver_v3_item_observations",
                    f"WHERE league = '{league}'",
                    "FORMAT JSONEachRow",
                ]
            ),
        )
        first_source_day = str(
            (start_rows[0] if start_rows else {}).get("first_day") or ""
        )
        start_day = first_source_day
        if training_day:
            try:
                next_day = datetime.strptime(
                    training_day, "%Y-%m-%d"
                ).date() + timedelta(days=1)
                start_day = next_day.isoformat()
            except ValueError:
                start_day = training_day
        if start_day and start_day <= source_day:
            v3_backfill_result = v3_backfill.backfill_range(
                client,
                league=league,
                start_day=start_day,
                end_day=source_day,
            )
            replayed_days = [
                str(row.get("day") or "")
                for row in v3_backfill_result.get("results", [])
                if str(row.get("day") or "")
            ]

    return {
        "latest_source_at": latest_source_at,
        "latest_training_at": latest_training_at or None,
        "replayed_days": replayed_days,
    }


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
            data_refresh = _refresh_v3_training_examples(client, league=league)
            v3_result = v3_train.train_all_routes_v3(
                client,
                league=league,
                model_dir=str(args.model_dir),
            )
            eval_result: dict[str, object] | None = None
            run_id = str(v3_result.get("run_id") or "")
            eval_prediction_rows = int(v3_result.get("eval_prediction_rows") or 0)
            if run_id and eval_prediction_rows > 0:
                eval_result = v3_eval.evaluate_run(
                    client,
                    league=league,
                    run_id=run_id,
                )
            result = {
                "status": "completed",
                "stop_reason": "v3_train_cycle",
                "active_model_version": "v3",
                "v3": v3_result,
                "data_refresh": data_refresh,
                "evaluation": eval_result,
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
