from __future__ import annotations

from datetime import datetime, timezone
import time
from uuid import uuid4

from ..db import ClickHouseClient
from .registry import list_strategy_packs


def run_scan_once(
    client: ClickHouseClient,
    *,
    league: str,
    dry_run: bool = False,
) -> str:
    scanner_run_id = uuid4().hex
    enabled_packs = [pack for pack in list_strategy_packs() if pack.enabled]

    if dry_run:
        return scanner_run_id

    for pack in enabled_packs:
        if pack.requires_journal:
            continue
        sql = pack.discover_sql_path.read_text(encoding="utf-8").strip().rstrip(";")
        filters = _runtime_filters(pack)
        where_clause = f" WHERE {' AND '.join(filters)}" if filters else ""
        _ = client.execute(
            "INSERT INTO poe_trade.scanner_recommendations "
            "WITH formatRowNoNewline('JSONEachRow', source.*) AS source_row_json "
            "SELECT "
            f"'{scanner_run_id}' AS scanner_run_id, "
            f"'{pack.strategy_id}' AS strategy_id, "
            f"'{league}' AS league, "
            "toString(cityHash64(source_row_json)) AS item_or_market_key, "
            "if(JSONHas(source_row_json, 'why_it_fired'), "
            f"JSONExtractString(source_row_json, 'why_it_fired'), 'discovered by {pack.strategy_id}') AS why_it_fired, "
            "if(JSONHas(source_row_json, 'buy_plan'), "
            "JSONExtractString(source_row_json, 'buy_plan'), 'buy candidate') AS buy_plan, "
            "if(JSONHas(source_row_json, 'max_buy'), "
            "JSONExtract(source_row_json, 'Nullable(Float64)', 'max_buy'), CAST(NULL AS Nullable(Float64))) AS max_buy, "
            "if(JSONHas(source_row_json, 'transform_plan'), "
            "JSONExtractString(source_row_json, 'transform_plan'), '') AS transform_plan, "
            "if(JSONHas(source_row_json, 'exit_plan'), "
            "JSONExtractString(source_row_json, 'exit_plan'), 'review and sell') AS exit_plan, "
            f"'{pack.execution_venue}' AS execution_venue, "
            "if(JSONHas(source_row_json, 'expected_profit_chaos'), "
            "JSONExtract(source_row_json, 'Nullable(Float64)', 'expected_profit_chaos'), CAST(NULL AS Nullable(Float64))) AS expected_profit_chaos, "
            "if(JSONHas(source_row_json, 'expected_roi'), "
            "JSONExtract(source_row_json, 'Nullable(Float64)', 'expected_roi'), CAST(NULL AS Nullable(Float64))) AS expected_roi, "
            "if(JSONHas(source_row_json, 'expected_hold_time'), "
            "JSONExtractString(source_row_json, 'expected_hold_time'), 'unknown') AS expected_hold_time, "
            "if(JSONHas(source_row_json, 'confidence'), "
            "JSONExtract(source_row_json, 'Nullable(Float64)', 'confidence'), CAST(NULL AS Nullable(Float64))) AS confidence, "
            "source_row_json AS evidence_snapshot, "
            "now64(3) AS recorded_at "
            f"FROM ({sql}) AS source{where_clause}"
        )
        _ = client.execute(
            "INSERT INTO poe_trade.scanner_alert_log "
            "SELECT "
            "candidate.alert_id, candidate.scanner_run_id, candidate.strategy_id, candidate.league, "
            "candidate.item_or_market_key, 'new' AS status, candidate.evidence_snapshot, candidate.recorded_at "
            "FROM ("
            "SELECT concat(strategy_id, '|', league, '|', item_or_market_key) AS alert_id, "
            "scanner_run_id, strategy_id, league, item_or_market_key, evidence_snapshot, recorded_at "
            "FROM poe_trade.scanner_recommendations "
            f"WHERE scanner_run_id = '{scanner_run_id}' AND strategy_id = '{pack.strategy_id}'"
            ") AS candidate "
            "LEFT JOIN ("
            "SELECT alert_id, max(recorded_at) AS last_recorded_at "
            "FROM poe_trade.scanner_alert_log GROUP BY alert_id"
            ") AS previous ON candidate.alert_id = previous.alert_id "
            "WHERE previous.last_recorded_at IS NULL "
            f"OR dateDiff('minute', previous.last_recorded_at, candidate.recorded_at) >= {pack.cooldown_minutes}"
        )

    return scanner_run_id


def run_scan_watch(
    client: ClickHouseClient,
    *,
    league: str,
    interval_seconds: float,
    max_runs: int | None = None,
    dry_run: bool = False,
) -> list[str]:
    run_ids: list[str] = []
    completed_runs = 0
    while max_runs is None or completed_runs < max_runs:
        run_ids.append(run_scan_once(client, league=league, dry_run=dry_run))
        completed_runs += 1
        if max_runs is not None and completed_runs >= max_runs:
            break
        time.sleep(interval_seconds)
    return run_ids


def format_scan_timestamp(value: datetime | None = None) -> str:
    current = value or datetime.now(timezone.utc)
    return current.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def _runtime_filters(pack: object) -> list[str]:
    filters: list[str] = []
    min_profit = _optional_float(getattr(pack, "min_expected_profit_chaos", None))
    if min_profit is not None:
        filters.append(
            "coalesce(JSONExtract(source_row_json, 'Nullable(Float64)', 'expected_profit_chaos'), CAST(-1e18 AS Float64)) "
            f">= {min_profit:.6f}"
        )
    min_roi = _optional_float(getattr(pack, "min_expected_roi", None))
    if min_roi is not None:
        filters.append(
            "coalesce(JSONExtract(source_row_json, 'Nullable(Float64)', 'expected_roi'), CAST(-1e18 AS Float64)) "
            f">= {min_roi:.6f}"
        )
    min_confidence = _optional_float(getattr(pack, "min_confidence", None))
    if min_confidence is not None:
        filters.append(
            "coalesce(JSONExtract(source_row_json, 'Nullable(Float64)', 'confidence'), CAST(-1e18 AS Float64)) "
            f">= {min_confidence:.6f}"
        )
    min_sample_count = _optional_int(getattr(pack, "min_sample_count", None))
    if min_sample_count is not None and min_sample_count > 0:
        filters.append(
            "coalesce("
            "JSONExtract(source_row_json, 'Nullable(Int64)', 'sample_count'), "
            "JSONExtract(source_row_json, 'Nullable(Int64)', 'listing_count'), "
            "JSONExtract(source_row_json, 'Nullable(Int64)', 'observed_samples'), "
            "CAST(0 AS Int64)"
            f") >= {min_sample_count}"
        )
    return filters


def _optional_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _optional_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip():
        try:
            return int(value)
        except ValueError:
            return None
    return None
