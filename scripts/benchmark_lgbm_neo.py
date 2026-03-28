#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from poe_trade.config import settings
from poe_trade.db import ClickHouseClient
from poe_trade.ml.v3 import benchmark
from poe_trade.ml.v3 import sql


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the LGBM-neo benchmark")
    _ = parser.add_argument("--output", required=True)
    return parser


def _load_training_frame(
    client: ClickHouseClient, *, chunk_size: int = 10_000
) -> pd.DataFrame:
    count_query = f"SELECT count() AS row_count FROM {sql.POE_RARE_ITEM_TRAIN_TABLE} WHERE price_chaos > 0"
    row_count_frame = client.query_df(count_query)
    row_count = int(row_count_frame.iloc[0]["row_count"])
    query = sql.build_lgbm_neo_training_query()
    frames: list[pd.DataFrame] = []
    for offset in range(0, row_count, chunk_size):
        chunk_query = f"{query} LIMIT {chunk_size} OFFSET {offset}"
        frames.append(client.query_df(chunk_query))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    cfg = settings.get_settings()
    client = ClickHouseClient.from_env(cfg.clickhouse_url)

    try:
        frame = _load_training_frame(client)
        report = benchmark.run_lgbm_neo_benchmark(frame)
        report = benchmark.save_lgbm_neo_benchmark_artifacts(report, str(args.output))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:
        logging.getLogger(__name__).exception(
            "lgbm-neo benchmark command failed: %s", exc
        )
        return 1

    print(
        json.dumps(
            {
                "benchmark": report["benchmark"],
                "benchmark_number": report["benchmark_number"],
                "row_count": report["row_count"],
                "split": report["split"],
                "validation_metrics": report.get(
                    "validation_metrics", report["metrics"]
                ),
                "test_metrics": report.get("test_metrics", {}),
                "artifacts": report["artifacts"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
