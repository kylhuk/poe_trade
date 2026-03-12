from __future__ import annotations

import json

from ..db import ClickHouseClient


def daily_report(client: ClickHouseClient, *, league: str) -> dict[str, object]:
    query = (
        "SELECT "
        f"'{league}' AS league, "
        "(SELECT count() FROM poe_trade.scanner_recommendations WHERE league = {league:String}) AS recommendations, "
        "(SELECT count() FROM poe_trade.scanner_alert_log WHERE league = {league:String}) AS alerts, "
        "(SELECT count() FROM poe_trade.journal_events WHERE league = {league:String}) AS journal_events, "
        "(SELECT count() FROM poe_trade.journal_positions WHERE league = {league:String}) AS journal_positions, "
        "(SELECT sum(realized_pnl_chaos) FROM poe_trade.journal_positions WHERE league = {league:String}) AS realized_pnl_chaos "
        "FORMAT JSONEachRow"
    )
    rendered = query.replace("{league:String}", f"'{league}'")
    payload = client.execute(rendered).strip()
    if not payload:
        return {
            "league": league,
            "recommendations": 0,
            "alerts": 0,
            "journal_events": 0,
            "journal_positions": 0,
            "realized_pnl_chaos": 0.0,
        }
    return json.loads(payload.splitlines()[0])
