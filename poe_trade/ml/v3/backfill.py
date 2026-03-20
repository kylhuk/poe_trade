from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from poe_trade.db import ClickHouseClient

from . import sql

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BackfillDayResult:
    league: str
    day: str
    events_inserted: bool
    disappearance_events_inserted: bool
    labels_inserted: bool
    training_examples_inserted: bool


def _query_rows(client: ClickHouseClient, query: str) -> list[dict[str, Any]]:
    payload = client.execute(query).strip()
    if not payload:
        return []
    rows: list[dict[str, Any]] = []
    for line in payload.splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
    return rows


def disk_usage_bytes(client: ClickHouseClient) -> int:
    rows = _query_rows(client, sql.disk_usage_query())
    if not rows:
        return 0
    return int(rows[0].get("bytes_on_disk") or 0)


def guard_disk_budget(client: ClickHouseClient, *, max_bytes: int) -> int:
    current = disk_usage_bytes(client)
    if current > max(0, max_bytes):
        raise ValueError(
            f"disk budget exceeded: current={current} max={max_bytes}; aborting backfill"
        )
    return current


def replay_day(
    client: ClickHouseClient,
    *,
    league: str,
    day: date,
    max_bytes: int = 13_500_000_000,
) -> BackfillDayResult:
    guard_disk_budget(client, max_bytes=max_bytes)
    client.execute(sql.build_events_insert_query(league=league, day=day))
    client.execute(sql.build_disappearance_events_insert_query(league=league, day=day))
    client.execute(sql.build_sale_proxy_labels_insert_query(league=league, day=day))
    client.execute(sql.build_training_examples_insert_query(league=league, day=day))
    logger.info("ml-v3 replay day complete league=%s day=%s", league, day.isoformat())
    return BackfillDayResult(
        league=league,
        day=day.isoformat(),
        events_inserted=True,
        disappearance_events_inserted=True,
        labels_inserted=True,
        training_examples_inserted=True,
    )


def _parse_day(value: str) -> date:
    parsed = datetime.strptime(value, "%Y-%m-%d")
    return parsed.date()


def backfill_range(
    client: ClickHouseClient,
    *,
    league: str,
    start_day: str,
    end_day: str,
    max_bytes: int = 13_500_000_000,
) -> dict[str, Any]:
    start = _parse_day(start_day)
    end = _parse_day(end_day)
    if end < start:
        raise ValueError("end_day must be >= start_day")

    days = (end - start).days + 1
    cursor = start
    results: list[dict[str, Any]] = []
    while cursor <= end:
        result = replay_day(
            client,
            league=league,
            day=cursor,
            max_bytes=max_bytes,
        )
        results.append(
            {
                "league": result.league,
                "day": result.day,
                "events_inserted": result.events_inserted,
                "disappearance_events_inserted": result.disappearance_events_inserted,
                "labels_inserted": result.labels_inserted,
                "training_examples_inserted": result.training_examples_inserted,
            }
        )
        cursor += timedelta(days=1)

    return {
        "league": league,
        "start_day": start_day,
        "end_day": end_day,
        "days_requested": days,
        "days_processed": len(results),
        "results": results,
        "disk_bytes_after": disk_usage_bytes(client),
    }
