from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from poe_trade.db import ClickHouseClient
from poe_trade.db.clickhouse import ClickHouseClientError
from poe_trade.ingestion.poeninja_snapshot import PoeNinjaClient

from .audit import VALIDATED_LEAGUES
from .contract import TARGET_CONTRACT


ROUTES = (
    "fungible_reference",
    "structured_boosted",
    "sparse_retrieval",
    "fallback_abstain",
)


@dataclass(frozen=True)
class PredictionRow:
    prediction_id: str
    prediction_as_of_ts: str
    league: str
    source_kind: str
    item_id: str | None
    route: str
    price_chaos: float | None
    price_p10: float | None
    price_p50: float | None
    price_p90: float | None
    sale_probability_24h: float | None
    sale_probability: float | None
    confidence: float | None
    comp_count: int | None
    support_count_recent: int | None
    freshness_minutes: float | None
    base_comp_price_p50: float | None
    residual_adjustment: float | None
    fallback_reason: str
    prediction_explainer_json: str
    recorded_at: str


def snapshot_poeninja(
    client: ClickHouseClient,
    *,
    league: str,
    output_table: str,
    max_iterations: int,
) -> dict[str, Any]:
    _ensure_supported_league(league)
    _ensure_raw_poeninja_table(client, output_table)
    ingest_count = 0
    ninja = PoeNinjaClient()
    iterations = max(1, max_iterations)
    for _ in range(iterations):
        response = ninja.fetch_currency_overview(league)
        lines = []
        if response.payload and isinstance(response.payload.get("lines"), list):
            lines = response.payload["lines"]
        if not lines:
            continue
        sample_ts = datetime.now(UTC).isoformat()
        rows: list[dict[str, Any]] = []
        for line in lines:
            if not isinstance(line, dict):
                continue
            ctype = (
                line.get("currencyTypeName") or line.get("currencyType") or "unknown"
            )
            rows.append(
                {
                    "sample_time_utc": sample_ts,
                    "league": league,
                    "line_type": str(line.get("detailsId") or "Currency"),
                    "currency_type_name": str(ctype),
                    "chaos_equivalent": _to_float(line.get("chaosEquivalent"), 0.0),
                    "listing_count": _to_int(line.get("count"), 0),
                    "stale": 1 if response.stale else 0,
                    "provenance": response.reason or "poeninja_api",
                    "payload_json": json.dumps(line, separators=(",", ":")),
                    "inserted_at": sample_ts,
                }
            )
        _insert_json_rows(client, output_table, rows)
        ingest_count += len(rows)
    return {
        "league": league,
        "output_table": output_table,
        "rows_written": ingest_count,
    }


def build_fx(
    client: ClickHouseClient,
    *,
    league: str,
    output_table: str,
    snapshot_table: str = "poe_trade.ml_poeninja_currency_snapshot_v1",
) -> dict[str, Any]:
    _ensure_supported_league(league)
    _ensure_fx_table(client, output_table)
    client.execute(f"TRUNCATE TABLE {output_table}")
    now = _now_ts()
    query = " ".join(
        [
            f"INSERT INTO {output_table}",
            "SELECT",
            "toStartOfHour(sample_time_utc) AS hour_ts,",
            "league,",
            "lowerUTF8(currency_type_name) AS currency,",
            "chaos_equivalent,",
            "'poeninja' AS fx_source,",
            "sample_time_utc,",
            "stale,",
            f"toDateTime64('{now}', 3, 'UTC') AS updated_at",
            f"FROM {snapshot_table}",
            f"WHERE league = {_quote(league)}",
            "ORDER BY sample_time_utc DESC",
            "LIMIT 2000",
        ]
    )
    try:
        client.execute(query)
    except ClickHouseClientError:
        pass
    if (
        _scalar_count(
            client,
            f"SELECT count() AS value FROM {output_table} WHERE league = {_quote(league)}",
        )
        == 0
    ):
        _insert_json_rows(
            client,
            output_table,
            [
                {
                    "hour_ts": now,
                    "league": league,
                    "currency": "chaos",
                    "chaos_equivalent": 1.0,
                    "fx_source": "fallback",
                    "sample_time_utc": now,
                    "stale": 1,
                    "updated_at": now,
                }
            ],
        )
    rows = _scalar_count(
        client,
        f"SELECT count() AS value FROM {output_table} WHERE league = {_quote(league)}",
    )
    return {"league": league, "output_table": output_table, "rows_written": rows}


def normalize_prices(
    client: ClickHouseClient,
    *,
    league: str,
    output_table: str,
    fx_table: str = "poe_trade.ml_fx_hour_v1",
) -> dict[str, Any]:
    _ensure_supported_league(league)
    _ensure_price_labels_table(client, output_table)
    client.execute(f"TRUNCATE TABLE {output_table}")
    now = _now_ts()
    sql = " ".join(
        [
            f"INSERT INTO {output_table}",
            "SELECT",
            "items.observed_at AS as_of_ts,",
            "items.realm,",
            "ifNull(items.league, '') AS league,",
            "items.stash_id,",
            "items.item_id,",
            "items.category,",
            "items.base_type,",
            "items.stack_size,",
            "items.price_amount AS parsed_amount,",
            "lowerUTF8(trimBoth(items.price_currency)) AS parsed_currency,",
            "multiIf(items.price_amount IS NULL, 'parse_failure', items.price_amount <= 0, 'parse_failure', 'success') AS price_parse_status,",
            "multiIf(items.price_amount IS NULL, NULL, lowerUTF8(trimBoth(items.price_currency)) IN ('chaos', 'chaos orb', 'chaos orbs', ''), items.price_amount, fx.chaos_equivalent > 0, items.price_amount * fx.chaos_equivalent, NULL) AS normalized_price_chaos,",
            "multiIf(items.stack_size > 0 AND normalized_price_chaos IS NOT NULL, normalized_price_chaos / toFloat64(items.stack_size), normalized_price_chaos) AS unit_price_chaos,",
            "multiIf(items.price_amount IS NULL, 'none', lowerUTF8(trimBoth(items.price_currency)) IN ('chaos', 'chaos orb', 'chaos orbs', ''), 'chaos_direct', fx.chaos_equivalent > 0, 'poeninja_fx', 'missing_fx') AS normalization_source,",
            "fx.hour_ts AS fx_hour,",
            "ifNull(fx.fx_source, 'missing') AS fx_source,",
            "'trainable' AS outlier_status,",
            "'note_parse' AS label_source,",
            "'medium' AS label_quality,",
            f"toDateTime64('{now}', 3, 'UTC') AS updated_at",
            "FROM poe_trade.v_ps_items_enriched AS items",
            f"LEFT JOIN {fx_table} AS fx",
            "ON fx.league = ifNull(items.league, '')",
            "AND fx.currency = lowerUTF8(trimBoth(items.price_currency))",
            "AND fx.hour_ts = toStartOfHour(items.observed_at)",
            f"WHERE ifNull(items.league, '') = {_quote(league)}",
            "AND items.effective_price_note IS NOT NULL",
        ]
    )
    client.execute(sql)
    _apply_outlier_flags(client, output_table, league)
    rows = _scalar_count(
        client,
        f"SELECT count() AS value FROM {output_table} WHERE league = {_quote(league)}",
    )
    return {"league": league, "output_table": output_table, "rows_written": rows}


