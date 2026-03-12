from __future__ import annotations

from datetime import datetime, timezone
import json
from uuid import uuid4

from ..db import ClickHouseClient


def record_trade_event(
    client: ClickHouseClient,
    *,
    action: str,
    strategy_id: str,
    league: str,
    item_or_market_key: str,
    price_chaos: float,
    quantity: float,
    notes: str = "",
    dry_run: bool = False,
) -> str:
    event_id = uuid4().hex
    event_ts = _format_ts(datetime.now(timezone.utc))
    if dry_run:
        return event_id

    event_row = {
        "event_id": event_id,
        "strategy_id": strategy_id,
        "league": league,
        "item_or_market_key": item_or_market_key,
        "action": action,
        "quantity": float(quantity),
        "price_chaos": float(price_chaos),
        "notes": notes,
        "event_ts": event_ts,
    }
    client.execute(
        "INSERT INTO poe_trade.journal_events "
        "(event_id, strategy_id, league, item_or_market_key, action, quantity, price_chaos, notes, event_ts)\n"
        "FORMAT JSONEachRow\n"
        f"{json.dumps(event_row, ensure_ascii=False)}"
    )

    quantity_expr = f"{float(quantity)}" if action == "buy" else f"-{float(quantity)}"
    avg_price_expr = (
        f"{float(price_chaos)}"
        if action == "buy"
        else "CAST(NULL AS Nullable(Float64))"
    )
    realized_expr = (
        f"{float(price_chaos)} * {float(quantity)}" if action == "sell" else "0.0"
    )
    client.execute(
        "INSERT INTO poe_trade.journal_positions "
        "SELECT "
        f"'{strategy_id}' AS strategy_id, "
        f"'{league}' AS league, "
        f"'{item_or_market_key}' AS item_or_market_key, "
        f"{quantity_expr} AS net_quantity, "
        f"{avg_price_expr} AS avg_entry_price_chaos, "
        f"{realized_expr} AS realized_pnl_chaos, "
        f"'{action}' AS last_action, "
        "now64(3) AS updated_at"
    )
    return event_id


def _format_ts(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
