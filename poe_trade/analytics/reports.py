from __future__ import annotations

import json
from typing import cast

from ..db import ClickHouseClient


def daily_report(client: ClickHouseClient, *, league: str) -> dict[str, object]:
    escaped_league = league.replace("'", "''")
    league_literal = f"'{escaped_league}'"
    query = (
        "SELECT "
        f"{league_literal} AS league, "
        f"(SELECT count() FROM poe_trade.scanner_recommendations WHERE league = {league_literal}) AS recommendations, "
        f"(SELECT count() FROM poe_trade.scanner_alert_log WHERE league = {league_literal}) AS alerts, "
        f"(SELECT count() FROM poe_trade.journal_events WHERE league = {league_literal}) AS journal_events, "
        f"(SELECT count() FROM poe_trade.journal_positions WHERE league = {league_literal}) AS journal_positions, "
        f"(SELECT count() FROM poe_trade.research_backtest_summary WHERE league = {league_literal}) AS backtest_summary_rows, "
        f"(SELECT count() FROM poe_trade.research_backtest_detail WHERE league = {league_literal}) AS backtest_detail_rows, "
        f"(SELECT count() FROM poe_trade.gold_currency_ref_hour WHERE league = {league_literal}) AS gold_currency_ref_hour_rows, "
        f"(SELECT count() FROM poe_trade.gold_listing_ref_hour WHERE ifNull(league, '') = {league_literal}) AS gold_listing_ref_hour_rows, "
        f"(SELECT count() FROM poe_trade.gold_liquidity_ref_hour WHERE ifNull(league, '') = {league_literal}) AS gold_liquidity_ref_hour_rows, "
        f"(SELECT count() FROM poe_trade.gold_bulk_premium_hour WHERE ifNull(league, '') = {league_literal}) AS gold_bulk_premium_hour_rows, "
        f"(SELECT count() FROM poe_trade.gold_set_ref_hour WHERE ifNull(league, '') = {league_literal}) AS gold_set_ref_hour_rows, "
        f"(SELECT coalesce(sum(realized_pnl_chaos), 0.0) FROM poe_trade.journal_positions WHERE league = {league_literal}) AS realized_pnl_chaos "
        "FORMAT JSONEachRow"
    )
    payload = client.execute(query).strip()
    if not payload:
        return {
            "league": league,
            "recommendations": 0,
            "alerts": 0,
            "journal_events": 0,
            "journal_positions": 0,
            "backtest_summary_rows": 0,
            "backtest_detail_rows": 0,
            "gold_currency_ref_hour_rows": 0,
            "gold_listing_ref_hour_rows": 0,
            "gold_liquidity_ref_hour_rows": 0,
            "gold_bulk_premium_hour_rows": 0,
            "gold_set_ref_hour_rows": 0,
            "realized_pnl_chaos": 0.0,
        }
    row: object = json.loads(payload.splitlines()[0])  # pyright: ignore[reportAny]
    return cast(dict[str, object], row)