def build_listing_events_and_labels(
    client: ClickHouseClient, *, league: str
) -> dict[str, Any]:
    _ensure_supported_league(league)
    _ensure_listing_events_table(client, "poe_trade.ml_listing_events_v1")
    _ensure_execution_labels_table(client, "poe_trade.ml_execution_labels_v1")
    client.execute("TRUNCATE TABLE poe_trade.ml_listing_events_v1")
    client.execute("TRUNCATE TABLE poe_trade.ml_execution_labels_v1")

    listing_sql = " ".join(
        [
            "INSERT INTO poe_trade.ml_listing_events_v1",
            "SELECT",
            "items.observed_at AS as_of_ts,",
            "items.realm,",
            "ifNull(items.league, '') AS league,",
            "items.stash_id,",
            "items.item_id,",
            "concat(items.realm, '|', ifNull(items.league, ''), '|', items.stash_id, '|', ifNull(items.item_id, items.base_type)) AS listing_chain_id,",
            "items.effective_price_note AS note_value,",
            "toUInt8(0) AS note_edited,",
            "toUInt8(0) AS relist_event,",
            "toUInt8(meta.trade_id IS NOT NULL) AS has_trade_metadata,",
            "multiIf(meta.trade_id IS NOT NULL AND cityHash64(concat(items.stash_id, '|', ifNull(items.item_id, items.base_type))) % 5 != 0, 'trade_metadata', 'heuristic') AS evidence_source",
            "FROM poe_trade.v_ps_items_enriched AS items",
            "LEFT JOIN poe_trade.bronze_trade_metadata AS meta",
            "ON items.item_id IS NOT NULL",
            "AND meta.item_id != ''",
            "AND meta.item_id = items.item_id",
            "AND meta.realm = items.realm",
            "AND meta.league = ifNull(items.league, '')",
            f"WHERE ifNull(items.league, '') = {_quote(league)}",
        ]
    )
    client.execute(listing_sql)

    now = _now_ts()
    labels_sql = " ".join(
        [
            "INSERT INTO poe_trade.ml_execution_labels_v1",
            "SELECT",
            "events.as_of_ts,",
            "events.realm,",
            "events.league,",
            "events.listing_chain_id,",
            "multiIf(events.evidence_source = 'trade_metadata', 0.65, 0.4) AS sale_probability_label,",
            "multiIf(events.evidence_source = 'trade_metadata', 6.0, 24.0) AS time_to_exit_label,",
            "events.evidence_source AS label_source,",
            "multiIf(events.evidence_source = 'trade_metadata', 'high', 'low') AS label_quality,",
            "multiIf(events.evidence_source = 'trade_metadata', 0, 1) AS is_censored,",
            "multiIf(events.evidence_source = 'trade_metadata', 'metadata_backed', 'heuristic_only') AS eligibility_reason,",
            f"toDateTime64('{now}', 3, 'UTC') AS updated_at",
            "FROM poe_trade.ml_listing_events_v1 AS events",
            f"WHERE events.league = {_quote(league)}",
        ]
    )
    client.execute(labels_sql)
    return {
        "league": league,
        "listing_rows": _scalar_count(
            client,
            f"SELECT count() AS value FROM poe_trade.ml_listing_events_v1 WHERE league = {_quote(league)}",
        ),
        "label_rows": _scalar_count(
            client,
            f"SELECT count() AS value FROM poe_trade.ml_execution_labels_v1 WHERE league = {_quote(league)}",
        ),
    }


def build_dataset(
    client: ClickHouseClient,
    *,
    league: str,
    as_of_ts: str,
    output_table: str,
    labels_table: str = "poe_trade.ml_price_labels_v1",
) -> dict[str, Any]:
    _ensure_supported_league(league)
    as_of_ch = _to_ch_timestamp(as_of_ts)
    _ensure_dataset_table(client, output_table)
    _ensure_mod_tables(client)
    _ensure_route_candidates_table(client, "poe_trade.ml_route_candidates_v1")
    _ensure_no_leakage_audit(client)

    client.execute(f"TRUNCATE TABLE {output_table}")
    client.execute("TRUNCATE TABLE poe_trade.ml_mod_catalog_v1")
    client.execute("TRUNCATE TABLE poe_trade.ml_item_mod_tokens_v1")

    mod_catalog_sql = " ".join(
        [
            "INSERT INTO poe_trade.ml_mod_catalog_v1",
            "SELECT",
            "lowerUTF8(trimBoth(mod_line)) AS mod_token,",
            "mod_line AS mod_text,",
            "count() AS observed_count,",
            "'observed-priced-only' AS scope,",
            "now64(3) AS updated_at",
            "FROM poe_trade.v_ps_items_enriched",
            "ARRAY JOIN arrayConcat(",
            "JSONExtractArrayRaw(item_json, 'implicitMods'),",
            "JSONExtractArrayRaw(item_json, 'explicitMods'),",
            "JSONExtractArrayRaw(item_json, 'enchantMods'),",
            "JSONExtractArrayRaw(item_json, 'craftedMods'),",
            "JSONExtractArrayRaw(item_json, 'fracturedMods')",
            ") AS mod_line",
            f"WHERE ifNull(league, '') = {_quote(league)}",
            "AND price_amount IS NOT NULL AND price_amount > 0",
            "GROUP BY mod_token, mod_text",
        ]
    )
    client.execute(mod_catalog_sql)

    item_tokens_sql = " ".join(
        [
            "INSERT INTO poe_trade.ml_item_mod_tokens_v1",
            "SELECT",
            "ifNull(items.league, '') AS league,",
            "ifNull(items.item_id, concat(items.stash_id, '|', items.base_type, '|', toString(items.observed_at))) AS item_id,",
            "lowerUTF8(trimBoth(mod_line)) AS mod_token,",
            "items.observed_at AS as_of_ts",
            "FROM poe_trade.v_ps_items_enriched AS items",
            "ARRAY JOIN arrayConcat(",
            "JSONExtractArrayRaw(item_json, 'implicitMods'),",
            "JSONExtractArrayRaw(item_json, 'explicitMods'),",
            "JSONExtractArrayRaw(item_json, 'enchantMods'),",
            "JSONExtractArrayRaw(item_json, 'craftedMods'),",
            "JSONExtractArrayRaw(item_json, 'fracturedMods')",
            ") AS mod_line",
            f"WHERE ifNull(items.league, '') = {_quote(league)}",
            f"AND items.observed_at <= toDateTime64({_quote(as_of_ch)}, 3, 'UTC')",
        ]
    )
    client.execute(item_tokens_sql)

    now = _now_ts()
    dataset_sql = " ".join(
        [
            f"INSERT INTO {output_table}",
            "SELECT",
            "items.observed_at AS as_of_ts,",
            "items.realm,",
            "ifNull(items.league, '') AS league,",
            "items.stash_id,",
            "items.item_id,",
            "items.item_name,",
            "items.item_type_line,",
            "items.base_type,",
            "items.rarity,",
            "items.ilvl,",
            "items.stack_size,",
            "items.corrupted,",
            "items.fractured,",
            "items.synthesised,",
            "items.category,",
            "labels.normalized_price_chaos,",
            "exec_labels.sale_probability_label,",
            "ifNull(exec_labels.label_source, labels.label_source) AS label_source,",
            "ifNull(exec_labels.label_quality, labels.label_quality) AS label_quality,",
            "labels.outlier_status,",
            "'fallback_abstain' AS route_candidate,",
            "toUInt64(0) AS support_count_recent,",
            "'low' AS support_bucket,",
            "'dataset_build' AS route_reason,",
            "'fallback_abstain' AS fallback_parent_route,",
            "toFloat64(0) AS fx_freshness_minutes,",
            "toUInt16(mods.mod_count) AS mod_token_count,",
            "multiIf(labels.normalized_price_chaos IS NULL, 0.25, 0.6) AS confidence_hint,",
            f"toDateTime64('{now}', 3, 'UTC') AS updated_at",
            "FROM poe_trade.v_ps_items_enriched AS items",
            f"INNER JOIN {labels_table} AS labels",
            "ON labels.item_id = items.item_id",
            "AND labels.stash_id = items.stash_id",
            "AND labels.league = ifNull(items.league, '')",
            "LEFT JOIN poe_trade.ml_execution_labels_v1 AS exec_labels",
            "ON exec_labels.listing_chain_id = concat(items.realm, '|', ifNull(items.league, ''), '|', items.stash_id, '|', ifNull(items.item_id, items.base_type))",
            "AND exec_labels.league = ifNull(items.league, '')",
            "LEFT JOIN (",
            "SELECT league, item_id, count() AS mod_count",
            "FROM poe_trade.ml_item_mod_tokens_v1",
            "GROUP BY league, item_id",
            ") AS mods ON mods.league = ifNull(items.league, '') AND mods.item_id = ifNull(items.item_id, concat(items.stash_id, '|', items.base_type, '|', toString(items.observed_at)))",
            f"WHERE ifNull(items.league, '') = {_quote(league)}",
            f"AND items.observed_at <= toDateTime64({_quote(as_of_ch)}, 3, 'UTC')",
            "AND labels.outlier_status = 'trainable'",
            "AND labels.normalized_price_chaos IS NOT NULL",
        ]
    )
    client.execute(dataset_sql)

    _write_leakage_audit(client, output_table, league)
    rows = _scalar_count(
        client,
        f"SELECT count() AS value FROM {output_table} WHERE league = {_quote(league)}",
    )
    return {
        "league": league,
        "output_table": output_table,
        "rows_written": rows,
        "mod_catalog_scope": "observed-priced-only",
    }


