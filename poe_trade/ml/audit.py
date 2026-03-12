from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import cast

from poe_trade.db import ClickHouseClient
from poe_trade.db.clickhouse import ClickHouseClientError

from .contract import TARGET_CONTRACT
from .runtime import RuntimeProfile


VALIDATED_LEAGUES = {"Mirage"}


def build_audit_report(
    client: ClickHouseClient,
    *,
    league: str,
    runtime_profile: RuntimeProfile,
) -> dict[str, object]:
    _ensure_supported_league(league)
    league_literal = _quote(league)

    total_rows = _required_count(
        client,
        "total_rows",
        f"SELECT count() AS value FROM poe_trade.silver_ps_items_raw WHERE league = {league_literal}",
    )
    priced_rows = _required_count(
        client,
        "priced_rows",
        f"SELECT count() AS value FROM poe_trade.v_ps_items_enriched WHERE league = {league_literal} AND price_amount IS NOT NULL AND price_amount > 0",
    )
    clean_currency_rows = _required_count(
        client,
        "clean_currency_rows",
        " ".join(
            [
                "SELECT count() AS value FROM poe_trade.v_ps_items_enriched",
                f"WHERE league = {league_literal}",
                "AND price_amount IS NOT NULL AND price_amount > 0",
                "AND price_currency IS NOT NULL",
                "AND match(lowerUTF8(trimBoth(price_currency)), '^[a-z][a-z\\- ]*$')",
            ]
        ),
    )
    base_type_count = _required_count(
        client,
        "base_type_count",
        " ".join(
            [
                "SELECT countDistinct(base_type) AS value FROM poe_trade.v_ps_items_enriched",
                f"WHERE league = {league_literal}",
                "AND price_amount IS NOT NULL AND price_amount > 0",
            ]
        ),
    )

    category_breakdown = _required_group_counts(
        client,
        "category_breakdown",
        " ".join(
            [
                "SELECT category AS key, count() AS value FROM poe_trade.v_ps_items_enriched",
                f"WHERE league = {league_literal}",
                "AND price_amount IS NOT NULL AND price_amount > 0",
                "GROUP BY category ORDER BY value DESC FORMAT JSONEachRow",
            ]
        ),
    )

    mod_storage_breakdown = _required_row(
        client,
        metric_name="mod_storage_breakdown",
        query=" ".join(
            [
                "SELECT",
                "sum(length(JSONExtractArrayRaw(item_json, 'implicitMods')) > 0) AS implicit_mod_rows,",
                "sum(length(JSONExtractArrayRaw(item_json, 'explicitMods')) > 0) AS explicit_mod_rows,",
                "sum(length(JSONExtractArrayRaw(item_json, 'enchantMods')) > 0) AS enchant_mod_rows,",
                "sum(length(JSONExtractArrayRaw(item_json, 'craftedMods')) > 0) AS crafted_mod_rows,",
                "sum(length(JSONExtractArrayRaw(item_json, 'fracturedMods')) > 0) AS fractured_mod_rows",
                "FROM poe_trade.v_ps_items_enriched",
                f"WHERE league = {league_literal}",
                "AND price_amount IS NOT NULL AND price_amount > 0",
                "FORMAT JSONEachRow",
            ]
        ),
    )

    poeninja_snapshot_rows = _safe_count_if_table_exists(
        client,
        database="poe_trade",
        table="raw_poeninja_currency_overview",
        query=f"SELECT count() AS value FROM poe_trade.raw_poeninja_currency_overview WHERE league = {league_literal}",
    )
    sale_proxy_rows = _safe_count(
        client,
        f"SELECT count() AS value FROM poe_trade.bronze_trade_metadata WHERE league = {league_literal}",
    )

    market_context_coverage = {
        "gold_currency_ref_hour_rows": _required_count(
            client,
            "gold_currency_ref_hour_rows",
            f"SELECT count() AS value FROM poe_trade.gold_currency_ref_hour WHERE league = {league_literal}",
        ),
        "gold_listing_ref_hour_rows": _required_count(
            client,
            "gold_listing_ref_hour_rows",
            f"SELECT count() AS value FROM poe_trade.gold_listing_ref_hour WHERE league = {league_literal}",
        ),
        "gold_liquidity_ref_hour_rows": _required_count(
            client,
            "gold_liquidity_ref_hour_rows",
            f"SELECT count() AS value FROM poe_trade.gold_liquidity_ref_hour WHERE league = {league_literal}",
        ),
    }

    q01 = _required_scalar_float(
        client,
        "q01_price_amount",
        " ".join(
            [
                "SELECT quantileTDigest(0.01)(price_amount) AS value FROM poe_trade.v_ps_items_enriched",
                f"WHERE league = {league_literal}",
                "AND price_amount IS NOT NULL AND price_amount > 0",
            ]
        ),
    )
    q99 = _required_scalar_float(
        client,
        "q99_price_amount",
        " ".join(
            [
                "SELECT quantileTDigest(0.99)(price_amount) AS value FROM poe_trade.v_ps_items_enriched",
                f"WHERE league = {league_literal}",
                "AND price_amount IS NOT NULL AND price_amount > 0",
            ]
        ),
    )

    quarantined_low_anchor = _required_count(
        client,
        "quarantined_low_anchor",
        " ".join(
            [
                "SELECT count() AS value FROM poe_trade.v_ps_items_enriched",
                f"WHERE league = {league_literal}",
                "AND price_amount IS NOT NULL AND price_amount > 0",
                f"AND price_amount < {q01}",
            ]
        ),
    )
    quarantined_high_anchor = _required_count(
        client,
        "quarantined_high_anchor",
        " ".join(
            [
                "SELECT count() AS value FROM poe_trade.v_ps_items_enriched",
                f"WHERE league = {league_literal}",
                "AND price_amount IS NOT NULL AND price_amount > 0",
                f"AND price_amount > {q99}",
            ]
        ),
    )
    parse_failure = _required_count(
        client,
        "parse_failure",
        " ".join(
            [
                "SELECT count() AS value FROM poe_trade.v_ps_items_enriched",
                f"WHERE league = {league_literal}",
                "AND effective_price_note IS NOT NULL",
                "AND price_amount IS NULL",
            ]
        ),
    )

    trainable_rows = max(
        priced_rows - quarantined_low_anchor - quarantined_high_anchor, 0
    )

    return {
        "as_of_ts": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "league": league,
        "total_rows": total_rows,
        "priced_rows": priced_rows,
        "clean_currency_rows": clean_currency_rows,
        "base_type_count": base_type_count,
        "category_breakdown": category_breakdown,
        "market_context_coverage": market_context_coverage,
        "mod_storage_breakdown": mod_storage_breakdown,
        "poeninja_snapshot_rows": poeninja_snapshot_rows,
        "sale_proxy_rows": sale_proxy_rows,
        "outlier_summary": {
            "q01_price_amount": q01,
            "q99_price_amount": q99,
            "quarantined_low_anchor": quarantined_low_anchor,
            "quarantined_high_anchor": quarantined_high_anchor,
            "parse_failure": parse_failure,
            "trainable": trainable_rows,
        },
        "hardware_profile": {
            "machine": runtime_profile.machine,
            "cpu_cores": runtime_profile.cpu_cores,
            "total_ram_gb": runtime_profile.total_ram_gb,
            "available_ram_gb": runtime_profile.available_ram_gb,
            "gpu_backend_available": runtime_profile.gpu_backend_available,
            "backend_availability": runtime_profile.backend_availability,
        },
        "chosen_backend": runtime_profile.chosen_backend,
        "default_workers": runtime_profile.default_workers,
        "memory_budget_gb": runtime_profile.memory_budget_gb,
        "target_contract": TARGET_CONTRACT.to_dict(),
    }


