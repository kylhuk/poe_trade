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
from poe_trade.db.clickhouse import ClickHouseClientError


def _query_rows(client: ClickHouseClient, query: str) -> list[dict[str, object]]:
    payload = client.execute(query).strip()
    if not payload:
        return []
    return [json.loads(line) for line in payload.splitlines() if line.strip()]


def _count_rows(client: ClickHouseClient, query: str) -> int:
    rows = _query_rows(client, query)
    if not rows:
        return 0
    value = rows[0].get("row_count")
    return max(0, int(str(value or 0)))


def _parse_families(raw_value: str) -> list[str]:
    families = [
        family.strip().lower() for family in raw_value.split(",") if family.strip()
    ]
    if not families:
        raise ValueError("--families must include at least one item family")
    if len(set(families)) != len(families):
        raise ValueError("--families must not contain duplicates")
    return families


def _family_output_path(output_dir: Path, family: str) -> Path:
    return output_dir / family / "benchmark.txt"


def _aggregate_output_path(output_dir: Path) -> Path:
    return output_dir / "benchmark-item-families.txt"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the pricing benchmark across deterministic item families"
    )
    _ = parser.add_argument("--league", required=True)
    _ = parser.add_argument("--as-of-ts", required=True)
    _ = parser.add_argument("--sample-size", type=int, default=10_000)
    _ = parser.add_argument(
        "--families",
        default=",".join(sql.ITEM_FAMILY_NAMES),
        help="Comma-separated item families to benchmark.",
    )
    _ = parser.add_argument("--output-dir", required=True)
    return parser


def _family_shortfall_error(family: str, available: int, required: int) -> ValueError:
    return ValueError(
        f"{family} family shortfall: available={available} required={required}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    sample_size = int(args.sample_size)
    if sample_size <= 0:
        parser.error("--sample-size must be greater than 0")

    families = _parse_families(str(args.families))
    output_dir = Path(str(args.output_dir))

    cfg = settings.get_settings()
    client = ClickHouseClient.from_env(cfg.clickhouse_url)

    family_reports: dict[str, dict[str, object]] = {}
    family_artifacts: dict[str, dict[str, str]] = {}
    family_sample_counts: dict[str, int] = {}

    try:
        for family in families:
            count_query = sql.build_item_family_sample_count_query(
                league=str(args.league),
                as_of_ts=str(args.as_of_ts),
                family=family,
            )
            available = _count_rows(client, count_query)
            if available < sample_size:
                raise _family_shortfall_error(family, available, sample_size)

            sample_query = sql.build_item_family_sample_query(
                league=str(args.league),
                as_of_ts=str(args.as_of_ts),
                family=family,
                sample_size=sample_size,
            )
            rows = [dict(row) for row in _query_rows(client, sample_query)]
            if len(rows) < sample_size:
                raise ValueError(
                    f"{family} family shortfall after sampling: available={len(rows)} required={sample_size}"
                )

            family_output_path = _family_output_path(output_dir, family)
            family_result = benchmark.save_benchmark_artifacts(rows, family_output_path)
            family_sample_counts[family] = len(rows)
            family_artifacts[family] = dict(family_result.get("artifacts", {}))
            family_report = {
                key: value for key, value in family_result.items() if key != "artifacts"
            }
            family_reports[family] = family_report

        aggregate_report = benchmark.build_item_family_benchmark_report(
            family_reports,
            league=str(args.league),
            as_of_ts=str(args.as_of_ts),
            sample_size=sample_size,
            families=families,
        )
        aggregate_output_path = _aggregate_output_path(output_dir)
        aggregate_result = benchmark.save_item_family_benchmark_artifacts(
            aggregate_report,
            aggregate_output_path,
        )

    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except (ClickHouseClientError, Exception) as exc:
        logging.getLogger(__name__).exception(
            "benchmark item families command failed: %s", exc
        )
        return 1

    print(
        json.dumps(
            {
                "benchmark": aggregate_report["benchmark"],
                "league": aggregate_report["league"],
                "as_of_ts": aggregate_report["as_of_ts"],
                "sample_size": aggregate_report["sample_size"],
                "families": aggregate_report["families"],
                "row_count": aggregate_report["row_count"],
                "family_sample_counts": family_sample_counts,
                "family_artifacts": family_artifacts,
                "aggregate_artifacts": aggregate_result["artifacts"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