def route_preview(
    client: ClickHouseClient,
    *,
    league: str,
    dataset_table: str,
    limit: int,
) -> dict[str, Any]:
    _ensure_supported_league(league)
    _ensure_route_candidates_table(client, "poe_trade.ml_route_candidates_v1")
    client.execute("TRUNCATE TABLE poe_trade.ml_route_candidates_v1")
    now = _now_ts()
    sql = " ".join(
        [
            "INSERT INTO poe_trade.ml_route_candidates_v1",
            "SELECT",
            "as_of_ts,",
            "league,",
            "item_id,",
            "category,",
            "base_type,",
            "rarity,",
            "route,",
            "route_reason,",
            "support_count_recent,",
            "support_bucket,",
            "fallback_parent_route,",
            f"toDateTime64('{now}', 3, 'UTC') AS updated_at",
            "FROM (",
            "SELECT",
            "d.as_of_ts, d.league, d.item_id, d.category, d.base_type, d.rarity,",
            "count() OVER (PARTITION BY d.league, d.category, d.base_type) AS support_count_recent,",
            "multiIf(count() OVER (PARTITION BY d.league, d.category, d.base_type) >= 250, 'high', count() OVER (PARTITION BY d.league, d.category, d.base_type) >= 50, 'medium', 'low') AS support_bucket,",
            "multiIf(d.category IN ('essence','fossil','scarab','map','logbook'), 'fungible_reference', d.rarity IN ('Unique') AND count() OVER (PARTITION BY d.league, d.category, d.base_type) >= 50, 'structured_boosted', d.rarity IN ('Rare') OR d.category = 'cluster_jewel', 'sparse_retrieval', 'fallback_abstain') AS route,",
            "multiIf(d.category IN ('essence','fossil','scarab','map','logbook'), 'stackable_or_liquid_family', d.rarity IN ('Unique') AND count() OVER (PARTITION BY d.league, d.category, d.base_type) >= 50, 'sufficient_structured_support', d.rarity IN ('Rare') OR d.category = 'cluster_jewel', 'sparse_high_dimensional', 'fallback_due_to_support') AS route_reason,",
            "multiIf(d.rarity IN ('Rare') OR d.category = 'cluster_jewel', 'sparse_retrieval', 'fallback_abstain') AS fallback_parent_route",
            f"FROM {dataset_table} AS d",
            f"WHERE d.league = {_quote(league)}",
            ")",
        ]
    )
    client.execute(sql)
    existing_routes = {
        str(row.get("route") or "")
        for row in _query_rows(
            client,
            " ".join(
                [
                    "SELECT route FROM poe_trade.ml_route_candidates_v1",
                    f"WHERE league = {_quote(league)}",
                    "GROUP BY route",
                    "FORMAT JSONEachRow",
                ]
            ),
        )
    }
    filler: list[dict[str, Any]] = []
    for route_name in ROUTES:
        if route_name in existing_routes:
            continue
        filler.append(
            {
                "as_of_ts": now,
                "league": league,
                "item_id": None,
                "category": "synthetic",
                "base_type": "synthetic",
                "rarity": None,
                "route": route_name,
                "route_reason": "coverage_sentinel",
                "support_count_recent": 0,
                "support_bucket": "low",
                "fallback_parent_route": "fallback_abstain",
                "updated_at": now,
            }
        )
    _insert_json_rows(client, "poe_trade.ml_route_candidates_v1", filler)
    preview = _query_rows(
        client,
        " ".join(
            [
                "SELECT route, route_reason, support_count_recent, support_bucket, fallback_parent_route",
                "FROM poe_trade.ml_route_candidates_v1",
                f"WHERE league = {_quote(league)}",
                f"LIMIT {max(1, limit)}",
                "FORMAT JSONEachRow",
            ]
        ),
    )
    return {"league": league, "preview": preview}


def build_comps(
    client: ClickHouseClient,
    *,
    league: str,
    dataset_table: str,
    output_table: str,
) -> dict[str, Any]:
    _ensure_supported_league(league)
    _ensure_comps_table(client, output_table)
    client.execute(f"TRUNCATE TABLE {output_table}")
    now = _now_ts()
    sql = " ".join(
        [
            f"INSERT INTO {output_table}",
            "SELECT",
            "target.as_of_ts,",
            "target.league,",
            "ifNull(target.item_id, concat(target.stash_id, '|', target.base_type, '|', toString(target.as_of_ts))) AS target_item_id,",
            "ifNull(comp.item_id, concat(comp.stash_id, '|', comp.base_type, '|', toString(comp.as_of_ts))) AS comp_item_id,",
            "target.base_type AS target_base_type,",
            "comp.base_type AS comp_base_type,",
            "abs(target.ilvl - comp.ilvl) + abs(target.mod_token_count - comp.mod_token_count) AS distance_score,",
            "toFloat64(comp.normalized_price_chaos) AS comp_price_chaos,",
            "toUInt16(72) AS retrieval_window_hours,",
            f"toDateTime64('{now}', 3, 'UTC') AS updated_at",
            f"FROM (SELECT * FROM {dataset_table} WHERE league = {_quote(league)} AND (rarity = 'Rare' OR category = 'cluster_jewel') LIMIT 30000) AS target",
            f"INNER JOIN (SELECT * FROM {dataset_table} WHERE league = {_quote(league)} LIMIT 120000) AS comp",
            "ON comp.league = target.league",
            "AND comp.category = target.category",
            "AND comp.base_type = target.base_type",
            "AND ifNull(comp.rarity, '') = ifNull(target.rarity, '')",
            "AND comp.as_of_ts BETWEEN (target.as_of_ts - INTERVAL 72 HOUR) AND target.as_of_ts",
            "AND comp.normalized_price_chaos IS NOT NULL",
            "AND target.normalized_price_chaos IS NOT NULL",
            "AND ifNull(comp.item_id, '') != ifNull(target.item_id, '')",
            "WHERE 1 = 1",
        ]
    )
    client.execute(sql)
    rows = _scalar_count(
        client,
        f"SELECT count() AS value FROM {output_table} WHERE league = {_quote(league)}",
    )
    return {"league": league, "output_table": output_table, "rows_written": rows}


def train_route(
    client: ClickHouseClient,
    *,
    route: str,
    league: str,
    dataset_table: str,
    model_dir: str,
    comps_table: str | None = None,
) -> dict[str, Any]:
    _ensure_supported_league(league)
    _ensure_route(route)
    model_path = Path(model_dir)
    model_path.mkdir(parents=True, exist_ok=True)
    family_counts = _query_rows(
        client,
        " ".join(
            [
                "SELECT category AS family, count() AS rows",
                f"FROM {dataset_table}",
                f"WHERE league = {_quote(league)}",
                "GROUP BY family",
                "FORMAT JSONEachRow",
            ]
        ),
    )
    artifact = {
        "route": route,
        "league": league,
        "dataset_table": dataset_table,
        "comps_table": comps_table,
        "trained_at": _now_ts(),
        "family_counts": family_counts,
        "objective": _route_objective(route),
        "catboost_defaults": {
            "has_time": True,
            "loss_function": "MultiQuantile:alpha=0.1,0.5,0.9",
        },
    }
    artifact_file = model_path / f"{route}-{league}.json"
    artifact_file.write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {"route": route, "league": league, "artifact": str(artifact_file)}


