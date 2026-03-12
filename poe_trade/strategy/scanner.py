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
        sql = pack.discover_sql_path.read_text(encoding="utf-8").strip().rstrip(";")
        client.execute(
            "INSERT INTO poe_trade.scanner_recommendations "
            "SELECT "
            f"'{scanner_run_id}' AS scanner_run_id, "
            f"'{pack.strategy_id}' AS strategy_id, "
            f"'{league}' AS league, "
            "toString(cityHash64(formatRowNoNewline('JSONEachRow', source.*))) AS item_or_market_key, "
            f"'discovered by {pack.strategy_id}' AS why_it_fired, "
            "'buy candidate' AS buy_plan, "
            "CAST(NULL AS Nullable(Float64)) AS max_buy, "
            "'' AS transform_plan, "
            "'review and sell' AS exit_plan, "
            f"'{pack.execution_venue}' AS execution_venue, "
            "CAST(NULL AS Nullable(Float64)) AS expected_profit_chaos, "
            "CAST(NULL AS Nullable(Float64)) AS expected_roi, "
            "'unknown' AS expected_hold_time, "
            "CAST(NULL AS Nullable(Float64)) AS confidence, "
            "formatRowNoNewline('JSONEachRow', source.*) AS evidence_snapshot, "
            "now64(3) AS recorded_at "
            f"FROM ({sql}) AS source"
        )
        client.execute(
            "INSERT INTO poe_trade.scanner_alert_log "
            "SELECT "
            "concat(scanner_run_id, '-', item_or_market_key) AS alert_id, "
            "scanner_run_id, strategy_id, league, item_or_market_key, 'new' AS status, evidence_snapshot, recorded_at "
            "FROM poe_trade.scanner_recommendations "
            f"WHERE scanner_run_id = '{scanner_run_id}' AND strategy_id = '{pack.strategy_id}'"
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
