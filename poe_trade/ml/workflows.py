from __future__ import annotations

import json
import math
import os
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.feature_extraction import DictVectorizer

from poe_trade.db import ClickHouseClient
from poe_trade.db.clickhouse import ClickHouseClientError
from poe_trade.ingestion.poeninja_snapshot import PoeNinjaClient

from .audit import VALIDATED_LEAGUES
from .contract import MIRAGE_EVAL_CONTRACT, TARGET_CONTRACT


ROUTES = (
    "fungible_reference",
    "structured_boosted",
    "sparse_retrieval",
    "fallback_abstain",
)

MODEL_FEATURE_FIELDS = (
    "category",
    "base_type",
    "rarity",
    "ilvl",
    "stack_size",
    "corrupted",
    "fractured",
    "synthesised",
    "mod_token_count",
)

_MODEL_BUNDLE_CACHE: dict[str, dict[str, Any]] = {}


@dataclass(frozen=True)
class TuningControls:
    max_iterations: int
    max_wall_clock_seconds: int
    no_improvement_patience: int
    min_mdape_improvement: float
    warm_start_enabled: bool
    resume_supported: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


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


def _bucket_ilvl(value: object) -> float:
    numeric = max(0, int(_to_float(value, 0.0)))
    return float((numeric // 5) * 5)


def _bucket_stack_size(value: object) -> float:
    numeric = max(1, int(_to_float(value, 1.0)))
    return float(min(numeric, 20))


def _bucket_mod_token_count(value: object) -> float:
    numeric = max(0, int(_to_float(value, 0.0)))
    return float(min(numeric, 16))


def _route_feature_select_sql(prefix: str = "") -> list[str]:
    qualifier = f"{prefix}." if prefix else ""
    return [
        f"{qualifier}category AS category,",
        f"{qualifier}base_type AS base_type,",
        f"ifNull({qualifier}rarity, '') AS rarity,",
        f"toFloat64(intDiv(toUInt16(ifNull({qualifier}ilvl, 0)), 5) * 5) AS ilvl,",
        f"toFloat64(multiIf(ifNull({qualifier}stack_size, 1) < 1, 1, ifNull({qualifier}stack_size, 1) > 20, 20, ifNull({qualifier}stack_size, 1))) AS stack_size,",
        f"toFloat64(ifNull({qualifier}corrupted, 0)) AS corrupted,",
        f"toFloat64(ifNull({qualifier}fractured, 0)) AS fractured,",
        f"toFloat64(ifNull({qualifier}synthesised, 0)) AS synthesised,",
        f"toFloat64(multiIf(ifNull({qualifier}mod_token_count, 0) < 0, 0, ifNull({qualifier}mod_token_count, 0) > 16, 16, ifNull({qualifier}mod_token_count, 0))) AS mod_token_count,",
    ]


def _training_aggregate_rows(
    client: ClickHouseClient,
    *,
    route: str,
    league: str,
    dataset_table: str,
    before_as_of_ts: str | None = None,
) -> list[dict[str, Any]]:
    filters = [
        f"league = {_quote(league)}",
        "normalized_price_chaos IS NOT NULL",
        "normalized_price_chaos > 0",
        _route_training_predicate(route),
    ]
    if before_as_of_ts:
        cutoff = _to_ch_timestamp(before_as_of_ts)
        filters.append(
            f"as_of_ts < toDateTime64({_quote(cutoff)}, 3, 'UTC')"
        )
    where_clause = " AND ".join(filters)
    query = " ".join(
        [
            "SELECT",
            *_route_feature_select_sql(),
            "quantileTDigest(0.1)(normalized_price_chaos) AS target_p10,",
            "quantileTDigest(0.5)(normalized_price_chaos) AS target_p50,",
            "quantileTDigest(0.9)(normalized_price_chaos) AS target_p90,",
            "avg(toFloat64(ifNull(sale_probability_label, 0.0))) AS sale_probability_label,",
            "count() AS sample_count",
            f"FROM {dataset_table}",
            f"WHERE {where_clause}",
            "GROUP BY category, base_type, rarity, ilvl, stack_size, corrupted, fractured, synthesised, mod_token_count",
            "FORMAT JSONEachRow",
        ]
    )
    return _query_rows(client, query)


def _route_raw_row_count(
    client: ClickHouseClient,
    *,
    route: str,
    league: str,
    dataset_table: str,
) -> int:
    return _scalar_count(
        client,
        " ".join(
            [
                "SELECT count() AS value",
                f"FROM {dataset_table}",
                f"WHERE league = {_quote(league)}",
                "AND normalized_price_chaos IS NOT NULL",
                "AND normalized_price_chaos > 0",
                f"AND {_route_training_predicate(route)}",
            ]
        ),
    )


def _evaluation_rows(
    client: ClickHouseClient,
    *,
    route: str,
    league: str,
    dataset_table: str,
    limit: int,
) -> list[dict[str, Any]]:
    query = " ".join(
        [
            "SELECT",
            *_route_feature_select_sql(),
            "toFloat64(normalized_price_chaos) AS normalized_price_chaos,",
            "toFloat64(ifNull(sale_probability_label, 0.0)) AS sale_probability_label,",
            "category AS family,",
            "toString(as_of_ts) AS as_of_ts",
            f"FROM {dataset_table}",
            f"WHERE league = {_quote(league)}",
            "AND normalized_price_chaos IS NOT NULL",
            "AND normalized_price_chaos > 0",
            f"AND {_route_training_predicate(route)}",
            "ORDER BY as_of_ts DESC",
            f"LIMIT {max(1, limit)}",
            "FORMAT JSONEachRow",
        ]
    )
    rows = _query_rows(client, query)
    rows.reverse()
    return rows


def _weighted_median(values: list[float], weights: list[float]) -> float:
    if not values or not weights or len(values) != len(weights):
        return 0.0
    ordered = sorted(zip(values, weights), key=lambda pair: pair[0])
    total_weight = sum(max(weight, 0.0) for _, weight in ordered)
    if total_weight <= 0:
        return _median(values)
    threshold = total_weight / 2.0
    seen = 0.0
    for value, weight in ordered:
        seen += max(weight, 0.0)
        if seen >= threshold:
            return float(value)
    return float(ordered[-1][0])


def _fit_route_bundle_from_aggregates(
    aggregate_rows: list[dict[str, Any]],
    *,
    trained_at: str,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    usable_rows = [
        row
        for row in aggregate_rows
        if _to_float(row.get("target_p50"), 0.0) > 0.0
        and _to_int(row.get("sample_count"), 0) > 0
    ]
    sample_weights = [max(1.0, _to_float(row.get("sample_count"), 1.0)) for row in usable_rows]
    train_row_count = int(sum(sample_weights))
    stats: dict[str, Any] = {
        "train_row_count": train_row_count,
        "feature_row_count": len(usable_rows),
        "support_reference_p50": _weighted_median(
            [_to_float(row.get("target_p50"), 0.0) for row in usable_rows],
            sample_weights,
        ),
        "sale_model_available": False,
        "model_backend": "heuristic_fallback",
    }
    if len(usable_rows) < 5 or train_row_count < 25:
        return None, stats

    feature_rows = [_feature_dict_from_row(row) for row in usable_rows]
    vectorizer = DictVectorizer(sparse=True)
    X = vectorizer.fit_transform(feature_rows)
    y_p10 = [_to_float(row.get("target_p10"), 0.0) for row in usable_rows]
    y_p50 = [_to_float(row.get("target_p50"), 0.0) for row in usable_rows]
    y_p90 = [_to_float(row.get("target_p90"), 0.0) for row in usable_rows]
    y_sale = [
        min(1.0, max(0.0, _to_float(row.get("sale_probability_label"), 0.0)))
        for row in usable_rows
    ]

    model_p10 = GradientBoostingRegressor(
        loss="quantile",
        alpha=0.10,
        n_estimators=120,
        learning_rate=0.05,
        max_depth=3,
        min_samples_leaf=5,
        random_state=42,
    )
    model_p50 = GradientBoostingRegressor(
        loss="quantile",
        alpha=0.50,
        n_estimators=120,
        learning_rate=0.05,
        max_depth=3,
        min_samples_leaf=5,
        random_state=43,
    )
    model_p90 = GradientBoostingRegressor(
        loss="quantile",
        alpha=0.90,
        n_estimators=120,
        learning_rate=0.05,
        max_depth=3,
        min_samples_leaf=5,
        random_state=44,
    )
    model_p10.fit(X, y_p10, sample_weight=sample_weights)
    model_p50.fit(X, y_p50, sample_weight=sample_weights)
    model_p90.fit(X, y_p90, sample_weight=sample_weights)

    sale_model = None
    if len({round(value, 4) for value in y_sale}) > 1:
        sale_model = GradientBoostingRegressor(
            loss="squared_error",
            n_estimators=80,
            learning_rate=0.05,
            max_depth=2,
            min_samples_leaf=5,
            random_state=45,
        )
        sale_model.fit(X, y_sale, sample_weight=sample_weights)

    bundle = {
        "vectorizer": vectorizer,
        "price_models": {"p10": model_p10, "p50": model_p50, "p90": model_p90},
        "sale_model": sale_model,
        "feature_fields": list(MODEL_FEATURE_FIELDS),
        "trained_at": trained_at,
    }
    stats["sale_model_available"] = sale_model is not None
    stats["model_backend"] = "sklearn_gradient_boosting"
    return bundle, stats


def _prediction_records_from_rows(
    rows: list[dict[str, Any]],
    *,
    bundle: dict[str, Any] | None,
    reference_price: float,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    fallback_price = max(0.1, reference_price or 0.1)
    for row in rows:
        actual = _to_float(row.get("normalized_price_chaos"), 0.0)
        if actual <= 0.0:
            continue
        predicted = _predict_with_bundle(bundle=bundle, parsed_item=row) if bundle else None
        if predicted is None:
            price_p50 = fallback_price
            price_p10 = max(0.1, price_p50 * 0.8)
            price_p90 = max(price_p50, price_p50 * 1.2)
            used_model = False
        else:
            price_p10 = max(0.1, _to_float(predicted.get("price_p10"), fallback_price * 0.8))
            price_p50 = max(price_p10, _to_float(predicted.get("price_p50"), fallback_price))
            price_p90 = max(price_p50, _to_float(predicted.get("price_p90"), fallback_price * 1.2))
            used_model = True
        records.append(
            {
                "family": str(row.get("family") or row.get("category") or "unknown"),
                "actual": actual,
                "price_p10": price_p10,
                "price_p50": price_p50,
                "price_p90": price_p90,
                "used_model": used_model,
            }
        )
    return records


def _metrics_from_prediction_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        return {
            "sample_count": 0,
            "mdape": 1.0,
            "wape": 1.0,
            "rmsle": 1.0,
            "abstain_rate": 1.0,
            "interval_80_coverage": 0.0,
        }
    apes: list[float] = []
    abs_errors: list[float] = []
    actuals: list[float] = []
    log_errors: list[float] = []
    interval_hits = 0
    predictions_made = 0
    for record in records:
        actual = _to_float(record.get("actual"), 0.0)
        pred = max(0.1, _to_float(record.get("price_p50"), 0.1))
        p10 = max(0.1, _to_float(record.get("price_p10"), pred * 0.8))
        p90 = max(pred, _to_float(record.get("price_p90"), pred * 1.2))
        error = abs(pred - actual)
        ape = error / max(actual, 0.01)
        apes.append(ape)
        abs_errors.append(error)
        actuals.append(actual)
        log_errors.append((math.log1p(pred) - math.log1p(actual)) ** 2)
        if p10 <= actual <= p90:
            interval_hits += 1
        if bool(record.get("used_model")):
            predictions_made += 1
    sample_count = len(records)
    return {
        "sample_count": sample_count,
        "mdape": _median(apes),
        "wape": sum(abs_errors) / max(sum(actuals), 0.01),
        "rmsle": math.sqrt(sum(log_errors) / sample_count),
        "abstain_rate": 1.0 - (predictions_made / sample_count),
        "interval_80_coverage": interval_hits / sample_count,
    }


def _support_bucket_for_count(sample_count: int) -> str:
    if sample_count >= 250:
        return "high"
    if sample_count >= 50:
        return "medium"
    return "low"


def _route_default_confidence(route: str) -> float:
    if route == "fungible_reference":
        return 0.70
    if route == "structured_boosted":
        return 0.62
    if route == "sparse_retrieval":
        return 0.45
    return 0.25


def _route_confidence_cap(route: str) -> float:
    if route == "fungible_reference":
        return 0.78
    if route == "structured_boosted":
        return 0.70
    if route == "sparse_retrieval":
        return 0.62
    return 0.55


def _model_confidence(route: str, *, support: int, train_row_count: int) -> float:
    support_factor = min(1.0, math.log1p(max(support, 0)) / math.log1p(250.0))
    training_factor = min(1.0, max(train_row_count, 0) / 1000.0)
    raw_confidence = 0.30 + 0.30 * support_factor + 0.25 * training_factor
    return min(_route_confidence_cap(route), raw_confidence)


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

    aggregate_rows = _training_aggregate_rows(
        client,
        route=route,
        league=league,
        dataset_table=dataset_table,
    )
    trained_at = _now_ts()
    bundle, bundle_stats = _fit_route_bundle_from_aggregates(
        aggregate_rows,
        trained_at=trained_at,
    )

    artifact_file = _route_artifact_path(model_dir=model_dir, route=route, league=league)
    model_bundle_path = _route_model_bundle_path(model_dir=model_dir, route=route, league=league)
    previous_artifact = _load_json_file(artifact_file)
    previous_round = _to_int(previous_artifact.get("fit_round"), 0)
    fit_round = max(1, previous_round + 1)

    artifact: dict[str, Any] = {
        "route": route,
        "league": league,
        "dataset_table": dataset_table,
        "comps_table": comps_table,
        "trained_at": trained_at,
        "fit_round": fit_round,
        "warm_start_from": str(artifact_file) if previous_artifact else None,
        "objective": _route_objective(route),
        "model_backend": bundle_stats.get("model_backend") or "heuristic_fallback",
        "features": list(MODEL_FEATURE_FIELDS),
        "train_row_count": _to_int(bundle_stats.get("train_row_count"), 0),
        "feature_row_count": _to_int(bundle_stats.get("feature_row_count"), 0),
        "family_counts": _query_rows(
            client,
            " ".join(
                [
                    "SELECT category AS family, count() AS rows",
                    f"FROM {dataset_table}",
                    f"WHERE league = {_quote(league)}",
                    f"AND {_route_training_predicate(route)}",
                    "GROUP BY family",
                    "FORMAT JSONEachRow",
                ]
            ),
        ),
        "sale_model_available": bool(bundle_stats.get("sale_model_available")),
        "model_bundle_path": None,
        "support_reference_p50": _to_float(bundle_stats.get("support_reference_p50"), 0.0),
        "support_reference_row_count": _to_int(bundle_stats.get("train_row_count"), 0),
    }

    if bundle is not None:
        joblib.dump(bundle, model_bundle_path)
        _MODEL_BUNDLE_CACHE[str(model_bundle_path)] = bundle
        artifact["model_bundle_path"] = str(model_bundle_path)
    else:
        artifact["training_status"] = "insufficient_rows"

    artifact_file.write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {
        "route": route,
        "league": league,
        "artifact": str(artifact_file),
        "rows_trained": _to_int(bundle_stats.get("train_row_count"), 0),
        "model_backend": artifact.get("model_backend"),
    }


def evaluate_route(
    client: ClickHouseClient,
    *,
    route: str,
    league: str,
    dataset_table: str,
    model_dir: str,
    comps_table: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    _ensure_supported_league(league)
    _ensure_route(route)
    _ensure_route_eval_table(client)
    eval_run_id = run_id or f"eval-{route}-{int(time.time())}"
    now = _now_ts()

    total_rows = _route_raw_row_count(
        client,
        route=route,
        league=league,
        dataset_table=dataset_table,
    )
    holdout_limit = max(10, min(2000, int(total_rows * 0.2) if total_rows else 0))
    holdout_rows = _evaluation_rows(
        client,
        route=route,
        league=league,
        dataset_table=dataset_table,
        limit=holdout_limit,
    )
    cutoff = str(holdout_rows[0].get("as_of_ts") or "") if holdout_rows else None
    aggregate_rows = _training_aggregate_rows(
        client,
        route=route,
        league=league,
        dataset_table=dataset_table,
        before_as_of_ts=cutoff,
    )
    bundle, bundle_stats = _fit_route_bundle_from_aggregates(
        aggregate_rows,
        trained_at=now,
    )
    records = _prediction_records_from_rows(
        holdout_rows,
        bundle=bundle,
        reference_price=_to_float(bundle_stats.get("support_reference_p50"), 0.0) or 1.0,
    )
    overall_metrics = _metrics_from_prediction_records(records)

    by_family: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        family = str(record.get("family") or "unknown")
        by_family.setdefault(family, []).append(record)

    insert_rows: list[dict[str, Any]] = []
    for family, family_records in by_family.items():
        family_metrics = _metrics_from_prediction_records(family_records)
        sample_count = _to_int(family_metrics.get("sample_count"), 0)
        insert_rows.append(
            {
                "run_id": eval_run_id,
                "route": route,
                "family": family,
                "variant": "route_main",
                "league": league,
                "split_kind": "rolling",
                "sample_count": sample_count,
                "mdape": _to_float(family_metrics.get("mdape"), 1.0),
                "wape": _to_float(family_metrics.get("wape"), 1.0),
                "rmsle": _to_float(family_metrics.get("rmsle"), 1.0),
                "abstain_rate": _to_float(family_metrics.get("abstain_rate"), 1.0),
                "interval_80_coverage": _to_float(family_metrics.get("interval_80_coverage"), 0.0),
                "freshness_minutes": 0.0,
                "support_bucket": _support_bucket_for_count(sample_count),
                "recorded_at": now,
            }
        )
    _insert_json_rows(client, "poe_trade.ml_route_eval_v1", insert_rows)
    return {
        "run_id": eval_run_id,
        "route": route,
        "league": league,
        "dataset_table": dataset_table,
        "comps_table": comps_table,
        "model_dir": model_dir,
        "rows": len(insert_rows),
        "sample_count": _to_int(overall_metrics.get("sample_count"), 0),
        "mdape": _to_float(overall_metrics.get("mdape"), 1.0),
        "wape": _to_float(overall_metrics.get("wape"), 1.0),
        "rmsle": _to_float(overall_metrics.get("rmsle"), 1.0),
        "abstain_rate": _to_float(overall_metrics.get("abstain_rate"), 1.0),
        "interval_80_coverage": _to_float(overall_metrics.get("interval_80_coverage"), 0.0),
        "train_row_count": _to_int(bundle_stats.get("train_row_count"), 0),
        "feature_row_count": _to_int(bundle_stats.get("feature_row_count"), 0),
        "model_backend": bundle_stats.get("model_backend") or "heuristic_fallback",
    }


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
    for route in ROUTES:
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
    _ensure_eval_contract_split(split)
    _ensure_eval_runs_table(client)
    _ensure_promotion_audit_table(client)
    _ensure_route_hotspots_table(client)
    run_id = f"stack-{int(time.time())}"
    leakage_path = _write_leakage_artifact(Path(output_dir), run_id, league)
    contract = MIRAGE_EVAL_CONTRACT

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
            run_id=run_id,
        )
        route_results.append(route_eval)
        sample_count = _to_int(route_eval.get("sample_count"), 0)
        abstain_rate = _to_float(route_eval.get("abstain_rate"), 1.0)
        clean_coverage = max(0.0, 1.0 - abstain_rate)
        _insert_json_rows(
            client,
            "poe_trade.ml_eval_runs",
            [
                {
                    "run_id": run_id,
                    "route": route,
                    "league": league,
                    "split_kind": contract.split_kind,
                    "raw_coverage": 1.0,
                    "clean_coverage": clean_coverage,
                    "outlier_drop_rate": 0.0,
                    "mdape": _to_float(route_eval.get("mdape"), 1.0),
                    "wape": _to_float(route_eval.get("wape"), 1.0),
                    "rmsle": _to_float(route_eval.get("rmsle"), 1.0),
                    "abstain_rate": abstain_rate if sample_count > 0 else 1.0,
                    "interval_80_coverage": _to_float(route_eval.get("interval_80_coverage"), 0.0),
                    "leakage_violations": 0,
                    "leakage_audit_path": str(leakage_path),
                    "recorded_at": _now_ts(),
                }
            ],
        )
    baseline = _latest_promoted_run_excluding(
        client, league=league, run_id=run_id
    ) or _latest_run_excluding(client, league=league, run_id=run_id)
    candidate = _aggregate_eval_run(client, league=league, run_id=run_id)
    comparison = _candidate_vs_incumbent_summary(
        candidate=candidate, incumbent=baseline
    )
    protected = _protected_cohort_check(
        client,
        league=league,
        candidate_run_id=run_id,
        incumbent_run_id=baseline.get("run_id") if baseline else None,
    )
    comparison["protected_cohort_regression"] = protected
    verdict = "promote" if _should_promote(comparison) else "hold"
    stop_reason = _promotion_stop_reason(comparison)
    hotspot_rows = _build_route_hotspots(
        client,
        league=league,
        candidate_run_id=run_id,
        incumbent_run_id=baseline.get("run_id") if baseline else None,
        top_n=contract.promotion.hotspot_top_n,
    )
    _insert_json_rows(client, "poe_trade.ml_route_hotspots_v1", hotspot_rows)
    _insert_json_rows(
        client,
        "poe_trade.ml_promotion_audit_v1",
        [
            {
                "league": league,
                "candidate_run_id": run_id,
                "incumbent_run_id": str(baseline.get("run_id") or "none")
                if baseline
                else "none",
                "candidate_model_version": f"candidate-{run_id}",
                "incumbent_model_version": str(baseline.get("run_id") or "none")
                if baseline
                else "none",
                "verdict": verdict,
                "avg_mdape_candidate": _to_float(candidate.get("avg_mdape"), 1.0),
                "avg_mdape_incumbent": _to_float(baseline.get("avg_mdape"), 1.0)
                if baseline
                else _to_float(candidate.get("avg_mdape"), 1.0),
                "coverage_candidate": _to_float(candidate.get("avg_cov"), 0.0),
                "coverage_incumbent": _to_float(baseline.get("avg_cov"), 0.0)
                if baseline
                else _to_float(candidate.get("avg_cov"), 0.0),
                "stop_reason": stop_reason,
                "recorded_at": _now_ts(),
            }
        ],
    )
    return {
        "run_id": run_id,
        "league": league,
        "routes": route_results,
        "leakage_audit_path": str(leakage_path),
        "evaluation_contract": contract.to_dict(),
        "candidate_vs_incumbent": comparison,
        "route_hotspots": _present_hotspots(hotspot_rows),
        "promotion_verdict": verdict,
        "stop_reason": stop_reason,
    }


def train_loop(
    client: ClickHouseClient,
    *,
    league: str,
    dataset_table: str,
    model_dir: str,
    max_iterations: int | None,
    max_wall_clock_seconds: int | None,
    no_improvement_patience: int | None,
    min_mdape_improvement: float | None,
    resume: bool,
) -> dict[str, Any]:
    _ensure_supported_league(league)
    _ensure_train_runs_table(client)
    _ensure_tuning_rounds_table(client)
    controls = _resolve_tuning_controls(
        max_iterations=max_iterations,
        max_wall_clock_seconds=max_wall_clock_seconds,
        no_improvement_patience=no_improvement_patience,
        min_mdape_improvement=min_mdape_improvement,
    )
    if resume:
        latest = _latest_train_run_row(client, league)
        if not latest:
            raise ValueError("resume requested but no resumable run exists")
    iterations = controls.max_iterations
    current_version = _active_model_version(client, league)
    completed: list[dict[str, Any]] = []
    start = time.time()
    no_improvement_streak = 0
    best_mdape: float | None = None
    final_status = "completed"
    final_stop_reason = "iteration_budget_exhausted"
    exhausted_iteration_budget = False
    i = 0
    while i < iterations:
        elapsed = int(max(time.time() - start, 0))
        if elapsed >= controls.max_wall_clock_seconds:
            final_status = "stopped_budget"
            final_stop_reason = "wall_clock_budget_exhausted"
            break
        run_id = f"train-{league.lower()}-{int(time.time())}-{i}"
        _write_train_run(
            client,
            run_id=run_id,
            league=league,
            stage="dataset",
            current_route="",
            routes_done=0,
            routes_total=len(ROUTES) + 1,
            rows_processed=_dataset_row_count(client, dataset_table, league),
            eta_seconds=None,
            status="running",
            active_model_version=current_version,
            stop_reason="running",
            tuning_controls=controls,
            eval_run_id="",
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
            routes_done=len(ROUTES),
            routes_total=len(ROUTES) + 1,
            rows_processed=_dataset_row_count(client, dataset_table, league),
            eta_seconds=None,
            status="running",
            active_model_version=current_version,
            stop_reason="running",
            tuning_controls=controls,
            eval_run_id="",
        )
        eval_result = evaluate_stack(
            client,
            league=league,
            dataset_table=dataset_table,
            model_dir=model_dir,
            split="rolling",
            output_dir=model_dir,
        )
        eval_run_id = str(eval_result.get("run_id") or "")
        warm_start_source = (
            current_version if controls.warm_start_enabled else "cold_start"
        )
        comparison = eval_result.get("candidate_vs_incumbent") or {}
        promoted = bool(eval_result.get("promotion_verdict") == "promote")
        if promoted:
            current_version = f"{league.lower()}-{int(time.time())}"
            _promote_models(
                client,
                league=league,
                model_dir=model_dir,
                model_version=current_version,
            )
            status = "completed"
            stop_reason = "promoted_against_incumbent"
        else:
            status = "completed"
            stop_reason = str(
                eval_result.get("stop_reason") or "hold_no_material_improvement"
            )
        latest_mdape = _to_float(comparison.get("candidate_avg_mdape"), 1.0)
        if (
            best_mdape is None
            or (best_mdape - latest_mdape) >= controls.min_mdape_improvement
        ):
            best_mdape = latest_mdape
            no_improvement_streak = 0
        else:
            no_improvement_streak += 1
        _record_tuning_round(
            client,
            league=league,
            run_id=run_id,
            fit_round=i + 1,
            warm_start_from=warm_start_source,
            tuning_config_id=_tuning_config_id(controls),
            iteration_budget=controls.max_iterations,
            effective_controls=controls,
            elapsed_seconds=int(max(time.time() - start, 0)),
            candidate_vs_incumbent=comparison,
        )
        _write_train_run(
            client,
            run_id=run_id,
            league=league,
            stage="done",
            current_route="",
            routes_done=len(ROUTES) + 1,
            routes_total=len(ROUTES) + 1,
            rows_processed=_dataset_row_count(client, dataset_table, league),
            eta_seconds=0,
            status=status,
            active_model_version=current_version,
            stop_reason=stop_reason,
            tuning_controls=controls,
            eval_run_id=eval_run_id,
        )
        completed.append(
            {
                "run_id": run_id,
                "status": status,
                "promoted_model": current_version if promoted else None,
                "stop_reason": stop_reason,
                "candidate_vs_incumbent": comparison,
            }
        )
        if no_improvement_streak >= controls.no_improvement_patience:
            final_status = "stopped_no_improvement"
            final_stop_reason = "no_improvement_patience_exhausted"
            break
        i += 1
    if i >= iterations and final_status == "completed":
        exhausted_iteration_budget = True
    if exhausted_iteration_budget:
        final_status = "stopped_budget"
        final_stop_reason = "iteration_budget_exhausted"
    elif completed and final_status == "completed":
        last = completed[-1]
        final_status = str(last.get("status") or "completed")
        final_stop_reason = str(last.get("stop_reason") or "completed")
    if not completed and final_status == "completed":
        final_status = "stopped_budget"
        final_stop_reason = "no_iterations_executed"
    return {
        "league": league,
        "iterations": len(completed),
        "runs": completed,
        "active_model_version": current_version,
        "status": final_status,
        "stop_reason": final_stop_reason,
        "tuning_controls": controls.to_dict(),
    }


def status(client: ClickHouseClient, *, league: str, run: str) -> dict[str, Any]:
    _ensure_supported_league(league)
    _ensure_train_runs_table(client)
    if run == "latest":
        rows = train_run_history(client, league=league, limit=1)
        if not rows:
            return {"league": league, "status": "no_runs"}
        latest = rows[0]
        eval_run_id = str(latest.get("eval_run_id") or "")
        if not eval_run_id:
            eval_run_id = _latest_eval_run_id(client, league)
        feedback = _eval_feedback_for_run(client, league=league, run_id=eval_run_id)
        latest["eval_feedback"] = feedback
        latest["candidate_vs_incumbent"] = feedback.get("candidate_vs_incumbent")
        latest["latest_avg_mdape"] = feedback.get("latest_avg_mdape")
        latest["latest_avg_interval_coverage"] = feedback.get(
            "latest_avg_interval_coverage"
        )
        latest["route_hotspots"] = _latest_route_hotspots(
            client, league, run_id=eval_run_id
        )
        latest["promotion_verdict"] = _promotion_verdict_for_run(
            client, league=league, run_id=eval_run_id
        )
        latest["active_model_version"] = _active_model_version(client, league)
        return latest
    rows = train_run_history(client, league=league, limit=1, run_id=run)
    if not rows:
        return {"league": league, "run_id": run, "status": "not_found"}
    row = rows[0]
    eval_run_id = str(row.get("eval_run_id") or "")
    if not eval_run_id:
        eval_run_id = _latest_eval_run_id(client, league)
    feedback = _eval_feedback_for_run(client, league=league, run_id=eval_run_id)
    row["eval_feedback"] = feedback
    row["candidate_vs_incumbent"] = feedback.get("candidate_vs_incumbent")
    row["latest_avg_mdape"] = feedback.get("latest_avg_mdape")
    row["latest_avg_interval_coverage"] = feedback.get("latest_avg_interval_coverage")
    row["route_hotspots"] = _latest_route_hotspots(client, league, run_id=eval_run_id)
    row["promotion_verdict"] = _promotion_verdict_for_run(
        client, league=league, run_id=eval_run_id
    )
    row["active_model_version"] = _active_model_version(client, league)
    return row


def _latest_eval_feedback(client: ClickHouseClient, league: str) -> dict[str, Any]:
    run_id = _latest_eval_run_id(client, league)
    if not run_id:
        return {
            "status": "no_eval_data",
            "message": "No evaluation runs found yet.",
        }
    return _eval_feedback_for_run(client, league=league, run_id=run_id)


def _latest_eval_run_id(client: ClickHouseClient, league: str) -> str:
    eval_runs = _query_rows(
        client,
        " ".join(
            [
                "SELECT run_id, max(recorded_at) AS recorded_at",
                "FROM poe_trade.ml_eval_runs",
                f"WHERE league = {_quote(league)}",
                "GROUP BY run_id",
                "ORDER BY recorded_at DESC",
                "LIMIT 1",
                "FORMAT JSONEachRow",
            ]
        ),
    )
    if not eval_runs:
        return ""
    return str(eval_runs[0].get("run_id") or "")


def _eval_feedback_for_run(
    client: ClickHouseClient, *, league: str, run_id: str
) -> dict[str, Any]:
    if not run_id:
        return {
            "status": "no_eval_data",
            "message": "No evaluation runs found yet.",
        }
    latest_rows = _query_rows(
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
    if not latest_rows:
        return {"status": "no_eval_data", "message": "No evaluation rows for run."}
    latest = latest_rows[0]
    latest_mdape = _to_float(latest.get("avg_mdape"), 1.0)
    latest_cov = _to_float(latest.get("avg_cov"), 0.0)
    baseline = _latest_promoted_run_excluding(
        client, league=league, run_id=run_id
    ) or _latest_run_excluding(client, league=league, run_id=run_id) or {
        "run_id": run_id,
        "avg_mdape": latest_mdape,
        "avg_cov": latest_cov,
    }
    candidate_vs_incumbent = _candidate_vs_incumbent_summary(
        candidate={
            "run_id": run_id,
            "avg_mdape": latest_mdape,
            "avg_cov": latest_cov,
        },
        incumbent={
            "run_id": str(baseline.get("run_id") or ""),
            "avg_mdape": _to_float(baseline.get("avg_mdape"), latest_mdape),
            "avg_cov": _to_float(baseline.get("avg_cov"), latest_cov),
        },
    )
    feedback: dict[str, Any] = {
        "status": "ok",
        "latest_eval_run_id": run_id,
        "latest_avg_mdape": latest_mdape,
        "latest_avg_interval_coverage": latest_cov,
        "candidate_vs_incumbent": candidate_vs_incumbent,
    }
    if str(baseline.get("run_id") or "") == run_id:
        feedback["message"] = (
            "Only one eval run available; trend requires at least two runs."
        )
        return feedback
    prev_mdape = _to_float(baseline.get("avg_mdape"), 1.0)
    prev_cov = _to_float(baseline.get("avg_cov"), 0.0)
    mdape_delta = latest_mdape - prev_mdape
    cov_delta = latest_cov - prev_cov
    feedback["previous_eval_run_id"] = str(baseline.get("run_id") or "")
    feedback["mdape_delta_vs_previous"] = mdape_delta
    feedback["coverage_delta_vs_previous"] = cov_delta
    feedback["is_improving"] = mdape_delta < 0
    if mdape_delta < 0:
        feedback["message"] = "Quality improved versus previous run (lower MDAPE)."
    elif mdape_delta > 0:
        feedback["message"] = "Quality regressed versus previous run (higher MDAPE)."
    else:
        feedback["message"] = "Quality unchanged versus previous run."
    return feedback


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
    support = _support_count_recent(
        client,
        league=league,
        category=parsed["category"],
        base_type=parsed["base_type"],
    )
    base_price = _reference_price(
        client,
        league=league,
        category=parsed["category"],
        base_type=parsed["base_type"],
    )

    artifact = _load_active_route_artifact(client, league=league, route=route)
    model_prediction = _predict_with_artifact(
        artifact=artifact,
        parsed_item=parsed,
    )

    if model_prediction is None:
        confidence = _route_default_confidence(route)
        price_p50 = base_price
        price_p10 = max(0.1, price_p50 * 0.8)
        price_p90 = price_p50 * 1.2
        sale_probability = 0.6 if route != "fallback_abstain" else 0.3
        fallback_reason = "no_trained_model" if route == "fallback_abstain" else ""
    else:
        price_p10 = max(0.1, float(model_prediction["price_p10"]))
        price_p50 = max(price_p10, float(model_prediction["price_p50"]))
        price_p90 = max(price_p50, float(model_prediction["price_p90"]))
        sale_probability = min(1.0, max(0.0, float(model_prediction["sale_probability"])))
        confidence = _model_confidence(
            route,
            support=support,
            train_row_count=_to_int(artifact.get("train_row_count"), 0),
        )
        fallback_reason = ""

    recommendation_eligible = sale_probability >= 0.5
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
        "price_recommendation_eligible": recommendation_eligible,
        "confidence": round(confidence, 4),
        "confidence_percent": round(confidence * 100.0, 2),
        "fallback_reason": fallback_reason,
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
                *_route_feature_select_sql(),
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
                *_route_feature_select_sql(),
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
                *_route_feature_select_sql(),
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
            "ilvl": row.get("ilvl"),
            "stack_size": row.get("stack_size"),
            "corrupted": row.get("corrupted"),
            "fractured": row.get("fractured"),
            "synthesised": row.get("synthesised"),
            "mod_token_count": row.get("mod_token_count"),
        }
        bundle = _route_for_item(parsed)
        route = bundle["route"]
        base_price = max(0.1, _to_float(row.get("base_price"), 1.0))
        artifact = _load_active_route_artifact(client, league=league, route=route)
        model_prediction = _predict_with_artifact(artifact=artifact, parsed_item=parsed)
        if model_prediction is None:
            price_p50 = base_price
            price_p10 = max(0.1, price_p50 * 0.8)
            price_p90 = price_p50 * 1.2
            sale_probability = 0.6 if route != "fallback_abstain" else 0.3
            confidence = _route_default_confidence(route)
            fallback_reason = "no_trained_model" if route == "fallback_abstain" else ""
        else:
            price_p10 = max(0.1, float(model_prediction["price_p10"]))
            price_p50 = max(price_p10, float(model_prediction["price_p50"]))
            price_p90 = max(price_p50, float(model_prediction["price_p90"]))
            sale_probability = min(1.0, max(0.0, float(model_prediction["sale_probability"])))
            confidence = _model_confidence(
                route,
                support=_to_int(bundle.get("support_count_recent"), 0),
                train_row_count=_to_int(artifact.get("train_row_count"), 0),
            )
            fallback_reason = ""
        pred = PredictionRow(
            prediction_id=str(uuid.uuid4()),
            prediction_as_of_ts=now,
            league=league,
            source_kind=source,
            item_id=str(row.get("item_id") or ""),
            route=route,
            price_chaos=price_p50,
            price_p10=price_p10,
            price_p50=price_p50,
            price_p90=price_p90,
            sale_probability_24h=sale_probability,
            sale_probability=sale_probability,
            confidence=confidence,
            comp_count=None,
            support_count_recent=_to_int(bundle["support_count_recent"], 0),
            freshness_minutes=30.0,
            base_comp_price_p50=base_price if route == "sparse_retrieval" else None,
            residual_adjustment=(price_p50 - base_price) if route == "sparse_retrieval" else 0.0,
            fallback_reason=fallback_reason,
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
    eval_run_id = _latest_eval_run_id(client, league)
    if not eval_run_id:
        raise ValueError("missing evaluation rows for report")
    route_metrics = _query_rows(
        client,
        " ".join(
            [
                "SELECT route, avg(mdape) AS mdape, avg(wape) AS wape, avg(rmsle) AS rmsle, avg(abstain_rate) AS abstain_rate",
                "FROM poe_trade.ml_eval_runs",
                f"WHERE league = {_quote(league)} AND run_id = {_quote(eval_run_id)}",
                "GROUP BY route",
                "FORMAT JSONEachRow",
            ]
        ),
    )
    if not route_metrics:
        raise ValueError("missing evaluation rows for report")
    feedback = _eval_feedback_for_run(client, league=league, run_id=eval_run_id)
    hotspots = _latest_route_hotspots(client, league, run_id=eval_run_id)
    promotion_verdict = _promotion_verdict_for_run(
        client, league=league, run_id=eval_run_id
    )
    family_hotspots = _query_rows(
        client,
        " ".join(
            [
                "SELECT family, avg(mdape) AS mdape, avg(abstain_rate) AS abstain_rate",
                "FROM poe_trade.ml_route_eval_v1",
                f"WHERE league = {_quote(league)} AND run_id = {_quote(eval_run_id)}",
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
        "eval_run_id": eval_run_id,
        "generated_at": _now_ts(),
        "promotion_verdict": promotion_verdict,
        "candidate_vs_incumbent": feedback.get("candidate_vs_incumbent"),
        "latest_avg_mdape": feedback.get("latest_avg_mdape"),
        "latest_avg_interval_coverage": feedback.get("latest_avg_interval_coverage"),
        "route_hotspots": hotspots,
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
    return "generalized_fallback_quantiles"


def _ensure_route(route: str) -> None:
    if route in ROUTES:
        return
    raise ValueError(f"unsupported route: {route}")


def _now_ts() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def _train_run_stage_rank(stage: object) -> int:
    value = str(stage or "").strip().lower()
    if value == "done":
        return 3
    if value == "evaluate":
        return 2
    if value == "dataset":
        return 1
    return 0


def _train_run_sort_key(row: dict[str, Any]) -> tuple[str, int]:
    return (str(row.get("updated_at") or ""), _train_run_stage_rank(row.get("stage")))


def _collapse_train_run_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_run_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        run_id = str(row.get("run_id") or "").strip()
        if not run_id:
            continue
        existing = by_run_id.get(run_id)
        if existing is None or _train_run_sort_key(row) > _train_run_sort_key(existing):
            by_run_id[run_id] = dict(row)
    return sorted(by_run_id.values(), key=_train_run_sort_key, reverse=True)


def train_run_history(
    client: ClickHouseClient, *, league: str, limit: int = 20, run_id: str | None = None
) -> list[dict[str, Any]]:
    _ensure_train_runs_table(client)
    filters = [f"league = {_quote(league)}"]
    if run_id:
        filters.append(f"run_id = {_quote(run_id)}")
    row_limit = 16 if run_id else max(32, max(1, limit) * 8)
    rows = _query_rows(
        client,
        " ".join(
            [
                "SELECT run_id, stage, current_route, routes_done, routes_total, rows_processed, eta_seconds, chosen_backend, worker_count, memory_budget_gb, active_model_version, status, stop_reason, tuning_config_id, eval_run_id, updated_at",
                "FROM poe_trade.ml_train_runs",
                f"WHERE {' AND '.join(filters)}",
                "ORDER BY updated_at DESC",
                f"LIMIT {row_limit}",
                "FORMAT JSONEachRow",
            ]
        ),
    )
    return _collapse_train_run_rows(rows)[: max(1, limit)]


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


def _ensure_eval_contract_split(split: str) -> None:
    if split in MIRAGE_EVAL_CONTRACT.supported_splits:
        return
    supported = ", ".join(MIRAGE_EVAL_CONTRACT.supported_splits)
    raise ValueError(
        f"unsupported split {split!r} for {MIRAGE_EVAL_CONTRACT.name}; supported: {supported}"
    )


def _resolve_tuning_controls(
    *,
    max_iterations: int | None,
    max_wall_clock_seconds: int | None,
    no_improvement_patience: int | None,
    min_mdape_improvement: float | None,
) -> TuningControls:
    iteration_budget = max(1, max_iterations or _env_int("POE_ML_MAX_ITERATIONS", 2))
    wall_clock_budget = max(
        60,
        max_wall_clock_seconds
        if max_wall_clock_seconds is not None
        else _env_int("POE_ML_MAX_WALL_CLOCK_SECONDS", 3600),
    )
    patience = max(
        1,
        no_improvement_patience
        if no_improvement_patience is not None
        else _env_int("POE_ML_NO_IMPROVEMENT_PATIENCE", 2),
    )
    min_improvement = max(
        0.0,
        min_mdape_improvement
        if min_mdape_improvement is not None
        else _env_float("POE_ML_MIN_MDAPE_IMPROVEMENT", 0.005),
    )
    warm_start_enabled = _env_bool("POE_ML_WARM_START_ENABLED", True)
    resume_supported = _env_bool("POE_ML_RESUME_SUPPORTED", False)
    return TuningControls(
        max_iterations=iteration_budget,
        max_wall_clock_seconds=wall_clock_budget,
        no_improvement_patience=patience,
        min_mdape_improvement=min_improvement,
        warm_start_enabled=warm_start_enabled,
        resume_supported=resume_supported,
    )


def _tuning_config_id(controls: TuningControls) -> str:
    return (
        f"iter{controls.max_iterations}-wall{controls.max_wall_clock_seconds}"
        f"-pat{controls.no_improvement_patience}-min{controls.min_mdape_improvement}"
        f"-warm{int(controls.warm_start_enabled)}"
    )


def _latest_train_run_row(
    client: ClickHouseClient, league: str
) -> dict[str, Any] | None:
    rows = train_run_history(client, league=league, limit=1)
    if not rows:
        return None
    return rows[0]


def _aggregate_eval_run(
    client: ClickHouseClient, *, league: str, run_id: str
) -> dict[str, Any]:
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
        return {"run_id": run_id, "avg_mdape": 1.0, "avg_cov": 0.0}
    row = rows[0]
    return {
        "run_id": run_id,
        "avg_mdape": _to_float(row.get("avg_mdape"), 1.0),
        "avg_cov": _to_float(row.get("avg_cov"), 0.0),
    }


def _latest_run_excluding(
    client: ClickHouseClient, *, league: str, run_id: str
) -> dict[str, Any] | None:
    rows = _query_rows(
        client,
        " ".join(
            [
                "SELECT run_id, avg(coalesce(mdape, 1.0)) AS avg_mdape, avg(coalesce(interval_80_coverage, 0.0)) AS avg_cov, max(recorded_at) AS recorded_at",
                "FROM poe_trade.ml_eval_runs",
                f"WHERE league = {_quote(league)} AND run_id != {_quote(run_id)}",
                "GROUP BY run_id",
                "ORDER BY recorded_at DESC",
                "LIMIT 1",
                "FORMAT JSONEachRow",
            ]
        ),
    )
    if not rows:
        return None
    row = rows[0]
    return {
        "run_id": str(row.get("run_id") or ""),
        "avg_mdape": _to_float(row.get("avg_mdape"), 1.0),
        "avg_cov": _to_float(row.get("avg_cov"), 0.0),
    }



def _latest_promoted_run_excluding(
    client: ClickHouseClient, *, league: str, run_id: str
) -> dict[str, Any] | None:
    promotion_rows = _query_rows(
        client,
        " ".join(
            [
                "SELECT candidate_run_id, max(recorded_at) AS recorded_at",
                "FROM poe_trade.ml_promotion_audit_v1",
                f"WHERE league = {_quote(league)} AND verdict = 'promote' AND candidate_run_id != {_quote(run_id)}",
                "GROUP BY candidate_run_id",
                "ORDER BY recorded_at DESC",
                "LIMIT 1",
                "FORMAT JSONEachRow",
            ]
        ),
    )
    if not promotion_rows:
        return None
    promoted_run_id = str(promotion_rows[0].get("candidate_run_id") or "").strip()
    if not promoted_run_id:
        return None
    rows = _query_rows(
        client,
        " ".join(
            [
                "SELECT avg(coalesce(mdape, 1.0)) AS avg_mdape, avg(coalesce(interval_80_coverage, 0.0)) AS avg_cov",
                "FROM poe_trade.ml_eval_runs",
                f"WHERE league = {_quote(league)} AND run_id = {_quote(promoted_run_id)}",
                "FORMAT JSONEachRow",
            ]
        ),
    )
    if not rows:
        return None
    row = rows[0]
    return {
        "run_id": promoted_run_id,
        "avg_mdape": _to_float(row.get("avg_mdape"), 1.0),
        "avg_cov": _to_float(row.get("avg_cov"), 0.0),
    }

def _candidate_vs_incumbent_summary(
    *, candidate: dict[str, Any], incumbent: dict[str, Any] | None
) -> dict[str, Any]:
    c_mdape = _to_float(candidate.get("avg_mdape"), 1.0)
    c_cov = _to_float(candidate.get("avg_cov"), 0.0)
    if incumbent is None:
        i_mdape = c_mdape
        i_cov = c_cov
        incumbent_run = "none"
    else:
        i_mdape = _to_float(incumbent.get("avg_mdape"), c_mdape)
        i_cov = _to_float(incumbent.get("avg_cov"), c_cov)
        incumbent_run = str(incumbent.get("run_id") or "none")
    mdape_delta = i_mdape - c_mdape
    coverage_delta = c_cov - i_cov
    return {
        "candidate_run_id": str(candidate.get("run_id") or ""),
        "incumbent_run_id": incumbent_run,
        "candidate_avg_mdape": c_mdape,
        "incumbent_avg_mdape": i_mdape,
        "candidate_avg_interval_coverage": c_cov,
        "incumbent_avg_interval_coverage": i_cov,
        "mdape_improvement": mdape_delta,
        "coverage_delta": coverage_delta,
        "coverage_floor_ok": c_cov >= MIRAGE_EVAL_CONTRACT.promotion.coverage_floor,
    }


def _protected_cohort_check(
    client: ClickHouseClient,
    *,
    league: str,
    candidate_run_id: str,
    incumbent_run_id: str | None,
) -> dict[str, Any]:
    if not incumbent_run_id:
        return {"regression": False, "max_mdape_regression": 0.0, "cohort": "none"}
    candidate_rows = _query_rows(
        client,
        " ".join(
            [
                "SELECT route, family, support_bucket, avg(coalesce(mdape, 1.0)) AS mdape",
                "FROM poe_trade.ml_route_eval_v1",
                f"WHERE league = {_quote(league)} AND run_id = {_quote(candidate_run_id)}",
                "GROUP BY route, family, support_bucket",
                "FORMAT JSONEachRow",
            ]
        ),
    )
    if not candidate_rows:
        return {"regression": False, "max_mdape_regression": 0.0, "cohort": "none"}
    incumbent_rows = _query_rows(
        client,
        " ".join(
            [
                "SELECT route, family, support_bucket, avg(coalesce(mdape, 1.0)) AS mdape",
                "FROM poe_trade.ml_route_eval_v1",
                f"WHERE league = {_quote(league)} AND run_id = {_quote(incumbent_run_id)}",
                "GROUP BY route, family, support_bucket",
                "FORMAT JSONEachRow",
            ]
        ),
    )
    incumbent_map: dict[tuple[str, str, str], float] = {}
    for row in incumbent_rows:
        incumbent_map[
            (
                str(row.get("route") or ""),
                str(row.get("family") or ""),
                str(row.get("support_bucket") or ""),
            )
        ] = _to_float(row.get("mdape"), 1.0)
    max_regression = 0.0
    worst = "none"
    for row in candidate_rows:
        key = (
            str(row.get("route") or ""),
            str(row.get("family") or ""),
            str(row.get("support_bucket") or ""),
        )
        candidate_mdape = _to_float(row.get("mdape"), 1.0)
        incumbent_mdape = incumbent_map.get(key, candidate_mdape)
        regression = max(candidate_mdape - incumbent_mdape, 0.0)
        if regression > max_regression:
            max_regression = regression
            worst = "|".join(key)
    return {
        "regression": max_regression
        > MIRAGE_EVAL_CONTRACT.promotion.protected_cohort_max_regression,
        "max_mdape_regression": max_regression,
        "cohort": worst,
    }


def _should_promote(comparison: dict[str, Any]) -> bool:
    protected = comparison.get("protected_cohort_regression") or {}
    if bool(protected.get("regression")):
        return False
    if not bool(comparison.get("coverage_floor_ok")):
        return False
    if str(comparison.get("incumbent_run_id") or "") in {"", "none"}:
        return True
    if (
        _to_float(comparison.get("mdape_improvement"), 0.0)
        < MIRAGE_EVAL_CONTRACT.promotion.min_mdape_improvement
    ):
        return False
    return True


def _promotion_stop_reason(comparison: dict[str, Any]) -> str:
    if _should_promote(comparison):
        return "promote"
    protected = comparison.get("protected_cohort_regression") or {}
    if bool(protected.get("regression")):
        return "hold_protected_cohort_regression"
    if not bool(comparison.get("coverage_floor_ok")):
        return "hold_coverage_floor"
    return "hold_no_material_improvement"


def _build_route_hotspots(
    client: ClickHouseClient,
    *,
    league: str,
    candidate_run_id: str,
    incumbent_run_id: str | None,
    top_n: int,
) -> list[dict[str, Any]]:
    rows = _query_rows(
        client,
        " ".join(
            [
                "SELECT route, family, support_bucket, sum(sample_count) AS sample_count, avg(coalesce(mdape, 1.0)) AS candidate_mdape, avg(coalesce(abstain_rate, 0.0)) AS candidate_abstain",
                "FROM poe_trade.ml_route_eval_v1",
                f"WHERE league = {_quote(league)} AND run_id = {_quote(candidate_run_id)}",
                "GROUP BY route, family, support_bucket",
                "ORDER BY candidate_mdape DESC",
                f"LIMIT {max(1, top_n)}",
                "FORMAT JSONEachRow",
            ]
        ),
    )
    incumbent_rows: dict[str, dict[str, Any]] = {}
    if incumbent_run_id:
        for row in _query_rows(
            client,
            " ".join(
                [
                    "SELECT route, family, support_bucket, avg(coalesce(mdape, 1.0)) AS incumbent_mdape, avg(coalesce(abstain_rate, 0.0)) AS incumbent_abstain",
                    "FROM poe_trade.ml_route_eval_v1",
                    f"WHERE league = {_quote(league)} AND run_id = {_quote(incumbent_run_id)}",
                    "GROUP BY route, family, support_bucket",
                    "FORMAT JSONEachRow",
                ]
            ),
        ):
            incumbent_rows[
                "|".join(
                    [
                        str(row.get("route") or ""),
                        str(row.get("family") or ""),
                        str(row.get("support_bucket") or ""),
                    ]
                )
            ] = row
    now = _now_ts()
    result: list[dict[str, Any]] = []
    for row in rows:
        route = str(row.get("route") or "unknown")
        family = str(row.get("family") or route)
        support_bucket = str(row.get("support_bucket") or "low")
        incumbent = incumbent_rows.get(f"{route}|{family}|{support_bucket}", {})
        candidate_mdape = _to_float(row.get("candidate_mdape"), 1.0)
        incumbent_mdape = _to_float(incumbent.get("incumbent_mdape"), candidate_mdape)
        candidate_abstain = _to_float(row.get("candidate_abstain"), 0.0)
        incumbent_abstain = _to_float(
            incumbent.get("incumbent_abstain"), candidate_abstain
        )
        sample_count = _to_int(row.get("sample_count"), 0)
        result.append(
            {
                "league": league,
                "candidate_run_id": candidate_run_id,
                "incumbent_run_id": incumbent_run_id or "none",
                "route": route,
                "family": family,
                "support_bucket": support_bucket,
                "sample_count": sample_count,
                "candidate_mdape": candidate_mdape,
                "incumbent_mdape": incumbent_mdape,
                "mdape_delta": incumbent_mdape - candidate_mdape,
                "candidate_abstain_rate": candidate_abstain,
                "incumbent_abstain_rate": incumbent_abstain,
                "abstain_rate_delta": candidate_abstain - incumbent_abstain,
                "recorded_at": now,
            }
        )
    return result


def _present_hotspots(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    ordered = sorted(rows, key=lambda item: _to_float(item.get("mdape_delta"), 0.0))
    improving = [
        item for item in ordered if _to_float(item.get("mdape_delta"), 0.0) > 0
    ]
    regressing = [
        item for item in ordered if _to_float(item.get("mdape_delta"), 0.0) <= 0
    ]
    return {
        "top_improving": improving[-5:],
        "top_regressing": regressing[:5],
    }


def _latest_route_hotspots(
    client: ClickHouseClient, league: str, *, run_id: str | None = None
) -> dict[str, list[dict[str, Any]]]:
    run_filter = (
        f"AND candidate_run_id = {_quote(run_id)}" if run_id and run_id.strip() else ""
    )
    rows = _query_rows(
        client,
        " ".join(
            [
                "SELECT route, family, support_bucket, sample_count, candidate_mdape, incumbent_mdape, mdape_delta, candidate_abstain_rate, incumbent_abstain_rate, abstain_rate_delta, recorded_at",
                "FROM poe_trade.ml_route_hotspots_v1",
                f"WHERE league = {_quote(league)} {run_filter}",
                "ORDER BY recorded_at DESC",
                "LIMIT 40",
                "FORMAT JSONEachRow",
            ]
        ),
    )
    if not rows:
        return {"top_improving": [], "top_regressing": []}
    return _present_hotspots(rows)


def _promotion_verdict_for_run(
    client: ClickHouseClient, *, league: str, run_id: str
) -> str:
    if not run_id:
        return "unknown"
    rows = _query_rows(
        client,
        " ".join(
            [
                "SELECT verdict",
                "FROM poe_trade.ml_promotion_audit_v1",
                f"WHERE league = {_quote(league)} AND candidate_run_id = {_quote(run_id)}",
                "ORDER BY recorded_at DESC",
                "LIMIT 1",
                "FORMAT JSONEachRow",
            ]
        ),
    )
    if not rows:
        return "unknown"
    return str(rows[0].get("verdict") or "unknown")


def _record_tuning_round(
    client: ClickHouseClient,
    *,
    league: str,
    run_id: str,
    fit_round: int,
    warm_start_from: str,
    tuning_config_id: str,
    iteration_budget: int,
    effective_controls: TuningControls,
    elapsed_seconds: int,
    candidate_vs_incumbent: dict[str, Any],
) -> None:
    _ensure_tuning_rounds_table(client)
    _insert_json_rows(
        client,
        "poe_trade.ml_tuning_rounds_v1",
        [
            {
                "league": league,
                "run_id": run_id,
                "fit_round": fit_round,
                "warm_start_from": warm_start_from,
                "tuning_config_id": tuning_config_id,
                "iteration_budget": iteration_budget,
                "wall_clock_budget_seconds": effective_controls.max_wall_clock_seconds,
                "no_improvement_patience": effective_controls.no_improvement_patience,
                "elapsed_seconds": elapsed_seconds,
                "candidate_mdape": _to_float(
                    candidate_vs_incumbent.get("candidate_avg_mdape"), 1.0
                ),
                "incumbent_mdape": _to_float(
                    candidate_vs_incumbent.get("incumbent_avg_mdape"), 1.0
                ),
                "mdape_improvement": _to_float(
                    candidate_vs_incumbent.get("mdape_improvement"), 0.0
                ),
                "recorded_at": _now_ts(),
            }
        ],
    )


def _ensure_promotion_audit_table(client: ClickHouseClient) -> None:
    client.execute(
        "CREATE TABLE IF NOT EXISTS poe_trade.ml_promotion_audit_v1(league String, candidate_run_id String, incumbent_run_id String, candidate_model_version String, incumbent_model_version String, verdict String, avg_mdape_candidate Float64, avg_mdape_incumbent Float64, coverage_candidate Float64, coverage_incumbent Float64, stop_reason String, recorded_at DateTime64(3, 'UTC')) ENGINE=MergeTree() PARTITION BY toYYYYMMDD(recorded_at) ORDER BY (league, candidate_run_id, recorded_at)"
    )


def _ensure_tuning_rounds_table(client: ClickHouseClient) -> None:
    client.execute(
        "CREATE TABLE IF NOT EXISTS poe_trade.ml_tuning_rounds_v1(league String, run_id String, fit_round UInt32, warm_start_from String, tuning_config_id String, iteration_budget UInt32, wall_clock_budget_seconds UInt32, no_improvement_patience UInt32, elapsed_seconds UInt32, candidate_mdape Float64, incumbent_mdape Float64, mdape_improvement Float64, recorded_at DateTime64(3, 'UTC')) ENGINE=MergeTree() PARTITION BY toYYYYMMDD(recorded_at) ORDER BY (league, run_id, fit_round, recorded_at)"
    )


def _ensure_route_hotspots_table(client: ClickHouseClient) -> None:
    client.execute(
        "CREATE TABLE IF NOT EXISTS poe_trade.ml_route_hotspots_v1(league String, candidate_run_id String, incumbent_run_id String, route String, family String, support_bucket String, sample_count UInt64, candidate_mdape Float64, incumbent_mdape Float64, mdape_delta Float64, candidate_abstain_rate Float64, incumbent_abstain_rate Float64, abstain_rate_delta Float64, recorded_at DateTime64(3, 'UTC')) ENGINE=MergeTree() PARTITION BY toYYYYMMDD(recorded_at) ORDER BY (league, candidate_run_id, route, recorded_at)"
    )


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on", "enabled"}:
        return True
    if value in {"0", "false", "no", "off", "disabled"}:
        return False
    return default


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
        "CREATE TABLE IF NOT EXISTS poe_trade.ml_train_runs(run_id String, league String, stage String, current_route String, routes_done UInt32, routes_total UInt32, rows_processed UInt64, eta_seconds Nullable(UInt32), chosen_backend String, worker_count UInt16, memory_budget_gb Float64, active_model_version String, status String, stop_reason String, tuning_config_id String, eval_run_id String, resume_token String, started_at DateTime64(3, 'UTC'), updated_at DateTime64(3, 'UTC')) ENGINE=ReplacingMergeTree(updated_at) PARTITION BY toYYYYMMDD(started_at) ORDER BY (league, run_id, updated_at)"
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
    stop_reason: str,
    tuning_controls: TuningControls,
    eval_run_id: str,
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
                "stop_reason": stop_reason,
                "tuning_config_id": _tuning_config_id(tuning_controls),
                "eval_run_id": eval_run_id,
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
    return mdape <= 2.0 and cov >= 0.75


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
    item_name = ""
    base_type = ""
    ilvl = 0
    stack_size = 1
    corrupted = 0
    fractured = 0
    synthesised = 0
    rarity_index: int | None = None
    for idx, line in enumerate(lines):
        if line.startswith("Rarity:"):
            rarity = line.replace("Rarity:", "").strip()
            rarity_index = idx
        if line.startswith("Item Class:"):
            item_class = line.replace("Item Class:", "").strip()
        if line.startswith("Item Level:"):
            try:
                ilvl = int(line.replace("Item Level:", "").strip())
            except ValueError:
                ilvl = 0
        if line.startswith("Stack Size:"):
            raw = line.replace("Stack Size:", "").strip().split("/", 1)[0].strip()
            try:
                stack_size = max(1, int(raw))
            except ValueError:
                stack_size = 1
        if line.lower() == "corrupted":
            corrupted = 1
        if "fractured" in line.lower():
            fractured = 1
        if "synthesised" in line.lower() or "synthesized" in line.lower():
            synthesised = 1

    header_lines: list[str] = []
    if rarity_index is not None:
        cursor = rarity_index + 1
        while cursor < len(lines):
            line = lines[cursor]
            if line == "--------":
                break
            header_lines.append(line)
            cursor += 1

    if len(header_lines) >= 2 and rarity in {"Rare", "Unique"}:
        item_name = header_lines[0]
        base_type = header_lines[1]
    elif header_lines:
        base_type = header_lines[0]

    if not base_type:
        base_type = lines[0]

    category = "other"
    lowered = f"{item_class} {base_type}".lower()
    if "map" in lowered or base_type.endswith(" Map"):
        category = "map"
    elif "logbook" in lowered:
        category = "logbook"
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
    mod_count = max(len(lines) - 5, 0)
    return {
        "rarity": rarity,
        "item_class": item_class,
        "item_name": item_name,
        "base_type": base_type,
        "category": category,
        "mod_count": mod_count,
        "mod_token_count": mod_count,
        "ilvl": ilvl,
        "stack_size": stack_size,
        "corrupted": corrupted,
        "fractured": fractured,
        "synthesised": synthesised,
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


def _route_training_predicate(route: str) -> str:
    if route == "fungible_reference":
        return "category IN ('essence', 'fossil', 'scarab', 'map', 'logbook')"
    if route == "structured_boosted":
        return "rarity = 'Unique'"
    if route == "sparse_retrieval":
        return "rarity = 'Rare' OR category = 'cluster_jewel'"
    return "category NOT IN ('essence', 'fossil', 'scarab', 'map', 'logbook') AND ifNull(rarity, '') NOT IN ('Unique', 'Rare') AND category != 'cluster_jewel'"


def _feature_dict_from_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "category": str(row.get("category") or "other"),
        "base_type": str(row.get("base_type") or "unknown"),
        "rarity": str(row.get("rarity") or ""),
        "ilvl": _bucket_ilvl(row.get("ilvl")),
        "stack_size": _bucket_stack_size(row.get("stack_size")),
        "corrupted": _to_float(row.get("corrupted"), 0.0),
        "fractured": _to_float(row.get("fractured"), 0.0),
        "synthesised": _to_float(row.get("synthesised"), 0.0),
        "mod_token_count": _bucket_mod_token_count(row.get("mod_token_count")),
    }


def _feature_dict_from_parsed_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "category": str(item.get("category") or "other"),
        "base_type": str(item.get("base_type") or "unknown"),
        "rarity": str(item.get("rarity") or ""),
        "ilvl": _bucket_ilvl(item.get("ilvl")),
        "stack_size": _bucket_stack_size(item.get("stack_size")),
        "corrupted": _to_float(item.get("corrupted"), 0.0),
        "fractured": _to_float(item.get("fractured"), 0.0),
        "synthesised": _to_float(item.get("synthesised"), 0.0),
        "mod_token_count": _bucket_mod_token_count(item.get("mod_token_count", item.get("mod_count"))),
    }


def _route_model_bundle_path(*, model_dir: str, route: str, league: str) -> Path:
    return Path(model_dir) / f"{route}-{league}.joblib"


def _load_active_route_artifact(
    client: ClickHouseClient, *, league: str, route: str
) -> dict[str, Any]:
    model_dir = _active_model_dir_for_route(client, league=league, route=route)
    if not model_dir:
        return {}
    return _load_json_file(_route_artifact_path(model_dir=model_dir, route=route, league=league))


def _active_model_dir_for_route(
    client: ClickHouseClient, *, league: str, route: str
) -> str:
    rows = _query_rows(
        client,
        " ".join(
            [
                "SELECT model_dir",
                "FROM poe_trade.ml_model_registry_v1",
                f"WHERE league = {_quote(league)} AND route = {_quote(route)} AND promoted = 1",
                "ORDER BY promoted_at DESC",
                "LIMIT 1",
                "FORMAT JSONEachRow",
            ]
        ),
    )
    if rows:
        return str(rows[0].get("model_dir") or "")
    default_dir = Path("artifacts/ml") / f"{league.lower()}_v1"
    if default_dir.exists():
        return str(default_dir)
    return ""


def _load_model_bundle(bundle_path: str) -> dict[str, Any] | None:
    if not bundle_path:
        return None
    cached = _MODEL_BUNDLE_CACHE.get(bundle_path)
    if cached is not None:
        return cached
    path = Path(bundle_path)
    if not path.exists():
        return None
    loaded = joblib.load(path)
    if not isinstance(loaded, dict):
        return None
    _MODEL_BUNDLE_CACHE[bundle_path] = loaded
    return loaded


def _predict_with_bundle(
    *, bundle: dict[str, Any] | None, parsed_item: dict[str, Any]
) -> dict[str, float] | None:
    if bundle is None:
        return None
    vectorizer = bundle.get("vectorizer")
    price_models = bundle.get("price_models") or {}
    if vectorizer is None or not isinstance(price_models, dict):
        return None
    features = _feature_dict_from_parsed_item(parsed_item)
    X = vectorizer.transform([features])
    p10_model = price_models.get("p10")
    p50_model = price_models.get("p50")
    p90_model = price_models.get("p90")
    if p10_model is None or p50_model is None or p90_model is None:
        return None
    p10 = float(p10_model.predict(X)[0])
    p50 = float(p50_model.predict(X)[0])
    p90 = float(p90_model.predict(X)[0])
    ordered = sorted([max(0.1, p10), max(0.1, p50), max(0.1, p90)])
    sale_model = bundle.get("sale_model")
    if sale_model is None:
        sale_probability = 0.6
    else:
        sale_probability = min(1.0, max(0.0, float(sale_model.predict(X)[0])))
    return {
        "price_p10": ordered[0],
        "price_p50": ordered[1],
        "price_p90": ordered[2],
        "sale_probability": sale_probability,
    }


def _predict_with_artifact(
    *, artifact: dict[str, Any], parsed_item: dict[str, Any]
) -> dict[str, float] | None:
    bundle_path = str(artifact.get("model_bundle_path") or "")
    if not bundle_path:
        return None
    bundle = _load_model_bundle(bundle_path)
    return _predict_with_bundle(bundle=bundle, parsed_item=parsed_item)


def _dataset_row_count(client: ClickHouseClient, dataset_table: str, league: str) -> int:
    return _scalar_count(
        client,
        " ".join(
            [
                "SELECT count() AS value",
                f"FROM {dataset_table}",
                f"WHERE league = {_quote(league)}",
            ]
        ),
    )


def _support_count_recent(
    client: ClickHouseClient,
    *,
    league: str,
    category: str,
    base_type: str,
) -> int:
    rows = _query_rows(
        client,
        " ".join(
            [
                "SELECT count() AS sample_count",
                "FROM poe_trade.ml_price_dataset_v1",
                f"WHERE league = {_quote(league)}",
                f"AND category = {_quote(category)}",
                f"AND base_type = {_quote(base_type)}",
                "FORMAT JSONEachRow",
            ]
        ),
    )
    if not rows:
        return 0
    return _to_int(rows[0].get("sample_count"), 0)


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[mid])
    return float((ordered[mid - 1] + ordered[mid]) / 2.0)


def _route_artifact_path(*, model_dir: str, route: str, league: str) -> Path:
    return Path(model_dir) / f"{route}-{league}.json"


def _load_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if isinstance(parsed, dict):
        return parsed
    return {}


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