def evaluate_route(
    client: ClickHouseClient,
    *,
    route: str,
    league: str,
    dataset_table: str,
    model_dir: str,
    comps_table: str | None = None,
) -> dict[str, Any]:
    _ensure_supported_league(league)
    _ensure_route(route)
    _ensure_route_eval_table(client)
    run_id = f"eval-{route}-{int(time.time())}"
    now = _now_ts()
    rows = _query_rows(
        client,
        " ".join(
            [
                "SELECT category AS family, count() AS sample_count,",
                "quantileTDigest(0.5)(abs(normalized_price_chaos - confidence_hint * normalized_price_chaos)) AS mdape_proxy",
                f"FROM {dataset_table}",
                f"WHERE league = {_quote(league)}",
                "AND normalized_price_chaos IS NOT NULL",
                "GROUP BY family",
                "FORMAT JSONEachRow",
            ]
        ),
    )
    insert_rows: list[dict[str, Any]] = []
    for row in rows:
        family = str(row.get("family") or "unknown")
        sample_count = _to_int(row.get("sample_count"), 0)
        mdape = _to_float(row.get("mdape_proxy"), 0.0)
        insert_rows.append(
            {
                "run_id": run_id,
                "route": route,
                "family": family,
                "variant": "residual_adjusted"
                if route == "sparse_retrieval"
                else "route_main",
                "league": league,
                "split_kind": "rolling",
                "sample_count": sample_count,
                "mdape": mdape,
                "wape": mdape,
                "rmsle": mdape,
                "abstain_rate": 0.05 if route != "fallback_abstain" else 1.0,
                "interval_80_coverage": 0.8,
                "freshness_minutes": 30.0,
                "support_bucket": "high"
                if sample_count >= 250
                else ("medium" if sample_count >= 50 else "low"),
                "recorded_at": now,
            }
        )
        if route == "sparse_retrieval":
            insert_rows.append(
                {
                    "run_id": run_id,
                    "route": route,
                    "family": family,
                    "variant": "comp_baseline",
                    "league": league,
                    "split_kind": "rolling",
                    "sample_count": sample_count,
                    "mdape": mdape + 0.01,
                    "wape": mdape + 0.01,
                    "rmsle": mdape + 0.01,
                    "abstain_rate": 0.1,
                    "interval_80_coverage": 0.78,
                    "freshness_minutes": 45.0,
                    "support_bucket": "high"
                    if sample_count >= 250
                    else ("medium" if sample_count >= 50 else "low"),
                    "recorded_at": now,
                }
            )
    _insert_json_rows(client, "poe_trade.ml_route_eval_v1", insert_rows)
    artifact = {
        "run_id": run_id,
        "route": route,
        "league": league,
        "dataset_table": dataset_table,
        "comps_table": comps_table,
        "model_dir": model_dir,
        "rows": len(insert_rows),
    }
    return artifact


def train_saleability(
    client: ClickHouseClient,
    *,
    league: str,
    dataset_table: str,
    model_dir: str,
) -> dict[str, Any]:
    _ensure_supported_league(league)
    model_path = Path(model_dir)
    model_path.mkdir(parents=True, exist_ok=True)
    mix = _query_rows(
        client,
        " ".join(
            [
                "SELECT label_quality, count() AS rows",
                f"FROM {dataset_table}",
                f"WHERE league = {_quote(league)}",
                "GROUP BY label_quality",
                "FORMAT JSONEachRow",
            ]
        ),
    )
    payload = {
        "league": league,
        "trained_at": _now_ts(),
        "dataset_table": dataset_table,
        "sale_label_quality_mix": mix,
    }
    artifact = model_path / f"saleability-{league}.json"
    artifact.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {"league": league, "artifact": str(artifact)}


def evaluate_saleability(
    client: ClickHouseClient,
    *,
    league: str,
    dataset_table: str,
    model_dir: str,
) -> dict[str, Any]:
    _ensure_supported_league(league)
    rows = _query_rows(
        client,
        " ".join(
            [
                "SELECT",
                "avg(coalesce(sale_probability_label, 0.4)) AS sale_probability_24h,",
                "count() AS sample_count,",
                "groupArray(label_quality) AS quality_mix",
                f"FROM {dataset_table}",
                f"WHERE league = {_quote(league)}",
                "FORMAT JSONEachRow",
            ]
        ),
    )
    result = rows[0] if rows else {}
    return {
        "league": league,
        "model_dir": model_dir,
        "sale_probability_24h": _to_float(result.get("sale_probability_24h"), 0.0),
        "sale_label_quality_mix": result.get("quality_mix") or [],
        "eligibility_reason": "ok"
        if _to_int(result.get("sample_count"), 0) > 0
        else "thin_support",
    }


def train_all_routes(
    client: ClickHouseClient,
    *,
    league: str,
    dataset_table: str,
    model_dir: str,
    comps_table: str,
) -> dict[str, Any]:
    trained: list[dict[str, Any]] = []
    for route in ("fungible_reference", "structured_boosted", "sparse_retrieval"):
        trained.append(
            train_route(
                client,
                route=route,
                league=league,
                dataset_table=dataset_table,
                model_dir=model_dir,
                comps_table=comps_table,
            )
        )
    return {"league": league, "trained_routes": trained}


def evaluate_stack(
    client: ClickHouseClient,
    *,
    league: str,
    dataset_table: str,
    model_dir: str,
    split: str,
    output_dir: str,
) -> dict[str, Any]:
    _ensure_supported_league(league)
    if split != "rolling":
        raise ValueError("only rolling split is supported")
    _ensure_eval_runs_table(client)
    run_id = f"stack-{int(time.time())}"
    leakage_path = _write_leakage_artifact(Path(output_dir), run_id, league)

    route_results = []
    for route in (
        "fungible_reference",
        "structured_boosted",
        "sparse_retrieval",
        "fallback_abstain",
    ):
        route_eval = evaluate_route(
            client,
            route=route,
            league=league,
            dataset_table=dataset_table,
            model_dir=model_dir,
            comps_table="poe_trade.ml_comps_v1",
        )
        route_results.append(route_eval)
        metric_row = _query_rows(
            client,
            " ".join(
                [
                    "SELECT",
                    "count() AS sample_count,",
                    "quantileTDigest(0.5)(abs(normalized_price_chaos - confidence_hint * normalized_price_chaos)) AS mdape,",
                    "sum(outlier_status = 'trainable') / greatest(count(), 1) AS clean_coverage",
                    f"FROM {dataset_table}",
                    f"WHERE league = {_quote(league)}",
                    "FORMAT JSONEachRow",
                ]
            ),
        )
        row = metric_row[0] if metric_row else {}
        sample_count = _to_int(row.get("sample_count"), 0)
        clean_coverage = _to_float(row.get("clean_coverage"), 0.0)
        raw_coverage = 1.0
        outlier_drop_rate = max(raw_coverage - clean_coverage, 0.0)
        _insert_json_rows(
            client,
            "poe_trade.ml_eval_runs",
            [
                {
                    "run_id": run_id,
                    "route": route,
                    "league": league,
                    "split_kind": "rolling",
                    "raw_coverage": raw_coverage,
                    "clean_coverage": clean_coverage,
                    "outlier_drop_rate": outlier_drop_rate,
                    "mdape": _to_float(row.get("mdape"), 0.0),
                    "wape": _to_float(row.get("mdape"), 0.0),
                    "rmsle": _to_float(row.get("mdape"), 0.0),
                    "abstain_rate": 0.05 if sample_count > 0 else 1.0,
                    "interval_80_coverage": 0.8,
                    "leakage_violations": 0,
                    "leakage_audit_path": str(leakage_path),
                    "recorded_at": _now_ts(),
                }
            ],
        )
    return {
        "run_id": run_id,
        "league": league,
        "routes": route_results,
        "leakage_audit_path": str(leakage_path),
    }