def _safe_count(client: ClickHouseClient, query: str) -> int:
    row = _safe_row(client, f"{query} FORMAT JSONEachRow")
    value = row.get("value", 0)
    return int(value) if isinstance(value, (int, float)) else 0


def _safe_row(client: ClickHouseClient, query: str) -> dict[str, object]:
    try:
        payload = client.execute(query)
    except ClickHouseClientError:
        return {}
    for line in payload.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            parsed = cast(dict[str, object], json.loads(line))
        except json.JSONDecodeError:
            continue
        return parsed
    return {}


def _required_count(client: ClickHouseClient, metric_name: str, query: str) -> int:
    row = _required_row(
        client, metric_name=metric_name, query=f"{query} FORMAT JSONEachRow"
    )
    value = row.get("value", 0)
    if not isinstance(value, (int, float)):
        raise RuntimeError(f"audit metric {metric_name!r} returned non-numeric value")
    return int(value)


def _required_scalar_float(
    client: ClickHouseClient, metric_name: str, query: str
) -> float:
    row = _required_row(
        client, metric_name=metric_name, query=f"{query} FORMAT JSONEachRow"
    )
    value = row.get("value", 0.0)
    if not isinstance(value, (int, float)):
        raise RuntimeError(f"audit metric {metric_name!r} returned non-numeric value")
    return float(value)


def _required_group_counts(
    client: ClickHouseClient,
    metric_name: str,
    query: str,
) -> list[dict[str, object]]:
    try:
        payload = client.execute(query)
    except ClickHouseClientError as exc:
        raise RuntimeError(f"audit metric {metric_name!r} query failed: {exc}") from exc
    rows: list[dict[str, object]] = []
    for line in payload.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = cast(dict[str, object], json.loads(line))
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"audit metric {metric_name!r} returned invalid JSON"
            ) from exc
        key = row.get("key")
        value = row.get("value")
        if isinstance(key, str) and isinstance(value, (int, float)):
            rows.append({"key": key, "value": int(value)})
    return rows


def _required_row(
    client: ClickHouseClient,
    *,
    metric_name: str,
    query: str,
) -> dict[str, object]:
    try:
        payload = client.execute(query)
    except ClickHouseClientError as exc:
        raise RuntimeError(f"audit metric {metric_name!r} query failed: {exc}") from exc
    for line in payload.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            parsed = cast(dict[str, object], json.loads(line))
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"audit metric {metric_name!r} returned invalid JSON"
            ) from exc
        return parsed
    raise RuntimeError(f"audit metric {metric_name!r} returned empty payload")


def _safe_count_if_table_exists(
    client: ClickHouseClient,
    *,
    database: str,
    table: str,
    query: str,
) -> int:
    if not _table_exists(client, database=database, table=table):
        return 0
    return _safe_count(client, query)


def _table_exists(client: ClickHouseClient, *, database: str, table: str) -> bool:
    table_literal = _quote(table)
    db_literal = _quote(database)
    row = _safe_row(
        client,
        " ".join(
            [
                "SELECT count() AS value FROM system.tables",
                f"WHERE database = {db_literal}",
                f"AND name = {table_literal}",
                "FORMAT JSONEachRow",
            ]
        ),
    )
    value = row.get("value", 0)
    return isinstance(value, (int, float)) and int(value) > 0


def _ensure_supported_league(league: str) -> None:
    if league in VALIDATED_LEAGUES:
        return
    supported = ", ".join(sorted(VALIDATED_LEAGUES))
    raise ValueError(
        f"league {league!r} is not yet validated for poe-ml v1; supported: {supported}"
    )


def _quote(value: str) -> str:
    escaped = value.replace("'", "''")
    return f"'{escaped}'"
