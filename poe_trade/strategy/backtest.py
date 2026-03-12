from __future__ import annotations

from datetime import datetime, timezone
import json
import re
from typing import Any
from uuid import uuid4

from ..db import ClickHouseClient
from .registry import StrategyPack, list_strategy_packs

UNSET_COMPLETED_AT = "1970-01-01 00:00:00.000"
BACKTEST_SUMMARY_COLUMNS = (
    "run_id",
    "strategy_id",
    "league",
    "lookback_days",
    "status",
    "opportunity_count",
    "expected_profit_chaos",
    "expected_roi",
    "confidence",
    "summary",
)
BACKTEST_SUMMARY_HEADER = "\t".join(BACKTEST_SUMMARY_COLUMNS)
BACKTEST_OUTCOMES = ("completed", "no_data", "no_opportunities", "failed")

_DEFAULT_SUMMARY_TEXT = {
    "completed": "opportunities found",
    "no_data": "no source data in league/lookback window",
    "no_opportunities": "source data exists but no strategy opportunities",
    "failed": "backtest execution failed",
}


def get_strategy_pack(strategy_id: str) -> StrategyPack:
    for pack in list_strategy_packs():
        if pack.strategy_id == strategy_id:
            return pack
    raise ValueError(f"Unknown strategy pack: {strategy_id}")


def run_backtest(
    client: ClickHouseClient,
    *,
    strategy_id: str,
    league: str,
    lookback_days: int,
    dry_run: bool = False,
) -> str:
    pack = get_strategy_pack(strategy_id)
    run_id = uuid4().hex
    started_at = datetime.now(timezone.utc)
    started_at_sql = _format_ts(started_at)
    sql = pack.backtest_sql_path.read_text(encoding="utf-8").strip().rstrip(";")
    wrapped_sql = _build_filtered_backtest_sql(
        sql, league=league, lookback_days=lookback_days
    )

    if dry_run:
        return run_id

    source_table = _extract_source_table(sql)
    client.execute(
        _build_run_insert_query(
            run_id,
            strategy_id,
            league,
            lookback_days,
            started_at_sql,
            status="running",
            notes="",
        )
    )

    status = "completed"
    summary_text = _DEFAULT_SUMMARY_TEXT["completed"]
    opportunity_count = 0
    expected_profit_chaos: float | None = None
    expected_roi: float | None = None
    confidence: float | None = None

    try:
        client.execute(
            "INSERT INTO poe_trade.research_backtest_detail "
            "(run_id, strategy_id, league, lookback_days, status, recorded_at, item_or_market_key, expected_profit_chaos, expected_roi, confidence, summary, detail_json) "
            "SELECT "
            f"'{_escape_sql(run_id)}' AS run_id, "
            f"'{_escape_sql(strategy_id)}' AS strategy_id, "
            f"'{_escape_sql(league)}' AS league, "
            f"{int(lookback_days)} AS lookback_days, "
            "'completed' AS status, "
            "now64(3) AS recorded_at, "
            "source.item_or_market_key AS item_or_market_key, "
            "source.expected_profit_chaos AS expected_profit_chaos, "
            "source.expected_roi AS expected_roi, "
            "source.confidence AS confidence, "
            "source.summary AS summary, "
            "formatRowNoNewline('JSONEachRow', source.*) AS detail_json "
            f"FROM ({wrapped_sql}) AS source"
        )

        summary_payload = client.execute(
            "SELECT "
            "count() AS opportunity_count, "
            "sumOrNull(expected_profit_chaos) AS expected_profit_chaos, "
            "avgOrNull(expected_roi) AS expected_roi, "
            "avgOrNull(confidence) AS confidence "
            "FROM poe_trade.research_backtest_detail "
            f"WHERE run_id = '{_escape_sql(run_id)}' "
            "FORMAT JSONEachRow"
        )
        summary_rows = _parse_json_rows(summary_payload)
        if summary_rows:
            summary_row = summary_rows[0]
            opportunity_count = int(summary_row.get("opportunity_count", 0) or 0)
            expected_profit_chaos = _as_optional_float(
                summary_row.get("expected_profit_chaos")
            )
            expected_roi = _as_optional_float(summary_row.get("expected_roi"))
            confidence = _as_optional_float(summary_row.get("confidence"))

        if opportunity_count == 0:
            source_rows = _count_source_rows(
                client,
                source_table=source_table,
                league=league,
                lookback_days=lookback_days,
            )
            if source_rows == 0:
                status = "no_data"
                summary_text = _DEFAULT_SUMMARY_TEXT["no_data"]
            else:
                status = "no_opportunities"
                summary_text = _DEFAULT_SUMMARY_TEXT["no_opportunities"]

    except Exception as exc:
        status = "failed"
        summary_text = f"{_DEFAULT_SUMMARY_TEXT['failed']}: {exc}"
        opportunity_count = 0
        expected_profit_chaos = None
        expected_roi = None
        confidence = None
        client.execute(
            _build_summary_insert_query(
                run_id=run_id,
                strategy_id=strategy_id,
                league=league,
                lookback_days=lookback_days,
                status=status,
                opportunity_count=opportunity_count,
                expected_profit_chaos=expected_profit_chaos,
                expected_roi=expected_roi,
                confidence=confidence,
                summary=summary_text,
            )
        )
        client.execute(
            _build_run_insert_query(
                run_id,
                strategy_id,
                league,
                lookback_days,
                started_at_sql,
                status="failed",
                notes=summary_text,
            )
        )
        raise

    client.execute(
        _build_summary_insert_query(
            run_id=run_id,
            strategy_id=strategy_id,
            league=league,
            lookback_days=lookback_days,
            status=status,
            opportunity_count=opportunity_count,
            expected_profit_chaos=expected_profit_chaos,
            expected_roi=expected_roi,
            confidence=confidence,
            summary=summary_text,
        )
    )
    client.execute(
        _build_run_insert_query(
            run_id,
            strategy_id,
            league,
            lookback_days,
            started_at_sql,
            status=status,
            notes="shared summary contract",
        )
    )
    return run_id