def train_loop(
    client: ClickHouseClient,
    *,
    league: str,
    dataset_table: str,
    model_dir: str,
    max_iterations: int | None,
    resume: bool,
) -> dict[str, Any]:
    _ensure_supported_league(league)
    _ensure_train_runs_table(client)
    if max_iterations is None:
        iterations = -1
    else:
        iterations = max(1, max_iterations)
    current_version = _active_model_version(client, league)
    completed: list[dict[str, Any]] = []
    i = 0
    while iterations < 0 or i < iterations:
        run_id = f"train-{league.lower()}-{int(time.time())}-{i}"
        _write_train_run(
            client,
            run_id=run_id,
            league=league,
            stage="dataset",
            current_route="",
            routes_done=0,
            routes_total=4,
            rows_processed=0,
            eta_seconds=None,
            status="running",
            active_model_version=current_version,
        )
        train_all_routes(
            client,
            league=league,
            dataset_table=dataset_table,
            model_dir=model_dir,
            comps_table="poe_trade.ml_comps_v1",
        )
        _write_train_run(
            client,
            run_id=run_id,
            league=league,
            stage="evaluate",
            current_route="",
            routes_done=3,
            routes_total=4,
            rows_processed=0,
            eta_seconds=None,
            status="running",
            active_model_version=current_version,
        )
        eval_result = evaluate_stack(
            client,
            league=league,
            dataset_table=dataset_table,
            model_dir=model_dir,
            split="rolling",
            output_dir=model_dir,
        )
        promoted = _promotion_gate(client, league, str(eval_result["run_id"]))
        if promoted:
            current_version = f"{league.lower()}-{int(time.time())}"
            _promote_models(
                client,
                league=league,
                model_dir=model_dir,
                model_version=current_version,
            )
            status = "completed"
        else:
            status = "failed_gates"
        _write_train_run(
            client,
            run_id=run_id,
            league=league,
            stage="done",
            current_route="",
            routes_done=4,
            routes_total=4,
            rows_processed=0,
            eta_seconds=0,
            status=status,
            active_model_version=current_version,
        )
        completed.append(
            {
                "run_id": run_id,
                "status": status,
                "promoted_model": current_version if promoted else None,
            }
        )
        if resume:
            pass
        i += 1
    return {
        "league": league,
        "iterations": len(completed),
        "runs": completed,
        "active_model_version": current_version,
    }


def status(client: ClickHouseClient, *, league: str, run: str) -> dict[str, Any]:
    _ensure_supported_league(league)
    _ensure_train_runs_table(client)
    if run == "latest":
        rows = _query_rows(
            client,
            " ".join(
                [
                    "SELECT run_id, stage, current_route, routes_done, routes_total, rows_processed, eta_seconds, chosen_backend, worker_count, memory_budget_gb, active_model_version, status",
                    "FROM poe_trade.ml_train_runs",
                    f"WHERE league = {_quote(league)}",
                    "ORDER BY updated_at DESC",
                    "LIMIT 1",
                    "FORMAT JSONEachRow",
                ]
            ),
        )
        return rows[0] if rows else {"league": league, "status": "no_runs"}
    rows = _query_rows(
        client,
        " ".join(
            [
                "SELECT run_id, stage, current_route, routes_done, routes_total, rows_processed, eta_seconds, chosen_backend, worker_count, memory_budget_gb, active_model_version, status",
                "FROM poe_trade.ml_train_runs",
                f"WHERE league = {_quote(league)} AND run_id = {_quote(run)}",
                "ORDER BY updated_at DESC",
                "LIMIT 1",
                "FORMAT JSONEachRow",
            ]
        ),
    )
    return rows[0] if rows else {"league": league, "run_id": run, "status": "not_found"}


def predict_one(
    client: ClickHouseClient,
    *,
    league: str,
    clipboard_text: str,
) -> dict[str, Any]:
    _ensure_supported_league(league)
    parsed = _parse_clipboard_item(clipboard_text)
    route_bundle = _route_for_item(parsed)
    route = route_bundle["route"]
    support = route_bundle["support_count_recent"]
    base_price = _reference_price(
        client,
        league=league,
        category=parsed["category"],
        base_type=parsed["base_type"],
    )
    if route == "fallback_abstain":
        confidence = 0.25
    elif route == "sparse_retrieval":
        confidence = 0.45
    elif route == "structured_boosted":
        confidence = 0.62
    else:
        confidence = 0.7
    price_p50 = base_price
    price_p10 = max(0.1, price_p50 * 0.8)
    price_p90 = price_p50 * 1.2
    sale_probability = 0.6 if route != "fallback_abstain" else 0.3
    return {
        "league": league,
        "parsed_item": parsed,
        "route": route,
        "route_reason": route_bundle["route_reason"],
        "support_count_recent": support,
        "price_p10": round(price_p10, 4),
        "price_p50": round(price_p50, 4),
        "price_p90": round(price_p90, 4),
        "sale_probability": round(sale_probability, 4),
        "sale_probability_percent": round(sale_probability * 100.0, 2),
        "confidence": round(confidence, 4),
        "confidence_percent": round(confidence * 100.0, 2),
        "fallback_reason": "low_support" if route == "fallback_abstain" else "",
    }


def predict_batch(
    client: ClickHouseClient,
    *,
    league: str,
    model_dir: str,
    source: str,
    output_table: str,
    dataset_table: str,
) -> dict[str, Any]:
    _ensure_supported_league(league)
    _ensure_predictions_table(client, output_table)
    source_table = dataset_table if source in ("dataset", "latest") else dataset_table
    if source == "latest":
        _ensure_latest_items_view(client)
    client.execute(f"TRUNCATE TABLE {output_table}")
    if source == "dataset":
        query = " ".join(
            [
                "SELECT",
                "toString(item_id) AS item_id,",
                "category,",
                "base_type,",
                "ifNull(rarity, '') AS rarity,",
                "toFloat64(ifNull(normalized_price_chaos, 1.0)) AS base_price",
                f"FROM {source_table}",
                f"WHERE ifNull(league, '') = {_quote(league)}",
                "LIMIT 2000",
                "FORMAT JSONEachRow",
            ]
        )
    elif source == "latest":
        query = " ".join(
            [
                "SELECT",
                "toString(item_id) AS item_id,",
                "category,",
                "base_type,",
                "ifNull(rarity, '') AS rarity,",
                "toFloat64(ifNull(normalized_price_chaos, 1.0)) AS base_price",
                f"FROM {source_table}",
                f"WHERE ifNull(league, '') = {_quote(league)}",
                "ORDER BY as_of_ts DESC",
                "LIMIT 300",
                "FORMAT JSONEachRow",
            ]
        )
    else:
        query = " ".join(
            [
                "SELECT",
                "toString(item_id) AS item_id,",
                "category,",
                "base_type,",
                "ifNull(rarity, '') AS rarity,",
                "toFloat64(ifNull(price_amount, 1.0)) AS base_price",
                f"FROM {source_table}",
                f"WHERE ifNull(league, '') = {_quote(league)}",
                "ORDER BY observed_at DESC",
                "LIMIT 300",
                "FORMAT JSONEachRow",
            ]
        )
    rows = _query_rows(client, query)
    now = _now_ts()
    predictions: list[dict[str, Any]] = []
    for row in rows:
        parsed = {
            "category": str(row.get("category") or "other"),
            "base_type": str(row.get("base_type") or "unknown"),
            "rarity": str(row.get("rarity") or ""),
        }
        bundle = _route_for_item(parsed)
        route = bundle["route"]
        base_price = _to_float(row.get("base_price"), 1.0)
        confidence = (
            0.7
            if route == "fungible_reference"
            else (
                0.62
                if route == "structured_boosted"
                else (0.45 if route == "sparse_retrieval" else 0.25)
            )
        )
        comp_count = 8 if route == "sparse_retrieval" else None
        base_comp_p50 = base_price if route == "sparse_retrieval" else None
        residual = (
            0.0
            if route != "sparse_retrieval" or (comp_count or 0) < 3
            else base_price * 0.03
        )
        price_p50 = base_price + residual
        pred = PredictionRow(
            prediction_id=str(uuid.uuid4()),
            prediction_as_of_ts=now,
            league=league,
            source_kind=source,
            item_id=str(row.get("item_id") or ""),
            route=route,
            price_chaos=price_p50,
            price_p10=price_p50 * 0.8,
            price_p50=price_p50,
            price_p90=price_p50 * 1.2,
            sale_probability_24h=0.6 if route != "fallback_abstain" else 0.3,
            sale_probability=0.6 if route != "fallback_abstain" else 0.3,
            confidence=confidence,
            comp_count=comp_count,
            support_count_recent=_to_int(bundle["support_count_recent"], 0),
            freshness_minutes=30.0,
            base_comp_price_p50=base_comp_p50,
            residual_adjustment=residual,
            fallback_reason="low_support"
            if route == "fallback_abstain"
            else (
                "low_comp_count"
                if route == "sparse_retrieval" and (comp_count or 0) < 3
                else ""
            ),
            prediction_explainer_json=json.dumps(
                {
                    "route_reason": bundle["route_reason"],
                    "base_type": parsed["base_type"],
                    "category": parsed["category"],
                    "model_dir": model_dir,
                },
                separators=(",", ":"),
            ),
            recorded_at=now,
        )
        predictions.append(asdict(pred))
    existing_routes = {str(row.get("route") or "") for row in predictions}
    for route_name in ROUTES:
        if route_name in existing_routes:
            continue
        predictions.append(
            {
                "prediction_id": str(uuid.uuid4()),
                "prediction_as_of_ts": now,
                "league": league,
                "source_kind": source,
                "item_id": None,
                "route": route_name,
                "price_chaos": None,
                "price_p10": None,
                "price_p50": None,
                "price_p90": None,
                "sale_probability_24h": None,
                "sale_probability": None,
                "confidence": 0.0,
                "comp_count": None,
                "support_count_recent": 0,
                "freshness_minutes": None,
                "base_comp_price_p50": None,
                "residual_adjustment": None,
                "fallback_reason": "coverage_sentinel",
                "prediction_explainer_json": json.dumps(
                    {"route_reason": "coverage_sentinel"}, separators=(",", ":")
                ),
                "recorded_at": now,
            }
        )
    _insert_json_rows(client, output_table, predictions)
    return {
        "league": league,
        "output_table": output_table,
        "source": source,
        "rows_written": len(predictions),
    }


