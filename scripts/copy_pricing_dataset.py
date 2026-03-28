#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from poe_trade.config import settings
from poe_trade.db import ClickHouseClient


CLICKHOUSE_SORT_SETTINGS = "SETTINGS max_bytes_before_external_sort = 268435456"


def _quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


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


def _sort_key(row: dict[str, object]) -> tuple[str, str, str]:
    return (
        str(row.get("as_of_ts") or ""),
        str(row.get("identity_key") or row.get("item_id") or ""),
        str(row.get("item_id") or ""),
    )


def _build_query(
    *,
    source_table: str,
    league: str,
    limit: int,
    half_sample: bool,
) -> str:
    order_by = "ORDER BY as_of_ts ASC, identity_key ASC, item_id ASC"
    if half_sample:
        return " ".join(
            [
                "SELECT *",
                f"FROM {source_table}",
                f"WHERE league = {_quote(league)}",
                order_by,
                f"LIMIT {max(1, int(limit))}",
                CLICKHOUSE_SORT_SETTINGS,
                "FORMAT JSONEachRow",
            ]
        )
    return " ".join(
        [
            "SELECT *",
            f"FROM {source_table}",
            f"WHERE league = {_quote(league)}",
            "ORDER BY as_of_ts DESC",
            f"LIMIT {max(1, int(limit))}",
            CLICKHOUSE_SORT_SETTINGS,
            "FORMAT JSONEachRow",
        ]
    )


def _build_half_sample_timestamp_query(
    *,
    source_table: str,
    league: str,
    limit: int,
) -> str:
    return " ".join(
        [
            "SELECT as_of_ts",
            f"FROM {source_table}",
            f"WHERE league = {_quote(league)}",
            "ORDER BY as_of_ts ASC",
            f"LIMIT {max(1, int(limit))}",
            CLICKHOUSE_SORT_SETTINGS,
            "FORMAT JSONEachRow",
        ]
    )


def _build_half_sample_data_query(
    *,
    source_table: str,
    league: str,
    limit: int,
    cutoff_as_of_ts: str,
) -> str:
    return " ".join(
        [
            "SELECT *",
            f"FROM {source_table}",
            f"WHERE league = {_quote(league)}",
            f"AND as_of_ts <= toDateTime64({_quote(cutoff_as_of_ts)}, 3, 'UTC')",
            "ORDER BY as_of_ts ASC, identity_key ASC, item_id ASC",
            f"LIMIT {max(1, int(limit))}",
            CLICKHOUSE_SORT_SETTINGS,
            "FORMAT JSONEachRow",
        ]
    )


def _build_count_query(*, source_table: str, league: str) -> str:
    return " ".join(
        [
            "SELECT count() AS row_count",
            f"FROM {source_table}",
            f"WHERE league = {_quote(league)}",
            "FORMAT JSONEachRow",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Copy a pricing benchmark dataset out of ClickHouse"
    )
    parser.add_argument("--league", required=True)
    parser.add_argument(
        "--source-table",
        default="poe_trade.ml_v3_training_examples",
        help="ClickHouse table to snapshot",
    )
    parser.add_argument("--limit", type=int, default=5000)
    parser.add_argument(
        "--half-sample",
        action="store_true",
        help="Deterministically export half of the eligible rows for benchmarking.",
    )
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    cfg = settings.get_settings()
    client = ClickHouseClient.from_env(cfg.clickhouse_url)
    half_sample_limit = int(args.limit)
    rows: list[dict[str, object]]
    if bool(args.half_sample):
        count_query = _build_count_query(
            source_table=str(args.source_table),
            league=str(args.league),
        )
        eligible_count = _count_rows(client, count_query)
        half_sample_limit = max(1, eligible_count // 2)
        timestamp_query = _build_half_sample_timestamp_query(
            source_table=str(args.source_table),
            league=str(args.league),
            limit=half_sample_limit,
        )
        timestamp_rows = [dict(row) for row in _query_rows(client, timestamp_query)]
        if not timestamp_rows:
            rows = []
        else:
            data_query = _build_half_sample_data_query(
                source_table=str(args.source_table),
                league=str(args.league),
                limit=half_sample_limit,
                cutoff_as_of_ts=str(timestamp_rows[-1].get("as_of_ts") or ""),
            )
            rows = [dict(row) for row in _query_rows(client, data_query)]
    else:
        query = _build_query(
            source_table=str(args.source_table),
            league=str(args.league),
            limit=half_sample_limit,
            half_sample=bool(args.half_sample),
        )
        rows = [dict(row) for row in _query_rows(client, query)]

    output_path = Path(str(args.output))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "\n".join(json.dumps(row, separators=(",", ":")) for row in rows)
        + ("\n" if rows else ""),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "league": args.league,
                "source_table": args.source_table,
                "output": str(output_path),
                "row_count": len(rows),
                "half_sample": bool(args.half_sample),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
