#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from poe_trade.config import settings
from poe_trade.db import ClickHouseClient
from poe_trade.ml.v3 import benchmark
from poe_trade.ml.v3 import sql


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the Mirage Iron Ring benchmark on the stable branch view"
    )
    _ = parser.add_argument("--league", required=True)
    _ = parser.add_argument("--sample-size", type=int, default=10_000)
    _ = parser.add_argument("--output", required=True)
    return parser


def _query_rows(client: ClickHouseClient, query: str) -> list[dict[str, object]]:
    payload = client.execute(query).strip()
    if not payload:
        return []
    return [json.loads(line) for line in payload.splitlines() if line.strip()]


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    sample_size = int(args.sample_size)
    if sample_size <= 0:
        parser.error("--sample-size must be greater than 0")

    cfg = settings.get_settings()
    client = ClickHouseClient.from_env(cfg.clickhouse_url)

    try:
        catalog_query = sql.build_mirage_iron_ring_affix_catalog_query()
        affix_catalog = benchmark.build_mirage_affix_catalog(
            _query_rows(client, catalog_query)
        )
        query = sql.build_mirage_iron_ring_benchmark_sample_query(
            league=str(args.league),
            sample_size=sample_size,
        )
        rows = [
            benchmark.normalize_mirage_iron_ring_branch_row(
                row, affix_catalog=affix_catalog
            )
            for row in _query_rows(client, query)
        ]
        report = benchmark.run_mirage_iron_ring_branch_benchmark(rows)
        report = benchmark.save_mirage_iron_ring_branch_benchmark_artifacts(
            report, str(args.output)
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:
        logging.getLogger(__name__).exception(
            "mirage iron ring benchmark command failed: %s", exc
        )
        return 1

    print(
        json.dumps(
            {
                "benchmark": "mirage_iron_ring_branch_benchmark_v1",
                "contract": report["contract"],
                "split": report["split"],
                "row_count": len(rows),
                "candidate_count": report["contract"]["candidate_count"],
                "best_candidate": report["best_candidate"],
                "artifacts": report["artifacts"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