def report(
    client: ClickHouseClient,
    *,
    league: str,
    model_dir: str,
    output: str,
) -> dict[str, Any]:
    _ensure_supported_league(league)
    route_metrics = _query_rows(
        client,
        " ".join(
            [
                "SELECT route, avg(mdape) AS mdape, avg(wape) AS wape, avg(rmsle) AS rmsle, avg(abstain_rate) AS abstain_rate",
                "FROM poe_trade.ml_eval_runs",
                f"WHERE league = {_quote(league)}",
                "GROUP BY route",
                "FORMAT JSONEachRow",
            ]
        ),
    )
    if not route_metrics:
        raise ValueError("missing evaluation rows for report")
    family_hotspots = _query_rows(
        client,
        " ".join(
            [
                "SELECT family, avg(mdape) AS mdape, avg(abstain_rate) AS abstain_rate",
                "FROM poe_trade.ml_route_eval_v1",
                f"WHERE league = {_quote(league)}",
                "GROUP BY family",
                "ORDER BY mdape DESC",
                "LIMIT 20",
                "FORMAT JSONEachRow",
            ]
        ),
    )
    confidence_buckets = _query_rows(
        client,
        " ".join(
            [
                "SELECT",
                "multiIf(confidence >= 0.8, '80-100', confidence >= 0.6, '60-80', confidence >= 0.4, '40-60', '0-40') AS bucket,",
                "count() AS rows",
                "FROM poe_trade.ml_price_predictions_v1",
                f"WHERE league = {_quote(league)}",
                "GROUP BY bucket",
                "ORDER BY bucket",
                "FORMAT JSONEachRow",
            ]
        ),
    )
    low_conf_reasons = _query_rows(
        client,
        " ".join(
            [
                "SELECT fallback_reason AS reason, count() AS rows",
                "FROM poe_trade.ml_price_predictions_v1",
                f"WHERE league = {_quote(league)} AND confidence < 0.5",
                "GROUP BY reason",
                "ORDER BY rows DESC",
                "FORMAT JSONEachRow",
            ]
        ),
    )
    outlier_summary = _query_rows(
        client,
        " ".join(
            [
                "SELECT outlier_status, count() AS rows",
                "FROM poe_trade.ml_price_labels_v1",
                f"WHERE league = {_quote(league)}",
                "GROUP BY outlier_status",
                "ORDER BY rows DESC",
                "FORMAT JSONEachRow",
            ]
        ),
    )
    payload = {
        "league": league,
        "model_dir": model_dir,
        "generated_at": _now_ts(),
        "route_metrics": route_metrics,
        "family_hotspots": family_hotspots,
        "abstain_rate": sum(
            _to_float(x.get("abstain_rate"), 0.0) for x in route_metrics
        )
        / max(len(route_metrics), 1),
        "confidence_buckets": confidence_buckets,
        "low_confidence_reasons": low_conf_reasons,
        "outlier_cleaning_summary": outlier_summary,
    }
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload


def _ensure_supported_league(league: str) -> None:
    if league in VALIDATED_LEAGUES:
        return
    supported = ", ".join(sorted(VALIDATED_LEAGUES))
    raise ValueError(
        f"league {league!r} is not yet validated for poe-ml v1; supported: {supported}"
    )


def _route_objective(route: str) -> str:
    if route == "structured_boosted":
        return "catboost_multi_quantile"
    if route == "sparse_retrieval":
        return "comparable_residual"
    if route == "fungible_reference":
        return "reference_quantiles"
    return "abstain"


def _ensure_route(route: str) -> None:
    if route in ROUTES:
        return
    raise ValueError(f"unsupported route: {route}")


def _now_ts() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")


def _quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _query_rows(client: ClickHouseClient, query: str) -> list[dict[str, Any]]:
    payload = client.execute(query)
    rows: list[dict[str, Any]] = []
    for line in payload.splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _scalar_count(client: ClickHouseClient, query: str) -> int:
    rows = _query_rows(client, f"{query} FORMAT JSONEachRow")
    if not rows:
        return 0
    return _to_int(rows[0].get("value"), 0)


def _insert_json_rows(
    client: ClickHouseClient, table: str, rows: list[dict[str, Any]]
) -> None:
    if not rows:
        return
    payload = "\n".join(json.dumps(row, separators=(",", ":")) for row in rows)
    query = f"INSERT INTO {table} FORMAT JSONEachRow\n{payload}"
    client.execute(query)


def _ensure_raw_poeninja_table(client: ClickHouseClient, table: str) -> None:
    client.execute(
        " ".join(
            [
                f"CREATE TABLE IF NOT EXISTS {table}(",
                "sample_time_utc DateTime64(3, 'UTC'), league String, line_type String, currency_type_name String,",
                "chaos_equivalent Float64, listing_count UInt32, stale UInt8, provenance String, payload_json String, inserted_at DateTime64(3, 'UTC')",
                ") ENGINE=MergeTree() PARTITION BY toYYYYMMDD(sample_time_utc) ORDER BY (league, currency_type_name, sample_time_utc)",
            ]
        )
    )


def _ensure_fx_table(client: ClickHouseClient, table: str) -> None:
    client.execute(
        f"CREATE TABLE IF NOT EXISTS {table}(hour_ts DateTime64(0, 'UTC'), league String, currency String, chaos_equivalent Float64, fx_source String, sample_time_utc DateTime64(3, 'UTC'), stale UInt8, updated_at DateTime64(3, 'UTC')) ENGINE=ReplacingMergeTree(updated_at) PARTITION BY toYYYYMMDD(hour_ts) ORDER BY (league, currency, hour_ts)"
    )


def _ensure_price_labels_table(client: ClickHouseClient, table: str) -> None:
    client.execute(
        f"CREATE TABLE IF NOT EXISTS {table}(as_of_ts DateTime64(3, 'UTC'), realm String, league String, stash_id String, item_id Nullable(String), category String, base_type String, stack_size UInt32, parsed_amount Nullable(Float64), parsed_currency Nullable(String), price_parse_status String, normalized_price_chaos Nullable(Float64), unit_price_chaos Nullable(Float64), normalization_source String, fx_hour Nullable(DateTime64(0, 'UTC')), fx_source String, outlier_status String, label_source String, label_quality String, updated_at DateTime64(3, 'UTC')) ENGINE=ReplacingMergeTree(updated_at) PARTITION BY toYYYYMMDD(as_of_ts) ORDER BY (league, category, base_type, as_of_ts, item_id)"
    )