def fetch_backtest_summary_rows(
    client: ClickHouseClient,
    *,
    run_id: str,
) -> list[dict[str, Any]]:
    payload = client.execute(
        "SELECT "
        "run_id, strategy_id, league, lookback_days, status, opportunity_count, expected_profit_chaos, expected_roi, confidence, summary "
        "FROM poe_trade.research_backtest_summary "
        f"WHERE run_id = '{_escape_sql(run_id)}' "
        "ORDER BY strategy_id "
        "FORMAT JSONEachRow"
    )
    return _parse_json_rows(payload)


def format_summary_row(row: dict[str, Any]) -> str:
    values: list[str] = []
    for column in BACKTEST_SUMMARY_COLUMNS:
        value = row.get(column)
        if value is None:
            values.append("")
        else:
            values.append(str(value))
    return "\t".join(values)


def backtest_status_rank(status: str) -> int:
    ranking = {
        "completed": 0,
        "no_opportunities": 1,
        "no_data": 2,
        "failed": 3,
    }
    return ranking.get(status, 9)


def _format_ts(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def _build_filtered_backtest_sql(sql: str, *, league: str, lookback_days: int) -> str:
    return (
        "SELECT * FROM ("
        f"{sql}"
        ") AS scoped_source "
        f"WHERE ifNull(scoped_source.league, '') = '{_escape_sql(league)}' "
        f"AND scoped_source.time_bucket >= now() - INTERVAL {max(1, int(lookback_days))} DAY"
    )


def _build_run_insert_query(
    run_id: str,
    strategy_id: str,
    league: str,
    lookback_days: int,
    started_at_sql: str,
    *,
    status: str,
    notes: str,
) -> str:
    payload = {
        "run_id": run_id,
        "strategy_id": strategy_id,
        "league": league,
        "lookback_days": int(lookback_days),
        "started_at": started_at_sql,
        "completed_at": _format_ts(datetime.now(timezone.utc))
        if status != "running"
        else UNSET_COMPLETED_AT,
        "status": status,
        "notes": notes,
    }
    return (
        "INSERT INTO poe_trade.research_backtest_runs "
        "(run_id, strategy_id, league, lookback_days, started_at, completed_at, status, notes)\n"
        "FORMAT JSONEachRow\n"
        f"{json.dumps(payload, separators=(',', ':'))}"
    )


def _build_summary_insert_query(
    *,
    run_id: str,
    strategy_id: str,
    league: str,
    lookback_days: int,
    status: str,
    opportunity_count: int,
    expected_profit_chaos: float | None,
    expected_roi: float | None,
    confidence: float | None,
    summary: str,
) -> str:
    payload = {
        "run_id": run_id,
        "strategy_id": strategy_id,
        "league": league,
        "lookback_days": int(lookback_days),
        "status": status,
        "opportunity_count": int(opportunity_count),
        "expected_profit_chaos": expected_profit_chaos,
        "expected_roi": expected_roi,
        "confidence": confidence,
        "summary": summary,
        "recorded_at": _format_ts(datetime.now(timezone.utc)),
    }
    return (
        "INSERT INTO poe_trade.research_backtest_summary "
        "(run_id, strategy_id, league, lookback_days, status, opportunity_count, expected_profit_chaos, expected_roi, confidence, summary, recorded_at)\n"
        "FORMAT JSONEachRow\n"
        f"{json.dumps(payload, separators=(',', ':'))}"
    )


def _parse_json_rows(payload: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in payload.splitlines():
        cleaned = line.strip()
        if not cleaned:
            continue
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            rows.append(parsed)
    return rows


def _count_source_rows(
    client: ClickHouseClient,
    *,
    source_table: str | None,
    league: str,
    lookback_days: int,
) -> int:
    if not source_table:
        return 0
    payload = client.execute(
        "SELECT count() AS source_rows "
        f"FROM {source_table} "
        f"WHERE ifNull(league, '') = '{_escape_sql(league)}' "
        f"AND time_bucket >= now() - INTERVAL {max(1, int(lookback_days))} DAY "
        "FORMAT JSONEachRow"
    )
    rows = _parse_json_rows(payload)
    if not rows:
        return 0
    return int(rows[0].get("source_rows", 0) or 0)


def _extract_source_table(sql: str) -> str | None:
    scrubbed = re.sub(r"'([^']|'')*'", "''", sql)
    match = re.search(r"\bFROM\s+([A-Za-z0-9_.]+)", scrubbed, flags=re.IGNORECASE)
    if not match:
        return None
    return match.group(1)


def _as_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _escape_sql(value: str) -> str:
    return value.replace("'", "''")
