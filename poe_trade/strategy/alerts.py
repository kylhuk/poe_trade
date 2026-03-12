from __future__ import annotations

import json
from datetime import datetime, timezone

from ..db import ClickHouseClient


def list_alerts(client: ClickHouseClient) -> list[dict[str, str]]:
    query = (
        "SELECT alert_id, strategy_id, league, item_or_market_key, status, latest_recorded_at AS recorded_at "
        "FROM ("
        "SELECT alert_id, argMax(strategy_id, recorded_at) AS strategy_id, argMax(league, recorded_at) AS league, "
        "argMax(item_or_market_key, recorded_at) AS item_or_market_key, argMax(status, recorded_at) AS status, max(recorded_at) AS latest_recorded_at "
        "FROM poe_trade.scanner_alert_log GROUP BY alert_id"
        ") ORDER BY latest_recorded_at DESC FORMAT JSONEachRow"
    )
    payload = client.execute(query).strip()
    if not payload:
        return []
    return [json.loads(line) for line in payload.splitlines() if line.strip()]


def ack_alert(client: ClickHouseClient, *, alert_id: str) -> str:
    recorded_at = _format_ts(datetime.now(timezone.utc))
    client.execute(
        "INSERT INTO poe_trade.scanner_alert_log "
        "SELECT "
        f"'{alert_id}' AS alert_id, "
        "scanner_run_id, strategy_id, league, item_or_market_key, 'acked' AS status, evidence_snapshot, "
        f"toDateTime64('{recorded_at}', 3, 'UTC') AS recorded_at "
        "FROM ("
        "SELECT scanner_run_id, strategy_id, league, item_or_market_key, evidence_snapshot "
        "FROM poe_trade.scanner_alert_log "
        f"WHERE alert_id = '{alert_id}' ORDER BY recorded_at DESC LIMIT 1"
        ")"
    )
    return alert_id


def _format_ts(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