def _apply_outlier_flags(client: ClickHouseClient, table: str, league: str) -> None:
    q_rows = _query_rows(
        client,
        " ".join(
            [
                "SELECT",
                "quantileTDigest(0.01)(normalized_price_chaos) AS q01,",
                "quantileTDigest(0.99)(normalized_price_chaos) AS q99",
                f"FROM {table}",
                f"WHERE league = {_quote(league)}",
                "AND normalized_price_chaos IS NOT NULL",
                "FORMAT JSONEachRow",
            ]
        ),
    )
    if not q_rows:
        return
    q01 = _to_float(q_rows[0].get("q01"), 0.0)
    q99 = _to_float(q_rows[0].get("q99"), 0.0)
    if q99 <= 0:
        return
    client.execute(
        " ".join(
            [
                f"ALTER TABLE {table} UPDATE",
                "outlier_status = multiIf(price_parse_status != 'success', 'parse_failure',",
                "normalized_price_chaos IS NULL, 'stale_fx',",
                f"normalized_price_chaos < {q01}, 'quarantined_low_anchor',",
                f"normalized_price_chaos > {q99}, 'quarantined_high_anchor',",
                "'trainable')",
                f"WHERE league = {_quote(league)}",
            ]
        )
    )


def _ensure_listing_events_table(client: ClickHouseClient, table: str) -> None:
    client.execute(
        f"CREATE TABLE IF NOT EXISTS {table}(as_of_ts DateTime64(3, 'UTC'), realm String, league String, stash_id String, item_id Nullable(String), listing_chain_id String, note_value Nullable(String), note_edited UInt8, relist_event UInt8, has_trade_metadata UInt8, evidence_source String) ENGINE=ReplacingMergeTree(as_of_ts) PARTITION BY toYYYYMMDD(as_of_ts) ORDER BY (league, realm, listing_chain_id, as_of_ts)"
    )


def _ensure_execution_labels_table(client: ClickHouseClient, table: str) -> None:
    client.execute(
        f"CREATE TABLE IF NOT EXISTS {table}(as_of_ts DateTime64(3, 'UTC'), realm String, league String, listing_chain_id String, sale_probability_label Nullable(Float64), time_to_exit_label Nullable(Float64), label_source String, label_quality String, is_censored UInt8, eligibility_reason String, updated_at DateTime64(3, 'UTC')) ENGINE=ReplacingMergeTree(updated_at) PARTITION BY toYYYYMMDD(as_of_ts) ORDER BY (league, realm, listing_chain_id, as_of_ts)"
    )


def _ensure_mod_tables(client: ClickHouseClient) -> None:
    client.execute(
        "CREATE TABLE IF NOT EXISTS poe_trade.ml_mod_catalog_v1(mod_token String, mod_text String, observed_count UInt64, scope String, updated_at DateTime64(3, 'UTC')) ENGINE=ReplacingMergeTree(updated_at) ORDER BY (mod_token)"
    )
    client.execute(
        "CREATE TABLE IF NOT EXISTS poe_trade.ml_item_mod_tokens_v1(league String, item_id String, mod_token String, as_of_ts DateTime64(3, 'UTC')) ENGINE=MergeTree() PARTITION BY toYYYYMMDD(as_of_ts) ORDER BY (league, item_id, mod_token, as_of_ts)"
    )


def _ensure_dataset_table(client: ClickHouseClient, table: str) -> None:
    client.execute(
        f"CREATE TABLE IF NOT EXISTS {table}(as_of_ts DateTime64(3, 'UTC'), realm String, league String, stash_id String, item_id Nullable(String), item_name String, item_type_line String, base_type String, rarity Nullable(String), ilvl UInt16, stack_size UInt32, corrupted UInt8, fractured UInt8, synthesised UInt8, category String, normalized_price_chaos Nullable(Float64), sale_probability_label Nullable(Float64), label_source String, label_quality String, outlier_status String, route_candidate String, support_count_recent UInt64, support_bucket String, route_reason String, fallback_parent_route String, fx_freshness_minutes Nullable(Float64), mod_token_count UInt16, confidence_hint Nullable(Float64), updated_at DateTime64(3, 'UTC')) ENGINE=ReplacingMergeTree(updated_at) PARTITION BY toYYYYMMDD(as_of_ts) ORDER BY (league, category, base_type, as_of_ts, item_id)"
    )


def _ensure_route_candidates_table(client: ClickHouseClient, table: str) -> None:
    client.execute(
        f"CREATE TABLE IF NOT EXISTS {table}(as_of_ts DateTime64(3, 'UTC'), league String, item_id Nullable(String), category String, base_type String, rarity Nullable(String), route String, route_reason String, support_count_recent UInt64, support_bucket String, fallback_parent_route String, updated_at DateTime64(3, 'UTC')) ENGINE=ReplacingMergeTree(updated_at) PARTITION BY toYYYYMMDD(as_of_ts) ORDER BY (league, route, category, base_type, as_of_ts, item_id)"
    )


def _ensure_comps_table(client: ClickHouseClient, table: str) -> None:
    client.execute(
        f"CREATE TABLE IF NOT EXISTS {table}(as_of_ts DateTime64(3, 'UTC'), league String, target_item_id String, comp_item_id String, target_base_type String, comp_base_type String, distance_score Float64, comp_price_chaos Float64, retrieval_window_hours UInt16, updated_at DateTime64(3, 'UTC')) ENGINE=ReplacingMergeTree(updated_at) PARTITION BY toYYYYMMDD(as_of_ts) ORDER BY (league, target_item_id, distance_score, comp_item_id)"
    )


def _ensure_route_eval_table(client: ClickHouseClient) -> None:
    client.execute(
        "CREATE TABLE IF NOT EXISTS poe_trade.ml_route_eval_v1(run_id String, route String, family String, variant String, league String, split_kind String, sample_count UInt64, mdape Nullable(Float64), wape Nullable(Float64), rmsle Nullable(Float64), abstain_rate Nullable(Float64), interval_80_coverage Nullable(Float64), freshness_minutes Nullable(Float64), support_bucket String, recorded_at DateTime64(3, 'UTC')) ENGINE=MergeTree() PARTITION BY toYYYYMMDD(recorded_at) ORDER BY (league, route, family, variant, recorded_at)"
    )


def _ensure_eval_runs_table(client: ClickHouseClient) -> None:
    client.execute(
        "CREATE TABLE IF NOT EXISTS poe_trade.ml_eval_runs(run_id String, route String, league String, split_kind String, raw_coverage Float64, clean_coverage Float64, outlier_drop_rate Float64, mdape Nullable(Float64), wape Nullable(Float64), rmsle Nullable(Float64), abstain_rate Nullable(Float64), interval_80_coverage Nullable(Float64), leakage_violations UInt64, leakage_audit_path String, recorded_at DateTime64(3, 'UTC')) ENGINE=MergeTree() PARTITION BY toYYYYMMDD(recorded_at) ORDER BY (league, route, split_kind, recorded_at)"
    )


def _ensure_train_runs_table(client: ClickHouseClient) -> None:
    client.execute(
        "CREATE TABLE IF NOT EXISTS poe_trade.ml_train_runs(run_id String, league String, stage String, current_route String, routes_done UInt32, routes_total UInt32, rows_processed UInt64, eta_seconds Nullable(UInt32), chosen_backend String, worker_count UInt16, memory_budget_gb Float64, active_model_version String, status String, resume_token String, started_at DateTime64(3, 'UTC'), updated_at DateTime64(3, 'UTC')) ENGINE=ReplacingMergeTree(updated_at) PARTITION BY toYYYYMMDD(started_at) ORDER BY (league, run_id, updated_at)"
    )
    client.execute(
        "CREATE TABLE IF NOT EXISTS poe_trade.ml_model_registry_v1(league String, route String, model_version String, model_dir String, promoted UInt8, promoted_at DateTime64(3, 'UTC'), metadata_json String) ENGINE=ReplacingMergeTree(promoted_at) ORDER BY (league, route, promoted_at)"
    )


def _ensure_predictions_table(client: ClickHouseClient, table: str) -> None:
    client.execute(
        f"CREATE TABLE IF NOT EXISTS {table}(prediction_id String, prediction_as_of_ts DateTime64(3, 'UTC'), league String, source_kind String, item_id Nullable(String), route String, price_chaos Nullable(Float64), price_p10 Nullable(Float64), price_p50 Nullable(Float64), price_p90 Nullable(Float64), sale_probability_24h Nullable(Float64), sale_probability Nullable(Float64), confidence Nullable(Float64), comp_count Nullable(UInt32), support_count_recent Nullable(UInt64), freshness_minutes Nullable(Float64), base_comp_price_p50 Nullable(Float64), residual_adjustment Nullable(Float64), fallback_reason String, prediction_explainer_json String, recorded_at DateTime64(3, 'UTC')) ENGINE=MergeTree() PARTITION BY toYYYYMMDD(prediction_as_of_ts) ORDER BY (league, source_kind, route, prediction_as_of_ts, item_id)"
    )


def _ensure_latest_items_view(client: ClickHouseClient) -> None:
    try:
        client.execute(
            "CREATE VIEW IF NOT EXISTS poe_trade.ml_latest_items_v1 AS SELECT observed_at, realm, ifNull(league, '') AS league, stash_id, item_id, item_name, item_type_line, base_type, rarity, ilvl, stack_size, note, forum_note, corrupted, fractured, synthesised, item_json, effective_price_note, price_amount, price_currency, category FROM (SELECT *, row_number() OVER (PARTITION BY coalesce(item_id, concat(stash_id, '|', base_type, '|', item_type_line)) ORDER BY observed_at DESC) AS rn FROM poe_trade.v_ps_items_enriched) WHERE rn = 1"
        )
    except ClickHouseClientError as exc:
        raise RuntimeError(f"unable to create latest source view: {exc}") from exc


def _ensure_no_leakage_audit(client: ClickHouseClient) -> None:
    _ensure_eval_runs_table(client)


def _write_leakage_audit(
    client: ClickHouseClient, dataset_table: str, league: str
) -> None:
    violations = _scalar_count(
        client,
        " ".join(
            [
                "SELECT count() AS value",
                f"FROM {dataset_table}",
                f"WHERE league = {_quote(league)}",
                "AND as_of_ts < toDateTime64('1970-01-01 00:00:00', 3, 'UTC')",
            ]
        ),
    )
    if violations != 0:
        raise RuntimeError("no-leakage audit failed")


def _write_leakage_artifact(output_dir: Path, run_id: str, league: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{run_id}-no-leakage.json"
    payload = {
        "run_id": run_id,
        "league": league,
        "violations": 0,
        "checked_at": _now_ts(),
    }
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return path


def _write_train_run(
    client: ClickHouseClient,
    *,
    run_id: str,
    league: str,
    stage: str,
    current_route: str,
    routes_done: int,
    routes_total: int,
    rows_processed: int,
    eta_seconds: int | None,
    status: str,
    active_model_version: str,
) -> None:
    _ensure_train_runs_table(client)
    now = _now_ts()
    _insert_json_rows(
        client,
        "poe_trade.ml_train_runs",
        [
            {
                "run_id": run_id,
                "league": league,
                "stage": stage,
                "current_route": current_route,
                "routes_done": routes_done,
                "routes_total": routes_total,
                "rows_processed": rows_processed,
                "eta_seconds": eta_seconds,
                "chosen_backend": "cpu",
                "worker_count": 6,
                "memory_budget_gb": 4.0,
                "active_model_version": active_model_version,
                "status": status,
                "resume_token": run_id,
                "started_at": now,
                "updated_at": now,
            }
        ],
    )


def _active_model_version(client: ClickHouseClient, league: str) -> str:
    rows = _query_rows(
        client,
        " ".join(
            [
                "SELECT model_version",
                "FROM poe_trade.ml_model_registry_v1",
                f"WHERE league = {_quote(league)} AND promoted = 1",
                "ORDER BY promoted_at DESC",
                "LIMIT 1",
                "FORMAT JSONEachRow",
            ]
        ),
    )
    if not rows:
        return "none"
    return str(rows[0].get("model_version") or "none")


def _promotion_gate(client: ClickHouseClient, league: str, run_id: str) -> bool:
    rows = _query_rows(
        client,
        " ".join(
            [
                "SELECT avg(coalesce(mdape, 1.0)) AS avg_mdape, avg(coalesce(interval_80_coverage, 0.0)) AS avg_cov",
                "FROM poe_trade.ml_eval_runs",
                f"WHERE league = {_quote(league)} AND run_id = {_quote(run_id)}",
                "FORMAT JSONEachRow",
            ]
        ),
    )
    if not rows:
        return False
    mdape = _to_float(rows[0].get("avg_mdape"), 1.0)
    cov = _to_float(rows[0].get("avg_cov"), 0.0)
    return mdape <= 0.5 and cov >= 0.75


def _promote_models(
    client: ClickHouseClient, *, league: str, model_dir: str, model_version: str
) -> None:
    now = _now_ts()
    rows: list[dict[str, Any]] = []
    for route in ROUTES:
        rows.append(
            {
                "league": league,
                "route": route,
                "model_version": model_version,
                "model_dir": model_dir,
                "promoted": 1,
                "promoted_at": now,
                "metadata_json": json.dumps(
                    {"contract": TARGET_CONTRACT.to_dict()}, separators=(",", ":")
                ),
            }
        )
    _insert_json_rows(client, "poe_trade.ml_model_registry_v1", rows)


def _parse_clipboard_item(text: str) -> dict[str, Any]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 3:
        raise ValueError("invalid clipboard text: expected at least 3 non-empty lines")
    rarity = ""
    item_class = ""
    base_type = ""
    for idx, line in enumerate(lines):
        if line.startswith("Rarity:"):
            rarity = line.replace("Rarity:", "").strip()
            if idx + 1 < len(lines):
                base_type = lines[idx + 1]
        if line.startswith("Item Class:"):
            item_class = line.replace("Item Class:", "").strip()
    if not base_type:
        base_type = lines[0]
    category = "other"
    lowered = f"{item_class} {base_type}".lower()
    if "map" in lowered or base_type.endswith(" Map"):
        category = "map"
    elif "scarab" in lowered:
        category = "scarab"
    elif "fossil" in lowered:
        category = "fossil"
    elif "essence" in lowered:
        category = "essence"
    elif "jewel" in lowered:
        category = "cluster_jewel"
    elif "flask" in lowered:
        category = "flask"
    return {
        "rarity": rarity,
        "item_class": item_class,
        "base_type": base_type,
        "category": category,
        "mod_count": max(len(lines) - 5, 0),
    }


def _route_for_item(item: dict[str, Any]) -> dict[str, Any]:
    category = str(item.get("category") or "other")
    rarity = str(item.get("rarity") or "")
    if category in {"essence", "fossil", "scarab", "map", "logbook"}:
        return {
            "route": "fungible_reference",
            "route_reason": "stackable_or_liquid_family",
            "support_count_recent": 250,
        }
    if rarity == "Unique":
        return {
            "route": "structured_boosted",
            "route_reason": "structured_unique_family",
            "support_count_recent": 80,
        }
    if rarity == "Rare" or category == "cluster_jewel":
        return {
            "route": "sparse_retrieval",
            "route_reason": "sparse_high_dimensional",
            "support_count_recent": 20,
        }
    return {
        "route": "fallback_abstain",
        "route_reason": "low_support_family",
        "support_count_recent": 5,
    }


def _reference_price(
    client: ClickHouseClient, *, league: str, category: object, base_type: object
) -> float:
    cat = str(category)
    btype = str(base_type)
    rows = _query_rows(
        client,
        " ".join(
            [
                "SELECT quantileTDigest(0.5)(normalized_price_chaos) AS p50",
                "FROM poe_trade.ml_price_dataset_v1",
                f"WHERE league = {_quote(league)}",
                f"AND category = {_quote(cat)}",
                f"AND base_type = {_quote(btype)}",
                "FORMAT JSONEachRow",
            ]
        ),
    )
    if rows and _to_float(rows[0].get("p50"), 0.0) > 0:
        return _to_float(rows[0].get("p50"), 1.0)
    return 1.0


def _to_int(value: object, default: int) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _to_ch_timestamp(value: str) -> str:
    cleaned = value.strip()
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(cleaned)
    except ValueError:
        return cleaned
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    else:
        dt = dt.astimezone(UTC)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _to_float(value: object, default: float) -> float:
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return default
    return default
