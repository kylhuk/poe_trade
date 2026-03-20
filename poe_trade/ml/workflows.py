from __future__ import annotations

import json
import hashlib
import logging
import math
import os
import re
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any

import joblib
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.feature_extraction import DictVectorizer

from poe_trade.db import ClickHouseClient
from poe_trade.db.clickhouse import ClickHouseClientError
from poe_trade.db.migrations import MigrationRunner
from poe_trade.ingestion.poeninja_snapshot import PoeNinjaClient

from .audit import VALIDATED_LEAGUES
from .contract import MIRAGE_EVAL_CONTRACT, TARGET_CONTRACT

logger = logging.getLogger(__name__)


def _clickhouse_datetime(dt: datetime) -> str:
    normalized = dt.astimezone(UTC)
    return normalized.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


ROUTES = (
    "fungible_reference",
    "structured_boosted",
    "structured_boosted_other",
    "sparse_retrieval",
    "cluster_jewel_retrieval",
    "fallback_abstain",
)

PROTECTED_COHORT_DIMENSIONS = (
    "route",
    "family",
    "support_bucket",
)

PROTECTED_COHORT_MIN_SUPPORT_COUNT = 50

PROTECTED_COHORT_ELIGIBLE_SUPPORT_BUCKETS = (
    "medium",
    "high",
)

PROMOTION_LEAKAGE_REASON_CODE = "hold_integrity_leakage_overlap"
PROMOTION_FRESHNESS_REASON_CODE = "hold_integrity_stale_source_watermarks"
PROMOTION_SHADOW_SLICE_MISMATCH_REASON_CODE = "hold_shadow_slice_mismatch"
PROMOTION_SHADOW_MISSING_INCUMBENT_REASON_CODE = "hold_shadow_missing_incumbent"
PROMOTION_SHADOW_MDAPE_REASON_CODE = "hold_no_material_improvement"
PROMOTION_SHADOW_MIN_RELATIVE_MDAPE_IMPROVEMENT = 0.20
PROMOTION_PROTECTED_COHORT_MAX_REGRESSION = 0.0
PROMOTION_FRESHNESS_MAX_LAG_MINUTES = 180.0
PROMOTION_FRESHNESS_WATERMARK_KEYS = (
    "dataset_max_as_of_ts",
    "poeninja_max_sample_time_utc",
    "price_labels_max_updated_at",
)

BASE_FEATURE_FIELDS = (
    "category",
    "base_type",
    "family_scope",
    "family_scope_is_other",
    "rarity",
    "ilvl",
    "stack_size",
    "corrupted",
    "fractured",
    "synthesised",
    "unique_state_pair_count",
    "unique_state_all_three_flag",
    "unique_state_corrupted_fractured",
    "unique_state_corrupted_synthesised",
    "unique_state_fractured_synthesised",
    "map_family_flag",
    "map_blighted_flag",
    "map_blight_ravaged_flag",
    "map_elder_guardian_flag",
    "map_shaper_guardian_flag",
    "map_t17_flag",
    "text_has_delirium_flag",
    "text_has_influence_flag",
    "text_has_parentheses_flag",
    "text_has_hyphen_flag",
    "mod_token_count",
    "base_type_price_tier",
    "category_price_tier",
)

_MODEL_BUNDLE_CACHE: dict[str, dict[str, Any]] = {}
_ACTIVE_ROUTE_MODEL_DIRS: dict[tuple[str, str], str] = {}
_ACTIVE_ROUTE_MODEL_META: dict[tuple[str, str], dict[str, Any]] = {}
_ACTIVE_MODEL_VERSION_HINT: dict[str, str] = {}
_SERVING_PROFILE_CACHE: dict[tuple[str, str, str], dict[str, Any]] = {}
_SERVING_PROFILE_SNAPSHOT_META: dict[str, dict[str, str]] = {}
_WARMUP_STATE: dict[str, "WarmupState"] = {}
_WARMUP_LOCK = Lock()
_ACTIVE_MODEL_CACHE_LOCK = Lock()
_SERVING_PROFILE_CACHE_LOCK = Lock()
_ROLLOUT_CONTROL_LOCK = Lock()
_ROLLOUT_CONTROLS: dict[str, dict[str, Any]] = {}

_ACTIVE_MODEL_CACHE_MAX_AGE_SECONDS = 30.0
_SERVING_PROFILE_CACHE_MAX_AGE_SECONDS = 30.0


@dataclass(frozen=True)
class WarmupState:
    last_attempt: str | None
    routes: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {"lastAttemptAt": self.last_attempt, "routes": dict(self.routes)}


_DEFAULT_SERVING_PROFILE_TABLE = "poe_trade.ml_serving_profile_v1"
_DEFAULT_DATASET_TABLE = "poe_trade.ml_price_dataset_v2"
_LEGACY_DATASET_TABLE = "poe_trade.ml_price_dataset_v1"
_DEFAULT_LABELS_TABLE = "poe_trade.ml_price_labels_v2"
_LEGACY_LABELS_TABLE = "poe_trade.ml_price_labels_v1"

_MOD_FEATURES_CACHE_PATH = Path("/tmp/mod_features_cache.json")

_MOD_FEATURE_BATCH_SIZE = 5000

_MOD_FEATURE_RULES: tuple[tuple[str, tuple[str, ...], float, float], ...] = (
    ("Strength", ("to strength",), 6.0, 60.0),
    ("Dexterity", ("to dexterity",), 6.0, 60.0),
    ("Intelligence", ("to intelligence",), 6.0, 60.0),
    ("MaximumLife", ("maximum life", "to life"), 12.0, 120.0),
    ("MaximumMana", ("maximum mana", "to mana"), 10.0, 100.0),
    (
        "MaximumEnergyShield",
        ("maximum energy shield", "energy shield"),
        10.0,
        100.0,
    ),
    ("EvasionRating", ("evasion",), 12.0, 120.0),
    ("Armor", ("armor", "armour"), 12.0, 120.0),
    ("MovementSpeed", ("movement speed",), 3.0, 30.0),
    ("CriticalStrikeChance", ("critical strike chance",), 6.0, 60.0),
    (
        "CriticalStrikeMultiplier",
        ("critical strike multiplier",),
        6.0,
        60.0,
    ),
    ("AttackSpeed", ("attack speed",), 2.0, 20.0),
    ("CastSpeed", ("cast speed",), 2.0, 20.0),
    ("PhysicalDamage", ("physical damage",), 10.0, 100.0),
    ("FireDamage", ("fire damage",), 10.0, 100.0),
    ("ColdDamage", ("cold damage",), 10.0, 100.0),
    ("LightningDamage", ("lightning damage",), 10.0, 100.0),
    ("ChaosDamage", ("chaos damage",), 10.0, 100.0),
    ("ElementalDamage", ("elemental damage",), 10.0, 100.0),
    ("SpellDamage", ("spell damage",), 10.0, 100.0),
    ("FireResistance", ("fire resistance",), 3.0, 30.0),
    ("ColdResistance", ("cold resistance",), 3.0, 30.0),
    ("LightningResistance", ("lightning resistance",), 3.0, 30.0),
    ("ChaosResistance", ("chaos resistance",), 2.0, 20.0),
    (
        "AllElementalResistances",
        ("all elemental resistances", "to all elemental resistances"),
        3.0,
        30.0,
    ),
)

_MOD_FEATURE_RULE_BY_NAME: dict[str, tuple[str, tuple[str, ...], float, float]] = {
    rule[0]: rule for rule in _MOD_FEATURE_RULES
}

_MOD_FEATURE_SQL_EXTRA_SNIPPETS: dict[str, tuple[str, ...]] = {
    "Strength": ("all attributes",),
    "Dexterity": ("all attributes",),
    "Intelligence": ("all attributes",),
    "AttackSpeed": ("attack and cast speed",),
    "CastSpeed": ("attack and cast speed",),
}


def _normalize_mod_token_sql(expr: str) -> str:
    lowered = f"lowerUTF8(trimBoth({expr}))"
    unescaped = f"replaceAll({lowered}, '\\\"', '\"')"
    unquoted = f"replaceRegexpAll({unescaped}, '^\"|\"$', '')"
    return f"replaceRegexpAll({unquoted}, '\\s+', ' ')"


def _primary_numeric_sql(token_expr: str) -> str:
    first_numeric = (
        "toFloat64OrZero(extract("
        + token_expr
        + ", '(?:^|\\\\s)[+-]?(\\\\d+(?:\\\\.\\\\d+)?)\\\\s*%?'))"
    )
    fallback_numeric = (
        "if(empty(extractAll(" + token_expr + ", '\\d+(?:\\\\.\\\\d+)?')), 0., "
        "arrayReduce('max', arrayMap(x -> toFloat64OrZero(x), "
        "extractAll(" + token_expr + ", '\\d+(?:\\\\.\\\\d+)?'))))"
    )
    return f"if({first_numeric} > 0., {first_numeric}, {fallback_numeric})"


def _added_damage_numeric_sql(token_expr: str, damage_type: str) -> str:
    prefix = (
        "adds\\\\s+(\\\\d+(?:\\\\.\\\\d+)?)\\\\s+to\\\\s+\\\\d+(?:\\\\.\\\\d+)?\\\\s+"
        + re.escape(damage_type)
        + "\\\\s+damage"
    )
    suffix = (
        "adds\\\\s+\\\\d+(?:\\\\.\\\\d+)?\\\\s+to\\\\s+(\\\\d+(?:\\\\.\\\\d+)?)\\\\s+"
        + re.escape(damage_type)
        + "\\\\s+damage"
    )
    return (
        "greatest(toFloat64OrZero(extract("
        + token_expr
        + f", '{prefix}')), toFloat64OrZero(extract({token_expr}, '{suffix}')))"
    )


def _feature_sql_snippets(mod_name: str) -> tuple[str, ...]:
    base_snippets = _MOD_FEATURE_RULE_BY_NAME[mod_name][1]
    return base_snippets + _MOD_FEATURE_SQL_EXTRA_SNIPPETS.get(mod_name, ())


def _feature_sql_condition(mod_name: str, token_expr: str) -> str:
    snippets = _feature_sql_snippets(mod_name)
    return " OR ".join(
        f"position({token_expr}, {_quote(snippet)}) > 0" for snippet in snippets
    )


def _all_feature_sql_snippets() -> tuple[str, ...]:
    ordered: list[str] = []
    seen: set[str] = set()
    for mod_name, *_rest in _MOD_FEATURE_RULES:
        for snippet in _feature_sql_snippets(mod_name):
            if snippet in seen:
                continue
            seen.add(snippet)
            ordered.append(snippet)
    return tuple(ordered)


def _feature_sql_value_alias(mod_name: str) -> str:
    return f"{mod_name.lower()}_value"


def _feature_sql_numeric_source(mod_name: str) -> str:
    if mod_name == "PhysicalDamage":
        return "if(physical_added_value > 0., physical_added_value, primary_numeric)"
    if mod_name == "FireDamage":
        return "if(fire_added_value > 0., fire_added_value, primary_numeric)"
    if mod_name == "ColdDamage":
        return "if(cold_added_value > 0., cold_added_value, primary_numeric)"
    if mod_name == "LightningDamage":
        return "if(lightning_added_value > 0., lightning_added_value, primary_numeric)"
    if mod_name == "ChaosDamage":
        return "if(chaos_added_value > 0., chaos_added_value, primary_numeric)"
    return "primary_numeric"


def _feature_sql_key_array(mod_name: str) -> str:
    alias = _feature_sql_value_alias(mod_name)
    return f"if({alias} > 0., ['{mod_name}_tier', '{mod_name}_roll'], [])"


def _feature_sql_value_array(mod_name: str) -> str:
    alias = _feature_sql_value_alias(mod_name)
    _, _, tier_divisor, roll_divisor = _MOD_FEATURE_RULE_BY_NAME[mod_name]
    return (
        f"if({alias} > 0., ["
        f"toFloat64(greatest(1, least(10, ceil({alias} / {max(tier_divisor, 1.0)})))), "
        f"round(greatest(0., least(1., {alias} / {max(roll_divisor, 1.0)})), 4)"
        "], [])"
    )


def _feature_sql_value_columns() -> tuple[str, ...]:
    return tuple(
        _feature_sql_value_alias(mod_name) for mod_name, *_rest in _MOD_FEATURE_RULES
    )


def _build_sql_mod_feature_stage_query(
    *, league: str, hour_ts: str | None = None
) -> str:
    token_expr = _normalize_mod_token_sql("mod_token")
    primary_numeric_expr = _primary_numeric_sql("token")
    prefilter_condition = " OR ".join(
        f"position(token, {_quote(snippet)}) > 0"
        for snippet in _all_feature_sql_snippets()
    )
    aggregate_fields = [
        f"maxIf({_feature_sql_numeric_source(mod_name)}, {_feature_sql_condition(mod_name, 'token')}) AS {_feature_sql_value_alias(mod_name)}"
        for mod_name, *_rest in _MOD_FEATURE_RULES
    ]
    where_clauses = [f"league = {_quote(league)}"]
    if hour_ts:
        where_clauses.append(
            "toStartOfHour(as_of_ts) = " + f"toDateTime64({_quote(hour_ts)}, 3, 'UTC')"
        )
    return " ".join(
        [
            "SELECT",
            "league,",
            "item_id,",
            "toStartOfHour(max(as_of_ts)) AS hour_ts,",
            "count() AS mod_count,",
            "max(as_of_ts) AS max_as_of_ts,",
            ", ".join(aggregate_fields),
            "FROM (",
            "SELECT",
            "league,",
            "item_id,",
            "as_of_ts,",
            f"{primary_numeric_expr} AS primary_numeric,",
            f"{_added_damage_numeric_sql('token', 'physical')} AS physical_added_value,",
            f"{_added_damage_numeric_sql('token', 'fire')} AS fire_added_value,",
            f"{_added_damage_numeric_sql('token', 'cold')} AS cold_added_value,",
            f"{_added_damage_numeric_sql('token', 'lightning')} AS lightning_added_value,",
            f"{_added_damage_numeric_sql('token', 'chaos')} AS chaos_added_value,",
            "token",
            "FROM (",
            "SELECT",
            "league,",
            "item_id,",
            "as_of_ts,",
            f"{token_expr} AS token",
            "FROM poe_trade.ml_item_mod_tokens_v1",
            "WHERE " + " AND ".join(where_clauses),
            ")",
            f"WHERE {prefilter_condition}",
            ")",
            "GROUP BY league, item_id",
        ]
    )


def _build_sql_mod_feature_finalize_query(*, league: str) -> str:
    key_arrays = ", ".join(
        _feature_sql_key_array(mod_name) for mod_name, *_rest in _MOD_FEATURE_RULES
    )
    value_arrays = ", ".join(
        _feature_sql_value_array(mod_name) for mod_name, *_rest in _MOD_FEATURE_RULES
    )
    rollup_fields = [
        f"max({_feature_sql_value_alias(mod_name)}) AS {_feature_sql_value_alias(mod_name)}"
        for mod_name, *_rest in _MOD_FEATURE_RULES
    ]
    return " ".join(
        [
            "INSERT INTO poe_trade.ml_item_mod_features_v1",
            "SELECT",
            "league,",
            "item_id,",
            f"toJSONString(mapFromArrays(arrayConcat({key_arrays}), arrayConcat({value_arrays}))) AS mod_features_json,",
            "toUInt8(least(mod_count, 255)) AS mod_count,",
            "max_as_of_ts AS as_of_ts,",
            "now64(3) AS updated_at",
            "FROM (",
            "SELECT",
            "league,",
            "item_id,",
            "sum(mod_count) AS mod_count,",
            "max(max_as_of_ts) AS max_as_of_ts,",
            ", ".join(rollup_fields),
            "FROM poe_trade.ml_item_mod_features_sql_stage_v1",
            f"WHERE league = {_quote(league)}",
            "GROUP BY league, item_id",
            ")",
        ]
    )


def _ensure_mod_feature_sql_stage_table(client: ClickHouseClient) -> None:
    column_defs = ", ".join(f"{name} Float64" for name in _feature_sql_value_columns())
    client.execute(
        " ".join(
            [
                "CREATE TABLE IF NOT EXISTS poe_trade.ml_item_mod_features_sql_stage_v1(",
                "league String,",
                "item_id String,",
                "mod_count UInt64,",
                "max_as_of_ts DateTime64(3, 'UTC'),",
                f"{column_defs}",
                ") ENGINE=MergeTree() ORDER BY (league, item_id, max_as_of_ts)",
            ]
        )
    )
    mv_sql = _read_mod_feature_stage_mv_sql()
    if mv_sql:
        client.execute(mv_sql)


def _read_mod_feature_stage_mv_sql() -> str:
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "schema"
        / "migrations"
        / "0047_poeninja_mod_feature_stage_mv_v1.sql"
    )
    if not migration_path.exists():
        return ""
    sql = migration_path.read_text(encoding="utf-8")
    statements = MigrationRunner._split_sql_statements(sql)
    for statement in statements:
        if (
            "CREATE MATERIALIZED VIEW IF NOT EXISTS poe_trade.mv_ml_item_mod_features_sql_stage_v1"
            in statement
        ):
            return statement
    return ""


def _build_sql_mod_feature_insert_query(*, league: str) -> str:
    token_expr = _normalize_mod_token_sql("mod_token")
    primary_numeric_expr = _primary_numeric_sql("token")
    prefilter_condition = " OR ".join(
        f"position(token, {_quote(snippet)}) > 0"
        for snippet in _all_feature_sql_snippets()
    )
    aggregate_fields = [
        f"maxIf({_feature_sql_numeric_source(mod_name)}, {_feature_sql_condition(mod_name, 'token')}) AS {_feature_sql_value_alias(mod_name)}"
        for mod_name, *_rest in _MOD_FEATURE_RULES
    ]
    key_arrays = ", ".join(
        _feature_sql_key_array(mod_name) for mod_name, *_rest in _MOD_FEATURE_RULES
    )
    value_arrays = ", ".join(
        _feature_sql_value_array(mod_name) for mod_name, *_rest in _MOD_FEATURE_RULES
    )
    feature_keys_sql = f"arrayConcat({key_arrays})"
    feature_values_sql = f"arrayConcat({value_arrays})"
    return " ".join(
        [
            "INSERT INTO poe_trade.ml_item_mod_features_v1",
            "SELECT",
            "league,",
            "item_id,",
            "toJSONString(mapFromArrays(feature_keys, feature_values)) AS mod_features_json,",
            "toUInt8(least(mod_count, 255)) AS mod_count,",
            "max_as_of_ts AS as_of_ts,",
            "now64(3) AS updated_at",
            "FROM (",
            "SELECT",
            "league,",
            "item_id,",
            "mod_count,",
            "max_as_of_ts,",
            f"{feature_keys_sql} AS feature_keys,",
            f"{feature_values_sql} AS feature_values",
            "FROM (",
            "SELECT",
            "league,",
            "item_id,",
            "count() AS mod_count,",
            "max(as_of_ts) AS max_as_of_ts,",
            ", ".join(aggregate_fields),
            "FROM (",
            "SELECT",
            "league,",
            "item_id,",
            "as_of_ts,",
            f"{primary_numeric_expr} AS primary_numeric,",
            f"{_added_damage_numeric_sql('token', 'physical')} AS physical_added_value,",
            f"{_added_damage_numeric_sql('token', 'fire')} AS fire_added_value,",
            f"{_added_damage_numeric_sql('token', 'cold')} AS cold_added_value,",
            f"{_added_damage_numeric_sql('token', 'lightning')} AS lightning_added_value,",
            f"{_added_damage_numeric_sql('token', 'chaos')} AS chaos_added_value,",
            "token",
            "FROM (",
            "SELECT",
            "league,",
            "item_id,",
            "as_of_ts,",
            f"{token_expr} AS token",
            "FROM poe_trade.ml_item_mod_tokens_v1",
            f"WHERE league = {_quote(league)}",
            ")",
            f"WHERE {prefilter_condition}",
            ")",
            "GROUP BY league, item_id",
            ")",
            ")",
        ]
    )


def _mod_feature_sql_query_settings() -> dict[str, str]:
    return {
        "max_memory_usage": str(
            max(1, _env_int("POE_ML_MOD_FEATURE_SQL_MAX_MEMORY_USAGE", 1610612736))
        ),
        "max_threads": str(max(1, _env_int("POE_ML_MOD_FEATURE_SQL_MAX_THREADS", 4))),
        "max_block_size": str(
            max(1, _env_int("POE_ML_MOD_FEATURE_SQL_MAX_BLOCK_SIZE", 2048))
        ),
        "optimize_aggregation_in_order": "1",
        "max_execution_time": str(
            max(1, _env_int("POE_ML_MOD_FEATURE_SQL_MAX_EXECUTION_TIME", 180))
        ),
        "max_bytes_before_external_group_by": str(
            max(
                1,
                _env_int(
                    "POE_ML_MOD_FEATURE_SQL_MAX_BYTES_BEFORE_EXTERNAL_GROUP_BY",
                    268435456,
                ),
            )
        ),
        "max_bytes_before_external_sort": str(
            max(
                1,
                _env_int(
                    "POE_ML_MOD_FEATURE_SQL_MAX_BYTES_BEFORE_EXTERNAL_SORT",
                    268435456,
                ),
            )
        ),
    }


def _populate_item_mod_features_from_tokens_sql(
    client: ClickHouseClient,
    *,
    league: str,
) -> dict[str, Any]:
    _ensure_mod_feature_table(client)
    _ensure_mod_feature_sql_stage_table(client)
    client.execute(
        " ".join(
            [
                "ALTER TABLE poe_trade.ml_item_mod_features_v1",
                f"DELETE WHERE league = {_quote(league)}",
                "SETTINGS mutations_sync = 2",
            ]
        )
    )
    try:
        client.execute(
            _build_sql_mod_feature_finalize_query(league=league),
            settings=_mod_feature_sql_query_settings(),
        )
    except TypeError:
        client.execute(_build_sql_mod_feature_finalize_query(league=league))
    rows_written = _scalar_count(
        client,
        " ".join(
            [
                "SELECT count() AS value",
                "FROM poe_trade.ml_item_mod_features_v1",
                f"WHERE league = {_quote(league)}",
            ]
        ),
    )
    non_empty_rows = _scalar_count(
        client,
        " ".join(
            [
                "SELECT count() AS value",
                "FROM poe_trade.ml_item_mod_features_v1",
                f"WHERE league = {_quote(league)}",
                "AND mod_features_json != '{}'",
            ]
        ),
    )
    return {
        "rows_written": rows_written,
        "non_empty_rows": non_empty_rows,
        "mode": "sql_primary",
    }


def _populate_item_mod_features(
    client: ClickHouseClient,
    *,
    league: str,
    page_size: int = _MOD_FEATURE_BATCH_SIZE,
) -> dict[str, Any]:
    if _env_bool("POE_ML_MOD_ROLLUP_FORCE_LEGACY", False):
        result = _populate_item_mod_features_from_tokens(
            client,
            league=league,
            page_size=page_size,
        )
        result.setdefault("mode", "legacy_fallback")
        return result
    if _env_bool("POE_ML_MOD_FEATURE_SQL_PRIMARY_ENABLED", True):
        return _populate_item_mod_features_from_tokens_sql(client, league=league)
    result = _populate_item_mod_features_from_tokens(
        client,
        league=league,
        page_size=page_size,
    )
    result.setdefault("mode", "legacy_disabled_sql")
    return result


def discover_mod_features(
    client: ClickHouseClient | None = None,
    *,
    league: str = "Mirage",
    min_frequency: int = 100,
    dataset_table: str = _DEFAULT_DATASET_TABLE,
    use_cache: bool = True,
) -> list[str]:
    """
    Discover mod features from dataset with frequency >= min_frequency.

    Returns sorted list of mod feature names (e.g., "MaximumLife_tier", "MaximumLife_roll").
    Results are cached to avoid repeated expensive queries.
    """
    if use_cache and _MOD_FEATURES_CACHE_PATH.exists():
        try:
            cache_data = json.loads(
                _MOD_FEATURES_CACHE_PATH.read_text(encoding="utf-8")
            )
            cached_features = cache_data.get("features", [])
            cached_league = cache_data.get("league", "")
            cached_min_freq = cache_data.get("min_frequency", 0)

            if (
                cached_league == league
                and cached_min_freq == min_frequency
                and cached_features
            ):
                logger.info(
                    f"Using cached mod features: {len(cached_features)} features from cache"
                )
                return cached_features
        except (json.JSONDecodeError, KeyError, IOError):
            pass

    if client is None:
        logger.warning(
            "No ClickHouse client provided for mod feature discovery, using empty list"
        )
        return []

    try:
        query = f"""
        SELECT
          arrayJoin(JSONExtractKeys(mod_features_json)) as feature_key,
          count() as feature_count
        FROM {dataset_table}
        WHERE league = {_quote(league)} AND mod_features_json != '{{}}'
        GROUP BY feature_key
        HAVING feature_count >= {min_frequency}
        ORDER BY feature_key
        FORMAT JSONEachRow
        """

        rows = _query_rows(client, query)

        mod_features: list[str] = []
        for row in rows:
            feature_key = str(row.get("feature_key", ""))
            if feature_key:
                mod_features.append(feature_key)

        mod_features.sort()

        if use_cache:
            try:
                cache_data = {
                    "league": league,
                    "min_frequency": min_frequency,
                    "features": mod_features,
                    "discovered_at": datetime.now(UTC).isoformat(),
                }
                _MOD_FEATURES_CACHE_PATH.write_text(
                    json.dumps(cache_data, indent=2), encoding="utf-8"
                )
                logger.info(
                    f"Cached {len(mod_features)} mod features to {_MOD_FEATURES_CACHE_PATH}"
                )
            except IOError as e:
                logger.warning(f"Failed to cache mod features: {e}")

        logger.info(f"Discovered {len(mod_features)} mod features from dataset")
        return mod_features

    except Exception as e:
        logger.error(f"Failed to discover mod features: {e}")
        return []


_discovered_mod_features: list[str] = []


def _get_model_feature_fields() -> tuple[str, ...]:
    if _discovered_mod_features:
        return (*BASE_FEATURE_FIELDS, *_discovered_mod_features)
    return BASE_FEATURE_FIELDS


MODEL_FEATURE_FIELDS: list[str] = list(BASE_FEATURE_FIELDS)

FEATURE_SCHEMA_VERSION = "v2"


class FeatureSchemaMismatchError(ValueError):
    pass


def _build_feature_schema(
    feature_fields: list[str] | tuple[str, ...],
) -> dict[str, Any]:
    ordered_fields = [str(field) for field in feature_fields]
    fingerprint = hashlib.sha256(
        json.dumps(ordered_fields, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "version": FEATURE_SCHEMA_VERSION,
        "fields": ordered_fields,
        "field_count": len(ordered_fields),
        "fingerprint": fingerprint,
    }


def initialize_mod_features(
    client: ClickHouseClient | None = None,
    *,
    league: str = "Mirage",
    min_frequency: int = 100,
    dataset_table: str = _DEFAULT_DATASET_TABLE,
) -> None:
    global _discovered_mod_features, MODEL_FEATURE_FIELDS
    discovered = discover_mod_features(
        client,
        league=league,
        min_frequency=min_frequency,
        dataset_table=dataset_table,
        use_cache=True,
    )
    _discovered_mod_features = discovered
    MODEL_FEATURE_FIELDS.clear()
    MODEL_FEATURE_FIELDS.extend(BASE_FEATURE_FIELDS)
    MODEL_FEATURE_FIELDS.extend(discovered)
    logger.info(
        f"ML feature initialization complete: "
        f"{len(BASE_FEATURE_FIELDS)} base + {len(discovered)} mod = "
        f"{len(MODEL_FEATURE_FIELDS)} total features"
    )


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
        sample_ts = _clickhouse_datetime(datetime.now(UTC))
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
    snapshot_table: str = "poe_trade.raw_poeninja_currency_overview",
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
    client.execute("TRUNCATE TABLE poe_trade.ml_item_mod_features_sql_stage_v1")
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

    def _item_tokens_insert_sql(hour_ts: str | None = None) -> str:
        clauses = [
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
        if hour_ts:
            clauses.append(
                "AND toStartOfHour(items.observed_at) = "
                f"toDateTime64({_quote(hour_ts)}, 3, 'UTC')"
            )
        return " ".join(clauses)

    item_tokens_query_settings = {
        "max_memory_usage": str(
            max(1, _env_int("POE_ML_ITEM_TOKENS_MAX_MEMORY_USAGE", 10147483648))
        ),
        "max_threads": str(max(1, _env_int("POE_ML_ITEM_TOKENS_MAX_THREADS", 12))),
        "max_bytes_before_external_group_by": str(
            max(
                1,
                _env_int(
                    "POE_ML_ITEM_TOKENS_MAX_BYTES_BEFORE_EXTERNAL_GROUP_BY",
                    1068435456,
                ),
            )
        ),
        "max_bytes_before_external_sort": str(
            max(
                1,
                _env_int(
                    "POE_ML_ITEM_TOKENS_MAX_BYTES_BEFORE_EXTERNAL_SORT",
                    1068435456,
                ),
            )
        ),
        "materialized_views_ignore_errors": "1"
        if _env_bool("POE_ML_ITEM_TOKENS_IGNORE_MV_ERRORS", True)
        else "0",
    }
    chunk_by_hour = _env_bool("POE_ML_ITEM_TOKENS_CHUNK_BY_HOUR", True)
    if chunk_by_hour:
        hour_rows = _query_rows(
            client,
            " ".join(
                [
                    "SELECT toStartOfHour(items.observed_at) AS hour_ts",
                    "FROM poe_trade.v_ps_items_enriched AS items",
                    f"WHERE ifNull(items.league, '') = {_quote(league)}",
                    f"AND items.observed_at <= toDateTime64({_quote(as_of_ch)}, 3, 'UTC')",
                    "GROUP BY hour_ts",
                    "ORDER BY hour_ts",
                    "FORMAT JSONEachRow",
                ]
            ),
        )
        for row in hour_rows:
            hour_ts = str(row.get("hour_ts") or "").strip()
            if not hour_ts:
                continue
            hour_insert_sql = _item_tokens_insert_sql(hour_ts)
            try:
                client.execute(hour_insert_sql, settings=item_tokens_query_settings)
            except TypeError:
                client.execute(hour_insert_sql)
    else:
        item_tokens_sql = _item_tokens_insert_sql()
        try:
            client.execute(item_tokens_sql, settings=item_tokens_query_settings)
        except TypeError:
            client.execute(item_tokens_sql)
    mod_feature_result = _populate_item_mod_features(client, league=league)

    now = _now_ts()

    def _dataset_insert_sql(hour_ts: str | None = None) -> str:
        clauses = [
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
            f"{_derive_category_sql('items')} AS category,",
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
            f"toDateTime64('{now}', 3, 'UTC') AS updated_at,",
            "ifNull(features.mod_features_json, '{}') AS mod_features_json",
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
            ") AS mods ON mods.league = ifNull(items.league, '') AND mods.item_id = items.item_id",
            "LEFT JOIN poe_trade.ml_item_mod_features_v1 AS features ON features.league = ifNull(items.league, '') AND features.item_id = items.item_id",
            f"WHERE ifNull(items.league, '') = {_quote(league)}",
            f"AND items.observed_at <= toDateTime64({_quote(as_of_ch)}, 3, 'UTC')",
            "AND labels.outlier_status = 'trainable'",
            "AND labels.normalized_price_chaos IS NOT NULL",
        ]
        if hour_ts:
            clauses.append(
                "AND toStartOfHour(items.observed_at) = "
                f"toDateTime64({_quote(hour_ts)}, 3, 'UTC')"
            )
        return " ".join(clauses)

    dataset_chunk_by_hour = _env_bool("POE_ML_DATASET_CHUNK_BY_HOUR", True)
    dataset_query_settings = {
        "max_threads": str(max(1, _env_int("POE_ML_DATASET_MAX_THREADS", 1))),
        "max_block_size": str(max(1, _env_int("POE_ML_DATASET_MAX_BLOCK_SIZE", 2048))),
    }
    if dataset_chunk_by_hour:
        dataset_hours = _query_rows(
            client,
            " ".join(
                [
                    "SELECT toStartOfHour(items.observed_at) AS hour_ts",
                    "FROM poe_trade.v_ps_items_enriched AS items",
                    f"WHERE ifNull(items.league, '') = {_quote(league)}",
                    f"AND items.observed_at <= toDateTime64({_quote(as_of_ch)}, 3, 'UTC')",
                    "GROUP BY hour_ts",
                    "ORDER BY hour_ts",
                    "FORMAT JSONEachRow",
                ]
            ),
        )
        for row in dataset_hours:
            hour_ts = str(row.get("hour_ts") or "").strip()
            if not hour_ts:
                continue
            hour_dataset_sql = _dataset_insert_sql(hour_ts)
            try:
                client.execute(hour_dataset_sql, settings=dataset_query_settings)
            except TypeError:
                client.execute(hour_dataset_sql)
    else:
        dataset_sql = _dataset_insert_sql()
        try:
            client.execute(dataset_sql, settings=dataset_query_settings)
        except TypeError:
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
        "mod_features_rows_written": _to_int(
            mod_feature_result.get("rows_written"),
            0,
        ),
        "mod_features_non_empty_rows": _to_int(
            mod_feature_result.get("non_empty_rows"),
            0,
        ),
    }


_DIRECT_CATEGORY_FAMILIES = {
    "essence",
    "fossil",
    "scarab",
    "map",
    "logbook",
    "cluster_jewel",
    "flask",
    "jewel",
    "ring",
    "amulet",
    "belt",
}

_MODEL_CATEGORY_COLLAPSE_TO_OTHER = {"jewel", "ring", "amulet", "belt"}

_FUNGIBLE_REFERENCE_EXCLUDED_CATEGORIES = ("essence",)

_FUNGIBLE_REFERENCE_CATEGORIES = (
    "fossil",
    "scarab",
    "logbook",
)

_FUNGIBLE_REFERENCE_FAMILY_SCOPES = {
    "fossil": "fossil",
    "scarab": "scarab",
    "logbook": "logbook",
}

_STRUCTURED_BOOSTED_OTHER_FAMILY_SCOPES = {
    "jewel": "jewel",
    "ring": "ring",
    "amulet": "amulet",
    "belt": "belt",
}

_FUNGIBLE_REFERENCE_CATEGORY_SET = set(_FUNGIBLE_REFERENCE_CATEGORIES)
_FUNGIBLE_REFERENCE_EXCLUDED_CATEGORY_SET = set(_FUNGIBLE_REFERENCE_EXCLUDED_CATEGORIES)
_FUNGIBLE_REFERENCE_FAMILY_SCOPE_SET = set(_FUNGIBLE_REFERENCE_FAMILY_SCOPES.values())
_STRUCTURED_BOOSTED_OTHER_FAMILY_SCOPE_SET = set(
    _STRUCTURED_BOOSTED_OTHER_FAMILY_SCOPES.values()
)


def _fungible_reference_categories_sql() -> str:
    return ", ".join(_quote(category) for category in _FUNGIBLE_REFERENCE_CATEGORIES)


def _fungible_reference_excluded_categories_sql() -> str:
    return ", ".join(
        _quote(category) for category in _FUNGIBLE_REFERENCE_EXCLUDED_CATEGORIES
    )


def _fungible_reference_family_scope(category: object) -> str:
    normalized = str(category or "").strip().lower()
    return _FUNGIBLE_REFERENCE_FAMILY_SCOPES.get(normalized, "other")


def _structured_boosted_other_family_scope(category: object) -> str:
    normalized = str(category or "").strip().lower()
    return _STRUCTURED_BOOSTED_OTHER_FAMILY_SCOPES.get(normalized, "other")


def _structured_boosted_other_family_scope_from_fields(
    category: object,
    *,
    base_type: object = "",
    item_type_line: object = "",
) -> str:
    direct_scope = _structured_boosted_other_family_scope(category)
    if direct_scope != "other":
        return direct_scope
    lowered = " ".join(
        part.strip().lower()
        for part in (str(base_type or ""), str(item_type_line or ""))
        if str(part or "").strip()
    )
    if re.search(r"\bring\b", lowered):
        return "ring"
    if re.search(r"\bamulet\b", lowered):
        return "amulet"
    if re.search(r"\bbelt\b", lowered):
        return "belt"
    if re.search(r"\b(?:cluster\s+)?jewel\b", lowered):
        return "jewel"
    return "other"


def _structured_boosted_other_family_scope_sql(prefix: str = "") -> str:
    qualifier = f"{prefix}." if prefix else ""
    category = f"lowerUTF8(trimBoth(ifNull({qualifier}category, '')))"
    lowered = (
        "lowerUTF8(concat(ifNull(" + qualifier + "item_type_line, ''), ' ', "
        "ifNull(" + qualifier + "base_type, '')))"
    )
    return (
        "multiIf("
        f"{category} = 'ring', 'ring', "
        f"{category} = 'amulet', 'amulet', "
        f"{category} = 'belt', 'belt', "
        f"{category} = 'jewel', 'jewel', "
        f"match({lowered}, '(^|\\W)ring(\\W|$)'), 'ring', "
        f"match({lowered}, '(^|\\W)amulet(\\W|$)'), 'amulet', "
        f"match({lowered}, '(^|\\W)belt(\\W|$)'), 'belt', "
        f"match({lowered}, '(^|\\W)(cluster\\s+)?jewel(\\W|$)'), 'jewel', "
        "'other')"
    )


def _route_family_scope(route: str, row: dict[str, Any]) -> str:
    normalized_route = str(route or "").strip().lower()
    category = row.get("category")
    if normalized_route == "fungible_reference":
        return _fungible_reference_family_scope(category)
    if normalized_route in {"structured_boosted", "structured_boosted_other"}:
        scoped = _structured_boosted_other_family_scope_from_fields(
            category,
            base_type=row.get("base_type"),
            item_type_line=row.get("item_type_line"),
        )
        if scoped != "other":
            return scoped
        return _canonical_model_category(category)
    return _canonical_model_category(category)


def _route_family_scope_sql(route: str, *, prefix: str = "") -> str:
    qualifier = f"{prefix}." if prefix else ""
    category = f"lowerUTF8(trimBoth(ifNull({qualifier}category, '')))"
    normalized_route = str(route or "").strip().lower()
    if normalized_route == "fungible_reference":
        return (
            "multiIf("
            f"{category} = 'fossil', 'fossil', "
            f"{category} = 'scarab', 'scarab', "
            f"{category} = 'logbook', 'logbook', "
            "'other')"
        )
    if normalized_route in {"structured_boosted", "structured_boosted_other"}:
        return _structured_boosted_other_family_scope_sql(prefix)
    return (
        "multiIf("
        f"{category} IN ('jewel', 'ring', 'amulet', 'belt'), 'other', "
        f"{category} = '', 'other', "
        f"{category})"
    )


def _derive_category(
    category: object,
    *,
    item_class: object = "",
    base_type: object = "",
    item_type_line: object = "",
) -> str:
    raw_category = str(category or "").strip().lower()
    if raw_category in _DIRECT_CATEGORY_FAMILIES:
        return raw_category

    lowered = " ".join(
        part.strip().lower()
        for part in (
            str(item_class or ""),
            str(base_type or ""),
            str(item_type_line or ""),
        )
        if str(part or "").strip()
    )

    if re.search(r"\bcluster\s+jewel\b", lowered):
        return "cluster_jewel"
    if re.search(r"\b(?:abyss\s+)?jewel\b", lowered):
        return "jewel"
    if re.search(r"\bring\b", lowered):
        return "ring"
    if re.search(r"\bamulet\b", lowered):
        return "amulet"
    if re.search(r"\bbelt\b", lowered):
        return "belt"
    if re.search(r"\bmap\b", lowered):
        return "map"

    if raw_category and raw_category != "other":
        return raw_category
    return "other"


def _canonical_model_category(category: object) -> str:
    normalized = str(category or "other").strip().lower() or "other"
    if normalized in _MODEL_CATEGORY_COLLAPSE_TO_OTHER:
        return "other"
    return normalized


def _model_category_for_route(category: object, *, route: str = "") -> str:
    normalized = str(category or "other").strip().lower() or "other"
    if (
        route in {"structured_boosted", "structured_boosted_other"}
        and normalized in _MODEL_CATEGORY_COLLAPSE_TO_OTHER
    ):
        return normalized
    return _canonical_model_category(normalized)


def _derive_category_sql(prefix: str = "") -> str:
    qualifier = f"{prefix}." if prefix else ""
    raw_category = f"lowerUTF8(trimBoth(ifNull({qualifier}category, '')))"
    lowered = (
        "lowerUTF8(concat(ifNull(" + qualifier + "item_type_line, ''), ' ', "
        "ifNull(" + qualifier + "base_type, '')))"
    )
    return (
        "multiIf("
        f"{raw_category} IN ('essence','fossil','scarab','map','logbook','cluster_jewel','flask','jewel','ring','amulet','belt'), {raw_category}, "
        f"match({lowered}, '(^|\\\\W)cluster\\\\s+jewel(\\\\W|$)'), 'cluster_jewel', "
        f"match({lowered}, '(^|\\\\W)(abyss\\\\s+)?jewel(\\\\W|$)'), 'jewel', "
        f"match({lowered}, '(^|\\\\W)ring(\\\\W|$)'), 'ring', "
        f"match({lowered}, '(^|\\\\W)amulet(\\\\W|$)'), 'amulet', "
        f"match({lowered}, '(^|\\\\W)belt(\\\\W|$)'), 'belt', "
        f"match({lowered}, '(^|\\\\W)map(\\\\W|$)'), 'map', "
        f"{raw_category} != '' AND {raw_category} != 'other', {raw_category}, "
        "'other')"
    )


def _max_numeric_from_token(token: str) -> float:
    matches = re.findall(r"\d+(?:\.\d+)?", token)
    if not matches:
        return 0.0
    return max(float(raw) for raw in matches)


def _normalize_mod_token(raw_token: str) -> str:
    token = raw_token.strip().lower()
    token = token.strip('"').strip("'")
    token = token.replace('\\"', '"')
    return re.sub(r"\s+", " ", token)


def _extract_added_damage_value(token: str, damage_type: str) -> float:
    pattern = (
        r"adds\s+(\d+(?:\.\d+)?)\s+to\s+(\d+(?:\.\d+)?)\s+"
        + re.escape(damage_type)
        + r"\s+damage"
    )
    match = re.search(pattern, token)
    if not match:
        return 0.0
    return max(float(match.group(1)), float(match.group(2)))


def _extract_primary_numeric(token: str) -> float:
    plus_or_plain = re.search(r"(?:^|\s)[+-]?(\d+(?:\.\d+)?)\s*%?", token)
    if plus_or_plain:
        return float(plus_or_plain.group(1))
    return _max_numeric_from_token(token)


def _token_numeric_for_mod(mod_name: str, token: str) -> float:
    if mod_name == "PhysicalDamage":
        added_value = _extract_added_damage_value(token, "physical")
        if added_value > 0.0:
            return added_value
    if mod_name == "FireDamage":
        added_value = _extract_added_damage_value(token, "fire")
        if added_value > 0.0:
            return added_value
    if mod_name == "ColdDamage":
        added_value = _extract_added_damage_value(token, "cold")
        if added_value > 0.0:
            return added_value
    if mod_name == "LightningDamage":
        added_value = _extract_added_damage_value(token, "lightning")
        if added_value > 0.0:
            return added_value
    if mod_name == "ChaosDamage":
        added_value = _extract_added_damage_value(token, "chaos")
        if added_value > 0.0:
            return added_value
    return _extract_primary_numeric(token)


def _mod_features_from_tokens(mod_tokens: list[str]) -> dict[str, Any]:
    best_values: dict[str, float] = {}

    def _record(mod_name: str, numeric: float) -> None:
        if numeric <= 0.0:
            return
        previous = best_values.get(mod_name, 0.0)
        if numeric > previous:
            best_values[mod_name] = numeric

    for raw_token in mod_tokens:
        token = _normalize_mod_token(raw_token)
        if not token:
            continue

        numeric = _extract_primary_numeric(token)

        if "all attributes" in token:
            _record("Strength", numeric)
            _record("Dexterity", numeric)
            _record("Intelligence", numeric)
        if "attack and cast speed" in token:
            _record("AttackSpeed", numeric)
            _record("CastSpeed", numeric)

        for (
            mod_name,
            token_snippets,
            _tier_divisor,
            _roll_divisor,
        ) in _MOD_FEATURE_RULES:
            if any(snippet in token for snippet in token_snippets):
                _record(mod_name, _token_numeric_for_mod(mod_name, token))

    feature_payload: dict[str, Any] = {}
    for mod_name, token_value in best_values.items():
        rule = _MOD_FEATURE_RULE_BY_NAME[mod_name]
        tier_divisor = max(rule[2], 1.0)
        roll_divisor = max(rule[3], 1.0)
        tier = max(1, min(10, int(math.ceil(token_value / tier_divisor))))
        roll = max(0.0, min(1.0, token_value / roll_divisor))
        feature_payload[f"{mod_name}_tier"] = tier
        feature_payload[f"{mod_name}_roll"] = round(roll, 4)
    return feature_payload


def _populate_item_mod_features_from_tokens(
    client: ClickHouseClient,
    *,
    league: str,
    page_size: int = _MOD_FEATURE_BATCH_SIZE,
) -> dict[str, Any]:
    _ensure_mod_feature_table(client)
    client.execute(
        " ".join(
            [
                "ALTER TABLE poe_trade.ml_item_mod_features_v1",
                f"DELETE WHERE league = {_quote(league)}",
                "SETTINGS mutations_sync = 2",
            ]
        )
    )

    now = _now_ts()
    rows_written = 0
    non_empty_rows = 0
    next_item_id = ""
    rollup_primary_enabled = _env_bool("POE_ML_MOD_ROLLUP_PRIMARY_ENABLED", False)
    force_legacy_fallback = _env_bool("POE_ML_MOD_ROLLUP_FORCE_LEGACY", False)
    fallback_page_size_cap = max(
        1,
        _env_int("POE_ML_MOD_FEATURE_FALLBACK_PAGE_SIZE_CAP", 500),
    )
    fallback_max_memory_usage = max(
        1,
        _env_int("POE_ML_MOD_FEATURE_FALLBACK_MAX_MEMORY_USAGE", 10147483648),
    )
    fallback_max_threads = max(
        1,
        _env_int("POE_ML_MOD_FEATURE_FALLBACK_MAX_THREADS", 12),
    )
    fallback_max_execution_time = max(
        1,
        _env_int("POE_ML_MOD_FEATURE_FALLBACK_MAX_EXECUTION_TIME", 180),
    )
    fallback_max_bytes_external_group = max(
        1,
        _env_int(
            "POE_ML_MOD_FEATURE_FALLBACK_MAX_BYTES_BEFORE_EXTERNAL_GROUP_BY",
            568435456,
        ),
    )
    fallback_max_bytes_external_sort = max(
        1,
        _env_int(
            "POE_ML_MOD_FEATURE_FALLBACK_MAX_BYTES_BEFORE_EXTERNAL_SORT",
            568435456,
        ),
    )
    shadow_enabled = _env_bool("POE_ML_MOD_ROLLUP_SHADOW_ENABLED", False)
    shadow_comparison_mode = (
        os.getenv("POE_ML_MOD_ROLLUP_SHADOW_COMPARISON_MODE", "strict").strip().lower()
    )
    if shadow_comparison_mode not in {"strict", "multiset"}:
        shadow_comparison_mode = "strict"
    shadow_report_path = os.getenv(
        "POE_ML_MOD_ROLLUP_SHADOW_REPORT_PATH",
        ".sisyphus/evidence/task-5-shadow-read.json",
    )
    shadow_summary: dict[str, Any] = {
        "enabled": shadow_enabled,
        "comparison_mode": shadow_comparison_mode,
        "pages_compared": 0,
        "mismatch_count": 0,
        "mismatches": [],
    }

    fallback_summary: dict[str, Any] = {
        "active": force_legacy_fallback,
        "triggered": False,
        "reason": "forced_legacy" if force_legacy_fallback else "",
        "page_size_cap": fallback_page_size_cap,
    }

    def _legacy_query(
        cursor: str,
        *,
        fallback_mode: bool,
        limit_value: int | None = None,
    ) -> str:
        resolved_limit = max(1, int(limit_value or page_size))
        settings_clause = ""
        if fallback_mode:
            resolved_limit = min(resolved_limit, fallback_page_size_cap)
            settings_clause = " SETTINGS " + ", ".join(
                [
                    f"max_memory_usage={fallback_max_memory_usage}",
                    f"max_threads={fallback_max_threads}",
                    f"max_execution_time={fallback_max_execution_time}",
                    f"max_bytes_before_external_group_by={fallback_max_bytes_external_group}",
                    f"max_bytes_before_external_sort={fallback_max_bytes_external_sort}",
                ]
            )
        return " ".join(
            [
                "SELECT",
                "item_id,",
                "groupArray(mod_token) AS mod_tokens,",
                "max(as_of_ts) AS max_as_of_ts",
                "FROM poe_trade.ml_item_mod_tokens_v1",
                f"WHERE league = {_quote(league)}",
                f"AND item_id > {_quote(cursor)}",
                "GROUP BY item_id",
                "ORDER BY item_id",
                f"LIMIT {resolved_limit}",
                settings_clause,
                "FORMAT JSONEachRow",
            ]
        )

    def _is_memory_limit_error(exc: ClickHouseClientError) -> bool:
        message = str(exc)
        return (
            "MEMORY_LIMIT_EXCEEDED" in message
            or "Query memory limit exceeded" in message
        )

    def _query_legacy_with_backoff(
        *, cursor: str, fallback_mode: bool
    ) -> list[dict[str, Any]]:
        limit_value = max(1, page_size)
        if fallback_mode:
            limit_value = min(limit_value, fallback_page_size_cap)
        while True:
            try:
                return _query_rows(
                    client,
                    _legacy_query(
                        cursor,
                        fallback_mode=fallback_mode,
                        limit_value=limit_value,
                    ),
                )
            except ClickHouseClientError as exc:
                if not fallback_mode or not _is_memory_limit_error(exc):
                    raise
                if limit_value <= 1:
                    raise
                next_limit = max(1, limit_value // 2)
                if next_limit >= limit_value:
                    raise
                fallback_summary["triggered"] = True
                fallback_summary["reason"] = "memory_limit_backoff"
                fallback_summary["last_page_size"] = next_limit
                logger.warning(
                    "ml mod features legacy query hit memory limit; reducing page size",
                    extra={
                        "league": league,
                        "cursor": cursor,
                        "previous_page_size": limit_value,
                        "next_page_size": next_limit,
                    },
                )
                limit_value = next_limit

    def _rollup_query(cursor: str) -> str:
        return " ".join(
            [
                "SELECT",
                "item_id,",
                "groupArrayMerge(mod_tokens_state) AS mod_tokens,",
                "maxMerge(max_as_of_ts_state) AS max_as_of_ts",
                "FROM poe_trade.ml_item_mod_feature_states_v1",
                f"WHERE league = {_quote(league)}",
                f"AND item_id > {_quote(cursor)}",
                "GROUP BY item_id",
                "ORDER BY item_id",
                f"LIMIT {max(1, page_size)}",
                "FORMAT JSONEachRow",
            ]
        )

    def _normalize_shadow_row(row: dict[str, Any]) -> dict[str, Any]:
        token_values = row.get("mod_tokens")
        mod_tokens = (
            [str(token) for token in token_values]
            if isinstance(token_values, list)
            else []
        )
        return {
            "item_id": str(row.get("item_id") or ""),
            "mod_tokens": mod_tokens,
            "max_as_of_ts": str(row.get("max_as_of_ts") or ""),
        }

    def _shadow_equal(left: dict[str, Any], right: dict[str, Any]) -> bool:
        if left.get("item_id") != right.get("item_id"):
            return False
        if left.get("max_as_of_ts") != right.get("max_as_of_ts"):
            return False
        left_tokens = list(left.get("mod_tokens") or [])
        right_tokens = list(right.get("mod_tokens") or [])
        if shadow_comparison_mode == "multiset":
            return sorted(left_tokens) == sorted(right_tokens)
        return left_tokens == right_tokens

    def _append_shadow_mismatch(
        *,
        page_index: int,
        mismatch_index: int,
        legacy_row: dict[str, Any],
        candidate_row: dict[str, Any],
    ) -> None:
        mismatches = shadow_summary["mismatches"]
        if not isinstance(mismatches, list):
            return
        if len(mismatches) >= 20:
            return
        mismatches.append(
            {
                "page_index": page_index,
                "row_index": mismatch_index,
                "legacy": legacy_row,
                "candidate": candidate_row,
            }
        )

    page_index = 0

    while True:
        use_fallback_now = force_legacy_fallback or not rollup_primary_enabled
        if rollup_primary_enabled and not force_legacy_fallback:
            try:
                token_rows = _query_rows(client, _rollup_query(next_item_id))
            except ClickHouseClientError:
                fallback_summary["triggered"] = True
                fallback_summary["reason"] = "rollup_query_error"
                use_fallback_now = True
                token_rows = _query_legacy_with_backoff(
                    cursor=next_item_id,
                    fallback_mode=True,
                )
        else:
            token_rows = _query_legacy_with_backoff(
                cursor=next_item_id,
                fallback_mode=use_fallback_now,
            )
        if not token_rows:
            break
        page_index += 1

        if shadow_enabled:
            candidate_rows = _query_rows(client, _rollup_query(next_item_id))
            legacy_norm = [_normalize_shadow_row(row) for row in token_rows]
            candidate_norm = [_normalize_shadow_row(row) for row in candidate_rows]
            shadow_summary["pages_compared"] = int(shadow_summary["pages_compared"]) + 1
            paired = min(len(legacy_norm), len(candidate_norm))
            for idx in range(paired):
                if _shadow_equal(legacy_norm[idx], candidate_norm[idx]):
                    continue
                shadow_summary["mismatch_count"] = (
                    int(shadow_summary["mismatch_count"]) + 1
                )
                _append_shadow_mismatch(
                    page_index=page_index,
                    mismatch_index=idx,
                    legacy_row=legacy_norm[idx],
                    candidate_row=candidate_norm[idx],
                )
            if len(legacy_norm) != len(candidate_norm):
                shadow_summary["mismatch_count"] = (
                    int(shadow_summary["mismatch_count"]) + 1
                )
                _append_shadow_mismatch(
                    page_index=page_index,
                    mismatch_index=paired,
                    legacy_row={
                        "row_count": len(legacy_norm),
                        "marker": "legacy_row_count",
                    },
                    candidate_row={
                        "row_count": len(candidate_norm),
                        "marker": "candidate_row_count",
                    },
                )

        batch: list[dict[str, Any]] = []
        for row in token_rows:
            item_id = str(row.get("item_id") or "")
            if not item_id:
                continue
            token_values = row.get("mod_tokens")
            mod_tokens = (
                [str(token) for token in token_values]
                if isinstance(token_values, list)
                else []
            )
            mod_features = _mod_features_from_tokens(mod_tokens)
            mod_features_json = json.dumps(mod_features, separators=(",", ":"))
            if mod_features:
                non_empty_rows += 1
            batch.append(
                {
                    "league": league,
                    "item_id": item_id,
                    "mod_features_json": mod_features_json,
                    "mod_count": len(mod_tokens),
                    "as_of_ts": str(row.get("max_as_of_ts") or now),
                    "updated_at": now,
                }
            )
            next_item_id = item_id

        _insert_json_rows(client, "poe_trade.ml_item_mod_features_v1", batch)
        rows_written += len(batch)

    if shadow_enabled:
        report = {
            "schema_version": "task-5-shadow-read-v1",
            "league": league,
            "page_size": page_size,
            "status": "ok"
            if int(shadow_summary["mismatch_count"]) == 0
            else "mismatch",
            "shadow": shadow_summary,
        }
        report_path = Path(shadow_report_path)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    result: dict[str, Any] = {
        "rows_written": rows_written,
        "non_empty_rows": non_empty_rows,
    }
    if shadow_enabled:
        result["shadow_mismatch_count"] = int(shadow_summary["mismatch_count"])
    result["fallback"] = fallback_summary
    return result


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
            f"multiIf(d.category IN ({_fungible_reference_excluded_categories_sql()}), 'fallback_abstain', d.category IN ({_fungible_reference_categories_sql()}), 'fungible_reference', d.rarity IN ('Unique') AND {_structured_boosted_other_family_scope_sql('d')} != 'other' AND count() OVER (PARTITION BY d.league, d.category, d.base_type) >= 50, 'structured_boosted_other', d.rarity IN ('Unique') AND count() OVER (PARTITION BY d.league, d.category, d.base_type) >= 50, 'structured_boosted', d.category = 'cluster_jewel', 'cluster_jewel_retrieval', d.category = 'map', 'fallback_abstain', d.rarity IN ('Rare'), 'sparse_retrieval', 'fallback_abstain') AS route,",
            f"multiIf(d.category IN ({_fungible_reference_excluded_categories_sql()}), 'noisy_essence_family', d.category = 'fossil', 'stackable_fossil_family', d.category = 'scarab', 'stackable_scarab_family', d.category = 'logbook', 'stackable_logbook_family', d.category IN ({_fungible_reference_categories_sql()}), 'stackable_other_family', d.rarity IN ('Unique') AND {_structured_boosted_other_family_scope_sql('d')} != 'other' AND count() OVER (PARTITION BY d.league, d.category, d.base_type) >= 50, 'specialized_other_unique_family', d.rarity IN ('Unique') AND count() OVER (PARTITION BY d.league, d.category, d.base_type) >= 50, 'sufficient_structured_support', d.category = 'cluster_jewel', 'cluster_jewel_specialized', d.category = 'map', 'map_sparse_guardrail', d.rarity IN ('Rare'), 'sparse_high_dimensional', 'fallback_due_to_support') AS route_reason,",
            "multiIf(d.category = 'cluster_jewel', 'cluster_jewel_retrieval', d.category = 'map', 'fallback_abstain', d.rarity IN ('Rare'), 'sparse_retrieval', 'fallback_abstain') AS fallback_parent_route",
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


def build_serving_profile(
    client: ClickHouseClient,
    *,
    league: str,
    dataset_table: str = _DEFAULT_DATASET_TABLE,
    output_table: str = _DEFAULT_SERVING_PROFILE_TABLE,
    snapshot_window_id: str = "",
) -> dict[str, Any]:
    _ensure_supported_league(league)
    delete_sql = f"ALTER TABLE {output_table} DELETE WHERE league = {_quote(league)}"
    try:
        client.execute(delete_sql, settings={"mutations_sync": "2"})
    except TypeError:
        client.execute(delete_sql)

    profile_as_of_rows = _query_rows(
        client,
        " ".join(
            [
                "SELECT max(as_of_ts) AS profile_as_of_ts",
                f"FROM {dataset_table}",
                f"WHERE league = {_quote(league)}",
                "AND normalized_price_chaos IS NOT NULL",
                "AND normalized_price_chaos > 0",
                "FORMAT JSONEachRow",
            ]
        ),
    )
    profile_as_of_ts = ""
    if profile_as_of_rows:
        profile_as_of_ts = str(profile_as_of_rows[0].get("profile_as_of_ts") or "")
    if not profile_as_of_ts:
        profile_as_of_ts = _now_ts()

    now = _now_ts()
    client.execute(
        " ".join(
            [
                f"INSERT INTO {output_table}",
                "SELECT",
                f"toDateTime64('{profile_as_of_ts}', 3, 'UTC') AS profile_as_of_ts,",
                f"{_quote(snapshot_window_id)} AS snapshot_window_id,",
                "league,",
                "category,",
                "base_type,",
                "count() AS support_count_recent,",
                "quantileTDigest(0.1)(normalized_price_chaos) AS reference_price_p10,",
                "quantileTDigest(0.5)(normalized_price_chaos) AS reference_price_p50,",
                "quantileTDigest(0.9)(normalized_price_chaos) AS reference_price_p90,",
                f"toDateTime64('{now}', 3, 'UTC') AS updated_at",
                f"FROM {dataset_table}",
                f"WHERE league = {_quote(league)}",
                "AND normalized_price_chaos IS NOT NULL",
                "AND normalized_price_chaos > 0",
                "GROUP BY league, category, base_type",
            ]
        )
    )
    rows = _scalar_count(
        client,
        " ".join(
            [
                "SELECT count() AS value FROM (",
                "SELECT category, base_type",
                f"FROM {dataset_table}",
                f"WHERE league = {_quote(league)}",
                "AND normalized_price_chaos IS NOT NULL",
                "AND normalized_price_chaos > 0",
                "GROUP BY category, base_type",
                ")",
            ]
        ),
    )
    result = {
        "league": league,
        "output_table": output_table,
        "rows_written": rows,
        "snapshot_window_id": snapshot_window_id,
        "profile_as_of_ts": profile_as_of_ts,
    }
    _invalidate_serving_profile_cache(
        league=league,
        snapshot_window_id=snapshot_window_id,
        profile_as_of_ts=profile_as_of_ts,
    )
    return result


def run_full_snapshot_rebuild_backfill(
    client: ClickHouseClient,
    *,
    league: str,
    snapshot_table: str = "poe_trade.raw_poeninja_currency_overview",
    fx_table: str = "poe_trade.ml_fx_hour_v1",
    labels_table: str = "poe_trade.ml_price_labels_v1",
    dataset_table: str = "poe_trade.ml_price_dataset_v1",
    comps_table: str = "poe_trade.ml_comps_v1",
) -> dict[str, Any]:
    _ensure_supported_league(league)
    fx_result = build_fx(
        client,
        league=league,
        output_table=fx_table,
        snapshot_table=snapshot_table,
    )
    labels_result = normalize_prices(
        client,
        league=league,
        output_table=labels_table,
        fx_table=fx_table,
    )
    rebuild_window = dataset_rebuild_window(
        client,
        league=league,
        labels_table=labels_table,
    )
    rebuild_window_id = str(rebuild_window.get("window_id") or "")
    events_result = build_listing_events_and_labels(client, league=league)
    dataset_result = build_dataset(
        client,
        league=league,
        as_of_ts=datetime.now(UTC).isoformat(),
        output_table=dataset_table,
        labels_table=labels_table,
    )
    comps_result = build_comps(
        client,
        league=league,
        dataset_table=dataset_table,
        output_table=comps_table,
    )
    serving_profile_result = build_serving_profile(
        client,
        league=league,
        dataset_table=dataset_table,
        snapshot_window_id=rebuild_window_id,
    )
    return {
        "league": league,
        "mode": "explicit_full_rebuild_backfill",
        "fx_rows": _to_int(fx_result.get("rows_written"), 0),
        "labels_rows": _to_int(labels_result.get("rows_written"), 0),
        "events_rows": _to_int(
            events_result.get("rows_written", events_result.get("listing_rows", 0)),
            0,
        ),
        "dataset_rows": _to_int(dataset_result.get("rows_written"), 0),
        "comps_rows": _to_int(comps_result.get("rows_written"), 0),
        "serving_profile_rows": _to_int(
            serving_profile_result.get("rows_written"),
            0,
        ),
        "serving_profile_as_of_ts": str(
            serving_profile_result.get("profile_as_of_ts") or ""
        ),
        "rebuild_window": rebuild_window,
    }


def repair_incremental_price_dataset_v2(
    client: ClickHouseClient,
    *,
    league: str,
    labels_table: str = _DEFAULT_LABELS_TABLE,
    dataset_table: str = _DEFAULT_DATASET_TABLE,
) -> dict[str, Any]:
    _ensure_supported_league(league)
    if not labels_table.endswith("_labels_v2"):
        raise ValueError("repair_incremental_price_dataset_v2 requires *_labels_v2")
    if not dataset_table.endswith("_dataset_v2"):
        raise ValueError("repair_incremental_price_dataset_v2 requires *_dataset_v2")

    missing_predicate = " ".join(
        [
            "labels.outlier_status = 'trainable'",
            "AND labels.normalized_price_chaos IS NOT NULL",
            f"AND labels.league = {_quote(league)}",
            "AND NOT EXISTS (",
            f"SELECT 1 FROM {dataset_table} AS dataset",
            "WHERE dataset.as_of_ts = labels.as_of_ts",
            "AND dataset.realm = labels.realm",
            "AND dataset.league = labels.league",
            "AND dataset.stash_id = labels.stash_id",
            "AND dataset.item_key = labels.item_key",
            ")",
        ]
    )

    missing_before = _scalar_count(
        client,
        " ".join(
            [
                "SELECT count() AS value",
                f"FROM {labels_table} AS labels",
                f"WHERE {missing_predicate}",
            ]
        ),
    )

    if missing_before <= 0:
        return {
            "league": league,
            "labels_table": labels_table,
            "dataset_table": dataset_table,
            "rows_repaired": 0,
            "missing_before": 0,
            "missing_after": 0,
        }

    client.execute(
        " ".join(
            [
                f"INSERT INTO {dataset_table}",
                "SELECT",
                "labels.as_of_ts AS as_of_ts,",
                "labels.realm AS realm,",
                "labels.league AS league,",
                "labels.stash_id AS stash_id,",
                "labels.item_id AS item_id,",
                "labels.item_key AS item_key,",
                "items.item_name AS item_name,",
                "items.item_type_line AS item_type_line,",
                "items.base_type AS base_type,",
                "items.rarity AS rarity,",
                "items.ilvl AS ilvl,",
                "items.stack_size AS stack_size,",
                "items.corrupted AS corrupted,",
                "items.fractured AS fractured,",
                "items.synthesised AS synthesised,",
                "labels.category AS category,",
                "labels.normalized_price_chaos AS normalized_price_chaos,",
                "exec_labels.sale_probability_label AS sale_probability_label,",
                "ifNull(exec_labels.label_source, labels.label_source) AS label_source,",
                "ifNull(exec_labels.label_quality, labels.label_quality) AS label_quality,",
                "labels.outlier_status AS outlier_status,",
                "'fallback_abstain' AS route_candidate,",
                "toUInt64(0) AS support_count_recent,",
                "'low' AS support_bucket,",
                "'incremental_dataset_v2_repair' AS route_reason,",
                "'fallback_abstain' AS fallback_parent_route,",
                "if(",
                "labels.fx_hour IS NULL,",
                "CAST(NULL, 'Nullable(Float64)'),",
                "toFloat64(greatest(dateDiff('minute', labels.fx_hour, labels.as_of_ts), 0))",
                ") AS fx_freshness_minutes,",
                "toUInt16(ifNull(features.mod_token_count, 0)) AS mod_token_count,",
                "multiIf(labels.normalized_price_chaos IS NULL, 0.25, 0.6) AS confidence_hint,",
                "ifNull(features.mod_features_json, '{}') AS mod_features_json,",
                "now64(3) AS inserted_at",
                f"FROM {labels_table} AS labels",
                "INNER JOIN poe_trade.silver_ps_items_raw AS items",
                "ON items.observed_at = labels.as_of_ts",
                "AND items.realm = labels.realm",
                "AND ifNull(items.league, '') = labels.league",
                "AND items.stash_id = labels.stash_id",
                "AND ifNull(items.item_id, concat(items.stash_id, '|', items.base_type, '|', toString(items.observed_at))) = labels.item_key",
                "LEFT JOIN poe_trade.ml_execution_labels_v2 AS exec_labels",
                "ON exec_labels.as_of_ts = labels.as_of_ts",
                "AND exec_labels.realm = labels.realm",
                "AND exec_labels.league = labels.league",
                "AND exec_labels.listing_chain_id = labels.listing_chain_id",
                "LEFT JOIN poe_trade.ml_item_mod_features_v2 AS features",
                "ON features.as_of_ts = labels.as_of_ts",
                "AND features.realm = labels.realm",
                "AND features.league = labels.league",
                "AND features.stash_id = labels.stash_id",
                "AND features.item_key = labels.item_key",
                f"WHERE {missing_predicate}",
            ]
        )
    )

    missing_after = _scalar_count(
        client,
        " ".join(
            [
                "SELECT count() AS value",
                f"FROM {labels_table} AS labels",
                f"WHERE {missing_predicate}",
            ]
        ),
    )

    return {
        "league": league,
        "labels_table": labels_table,
        "dataset_table": dataset_table,
        "rows_repaired": max(0, missing_before - missing_after),
        "missing_before": missing_before,
        "missing_after": missing_after,
    }


def repair_incremental_price_labels_v2(
    client: ClickHouseClient,
    *,
    league: str,
    labels_table: str = _DEFAULT_LABELS_TABLE,
) -> dict[str, Any]:
    _ensure_supported_league(league)

    normalized_currency_expr = " ".join(
        [
            "multiIf(",
            "replaceRegexpAll(replaceRegexpAll(lowerUTF8(trimBoth(items.parsed_currency)), '\\s+', ' '), '\\s+orbs?$', '') IN ('div', 'divine', 'divines'), 'divine',",
            "replaceRegexpAll(replaceRegexpAll(lowerUTF8(trimBoth(items.parsed_currency)), '\\s+', ' '), '\\s+orbs?$', '') IN ('exa', 'exalt', 'exalted', 'exalts'), 'exalted',",
            "replaceRegexpAll(replaceRegexpAll(lowerUTF8(trimBoth(items.parsed_currency)), '\\s+', ' '), '\\s+orbs?$', '') IN ('alch', 'alchemy'), 'orb of alchemy',",
            "replaceRegexpAll(replaceRegexpAll(lowerUTF8(trimBoth(items.parsed_currency)), '\\s+', ' '), '\\s+orbs?$', '') IN ('gcp', 'gemcutter', 'gemcutters', 'gemcutter''s prism'), 'gemcutter''s prism',",
            "replaceRegexpAll(replaceRegexpAll(lowerUTF8(trimBoth(items.parsed_currency)), '\\s+', ' '), '\\s+orbs?$', '') IN ('alt', 'alteration'), 'orb of alteration',",
            "replaceRegexpAll(replaceRegexpAll(lowerUTF8(trimBoth(items.parsed_currency)), '\\s+', ' '), '\\s+orbs?$', '') IN ('scour', 'scouring'), 'orb of scouring',",
            "replaceRegexpAll(replaceRegexpAll(lowerUTF8(trimBoth(items.parsed_currency)), '\\s+', ' '), '\\s+orbs?$', '') IN ('wisdom', 'wisdom scroll'), 'scroll of wisdom',",
            "replaceRegexpAll(replaceRegexpAll(lowerUTF8(trimBoth(items.parsed_currency)), '\\s+', ' '), '\\s+orbs?$', '') IN ('annul', 'annulment'), 'orb of annulment',",
            "replaceRegexpAll(replaceRegexpAll(lowerUTF8(trimBoth(items.parsed_currency)), '\\s+', ' '), '\\s+orbs?$', '') IN ('chrome', 'chromatic'), 'chromatic',",
            "replaceRegexpAll(replaceRegexpAll(lowerUTF8(trimBoth(items.parsed_currency)), '\\s+', ' '), '\\s+orbs?$', '') IN ('fusing',), 'orb of fusing',",
            "replaceRegexpAll(replaceRegexpAll(lowerUTF8(trimBoth(items.parsed_currency)), '\\s+', ' '), '\\s+orbs?$', '') IN ('portal',), 'portal scroll',",
            "replaceRegexpAll(replaceRegexpAll(lowerUTF8(trimBoth(items.parsed_currency)), '\\s+', ' '), '\\s+orbs?$', '') IN ('bauble',), 'glassblower''s bauble',",
            "replaceRegexpAll(replaceRegexpAll(lowerUTF8(trimBoth(items.parsed_currency)), '\\s+', ' '), '\\s+orbs?$', '') IN ('aug', 'augmentation'), 'orb of augmentation',",
            "replaceRegexpAll(replaceRegexpAll(lowerUTF8(trimBoth(items.parsed_currency)), '\\s+', ' '), '\\s+orbs?$', '') IN ('transmute', 'transmutation'), 'orb of transmutation',",
            "replaceRegexpAll(replaceRegexpAll(lowerUTF8(trimBoth(items.parsed_currency)), '\\s+', ' '), '\\s+orbs?$', '') IN ('mirror',), 'mirror of kalandra',",
            "replaceRegexpAll(replaceRegexpAll(lowerUTF8(trimBoth(items.parsed_currency)), '\\s+', ' '), '\\s+orbs?$', '')",
            ")",
        ]
    )
    fx_currency_expr = (
        "replaceRegexpAll(lowerUTF8(trimBoth(fx.currency)), '\\s+orbs?$', '')"
    )
    alias_non_chaos_predicate = (
        "lowerUTF8(trimBoth(labels.parsed_currency)) NOT IN "
        "('chaos', 'chaos orb', 'chaos orbs', '')"
    )
    candidate_key_query = " ".join(
        [
            "SELECT DISTINCT",
            "items.as_of_ts AS as_of_ts,",
            "items.realm AS realm,",
            "items.league AS league,",
            "items.stash_id AS stash_id,",
            "items.item_key AS item_key",
            "FROM (",
            "SELECT",
            "observed_at AS as_of_ts,",
            "realm,",
            "ifNull(league, '') AS league,",
            "stash_id,",
            "ifNull(item_id, concat(stash_id, '|', base_type, '|', toString(observed_at))) AS item_key,",
            "toFloat64OrNull(extract(coalesce(note, forum_note, if(match(ifNull(stash_name, ''), '^~'), stash_name, '')), '^~(?:b/o|price)\\s+([0-9]+(?:\\.[0-9]+)?)')) AS parsed_amount,",
            "nullIf(extract(coalesce(note, forum_note, if(match(ifNull(stash_name, ''), '^~'), stash_name, '')), '^~(?:b/o|price)\\s+[0-9]+(?:\\.[0-9]+)?\\s+(.+)$'), '') AS parsed_currency",
            "FROM poe_trade.silver_ps_items_raw",
            ") AS items",
            f"INNER JOIN {labels_table} AS labels",
            "ON labels.as_of_ts = items.as_of_ts",
            "AND labels.realm = items.realm",
            "AND labels.league = items.league",
            "AND labels.stash_id = items.stash_id",
            "AND labels.item_key = items.item_key",
            "INNER JOIN poe_trade.ml_fx_hour_latest_v2 AS fx",
            "ON fx.league = items.league",
            f"AND {fx_currency_expr} = {normalized_currency_expr}",
            "AND fx.hour_ts = toStartOfHour(items.as_of_ts)",
            f"WHERE labels.league = {_quote(league)}",
            "AND labels.normalization_source = 'missing_fx'",
            f"AND {alias_non_chaos_predicate}",
            "AND items.parsed_amount IS NOT NULL",
            "AND fx.chaos_equivalent > 0",
        ]
    )

    candidate_before = _scalar_count(
        client,
        f"SELECT count() AS value FROM ({candidate_key_query})",
    )

    if candidate_before <= 0:
        return {
            "league": league,
            "labels_table": labels_table,
            "rows_repaired": 0,
            "missing_fx_before": 0,
            "missing_fx_after": 0,
        }

    client.execute(
        " ".join(
            [
                f"ALTER TABLE {labels_table}",
                "DELETE WHERE",
                "tuple(as_of_ts, realm, league, stash_id, item_key) IN (",
                "SELECT tuple(as_of_ts, realm, league, stash_id, item_key)",
                "FROM (",
                candidate_key_query,
                ")",
                ")",
                "SETTINGS mutations_sync = 2",
            ]
        )
    )

    client.execute(
        " ".join(
            [
                f"INSERT INTO {labels_table}",
                "SELECT",
                "items.as_of_ts AS as_of_ts,",
                "items.realm AS realm,",
                "items.league AS league,",
                "items.stash_id AS stash_id,",
                "items.item_id AS item_id,",
                "items.item_key AS item_key,",
                "concat(items.realm, '|', items.league, '|', items.stash_id, '|', ifNull(items.item_id, items.base_type)) AS listing_chain_id,",
                "items.category AS category,",
                "items.base_type AS base_type,",
                "items.stack_size AS stack_size,",
                "items.parsed_amount AS parsed_amount,",
                "lowerUTF8(trimBoth(items.parsed_currency)) AS parsed_currency,",
                "multiIf(items.parsed_amount IS NULL, 'parse_failure', items.parsed_amount <= 0, 'parse_failure', 'success') AS price_parse_status,",
                "multiIf(items.parsed_amount IS NULL, NULL, lowerUTF8(trimBoth(items.parsed_currency)) IN ('chaos', 'chaos orb', 'chaos orbs', ''), items.parsed_amount, fx.chaos_equivalent > 0, items.parsed_amount * fx.chaos_equivalent, NULL) AS normalized_price_chaos,",
                "multiIf(items.stack_size > 0 AND normalized_price_chaos IS NOT NULL, normalized_price_chaos / toFloat64(items.stack_size), normalized_price_chaos) AS unit_price_chaos,",
                "multiIf(items.parsed_amount IS NULL, 'none', lowerUTF8(trimBoth(items.parsed_currency)) IN ('chaos', 'chaos orb', 'chaos orbs', ''), 'chaos_direct', fx.chaos_equivalent > 0, 'poeninja_fx', 'missing_fx') AS normalization_source,",
                "fx.hour_ts AS fx_hour,",
                "ifNull(fx.fx_source, 'missing') AS fx_source,",
                "'trainable' AS outlier_status,",
                "'note_parse' AS label_source,",
                "'medium' AS label_quality,",
                "now64(3) AS inserted_at",
                "FROM (",
                "SELECT",
                "observed_at AS as_of_ts,",
                "realm,",
                "ifNull(league, '') AS league,",
                "stash_id,",
                "item_id,",
                "ifNull(item_id, concat(stash_id, '|', base_type, '|', toString(observed_at))) AS item_key,",
                "base_type,",
                "greatest(1, stack_size) AS stack_size,",
                "toFloat64OrNull(extract(coalesce(note, forum_note, if(match(ifNull(stash_name, ''), '^~'), stash_name, '')), '^~(?:b/o|price)\\s+([0-9]+(?:\\.[0-9]+)?)')) AS parsed_amount,",
                "nullIf(extract(coalesce(note, forum_note, if(match(ifNull(stash_name, ''), '^~'), stash_name, '')), '^~(?:b/o|price)\\s+[0-9]+(?:\\.[0-9]+)?\\s+(.+)$'), '') AS parsed_currency,",
                "multiIf(",
                "match(base_type, 'Essence'), 'essence',",
                "match(base_type, 'Fossil'), 'fossil',",
                "match(base_type, 'Scarab'), 'scarab',",
                "match(base_type, 'Cluster Jewel'), 'cluster_jewel',",
                "match(item_type_line, ' Map$'), 'map',",
                "match(base_type, 'Logbook'), 'logbook',",
                "match(base_type, 'Flask'), 'flask',",
                "'other'",
                ") AS category",
                "FROM poe_trade.silver_ps_items_raw",
                ") AS items",
                "INNER JOIN poe_trade.ml_fx_hour_latest_v2 AS fx",
                "ON fx.league = items.league",
                f"AND {fx_currency_expr} = {normalized_currency_expr}",
                "AND fx.hour_ts = toStartOfHour(items.as_of_ts)",
                "INNER JOIN (",
                candidate_key_query,
                ") AS candidate_keys",
                "ON candidate_keys.as_of_ts = items.as_of_ts",
                "AND candidate_keys.realm = items.realm",
                "AND candidate_keys.league = items.league",
                "AND candidate_keys.stash_id = items.stash_id",
                "AND candidate_keys.item_key = items.item_key",
                f"WHERE items.league = {_quote(league)}",
                "AND items.parsed_amount IS NOT NULL",
                "AND lowerUTF8(trimBoth(items.parsed_currency)) NOT IN ('chaos', 'chaos orb', 'chaos orbs', '')",
                "AND fx.chaos_equivalent > 0",
                "AND NOT EXISTS (",
                f"SELECT 1 FROM {labels_table} AS labels",
                "WHERE labels.as_of_ts = items.as_of_ts",
                "AND labels.realm = items.realm",
                "AND labels.league = items.league",
                "AND labels.stash_id = items.stash_id",
                "AND labels.item_key = items.item_key",
                "AND labels.normalization_source != 'missing_fx'",
                ")",
            ]
        )
    )

    missing_after = _scalar_count(
        client,
        f"SELECT count() AS value FROM ({candidate_key_query})",
    )

    return {
        "league": league,
        "labels_table": labels_table,
        "rows_repaired": max(0, candidate_before - missing_after),
        "missing_fx_before": candidate_before,
        "missing_fx_after": missing_after,
    }


def _bucket_ilvl(value: object) -> float:
    numeric = max(0, int(_to_float(value, 0.0)))
    return float((numeric // 5) * 5)


def _bucket_stack_size(value: object) -> float:
    numeric = max(1, int(_to_float(value, 1.0)))
    return float(min(numeric, 20))


def _bucket_mod_token_count(value: object) -> float:
    numeric = max(0, int(_to_float(value, 0.0)))
    return float(min(numeric, 16))


_MAP_T17_PATTERN = re.compile(r"\bt\s*17\b", flags=re.IGNORECASE)
_MAP_BLIGHTED_PATTERN = re.compile(r"\bblighted\b", flags=re.IGNORECASE)
_MAP_BLIGHT_RAVAGED_PATTERN = re.compile(
    r"\bblight(?:\s+|-)?ravaged\b",
    flags=re.IGNORECASE,
)
_MAP_ELDER_GUARDIAN_PATTERN = re.compile(
    r"\b(?:constrictor|eradicator|enslaver|purifier)\b",
    flags=re.IGNORECASE,
)
_MAP_SHAPER_GUARDIAN_PATTERN = re.compile(
    r"\b(?:hydra|chimera|minotaur|phoenix)\b",
    flags=re.IGNORECASE,
)
_TEXT_DELIRIUM_PATTERN = re.compile(r"\bdelir(?:ium|ious)\b", flags=re.IGNORECASE)
_TEXT_INFLUENCE_PATTERN = re.compile(
    r"\b(?:shaper|elder|crusader|redeemer|hunter|warlord)\b",
    flags=re.IGNORECASE,
)


def _combined_item_text(
    *,
    base_type: object,
    item_type_line: object,
    item_name: object,
) -> str:
    return " ".join(
        part.strip()
        for part in (
            str(base_type or ""),
            str(item_type_line or ""),
            str(item_name or ""),
        )
        if str(part or "").strip()
    )


def _regex_flag(pattern: re.Pattern[str], text: str) -> float:
    return 1.0 if pattern.search(text) else 0.0


def _map_text_features(*, category: str, combined_text: str) -> dict[str, float]:
    normalized_category = str(category or "").strip().lower()
    map_family_flag = 1.0 if normalized_category == "map" else 0.0
    map_like_flag = (
        1.0
        if (
            map_family_flag > 0.0
            or re.search(r"\bmap\b", combined_text, flags=re.IGNORECASE)
        )
        else 0.0
    )
    blighted_flag = _regex_flag(_MAP_BLIGHTED_PATTERN, combined_text)
    blight_ravaged_flag = _regex_flag(_MAP_BLIGHT_RAVAGED_PATTERN, combined_text)
    return {
        "map_family_flag": map_family_flag,
        "map_blighted_flag": map_like_flag * max(blighted_flag, blight_ravaged_flag),
        "map_blight_ravaged_flag": map_like_flag * blight_ravaged_flag,
        "map_elder_guardian_flag": map_like_flag
        * _regex_flag(_MAP_ELDER_GUARDIAN_PATTERN, combined_text),
        "map_shaper_guardian_flag": map_like_flag
        * _regex_flag(_MAP_SHAPER_GUARDIAN_PATTERN, combined_text),
        "map_t17_flag": map_like_flag * _regex_flag(_MAP_T17_PATTERN, combined_text),
    }


def _unique_state_interaction_features(
    *,
    corrupted: float,
    fractured: float,
    synthesised: float,
) -> dict[str, float]:
    corr = 1.0 if corrupted > 0.0 else 0.0
    frac = 1.0 if fractured > 0.0 else 0.0
    synth = 1.0 if synthesised > 0.0 else 0.0
    pair_count = (corr * frac) + (corr * synth) + (frac * synth)
    return {
        "unique_state_pair_count": pair_count,
        "unique_state_all_three_flag": 1.0
        if (corr > 0.0 and frac > 0.0 and synth > 0.0)
        else 0.0,
        "unique_state_corrupted_fractured": corr * frac,
        "unique_state_corrupted_synthesised": corr * synth,
        "unique_state_fractured_synthesised": frac * synth,
    }


def _text_pattern_features(combined_text: str) -> dict[str, float]:
    return {
        "text_has_delirium_flag": _regex_flag(_TEXT_DELIRIUM_PATTERN, combined_text),
        "text_has_influence_flag": _regex_flag(_TEXT_INFLUENCE_PATTERN, combined_text),
        "text_has_parentheses_flag": 1.0
        if ("(" in combined_text or ")" in combined_text)
        else 0.0,
        "text_has_hyphen_flag": 1.0 if "-" in combined_text else 0.0,
    }


def _derived_route_features(
    *,
    category: object,
    base_type: object,
    item_type_line: object,
    item_name: object,
    corrupted: float,
    fractured: float,
    synthesised: float,
    route: str,
) -> dict[str, Any]:
    family_scope = _route_family_scope(
        route,
        {
            "category": category,
            "base_type": base_type,
            "item_type_line": item_type_line,
        },
    )
    combined_text = _combined_item_text(
        base_type=base_type,
        item_type_line=item_type_line,
        item_name=item_name,
    )
    derived: dict[str, Any] = {
        "family_scope": family_scope,
        "family_scope_is_other": 1.0 if family_scope == "other" else 0.0,
    }
    derived.update(
        _unique_state_interaction_features(
            corrupted=corrupted,
            fractured=fractured,
            synthesised=synthesised,
        )
    )
    derived.update(
        _map_text_features(
            category=str(category or ""),
            combined_text=combined_text,
        )
    )
    derived.update(_text_pattern_features(combined_text))
    return derived


def _compute_price_tiers(
    aggregate_rows: list[dict[str, Any]],
) -> dict[str, dict[str, float]]:
    """Compute target encoding: percentile rank of base_type/category prices."""
    from collections import defaultdict
    import math

    base_type_prices: dict[str, list[float]] = defaultdict(list)
    category_prices: dict[str, list[float]] = defaultdict(list)

    for row in aggregate_rows:
        target_p50 = _to_float(row.get("target_p50"), 0.0)
        sample_count = max(1, _to_int(row.get("sample_count"), 1))
        if target_p50 <= 0:
            continue
        log_price = math.log1p(target_p50)
        base_type = str(row.get("base_type") or "unknown")
        category = str(row.get("category") or "other")
        base_type_prices[base_type].extend([log_price] * sample_count)
        category_prices[category].extend([log_price] * sample_count)

    def compute_percentiles(prices_dict):
        if not prices_dict:
            return {}
        all_prices = []
        for prices in prices_dict.values():
            all_prices.extend(prices)
        all_prices.sort()
        n_total = len(all_prices)

        result = {}
        for key, prices in prices_dict.items():
            if not prices:
                result[key] = 0.5
                continue
            prices_sorted = sorted(prices)
            median_idx = len(prices_sorted) // 2
            median_price = prices_sorted[median_idx]
            import bisect

            rank = bisect.bisect_left(all_prices, median_price)
            result[key] = rank / max(n_total, 1)
        return result

    return {
        "base_type": compute_percentiles(base_type_prices),
        "category": compute_percentiles(category_prices),
    }


def _route_feature_select_sql(prefix: str = "") -> list[str]:
    qualifier = f"{prefix}." if prefix else ""
    return [
        f"{qualifier}category AS category,",
        f"{qualifier}base_type AS base_type,",
        f"ifNull({qualifier}item_type_line, {qualifier}base_type) AS item_type_line,",
        f"ifNull({qualifier}rarity, '') AS rarity,",
        f"toFloat64(intDiv(toUInt16(ifNull({qualifier}ilvl, 0)), 5) * 5) AS ilvl,",
        f"toFloat64(multiIf(ifNull({qualifier}stack_size, 1) < 1, 1, ifNull({qualifier}stack_size, 1) > 20, 20, ifNull({qualifier}stack_size, 1))) AS stack_size,",
        f"toFloat64(ifNull({qualifier}corrupted, 0)) AS corrupted,",
        f"toFloat64(ifNull({qualifier}fractured, 0)) AS fractured,",
        f"toFloat64(ifNull({qualifier}synthesised, 0)) AS synthesised,",
        f"toFloat64(multiIf(ifNull({qualifier}mod_token_count, 0) < 0, 0, ifNull({qualifier}mod_token_count, 0) > 16, 16, ifNull({qualifier}mod_token_count, 0))) AS mod_token_count,",
        f"ifNull({qualifier}mod_features_json, '{{}}') AS mod_features_json,",
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
        filters.append(f"as_of_ts < toDateTime64({_quote(cutoff)}, 3, 'UTC')")
    where_clause = " AND ".join(filters)
    query = " ".join(
        [
            "SELECT",
            *_route_feature_select_sql(),
            f"{_route_family_scope_sql(route)} AS family,",
            "max(as_of_ts) AS max_as_of_ts,",
            "quantileTDigest(0.1)(normalized_price_chaos) AS target_p10,",
            "quantileTDigest(0.5)(normalized_price_chaos) AS target_p50,",
            "quantileTDigest(0.9)(normalized_price_chaos) AS target_p90,",
            "avg(toFloat64(ifNull(sale_probability_label, 0.0))) AS sale_probability_label,",
            "count() AS sample_count",
            f"FROM {dataset_table}",
            f"WHERE {where_clause}",
            "GROUP BY category, base_type, item_type_line, rarity, ilvl, stack_size, corrupted, fractured, synthesised, mod_token_count, mod_features_json, family",
            "FORMAT JSONEachRow",
        ]
    )
    return _query_rows(client, query)


def _family_counts_from_aggregate_rows(
    aggregate_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for row in aggregate_rows:
        family = str(row.get("family") or row.get("category") or "")
        if not family:
            continue
        counts[family] = counts.get(family, 0) + max(
            0,
            _to_int(row.get("sample_count"), 0),
        )
    return [{"family": family, "rows": counts[family]} for family in sorted(counts)]


def _max_as_of_ts_from_aggregate_rows(aggregate_rows: list[dict[str, Any]]) -> str:
    latest: datetime | None = None
    latest_raw = ""
    for row in aggregate_rows:
        raw = str(row.get("max_as_of_ts") or "").strip()
        if not raw:
            continue
        parsed = _parse_manifest_timestamp(raw)
        if parsed is None:
            continue
        if latest is None or parsed > latest:
            latest = parsed
            latest_raw = raw
    return latest_raw


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
            f"{_route_family_scope_sql(route)} AS family,",
            "formatDateTime(as_of_ts, '%Y-%m-%d %H:%i:%S.%f', 'UTC') AS as_of_ts",
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


def _weighted_quantile(values: list[float], weights: list[float], q: float) -> float:
    if not values or not weights or len(values) != len(weights):
        return 0.0
    quantile = min(1.0, max(0.0, _to_float(q, 0.5)))
    ordered = sorted(zip(values, weights), key=lambda pair: pair[0])
    total_weight = sum(max(weight, 0.0) for _, weight in ordered)
    if total_weight <= 0.0:
        return _median(values)
    threshold = quantile * total_weight
    seen = 0.0
    for value, weight in ordered:
        seen += max(weight, 0.0)
        if seen >= threshold:
            return float(value)
    return float(ordered[-1][0])


def _fit_single_route_bundle_from_usable_rows(
    usable_rows: list[dict[str, Any]],
    *,
    route: str,
    trained_at: str,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    sample_weights = [
        max(1.0, _to_float(row.get("sample_count"), 1.0)) for row in usable_rows
    ]
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

    price_tiers = _compute_price_tiers(usable_rows)
    feature_rows = [
        _feature_dict_from_row(row, price_tiers, route=route) for row in usable_rows
    ]
    vectorizer = DictVectorizer(sparse=True)
    X = vectorizer.fit_transform(feature_rows)
    y_p10_raw = [max(0.0, _to_float(row.get("target_p10"), 0.0)) for row in usable_rows]
    y_p50_raw = [max(0.0, _to_float(row.get("target_p50"), 0.0)) for row in usable_rows]
    y_p90_raw = [max(0.0, _to_float(row.get("target_p90"), 0.0)) for row in usable_rows]
    y_sale = [
        min(1.0, max(0.0, _to_float(row.get("sale_probability_label"), 0.0)))
        for row in usable_rows
    ]

    target_transform = "identity"
    target_transform_meta: dict[str, Any] = {}
    if route in {"structured_boosted", "structured_boosted_other"}:
        winsor_lower = max(0.0, _weighted_quantile(y_p50_raw, sample_weights, 0.02))
        winsor_upper = max(
            winsor_lower,
            _weighted_quantile(y_p50_raw, sample_weights, 0.98),
        )

        def _winsorize_price(value: float) -> float:
            return min(winsor_upper, max(winsor_lower, max(0.0, value)))

        y_p10 = [math.log1p(_winsorize_price(value)) for value in y_p10_raw]
        y_p50 = [math.log1p(_winsorize_price(value)) for value in y_p50_raw]
        y_p90 = [math.log1p(_winsorize_price(value)) for value in y_p90_raw]
        target_transform = "log1p_winsorized_p50_anchor"
        target_transform_meta = {
            "winsor_lower": winsor_lower,
            "winsor_upper": winsor_upper,
        }
    else:
        y_p10 = y_p10_raw
        y_p50 = y_p50_raw
        y_p90 = y_p90_raw

    price_model_params_by_route: dict[str, dict[str, Any]] = {
        "structured_boosted": {
            "n_estimators": 160,
            "learning_rate": 0.035,
            "max_depth": 3,
            "min_samples_leaf": 4,
            "min_samples_split": 8,
            "subsample": 0.85,
            "max_features": "sqrt",
        },
        "structured_boosted_other": {
            "n_estimators": 180,
            "learning_rate": 0.025,
            "max_depth": 2,
            "min_samples_leaf": 8,
            "min_samples_split": 16,
            "subsample": 0.85,
            "max_features": "sqrt",
        },
        "sparse_retrieval": {
            "n_estimators": 90,
            "learning_rate": 0.03,
            "max_depth": 2,
            "min_samples_leaf": 8,
            "min_samples_split": 16,
            "subsample": 0.85,
            "max_features": "sqrt",
        },
        "cluster_jewel_retrieval": {
            "n_estimators": 120,
            "learning_rate": 0.04,
            "max_depth": 2,
            "min_samples_leaf": 6,
            "min_samples_split": 12,
            "subsample": 0.9,
            "max_features": "sqrt",
        },
    }
    default_price_model_params = {
        "n_estimators": 180,
        "learning_rate": 0.035,
        "max_depth": 4,
        "min_samples_leaf": 3,
        "min_samples_split": 6,
        "subsample": 0.8,
        "max_features": "sqrt",
    }
    price_model_params = price_model_params_by_route.get(
        route, default_price_model_params
    )

    sale_model_params_by_route: dict[str, dict[str, Any]] = {
        "structured_boosted": {
            "n_estimators": 100,
            "learning_rate": 0.04,
            "max_depth": 2,
            "min_samples_leaf": 5,
            "min_samples_split": 10,
            "subsample": 0.9,
            "max_features": "sqrt",
        },
        "structured_boosted_other": {
            "n_estimators": 110,
            "learning_rate": 0.035,
            "max_depth": 2,
            "min_samples_leaf": 8,
            "min_samples_split": 16,
            "subsample": 0.9,
            "max_features": "sqrt",
        },
        "sparse_retrieval": {
            "n_estimators": 70,
            "learning_rate": 0.04,
            "max_depth": 2,
            "min_samples_leaf": 8,
            "min_samples_split": 16,
            "subsample": 0.9,
            "max_features": "sqrt",
        },
        "cluster_jewel_retrieval": {
            "n_estimators": 80,
            "learning_rate": 0.05,
            "max_depth": 2,
            "min_samples_leaf": 6,
            "min_samples_split": 12,
            "subsample": 0.95,
            "max_features": "sqrt",
        },
    }
    default_sale_model_params = {
        "n_estimators": 120,
        "learning_rate": 0.04,
        "max_depth": 3,
        "min_samples_leaf": 4,
        "min_samples_split": 8,
        "subsample": 0.85,
        "max_features": "sqrt",
    }
    sale_model_params = sale_model_params_by_route.get(route, default_sale_model_params)

    model_p10 = GradientBoostingRegressor(
        loss="quantile",
        alpha=0.10,
        **price_model_params,
        random_state=42,
    )
    model_p50 = GradientBoostingRegressor(
        loss="quantile",
        alpha=0.50,
        **price_model_params,
        random_state=43,
    )
    model_p90 = GradientBoostingRegressor(
        loss="quantile",
        alpha=0.90,
        **price_model_params,
        random_state=44,
    )
    model_p10.fit(X, y_p10, sample_weight=sample_weights)
    model_p50.fit(X, y_p50, sample_weight=sample_weights)
    model_p90.fit(X, y_p90, sample_weight=sample_weights)

    sale_model = None
    if len({round(value, 4) for value in y_sale}) > 1:
        sale_model = GradientBoostingRegressor(
            loss="squared_error",
            **sale_model_params,
            random_state=45,
        )
        sale_model.fit(X, y_sale, sample_weight=sample_weights)

    bundle = {
        "vectorizer": vectorizer,
        "price_models": {"p10": model_p10, "p50": model_p50, "p90": model_p90},
        "sale_model": sale_model,
        "route": route,
        "target_transform": target_transform,
        "target_transform_meta": target_transform_meta,
        "feature_fields": list(MODEL_FEATURE_FIELDS),
        "price_tiers": price_tiers,
        "trained_at": trained_at,
    }
    stats["sale_model_available"] = sale_model is not None
    stats["model_backend"] = "sklearn_gradient_boosting"
    return bundle, stats


def _fit_route_bundle_from_aggregates(
    aggregate_rows: list[dict[str, Any]],
    *,
    route: str,
    trained_at: str,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    usable_rows = [
        row
        for row in aggregate_rows
        if _to_float(row.get("target_p50"), 0.0) > 0.0
        and _to_int(row.get("sample_count"), 0) > 0
    ]
    if route == "structured_boosted_other":
        scoped_rows: dict[str, list[dict[str, Any]]] = {
            scope: [] for scope in sorted(_STRUCTURED_BOOSTED_OTHER_FAMILY_SCOPE_SET)
        }
        for row in usable_rows:
            scope = str(row.get("family") or "").strip().lower()
            if scope not in _STRUCTURED_BOOSTED_OTHER_FAMILY_SCOPE_SET:
                scope = _structured_boosted_other_family_scope_from_fields(
                    row.get("category"),
                    base_type=row.get("base_type"),
                    item_type_line=row.get("item_type_line"),
                )
            if scope in scoped_rows:
                scoped_rows[scope].append(row)

        family_scoped_bundles: dict[str, dict[str, Any]] = {}
        family_scope_counts: list[dict[str, Any]] = []
        support_values: list[float] = []
        support_weights: list[float] = []
        total_train_row_count = 0
        total_feature_row_count = 0
        sale_model_available = False
        for scope in sorted(scoped_rows):
            scope_bundle, scope_stats = _fit_single_route_bundle_from_usable_rows(
                scoped_rows[scope],
                route=route,
                trained_at=trained_at,
            )
            scope_train_row_count = max(
                0, _to_int(scope_stats.get("train_row_count"), 0)
            )
            scope_feature_row_count = max(
                0,
                _to_int(scope_stats.get("feature_row_count"), 0),
            )
            total_train_row_count += scope_train_row_count
            total_feature_row_count += scope_feature_row_count
            sale_model_available = sale_model_available or bool(
                scope_stats.get("sale_model_available")
            )
            scope_support_reference_p50 = _to_float(
                scope_stats.get("support_reference_p50"),
                0.0,
            )
            if scope_train_row_count > 0 and scope_support_reference_p50 > 0.0:
                support_values.append(scope_support_reference_p50)
                support_weights.append(float(scope_train_row_count))
            family_scope_counts.append(
                {
                    "family_scope": scope,
                    "rows": scope_train_row_count,
                }
            )
            if scope_bundle is not None:
                family_scoped_bundles[scope] = scope_bundle

        stats = {
            "train_row_count": total_train_row_count,
            "feature_row_count": total_feature_row_count,
            "support_reference_p50": _weighted_median(support_values, support_weights),
            "sale_model_available": sale_model_available,
            "model_backend": "heuristic_fallback",
            "family_scope_counts": family_scope_counts,
            "family_scoped_bundle_count": len(family_scoped_bundles),
        }
        if not family_scoped_bundles:
            return None, stats

        bundle = {
            "route": route,
            "trained_at": trained_at,
            "feature_fields": list(MODEL_FEATURE_FIELDS),
            "family_scoped_bundles": family_scoped_bundles,
        }
        stats["model_backend"] = "sklearn_gradient_boosting_family_scoped"
        return bundle, stats

    if route != "fungible_reference":
        return _fit_single_route_bundle_from_usable_rows(
            usable_rows,
            route=route,
            trained_at=trained_at,
        )

    scoped_rows: dict[str, list[dict[str, Any]]] = {
        scope: [] for scope in sorted(_FUNGIBLE_REFERENCE_FAMILY_SCOPE_SET)
    }
    for row in usable_rows:
        scope = str(row.get("family") or "").strip().lower()
        if scope not in _FUNGIBLE_REFERENCE_FAMILY_SCOPE_SET:
            scope = _fungible_reference_family_scope(row.get("category"))
        if scope in scoped_rows:
            scoped_rows[scope].append(row)

    family_scoped_bundles: dict[str, dict[str, Any]] = {}
    family_scope_counts: list[dict[str, Any]] = []
    support_values: list[float] = []
    support_weights: list[float] = []
    total_train_row_count = 0
    total_feature_row_count = 0
    sale_model_available = False
    for scope in sorted(scoped_rows):
        scope_bundle, scope_stats = _fit_single_route_bundle_from_usable_rows(
            scoped_rows[scope],
            route=route,
            trained_at=trained_at,
        )
        scope_train_row_count = max(0, _to_int(scope_stats.get("train_row_count"), 0))
        scope_feature_row_count = max(
            0,
            _to_int(scope_stats.get("feature_row_count"), 0),
        )
        total_train_row_count += scope_train_row_count
        total_feature_row_count += scope_feature_row_count
        sale_model_available = sale_model_available or bool(
            scope_stats.get("sale_model_available")
        )
        scope_support_reference_p50 = _to_float(
            scope_stats.get("support_reference_p50"),
            0.0,
        )
        if scope_train_row_count > 0 and scope_support_reference_p50 > 0.0:
            support_values.append(scope_support_reference_p50)
            support_weights.append(float(scope_train_row_count))
        family_scope_counts.append(
            {
                "family_scope": scope,
                "rows": scope_train_row_count,
            }
        )
        if scope_bundle is not None:
            family_scoped_bundles[scope] = scope_bundle

    stats: dict[str, Any] = {
        "train_row_count": total_train_row_count,
        "feature_row_count": total_feature_row_count,
        "support_reference_p50": _weighted_median(support_values, support_weights),
        "sale_model_available": sale_model_available,
        "model_backend": "heuristic_fallback",
        "family_scope_counts": family_scope_counts,
        "family_scoped_bundle_count": len(family_scoped_bundles),
    }
    if not family_scoped_bundles:
        return None, stats

    bundle = {
        "route": route,
        "trained_at": trained_at,
        "feature_fields": list(MODEL_FEATURE_FIELDS),
        "family_scoped_bundles": family_scoped_bundles,
    }
    stats["model_backend"] = "sklearn_gradient_boosting_family_scoped"
    return bundle, stats


def _prediction_records_from_rows(
    rows: list[dict[str, Any]],
    *,
    bundle: dict[str, Any] | None,
    reference_price: float,
    route: str = "",
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    fallback_price = max(0.1, reference_price or 0.1)
    for row in rows:
        actual = _to_float(row.get("normalized_price_chaos"), 0.0)
        if actual <= 0.0:
            continue
        predicted = (
            _predict_with_bundle(bundle=bundle, parsed_item=row) if bundle else None
        )
        if predicted is None:
            price_p50 = fallback_price
            price_p10 = max(0.1, price_p50 * 0.8)
            price_p90 = max(price_p50, price_p50 * 1.2)
            used_model = False
        else:
            price_p10 = max(
                0.1, _to_float(predicted.get("price_p10"), fallback_price * 0.8)
            )
            price_p50 = max(
                price_p10, _to_float(predicted.get("price_p50"), fallback_price)
            )
            price_p90 = max(
                price_p50, _to_float(predicted.get("price_p90"), fallback_price * 1.2)
            )
            used_model = True
        records.append(
            {
                "family": _route_family_scope(route, row),
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
    if route == "structured_boosted_other":
        return 0.56
    if route == "sparse_retrieval":
        return 0.45
    if route == "cluster_jewel_retrieval":
        return 0.45
    return 0.25


def _route_confidence_cap(route: str) -> float:
    if route == "fungible_reference":
        return 0.78
    if route == "structured_boosted":
        return 0.70
    if route == "structured_boosted_other":
        return 0.64
    if route == "sparse_retrieval":
        return 0.62
    if route == "cluster_jewel_retrieval":
        return 0.62
    return 0.55


def _model_confidence(route: str, *, support: int, train_row_count: int) -> float:
    support_factor = min(1.0, math.log1p(max(support, 0)) / math.log1p(250.0))
    training_factor = min(1.0, max(train_row_count, 0) / 1000.0)
    raw_confidence = 0.30 + 0.30 * support_factor + 0.25 * training_factor
    return min(_route_confidence_cap(route), raw_confidence)


def _low_confidence_threshold(route: str) -> float:
    if route == "fungible_reference":
        return 0.45
    if route == "structured_boosted":
        return 0.50
    if route == "structured_boosted_other":
        return 0.54
    if route in {"sparse_retrieval", "cluster_jewel_retrieval"}:
        return 0.58
    return 0.40


def _prediction_tuple(
    prediction: dict[str, Any], *, fallback_price: float
) -> tuple[float, float, float, float]:
    price_p10 = max(0.1, _to_float(prediction.get("price_p10"), fallback_price * 0.8))
    price_p50 = max(price_p10, _to_float(prediction.get("price_p50"), fallback_price))
    price_p90 = max(
        price_p50, _to_float(prediction.get("price_p90"), fallback_price * 1.2)
    )
    sale_probability = min(
        1.0,
        max(0.0, _to_float(prediction.get("sale_probability"), 0.6)),
    )
    return price_p10, price_p50, price_p90, sale_probability


def _apply_low_confidence_fallback(
    *,
    route: str,
    confidence: float,
    reference_price: float,
    model_prediction: dict[str, Any],
    incumbent_prediction: dict[str, Any] | None,
) -> dict[str, Any]:
    reference_p50 = max(0.1, reference_price)
    reference_p10 = max(0.1, reference_p50 * 0.8)
    reference_p90 = max(reference_p50, reference_p50 * 1.2)
    candidate_p10, candidate_p50, candidate_p90, candidate_sale = _prediction_tuple(
        model_prediction,
        fallback_price=reference_p50,
    )
    blended_p10 = candidate_p10
    blended_p50 = candidate_p50
    blended_p90 = candidate_p90
    blended_sale = candidate_sale
    fallback_reason = "low_confidence_reference_blend"
    if incumbent_prediction is not None:
        incumbent_p10, incumbent_p50, incumbent_p90, incumbent_sale = _prediction_tuple(
            incumbent_prediction,
            fallback_price=reference_p50,
        )
        blended_p10 = (candidate_p10 + incumbent_p10) / 2.0
        blended_p50 = (candidate_p50 + incumbent_p50) / 2.0
        blended_p90 = (candidate_p90 + incumbent_p90) / 2.0
        blended_sale = (candidate_sale + incumbent_sale) / 2.0
        fallback_reason = "low_confidence_incumbent_blend"
    threshold = max(0.01, _low_confidence_threshold(route))
    trust_weight = min(1.0, max(0.0, confidence / threshold))
    final_p10 = trust_weight * blended_p10 + (1.0 - trust_weight) * reference_p10
    final_p50 = trust_weight * blended_p50 + (1.0 - trust_weight) * reference_p50
    final_p90 = trust_weight * blended_p90 + (1.0 - trust_weight) * reference_p90
    ordered = sorted([max(0.1, final_p10), max(0.1, final_p50), max(0.1, final_p90)])
    final_sale = min(
        1.0,
        max(0.0, trust_weight * blended_sale + (1.0 - trust_weight) * 0.5),
    )
    return {
        "price_p10": ordered[0],
        "price_p50": ordered[1],
        "price_p90": ordered[2],
        "sale_probability": final_sale,
        "fallback_reason": fallback_reason,
    }


def _safe_incumbent_model_version(client: ClickHouseClient, *, league: str) -> str:
    try:
        controls = rollout_controls(client, league=league)
    except Exception:
        return ""
    incumbent = str(controls.get("incumbent_model_version") or "").strip()
    if incumbent in {"", "none"}:
        return ""
    return incumbent


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
        route=route,
        trained_at=trained_at,
    )

    artifact_file = _route_artifact_path(
        model_dir=model_dir, route=route, league=league
    )
    model_bundle_path = _route_model_bundle_path(
        model_dir=model_dir, route=route, league=league
    )
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
        "feature_schema": _build_feature_schema(MODEL_FEATURE_FIELDS),
        "train_row_count": _to_int(bundle_stats.get("train_row_count"), 0),
        "feature_row_count": _to_int(bundle_stats.get("feature_row_count"), 0),
        "family_counts": _family_counts_from_aggregate_rows(aggregate_rows),
        "family_scope_counts": bundle_stats.get("family_scope_counts") or [],
        "sale_model_available": bool(bundle_stats.get("sale_model_available")),
        "model_bundle_path": None,
        "support_reference_p50": _to_float(
            bundle_stats.get("support_reference_p50"), 0.0
        ),
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
    train_max_as_of_ts = _max_as_of_ts_from_aggregate_rows(aggregate_rows)
    bundle, bundle_stats = _fit_route_bundle_from_aggregates(
        aggregate_rows,
        route=route,
        trained_at=now,
    )
    records = _prediction_records_from_rows(
        holdout_rows,
        bundle=bundle,
        reference_price=_to_float(bundle_stats.get("support_reference_p50"), 0.0)
        or 1.0,
        route=route,
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
                "interval_80_coverage": _to_float(
                    family_metrics.get("interval_80_coverage"), 0.0
                ),
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
        "interval_80_coverage": _to_float(
            overall_metrics.get("interval_80_coverage"), 0.0
        ),
        "train_row_count": _to_int(bundle_stats.get("train_row_count"), 0),
        "feature_row_count": _to_int(bundle_stats.get("feature_row_count"), 0),
        "model_backend": bundle_stats.get("model_backend") or "heuristic_fallback",
        "eval_slice_id": _route_slice_id(route, holdout_rows),
        "eval_min_as_of_ts": str(
            (holdout_rows[0] if holdout_rows else {}).get("as_of_ts") or ""
        ),
        "eval_max_as_of_ts": str(
            (holdout_rows[-1] if holdout_rows else {}).get("as_of_ts") or ""
        ),
        "train_max_as_of_ts": train_max_as_of_ts,
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
    run_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _ensure_supported_league(league)
    _ensure_eval_contract_split(split)
    _ensure_eval_runs_table(client)
    _ensure_promotion_audit_table(client)
    _ensure_route_hotspots_table(client)
    run_id = f"stack-{int(time.time())}"
    leakage_path = _write_leakage_artifact(
        Path(output_dir),
        run_id,
        league,
        violations=0,
        reason_codes=[],
        details={},
    )
    contract = MIRAGE_EVAL_CONTRACT
    manifest = dict(
        run_manifest
        or _run_manifest(
            client,
            league=league,
            dataset_table=dataset_table,
            split_kind=split,
            fallback_seed=run_id,
        )
    )

    route_results = []
    eval_rows: list[dict[str, Any]] = []
    for route in (
        "fungible_reference",
        "structured_boosted",
        "structured_boosted_other",
        "sparse_retrieval",
        "cluster_jewel_retrieval",
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
        eval_rows.append(
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
                "interval_80_coverage": _to_float(
                    route_eval.get("interval_80_coverage"), 0.0
                ),
                "leakage_violations": 0,
                "leakage_audit_path": str(leakage_path),
                "dataset_snapshot_id": str(manifest.get("dataset_snapshot_id") or ""),
                "eval_slice_id": str(manifest.get("eval_slice_id") or ""),
                "source_watermarks_json": _source_watermarks_json(
                    manifest.get("source_watermarks")
                ),
                "recorded_at": _now_ts(),
            }
        )
    route_slice_ids = [
        str(route_result.get("eval_slice_id") or "")
        for route_result in route_results
        if str(route_result.get("eval_slice_id") or "")
    ]
    manifest["eval_slice_id"] = _eval_slice_id(
        league=league,
        split_kind=split,
        dataset_snapshot_id=str(manifest.get("dataset_snapshot_id") or ""),
        route_slice_ids=route_slice_ids,
        fallback_seed=run_id,
    )
    integrity_gate = _integrity_gate_assessment(manifest, route_results)
    leakage_violations = _to_int(
        (integrity_gate.get("leakage") or {}).get("violations"),
        0,
    )
    _write_leakage_artifact(
        Path(output_dir),
        run_id,
        league,
        violations=leakage_violations,
        reason_codes=integrity_gate.get("reason_codes") or [],
        details=integrity_gate.get("leakage") or {},
    )
    for row in eval_rows:
        row["eval_slice_id"] = str(manifest.get("eval_slice_id") or "")
        row["leakage_violations"] = leakage_violations
    try:
        _insert_json_rows(client, "poe_trade.ml_eval_runs", eval_rows)
    except ClickHouseClientError:
        for row in eval_rows:
            row.pop("dataset_snapshot_id", None)
            row.pop("eval_slice_id", None)
            row.pop("source_watermarks_json", None)
        _insert_json_rows(client, "poe_trade.ml_eval_runs", eval_rows)
    baseline = _latest_promoted_run_excluding(
        client, league=league, run_id=run_id
    ) or _latest_run_excluding(client, league=league, run_id=run_id)
    eval_slice_id = str(manifest.get("eval_slice_id") or "")
    candidate = _aggregate_eval_run_for_slice(
        client,
        league=league,
        run_id=run_id,
        eval_slice_id=eval_slice_id,
    ) or _aggregate_eval_run(client, league=league, run_id=run_id)
    baseline_for_slice: dict[str, Any] | None = None
    if baseline:
        baseline_for_slice = _aggregate_eval_run_for_slice(
            client,
            league=league,
            run_id=str(baseline.get("run_id") or ""),
            eval_slice_id=eval_slice_id,
        )
        if baseline_for_slice is None:
            baseline_for_slice = {
                "run_id": str(baseline.get("run_id") or ""),
                "avg_mdape": _to_float(baseline.get("avg_mdape"), 1.0),
                "avg_cov": _to_float(baseline.get("avg_cov"), 0.0),
                "eval_slice_id": "",
            }
    comparison = _candidate_vs_incumbent_summary(
        candidate=candidate,
        incumbent=baseline_for_slice,
    )
    comparison["integrity_gate"] = integrity_gate
    protected = _protected_cohort_check(
        client,
        league=league,
        candidate_run_id=run_id,
        incumbent_run_id=baseline_for_slice.get("run_id")
        if baseline_for_slice
        else None,
    )
    comparison["protected_cohort_regression"] = protected
    comparison["hold_reason_codes"] = _promotion_hold_reason_codes(comparison)
    verdict = "promote" if _should_promote(comparison) else "hold"
    stop_reason = _promotion_stop_reason(comparison)
    hotspot_rows = _build_route_hotspots(
        client,
        league=league,
        candidate_run_id=run_id,
        incumbent_run_id=baseline_for_slice.get("run_id")
        if baseline_for_slice
        else None,
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
                "incumbent_run_id": str(baseline_for_slice.get("run_id") or "none")
                if baseline_for_slice
                else "none",
                "candidate_model_version": f"candidate-{run_id}",
                "incumbent_model_version": str(
                    baseline_for_slice.get("run_id") or "none"
                )
                if baseline_for_slice
                else "none",
                "verdict": verdict,
                "avg_mdape_candidate": _to_float(candidate.get("avg_mdape"), 1.0),
                "avg_mdape_incumbent": _to_float(
                    baseline_for_slice.get("avg_mdape"),
                    1.0,
                )
                if baseline_for_slice
                else _to_float(candidate.get("avg_mdape"), 1.0),
                "coverage_candidate": _to_float(candidate.get("avg_cov"), 0.0),
                "coverage_incumbent": _to_float(
                    baseline_for_slice.get("avg_cov"),
                    0.0,
                )
                if baseline_for_slice
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
        "promotion_policy": {
            "shadow": _shadow_gate_policy(),
            "protected_cohort": _protected_cohort_policy(),
            "integrity": _integrity_gate_policy(),
        },
        "route_hotspots": _present_hotspots(hotspot_rows),
        "promotion_verdict": verdict,
        "stop_reason": stop_reason,
        "run_manifest": manifest,
    }


def _serving_eval_rows(
    client: ClickHouseClient,
    *,
    league: str,
    dataset_table: str,
    limit: int,
) -> list[dict[str, Any]]:
    query = " ".join(
        [
            "SELECT",
            "toString(ifNull(clipboard_text, '')) AS clipboard_text,",
            "toFloat64(ifNull(normalized_price_chaos, 0.0)) AS target_price,",
            "toFloat64(ifNull(normalized_price_chaos, 0.0)) AS credible_low,",
            "toFloat64(ifNull(normalized_price_chaos, 0.0)) AS credible_high,",
            "toString(ifNull(route, 'fallback_abstain')) AS route,",
            "toString(ifNull(rarity, '')) AS rarity,",
            "toString(ifNull(support_bucket, 'unknown')) AS support_bucket,",
            "toString(ifNull(value_band, 'unknown')) AS value_band,",
            "toString(ifNull(category, 'other')) AS category_family,",
            "toString(ifNull(league, '')) AS league",
            f"FROM {dataset_table}",
            f"WHERE league = {_quote(league)}",
            "AND normalized_price_chaos IS NOT NULL",
            "AND normalized_price_chaos > 0",
            "ORDER BY as_of_ts DESC",
            f"LIMIT {max(1, limit)}",
            "FORMAT JSONEachRow",
        ]
    )
    try:
        rows = _query_rows(client, query)
    except ClickHouseClientError:
        return []
    return [row for row in rows if str(row.get("clipboard_text") or "").strip()]


def _serving_bucket_metrics(rows: list[dict[str, Any]]) -> dict[str, float]:
    if not rows:
        return {
            "count": 0,
            "relative_abs_error_mean": 0.0,
            "extreme_miss_rate": 0.0,
            "band_hit_rate": 0.0,
            "abstain_rate": 0.0,
            "abstain_precision": 0.0,
        }
    raes = [
        abs(
            _to_float(row.get("predicted_price"), 0.0)
            - _to_float(row.get("target_price"), 0.0)
        )
        / max(_to_float(row.get("target_price"), 0.0), 0.01)
        for row in rows
    ]
    band_hits = [
        1.0
        if _to_float(row.get("credible_low"), 0.0)
        <= _to_float(row.get("predicted_price"), 0.0)
        <= _to_float(row.get("credible_high"), 0.0)
        else 0.0
        for row in rows
    ]
    abstains = [1.0 if bool(row.get("abstained")) else 0.0 for row in rows]
    abstain_true_positive = [
        1.0
        if bool(row.get("abstained"))
        and _to_float(row.get("forced_baseline_rae"), 0.0) >= 0.75
        else 0.0
        for row in rows
    ]
    total = float(len(rows))
    abstain_count = sum(abstains)
    return {
        "count": int(total),
        "relative_abs_error_mean": sum(raes) / total,
        "extreme_miss_rate": sum(1.0 for value in raes if value >= 1.0) / total,
        "band_hit_rate": sum(band_hits) / total,
        "abstain_rate": abstain_count / total,
        "abstain_precision": (sum(abstain_true_positive) / abstain_count)
        if abstain_count > 0.0
        else 0.0,
    }


def _comparable_similarity_score(
    *, item: dict[str, Any], comparable: dict[str, Any]
) -> float:
    base_type_match = (
        1.0
        if str(item.get("base_type") or "") == str(comparable.get("base_type") or "")
        else 0.0
    )
    item_mod = set(str(item.get("mod_signature") or "").split(",")) - {""}
    comp_mod = set(str(comparable.get("mod_signature") or "").split(",")) - {""}
    if not item_mod and not comp_mod:
        mod_overlap = 1.0
    else:
        denom = max(1, len(item_mod | comp_mod))
        mod_overlap = len(item_mod & comp_mod) / denom
    ilvl_delta = abs(
        _to_float(item.get("ilvl"), 0.0) - _to_float(comparable.get("ilvl"), 0.0)
    )
    ilvl_proximity = max(0.0, 1.0 - min(ilvl_delta, 20.0) / 20.0)
    state_compat = (
        1.0
        if str(item.get("state") or "") == str(comparable.get("state") or "")
        else 0.0
    )
    hours_ago = max(0.0, _to_float(comparable.get("hours_ago"), 9999.0))
    recency = max(0.0, 1.0 - min(hours_ago, 72.0) / 72.0)
    return (
        0.35 * base_type_match
        + 0.30 * mod_overlap
        + 0.10 * ilvl_proximity
        + 0.10 * state_compat
        + 0.15 * recency
    )


def _select_top_comparables(
    *,
    item: dict[str, Any],
    comparable_rows: list[dict[str, Any]],
    cap: int = 200,
    allow_broader_fallback: bool = True,
) -> list[dict[str, Any]]:
    filtered = [
        row
        for row in comparable_rows
        if str(row.get("league") or "") == str(item.get("league") or "")
        and str(row.get("item_class") or "") == str(item.get("item_class") or "")
        and (
            str(row.get("route_family") or "") == str(item.get("route_family") or "")
            or allow_broader_fallback
        )
    ]
    scored = []
    for row in filtered:
        score = _comparable_similarity_score(item=item, comparable=row)
        scored.append({**row, "similarity": score})
    scored.sort(
        key=lambda row: (
            -_to_float(row.get("similarity"), 0.0),
            _to_float(row.get("hours_ago"), 9999.0),
            str(row.get("listing_id") or ""),
        )
    )
    return scored[: max(1, cap)]


def _robust_anchor_from_comparables(
    comparable_rows: list[dict[str, Any]], *, route_kind: str
) -> dict[str, Any]:
    route_min_support = {
        "structured": 25,
        "sparse": 15,
        "fallback": 10,
    }
    floor_ratio = {
        "structured": 0.60,
        "sparse": 0.70,
        "fallback": 0.75,
    }
    recency_filtered = [
        row
        for row in comparable_rows
        if _to_float(row.get("hours_ago"), 9999.0) <= 72.0
    ]
    if len(recency_filtered) < route_min_support.get(route_kind, 10):
        return {
            "anchor_price": 0.0,
            "credible_low": 0.0,
            "credible_high": 0.0,
            "support_count": 0,
            "trim_low_count": 0,
            "trim_high_count": max(0, len(comparable_rows) - len(recency_filtered)),
            "abstain_reason": "low_support",
        }
    prices = [_to_float(row.get("price_chaos"), 0.0) for row in recency_filtered]
    prices = [price for price in prices if price > 0.0]
    if not prices:
        return {
            "anchor_price": 0.0,
            "credible_low": 0.0,
            "credible_high": 0.0,
            "support_count": 0,
            "trim_low_count": 0,
            "trim_high_count": 0,
            "abstain_reason": "no_valid_prices",
        }
    q05 = _weighted_quantile(prices, [1.0] * len(prices), 0.05)
    q25 = _weighted_quantile(prices, [1.0] * len(prices), 0.25)
    q75 = _weighted_quantile(prices, [1.0] * len(prices), 0.75)
    q95 = _weighted_quantile(prices, [1.0] * len(prices), 0.95)
    iqr = max(0.0, q75 - q25)
    low_bound = max(q25 * floor_ratio.get(route_kind, 0.75), q05 - 1.5 * iqr)
    high_bound = q95 + 1.5 * iqr
    kept = [price for price in prices if low_bound <= price <= high_bound]
    trim_low_count = sum(1 for price in prices if price < low_bound)
    trim_high_count = sum(1 for price in prices if price > high_bound) + max(
        0, len(comparable_rows) - len(recency_filtered)
    )
    if len(kept) < route_min_support.get(route_kind, 10):
        return {
            "anchor_price": 0.0,
            "credible_low": 0.0,
            "credible_high": 0.0,
            "support_count": 0,
            "trim_low_count": trim_low_count,
            "trim_high_count": trim_high_count,
            "abstain_reason": "low_support",
        }
    return {
        "anchor_price": _weighted_quantile(kept, [1.0] * len(kept), 0.5),
        "credible_low": _weighted_quantile(kept, [1.0] * len(kept), 0.25),
        "credible_high": _weighted_quantile(kept, [1.0] * len(kept), 0.75),
        "support_count": len(kept),
        "trim_low_count": trim_low_count,
        "trim_high_count": trim_high_count,
        "abstain_reason": "",
    }


def _anchor_adjustment_target(*, price: float, anchor_price: float) -> float:
    safe_anchor = max(0.01, _to_float(anchor_price, 0.01))
    safe_price = max(0.01, _to_float(price, 0.01))
    return math.log(safe_price / safe_anchor)


def _invert_anchor_adjustment_target(
    *, adjustment_target: float, anchor_price: float
) -> float:
    safe_anchor = max(0.01, _to_float(anchor_price, 0.01))
    return max(0.01, safe_anchor * math.exp(_to_float(adjustment_target, 0.0)))


def _censored_reliability_weight(*, is_sold_proxy: bool, support_count: int) -> float:
    if is_sold_proxy:
        return 1.0
    if max(0, _to_int(support_count, 0)) >= 25:
        return 0.6
    return 0.4


def _apply_recommendation_policy(
    *,
    support_count: int,
    confidence: float,
    price_p10: float,
    price_p50: float,
    price_p90: float,
) -> dict[str, Any]:
    reasons: list[str] = []
    if _to_int(support_count, 0) < 10:
        reasons.append("low_support")
    width_ratio = (_to_float(price_p90, 0.0) - _to_float(price_p10, 0.0)) / max(
        _to_float(price_p50, 0.0), 0.01
    )
    if width_ratio > 0.9:
        reasons.append("unstable_band")
    if _to_float(confidence, 0.0) < 0.35:
        reasons.append("low_confidence")
    return {
        "abstained": bool(reasons),
        "abstain_reasons": reasons,
        "band_width_ratio": width_ratio,
    }


def _expected_calibration_error(
    observations: list[dict[str, Any]], *, bins: int = 10
) -> float:
    if not observations:
        return 0.0
    bucketed: dict[int, list[dict[str, Any]]] = {}
    for row in observations:
        conf = min(0.9999, max(0.0, _to_float(row.get("confidence"), 0.0)))
        idx = min(bins - 1, int(conf * bins))
        bucketed.setdefault(idx, []).append(row)
    total = float(len(observations))
    ece = 0.0
    for bucket in bucketed.values():
        mean_conf = sum(_to_float(row.get("confidence"), 0.0) for row in bucket) / len(
            bucket
        )
        empirical = sum(
            1.0 for row in bucket if _to_float(row.get("rae"), 1.0) <= 0.30
        ) / len(bucket)
        ece += (len(bucket) / total) * abs(mean_conf - empirical)
    return ece


def evaluate_serving_path(
    client: ClickHouseClient,
    *,
    league: str,
    dataset_table: str,
    limit: int = 200,
) -> dict[str, Any]:
    _ensure_supported_league(league)
    rows = _serving_eval_rows(
        client,
        league=league,
        dataset_table=dataset_table,
        limit=limit,
    )
    scored_rows: list[dict[str, Any]] = []
    for row in rows:
        clipboard_text = str(row.get("clipboard_text") or "")
        if not clipboard_text:
            continue
        prediction = predict_one(client, league=league, clipboard_text=clipboard_text)
        predicted_price = _to_float(prediction.get("price_p50"), 0.0)
        target_price = _to_float(row.get("target_price"), 0.0)
        forced_baseline_rae = (
            abs(_to_float(row.get("credible_low"), target_price) - target_price)
            / max(target_price, 0.01)
            if target_price > 0
            else 0.0
        )
        scored_rows.append(
            {
                **row,
                "route": str(prediction.get("route") or row.get("route") or ""),
                "predicted_price": predicted_price,
                "confidence": _to_float(prediction.get("confidence"), 0.0),
                "abstained": not bool(
                    prediction.get("price_recommendation_eligible", False)
                ),
                "forced_baseline_rae": forced_baseline_rae,
            }
        )

    cohort_dimensions = (
        "route",
        "rarity",
        "support_bucket",
        "value_band",
        "category_family",
        "league",
    )
    cohorts: dict[str, dict[str, dict[str, float]]] = {}
    for dimension in cohort_dimensions:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in scored_rows:
            key = str(row.get(dimension) or "unknown")
            grouped.setdefault(key, []).append(row)
        cohorts[dimension] = {
            key: _serving_bucket_metrics(group_rows)
            for key, group_rows in grouped.items()
        }

    return {
        "league": league,
        "overall": _serving_bucket_metrics(scored_rows),
        "cohorts": cohorts,
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
    initialize_mod_features(client, league=league, dataset_table=dataset_table)
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
        run_manifest = _run_manifest(
            client,
            league=league,
            dataset_table=dataset_table,
            split_kind="rolling",
            fallback_seed=run_id,
        )
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
            run_manifest=run_manifest,
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
            run_manifest=run_manifest,
        )
        eval_result = evaluate_stack(
            client,
            league=league,
            dataset_table=dataset_table,
            model_dir=model_dir,
            split="rolling",
            output_dir=model_dir,
            run_manifest=run_manifest,
        )
        final_manifest = dict(run_manifest)
        final_manifest.update(eval_result.get("run_manifest") or {})
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
            run_manifest=final_manifest,
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
            return {
                "league": league,
                "status": "no_runs",
                "warmup": _warmup_status_payload(league),
            }
        latest = rows[0]
        eval_run_id = str(latest.get("eval_run_id") or "")
        if not eval_run_id:
            eval_run_id = _latest_eval_run_id(client, league)
        feedback = _eval_feedback_for_run(client, league=league, run_id=eval_run_id)
        latest["eval_feedback"] = feedback
        latest["candidate_vs_incumbent"] = feedback.get("candidate_vs_incumbent")
        latest["promotion_policy"] = feedback.get("promotion_policy")
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
        latest["dataset_snapshot_id"] = str(latest.get("dataset_snapshot_id") or "")
        latest["eval_slice_id"] = str(latest.get("eval_slice_id") or "")
        latest["source_watermarks"] = _parse_source_watermarks(
            latest.get("source_watermarks_json")
        )
        latest["serving_path_gate"] = _default_serving_path_gate_payload()
        latest["observability"] = _default_observability_payload()
        latest["warmup"] = _warmup_status_payload(league)
        return latest
    rows = train_run_history(client, league=league, limit=1, run_id=run)
    if not rows:
        return {
            "league": league,
            "run_id": run,
            "status": "not_found",
            "warmup": _warmup_status_payload(league),
        }
    row = rows[0]
    eval_run_id = str(row.get("eval_run_id") or "")
    if not eval_run_id:
        eval_run_id = _latest_eval_run_id(client, league)
    feedback = _eval_feedback_for_run(client, league=league, run_id=eval_run_id)
    row["eval_feedback"] = feedback
    row["candidate_vs_incumbent"] = feedback.get("candidate_vs_incumbent")
    row["promotion_policy"] = feedback.get("promotion_policy")
    row["latest_avg_mdape"] = feedback.get("latest_avg_mdape")
    row["latest_avg_interval_coverage"] = feedback.get("latest_avg_interval_coverage")
    row["route_hotspots"] = _latest_route_hotspots(client, league, run_id=eval_run_id)
    row["promotion_verdict"] = _promotion_verdict_for_run(
        client, league=league, run_id=eval_run_id
    )
    row["active_model_version"] = _active_model_version(client, league)
    row["dataset_snapshot_id"] = str(row.get("dataset_snapshot_id") or "")
    row["eval_slice_id"] = str(row.get("eval_slice_id") or "")
    row["source_watermarks"] = _parse_source_watermarks(
        row.get("source_watermarks_json")
    )
    row["serving_path_gate"] = _default_serving_path_gate_payload()
    row["observability"] = _default_observability_payload()
    row["warmup"] = _warmup_status_payload(league)
    return row


def _default_serving_path_gate_payload() -> dict[str, Any]:
    return {
        "shadow_min_days": 7,
        "shadow_min_scored_items": 10000,
        "required_consecutive_windows": 3,
        "rollback_thresholds": {
            "protected_cohort_extreme_miss_worsening": 0.15,
            "ece_degradation": 0.03,
            "abstain_spike": 0.25,
        },
    }


def _default_observability_payload() -> dict[str, Any]:
    return {
        "anchor_usage_rate": 0.0,
        "fallback_or_blend_rate": 0.0,
        "abstain_rate": 0.0,
        "outlier_trim_rate": 0.0,
        "confidence_calibration_ece": 0.0,
    }


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
    manifest_rows = _query_rows(
        client,
        " ".join(
            [
                "SELECT source_watermarks_json, leakage_violations, eval_slice_id",
                "FROM poe_trade.ml_eval_runs",
                f"WHERE league = {_quote(league)} AND run_id = {_quote(run_id)}",
                "ORDER BY recorded_at DESC",
                "LIMIT 1",
                "FORMAT JSONEachRow",
            ]
        ),
    )
    manifest_row = manifest_rows[0] if manifest_rows else {}
    integrity_gate = _integrity_gate_assessment(
        {
            "source_watermarks": _parse_source_watermarks(
                manifest_row.get("source_watermarks_json")
            )
        },
        [],
        leakage_violations=_to_int(manifest_row.get("leakage_violations"), 0),
    )
    candidate_eval_slice_id = str(manifest_row.get("eval_slice_id") or "")
    baseline = (
        _latest_promoted_run_excluding(client, league=league, run_id=run_id)
        or _latest_run_excluding(client, league=league, run_id=run_id)
        or {
            "run_id": run_id,
            "avg_mdape": latest_mdape,
            "avg_cov": latest_cov,
            "eval_slice_id": candidate_eval_slice_id,
        }
    )
    baseline_for_slice: dict[str, Any] | None = None
    if (
        str(baseline.get("run_id") or "")
        and str(baseline.get("run_id") or "") != run_id
    ):
        baseline_for_slice = _aggregate_eval_run_for_slice(
            client,
            league=league,
            run_id=str(baseline.get("run_id") or ""),
            eval_slice_id=candidate_eval_slice_id,
        )
    if baseline_for_slice is None:
        baseline_for_slice = {
            "run_id": str(baseline.get("run_id") or ""),
            "avg_mdape": _to_float(baseline.get("avg_mdape"), latest_mdape),
            "avg_cov": _to_float(baseline.get("avg_cov"), latest_cov),
            "eval_slice_id": str(baseline.get("eval_slice_id") or ""),
        }
    candidate_vs_incumbent = _candidate_vs_incumbent_summary(
        candidate={
            "run_id": run_id,
            "avg_mdape": latest_mdape,
            "avg_cov": latest_cov,
            "eval_slice_id": candidate_eval_slice_id,
        },
        incumbent={
            "run_id": str(baseline_for_slice.get("run_id") or ""),
            "avg_mdape": _to_float(baseline_for_slice.get("avg_mdape"), latest_mdape),
            "avg_cov": _to_float(baseline_for_slice.get("avg_cov"), latest_cov),
            "eval_slice_id": str(baseline_for_slice.get("eval_slice_id") or ""),
        },
    )
    protected = _protected_cohort_check(
        client,
        league=league,
        candidate_run_id=run_id,
        incumbent_run_id=str(baseline_for_slice.get("run_id") or "") or None,
    )
    candidate_vs_incumbent["integrity_gate"] = integrity_gate
    candidate_vs_incumbent["protected_cohort_regression"] = protected
    candidate_vs_incumbent["hold_reason_codes"] = _promotion_hold_reason_codes(
        candidate_vs_incumbent
    )
    candidate_vs_incumbent["promotion_policy"] = {
        "shadow": _shadow_gate_policy(),
        "protected_cohort": _protected_cohort_policy(),
        "integrity": _integrity_gate_policy(),
    }
    feedback: dict[str, Any] = {
        "status": "ok",
        "latest_eval_run_id": run_id,
        "latest_avg_mdape": latest_mdape,
        "latest_avg_interval_coverage": latest_cov,
        "candidate_vs_incumbent": candidate_vs_incumbent,
        "promotion_policy": {
            "shadow": _shadow_gate_policy(),
            "protected_cohort": _protected_cohort_policy(),
            "integrity": _integrity_gate_policy(),
        },
    }
    if str(baseline_for_slice.get("run_id") or "") == run_id:
        feedback["message"] = (
            "Only one eval run available; trend requires at least two runs."
        )
        return feedback
    prev_mdape = _to_float(baseline_for_slice.get("avg_mdape"), 1.0)
    prev_cov = _to_float(baseline_for_slice.get("avg_cov"), 0.0)
    mdape_delta = latest_mdape - prev_mdape
    cov_delta = latest_cov - prev_cov
    feedback["previous_eval_run_id"] = str(baseline_for_slice.get("run_id") or "")
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
    model_version: str | None = None,
) -> dict[str, Any]:
    _ensure_supported_league(league)
    parsed = _parse_clipboard_item(clipboard_text)
    route_bundle = _route_for_item(parsed)
    route = route_bundle["route"]
    profile = _serving_profile_lookup(
        client,
        league=league,
        category=parsed["category"],
        base_type=parsed["base_type"],
    )
    if profile["hit"]:
        support = _to_int(profile.get("support_count_recent"), 0)
        base_price = max(0.1, _to_float(profile.get("reference_price"), 1.0))
    else:
        logger.info(
            "predict_one serving profile miss; using deterministic fallback "
            "reason=%s league=%s category=%s base_type=%s",
            profile.get("reason") or "profile_miss",
            league,
            parsed["category"],
            parsed["base_type"],
        )
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

    incumbent_model_version = (
        ""
        if model_version is not None
        else _safe_incumbent_model_version(client, league=league)
    )

    artifact = _load_active_route_artifact(
        client,
        league=league,
        route=route,
        model_version=model_version,
    )
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
        sale_probability = min(
            1.0, max(0.0, float(model_prediction["sale_probability"]))
        )
        confidence = _model_confidence(
            route,
            support=support,
            train_row_count=_to_int(artifact.get("train_row_count"), 0),
        )
        fallback_reason = ""
        if confidence < _low_confidence_threshold(route):
            incumbent_prediction = None
            active_version = str(artifact.get("active_model_version") or "").strip()
            if incumbent_model_version and incumbent_model_version != active_version:
                incumbent_artifact = _load_active_route_artifact(
                    client,
                    league=league,
                    route=route,
                    model_version=incumbent_model_version,
                )
                incumbent_prediction = _predict_with_artifact(
                    artifact=incumbent_artifact,
                    parsed_item=parsed,
                )
            adjusted = _apply_low_confidence_fallback(
                route=route,
                confidence=confidence,
                reference_price=base_price,
                model_prediction=model_prediction,
                incumbent_prediction=incumbent_prediction,
            )
            price_p10 = _to_float(adjusted.get("price_p10"), price_p10)
            price_p50 = _to_float(adjusted.get("price_p50"), price_p50)
            price_p90 = _to_float(adjusted.get("price_p90"), price_p90)
            sale_probability = _to_float(
                adjusted.get("sale_probability"),
                sale_probability,
            )
            fallback_reason = str(adjusted.get("fallback_reason") or "")

    policy = _apply_recommendation_policy(
        support_count=support,
        confidence=confidence,
        price_p10=price_p10,
        price_p50=price_p50,
        price_p90=price_p90,
    )
    recommendation_eligible = sale_probability >= 0.5 and not bool(policy["abstained"])
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
        "abstained": bool(policy["abstained"]),
        "abstain_reasons": list(policy["abstain_reasons"]),
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
    incumbent_model_version = _safe_incumbent_model_version(client, league=league)
    incumbent_artifacts: dict[str, dict[str, Any]] = {}
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
            sale_probability = min(
                1.0, max(0.0, float(model_prediction["sale_probability"]))
            )
            confidence = _model_confidence(
                route,
                support=_to_int(bundle.get("support_count_recent"), 0),
                train_row_count=_to_int(artifact.get("train_row_count"), 0),
            )
            fallback_reason = ""
            if confidence < _low_confidence_threshold(route):
                incumbent_prediction = None
                active_version = str(artifact.get("active_model_version") or "").strip()
                if (
                    incumbent_model_version
                    and incumbent_model_version != active_version
                ):
                    incumbent_artifact = incumbent_artifacts.get(route)
                    if incumbent_artifact is None:
                        incumbent_artifact = _load_active_route_artifact(
                            client,
                            league=league,
                            route=route,
                            model_version=incumbent_model_version,
                        )
                        incumbent_artifacts[route] = incumbent_artifact
                    incumbent_prediction = _predict_with_artifact(
                        artifact=incumbent_artifact,
                        parsed_item=parsed,
                    )
                adjusted = _apply_low_confidence_fallback(
                    route=route,
                    confidence=confidence,
                    reference_price=base_price,
                    model_prediction=model_prediction,
                    incumbent_prediction=incumbent_prediction,
                )
                price_p10 = _to_float(adjusted.get("price_p10"), price_p10)
                price_p50 = _to_float(adjusted.get("price_p50"), price_p50)
                price_p90 = _to_float(adjusted.get("price_p90"), price_p90)
                sale_probability = _to_float(
                    adjusted.get("sale_probability"),
                    sale_probability,
                )
                fallback_reason = str(adjusted.get("fallback_reason") or "")
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
            base_comp_price_p50=base_price
            if route in {"sparse_retrieval", "cluster_jewel_retrieval"}
            else None,
            residual_adjustment=(price_p50 - base_price)
            if route in {"sparse_retrieval", "cluster_jewel_retrieval"}
            else 0.0,
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
    outlier_summary_query = " ".join(
        [
            "SELECT outlier_status, count() AS rows",
            f"FROM {_DEFAULT_LABELS_TABLE}",
            f"WHERE league = {_quote(league)}",
            "GROUP BY outlier_status",
            "ORDER BY rows DESC",
            "FORMAT JSONEachRow",
        ]
    )
    try:
        outlier_summary = _query_rows(client, outlier_summary_query)
    except ClickHouseClientError:
        outlier_summary = _query_rows(
            client,
            " ".join(
                [
                    "SELECT outlier_status, count() AS rows",
                    f"FROM {_LEGACY_LABELS_TABLE}",
                    f"WHERE league = {_quote(league)}",
                    "GROUP BY outlier_status",
                    "ORDER BY rows DESC",
                    "FORMAT JSONEachRow",
                ]
            ),
        )
    manifest_row: dict[str, Any] = {}
    try:
        manifest_rows = _query_rows(
            client,
            " ".join(
                [
                    "SELECT dataset_snapshot_id, eval_slice_id, source_watermarks_json",
                    "FROM poe_trade.ml_eval_runs",
                    f"WHERE league = {_quote(league)} AND run_id = {_quote(eval_run_id)}",
                    "ORDER BY recorded_at DESC",
                    "LIMIT 1",
                    "FORMAT JSONEachRow",
                ]
            ),
        )
        if manifest_rows:
            manifest_row = manifest_rows[0]
    except ClickHouseClientError:
        manifest_row = {}
    baseline_path = Path(
        os.getenv(
            "POE_ML_BASELINE_BENCHMARK_PATH",
            ".sisyphus/evidence/task-1-baseline.json",
        )
    )
    baseline_metadata = _baseline_benchmark_metadata(baseline_path)
    payload = {
        "league": league,
        "model_dir": model_dir,
        "eval_run_id": eval_run_id,
        "generated_at": _now_ts(),
        "promotion_verdict": promotion_verdict,
        "promotion_policy": feedback.get("promotion_policy"),
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
        "dataset_snapshot_id": str(manifest_row.get("dataset_snapshot_id") or ""),
        "eval_slice_id": str(manifest_row.get("eval_slice_id") or ""),
        "source_watermarks_json": _source_watermarks_json(
            manifest_row.get("source_watermarks_json")
        ),
        "source_watermarks": _parse_source_watermarks(
            manifest_row.get("source_watermarks_json")
        ),
        "baseline_benchmark_evidence_path": str(baseline_path),
        "baseline_benchmark": baseline_metadata,
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
    if route in {"structured_boosted", "structured_boosted_other"}:
        return "catboost_multi_quantile"
    if route in {"sparse_retrieval", "cluster_jewel_retrieval"}:
        return "comparable_residual"
    if route == "fungible_reference":
        return "reference_quantiles_family_scoped"
    return "generalized_fallback_quantiles"


def _ensure_route(route: str) -> None:
    if route in ROUTES:
        return
    raise ValueError(f"unsupported route: {route}")


def _now_ts() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def _stable_manifest_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(encoded.encode("utf-8")).hexdigest()[:16]


def dataset_rebuild_window(
    client: ClickHouseClient,
    *,
    league: str,
    labels_table: str = _DEFAULT_LABELS_TABLE,
) -> dict[str, Any]:
    _ensure_supported_league(league)
    _ensure_price_labels_table(client, labels_table)
    label_digest = (
        "cityHash64(concat("
        "toString(as_of_ts), '|', "
        "ifNull(stash_id, ''), '|', "
        "ifNull(item_id, ''), '|', "
        "ifNull(category, ''), '|', "
        "ifNull(base_type, ''), '|', "
        "toString(ifNull(round(normalized_price_chaos, 6), -1.0)), '|', "
        "ifNull(outlier_status, ''))"
        ")"
    )
    label_rows = _query_rows(
        client,
        " ".join(
            [
                "SELECT",
                "count() AS row_count,",
                "min(as_of_ts) AS min_as_of_ts,",
                "max(as_of_ts) AS max_as_of_ts,",
                f"toString(sum({label_digest})) AS digest_sum,",
                f"toString(max({label_digest})) AS digest_max",
                f"FROM {labels_table}",
                f"WHERE league = {_quote(league)}",
                "FORMAT JSONEachRow",
            ]
        ),
    )
    label_row = label_rows[0] if label_rows else {}
    label_count = _to_int(label_row.get("row_count"), 0)
    label_min_as_of_ts = str(label_row.get("min_as_of_ts") or "")
    label_max_as_of_ts = str(label_row.get("max_as_of_ts") or "")
    label_digest_sum = str(label_row.get("digest_sum") or "0")
    label_digest_max = str(label_row.get("digest_max") or "0")

    trade_metadata_rows = 0
    trade_metadata_max_retrieved_at = ""
    try:
        trade_metadata = _query_rows(
            client,
            " ".join(
                [
                    "SELECT count() AS row_count, max(retrieved_at) AS max_retrieved_at",
                    "FROM poe_trade.bronze_trade_metadata",
                    f"WHERE league = {_quote(league)}",
                    "FORMAT JSONEachRow",
                ]
            ),
        )
        trade_row = trade_metadata[0] if trade_metadata else {}
        trade_metadata_rows = _to_int(trade_row.get("row_count"), 0)
        trade_metadata_max_retrieved_at = str(trade_row.get("max_retrieved_at") or "")
    except ClickHouseClientError:
        pass

    window_seed = {
        "league": league,
        "labels_table": labels_table,
        "label_count": label_count,
        "label_min_as_of_ts": label_min_as_of_ts,
        "label_max_as_of_ts": label_max_as_of_ts,
        "label_digest_sum": label_digest_sum,
        "label_digest_max": label_digest_max,
        "trade_metadata_rows": trade_metadata_rows,
        "trade_metadata_max_retrieved_at": trade_metadata_max_retrieved_at,
    }
    return {
        "window_id": f"rebuild-window-{_stable_manifest_hash(window_seed)}",
        "label_rows": label_count,
        "label_min_as_of_ts": label_min_as_of_ts,
        "label_max_as_of_ts": label_max_as_of_ts,
        "label_digest_sum": label_digest_sum,
        "label_digest_max": label_digest_max,
        "trade_metadata_rows": trade_metadata_rows,
        "trade_metadata_max_retrieved_at": trade_metadata_max_retrieved_at,
    }


def _dataset_snapshot_manifest(
    client: ClickHouseClient, *, league: str, dataset_table: str
) -> dict[str, Any]:
    try:
        rows = _query_rows(
            client,
            " ".join(
                [
                    "SELECT count() AS row_count, min(as_of_ts) AS min_as_of_ts, max(as_of_ts) AS max_as_of_ts",
                    f"FROM {dataset_table}",
                    f"WHERE league = {_quote(league)}",
                    "FORMAT JSONEachRow",
                ]
            ),
        )
    except Exception:
        rows = []
    row = rows[0] if rows else {}
    row_count = _to_int(row.get("row_count"), 0)
    min_as_of_ts = str(row.get("min_as_of_ts") or "")
    max_as_of_ts = str(row.get("max_as_of_ts") or "")
    snapshot_seed = {
        "league": league,
        "dataset_table": dataset_table,
        "row_count": row_count,
        "min_as_of_ts": min_as_of_ts,
        "max_as_of_ts": max_as_of_ts,
    }
    return {
        "dataset_snapshot_id": f"dataset-{_stable_manifest_hash(snapshot_seed)}",
        "dataset_snapshot_rows": row_count,
        "dataset_snapshot_min_as_of_ts": min_as_of_ts,
        "dataset_snapshot_max_as_of_ts": max_as_of_ts,
    }


def _source_watermarks_manifest(
    client: ClickHouseClient,
    *,
    league: str,
    dataset_table: str = _DEFAULT_DATASET_TABLE,
    labels_table: str = _DEFAULT_LABELS_TABLE,
) -> dict[str, str]:
    watermarks: dict[str, str] = {}
    queries = (
        (
            "dataset_max_as_of_ts",
            " ".join(
                [
                    "SELECT max(as_of_ts) AS value",
                    f"FROM {dataset_table}",
                    f"WHERE league = {_quote(league)}",
                    "FORMAT JSONEachRow",
                ]
            ),
        ),
        (
            "poeninja_max_sample_time_utc",
            " ".join(
                [
                    "SELECT max(sample_time_utc) AS value",
                    "FROM poe_trade.raw_poeninja_currency_overview",
                    f"WHERE league = {_quote(league)}",
                    "FORMAT JSONEachRow",
                ]
            ),
        ),
        (
            "price_labels_max_updated_at",
            " ".join(
                [
                    (
                        "SELECT max(inserted_at) AS value"
                        if labels_table.endswith("_v2")
                        else "SELECT max(updated_at) AS value"
                    ),
                    f"FROM {labels_table}",
                    f"WHERE league = {_quote(league)}",
                    "FORMAT JSONEachRow",
                ]
            ),
        ),
    )
    for key, query in queries:
        try:
            rows = _query_rows(client, query)
        except ClickHouseClientError:
            if key == "price_labels_max_updated_at":
                try:
                    rows = _query_rows(
                        client,
                        " ".join(
                            [
                                "SELECT max(inserted_at) AS value",
                                f"FROM {labels_table}",
                                f"WHERE league = {_quote(league)}",
                                "FORMAT JSONEachRow",
                            ]
                        ),
                    )
                except ClickHouseClientError:
                    continue
            else:
                continue
        raw_value = str((rows[0] if rows else {}).get("value") or "").strip()
        if raw_value:
            watermarks[key] = raw_value
    if not watermarks:
        watermarks["captured_at"] = _now_ts()
    return watermarks


def _eval_slice_id(
    *,
    league: str,
    split_kind: str,
    dataset_snapshot_id: str,
    route_slice_ids: list[str],
    fallback_seed: str,
) -> str:
    normalized_route_slice_ids = sorted(route_slice_ids)
    seed = {
        "league": league,
        "split_kind": split_kind,
        "dataset_snapshot_id": dataset_snapshot_id,
        "route_slice_ids": normalized_route_slice_ids,
    }
    if not dataset_snapshot_id and not normalized_route_slice_ids:
        seed["fallback_seed"] = fallback_seed
    return f"eval-slice-{_stable_manifest_hash(seed)}"


def _run_manifest(
    client: ClickHouseClient,
    *,
    league: str,
    dataset_table: str,
    split_kind: str,
    fallback_seed: str,
    route_slice_ids: list[str] | None = None,
) -> dict[str, Any]:
    dataset_manifest = _dataset_snapshot_manifest(
        client,
        league=league,
        dataset_table=dataset_table,
    )
    source_watermarks = _source_watermarks_manifest(
        client,
        league=league,
        dataset_table=dataset_table,
        labels_table=_labels_table_for_dataset(dataset_table),
    )
    eval_slice_id = _eval_slice_id(
        league=league,
        split_kind=split_kind,
        dataset_snapshot_id=str(dataset_manifest.get("dataset_snapshot_id") or ""),
        route_slice_ids=route_slice_ids or [],
        fallback_seed=fallback_seed,
    )
    return {
        "dataset_snapshot_id": str(dataset_manifest.get("dataset_snapshot_id") or ""),
        "eval_slice_id": eval_slice_id,
        "source_watermarks": source_watermarks,
    }


def _source_watermarks_json(value: object) -> str:
    if isinstance(value, dict):
        return json.dumps(value, separators=(",", ":"), sort_keys=True)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return "{}"
        if isinstance(parsed, dict):
            return json.dumps(parsed, separators=(",", ":"), sort_keys=True)
    return "{}"


def _parse_source_watermarks(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, dict):
            return parsed
    return {}


def _route_slice_id(route: str, holdout_rows: list[dict[str, Any]]) -> str:
    first_as_of_ts = str(
        (holdout_rows[0] if holdout_rows else {}).get("as_of_ts") or ""
    )
    last_as_of_ts = str(
        (holdout_rows[-1] if holdout_rows else {}).get("as_of_ts") or ""
    )
    seed = {
        "route": route,
        "sample_count": len(holdout_rows),
        "first_as_of_ts": first_as_of_ts,
        "last_as_of_ts": last_as_of_ts,
        "rows_digest": _route_slice_rows_digest(holdout_rows),
    }
    return f"route-slice-{_stable_manifest_hash(seed)}"


def _route_slice_rows_digest(holdout_rows: list[dict[str, Any]]) -> str:
    if not holdout_rows:
        return ""
    digest = hashlib.sha256()
    for row in holdout_rows:
        projection = {
            "as_of_ts": str(row.get("as_of_ts") or ""),
            "category": str(row.get("category") or ""),
            "base_type": str(row.get("base_type") or ""),
            "rarity": str(row.get("rarity") or ""),
            "ilvl": _to_int(row.get("ilvl"), 0),
            "stack_size": _to_int(row.get("stack_size"), 0),
            "corrupted": _to_int(row.get("corrupted"), 0),
            "fractured": _to_int(row.get("fractured"), 0),
            "synthesised": _to_int(row.get("synthesised"), 0),
            "mod_token_count": _to_int(row.get("mod_token_count"), 0),
            "normalized_price_chaos": _to_float(
                row.get("normalized_price_chaos"),
                0.0,
            ),
            "sale_probability_label": _to_float(
                row.get("sale_probability_label"),
                0.0,
            ),
        }
        digest.update(
            json.dumps(projection, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        )
    return digest.hexdigest()


def _baseline_benchmark_metadata(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    latency = payload.get("latency_ms")
    if not isinstance(latency, dict):
        latency = {}

    def _pick_float(*keys: str) -> float | None:
        for key in keys:
            if key in payload:
                value = _to_float(payload.get(key), float("nan"))
                if not math.isnan(value):
                    return value
            if key in latency:
                value = _to_float(latency.get(key), float("nan"))
                if not math.isnan(value):
                    return value
        return None

    p50 = _pick_float("p50_ms", "p50")
    p95 = _pick_float("p95_ms", "p95")
    corpus_hash = str(
        payload.get("corpus_hash") or payload.get("request_corpus_hash") or ""
    )
    result: dict[str, Any] = {}
    if p50 is not None:
        result["p50_ms"] = p50
    if p95 is not None:
        result["p95_ms"] = p95
    if corpus_hash:
        result["corpus_hash"] = corpus_hash
    return result


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
    query_with_manifest = " ".join(
        [
            "SELECT run_id, stage, current_route, routes_done, routes_total, rows_processed, eta_seconds, chosen_backend, worker_count, memory_budget_gb, active_model_version, status, stop_reason, tuning_config_id, eval_run_id, dataset_snapshot_id, eval_slice_id, source_watermarks_json, updated_at",
            "FROM poe_trade.ml_train_runs",
            f"WHERE {' AND '.join(filters)}",
            "ORDER BY updated_at DESC",
            f"LIMIT {row_limit}",
            "FORMAT JSONEachRow",
        ]
    )
    query_without_manifest = " ".join(
        [
            "SELECT run_id, stage, current_route, routes_done, routes_total, rows_processed, eta_seconds, chosen_backend, worker_count, memory_budget_gb, active_model_version, status, stop_reason, tuning_config_id, eval_run_id, updated_at",
            "FROM poe_trade.ml_train_runs",
            f"WHERE {' AND '.join(filters)}",
            "ORDER BY updated_at DESC",
            f"LIMIT {row_limit}",
            "FORMAT JSONEachRow",
        ]
    )
    try:
        rows = _query_rows(client, query_with_manifest)
    except ClickHouseClientError:
        rows = _query_rows(client, query_without_manifest)
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
                "SELECT avg(coalesce(mdape, 1.0)) AS avg_mdape, avg(coalesce(interval_80_coverage, 0.0)) AS avg_cov, any(eval_slice_id) AS eval_slice_id",
                "FROM poe_trade.ml_eval_runs",
                f"WHERE league = {_quote(league)} AND run_id = {_quote(run_id)}",
                "FORMAT JSONEachRow",
            ]
        ),
    )
    if not rows:
        return {
            "run_id": run_id,
            "avg_mdape": 1.0,
            "avg_cov": 0.0,
            "eval_slice_id": "",
        }
    row = rows[0]
    return {
        "run_id": run_id,
        "avg_mdape": _to_float(row.get("avg_mdape"), 1.0),
        "avg_cov": _to_float(row.get("avg_cov"), 0.0),
        "eval_slice_id": str(row.get("eval_slice_id") or ""),
    }


def _aggregate_eval_run_for_slice(
    client: ClickHouseClient,
    *,
    league: str,
    run_id: str,
    eval_slice_id: str,
) -> dict[str, Any] | None:
    if not eval_slice_id.strip():
        return None
    rows = _query_rows(
        client,
        " ".join(
            [
                "SELECT avg(coalesce(mdape, 1.0)) AS avg_mdape, avg(coalesce(interval_80_coverage, 0.0)) AS avg_cov",
                "FROM poe_trade.ml_eval_runs",
                f"WHERE league = {_quote(league)} AND run_id = {_quote(run_id)} AND eval_slice_id = {_quote(eval_slice_id)}",
                "FORMAT JSONEachRow",
            ]
        ),
    )
    if not rows:
        return None
    row = rows[0]
    return {
        "run_id": run_id,
        "avg_mdape": _to_float(row.get("avg_mdape"), 1.0),
        "avg_cov": _to_float(row.get("avg_cov"), 0.0),
        "eval_slice_id": eval_slice_id,
    }


def _latest_run_excluding(
    client: ClickHouseClient, *, league: str, run_id: str
) -> dict[str, Any] | None:
    rows = _query_rows(
        client,
        " ".join(
            [
                "SELECT run_id, avg(coalesce(mdape, 1.0)) AS avg_mdape, avg(coalesce(interval_80_coverage, 0.0)) AS avg_cov, any(eval_slice_id) AS eval_slice_id, max(recorded_at) AS recorded_at",
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
        "eval_slice_id": str(row.get("eval_slice_id") or ""),
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
                "SELECT avg(coalesce(mdape, 1.0)) AS avg_mdape, avg(coalesce(interval_80_coverage, 0.0)) AS avg_cov, any(eval_slice_id) AS eval_slice_id",
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
        "eval_slice_id": str(row.get("eval_slice_id") or ""),
    }


def _integrity_gate_policy() -> dict[str, Any]:
    return {
        "league": "Mirage",
        "leakage_reason_code": PROMOTION_LEAKAGE_REASON_CODE,
        "freshness_reason_code": PROMOTION_FRESHNESS_REASON_CODE,
        "freshness_max_lag_minutes": PROMOTION_FRESHNESS_MAX_LAG_MINUTES,
        "freshness_watermark_keys": list(PROMOTION_FRESHNESS_WATERMARK_KEYS),
    }


def _shadow_gate_policy() -> dict[str, Any]:
    return {
        "league": "Mirage",
        "require_same_eval_slice": True,
        "min_relative_mdape_improvement": PROMOTION_SHADOW_MIN_RELATIVE_MDAPE_IMPROVEMENT,
        "slice_mismatch_reason_code": PROMOTION_SHADOW_SLICE_MISMATCH_REASON_CODE,
        "missing_incumbent_reason_code": PROMOTION_SHADOW_MISSING_INCUMBENT_REASON_CODE,
        "mdape_reason_code": PROMOTION_SHADOW_MDAPE_REASON_CODE,
    }


def _parse_manifest_timestamp(value: object) -> datetime | None:
    raw_value = str(value or "").strip()
    if not raw_value:
        return None
    normalized = raw_value.replace(" ", "T")
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _integrity_gate_assessment(
    run_manifest: dict[str, Any] | None,
    route_results: list[dict[str, Any]],
    *,
    leakage_violations: int | None = None,
) -> dict[str, Any]:
    policy = _integrity_gate_policy()
    reason_codes: list[str] = []

    leakage_detected = max(0, _to_int(leakage_violations, 0)) > 0
    leakage_route = ""
    leakage_train_max_as_of_ts = ""
    leakage_eval_min_as_of_ts = ""
    if leakage_detected:
        reason_codes.append(PROMOTION_LEAKAGE_REASON_CODE)

    manifest = run_manifest or {}
    source_watermarks = _parse_source_watermarks(manifest.get("source_watermarks"))
    if not source_watermarks:
        source_watermarks = _parse_source_watermarks(
            manifest.get("source_watermarks_json")
        )

    parsed_watermarks: dict[str, datetime] = {}
    observed_watermarks: dict[str, str] = {}
    for key in PROMOTION_FRESHNESS_WATERMARK_KEYS:
        raw_value = str(source_watermarks.get(key) or "").strip()
        if not raw_value:
            continue
        parsed = _parse_manifest_timestamp(raw_value)
        if parsed is None:
            continue
        observed_watermarks[key] = raw_value
        parsed_watermarks[key] = parsed

    required_keys = [str(key) for key in PROMOTION_FRESHNESS_WATERMARK_KEYS]
    missing_or_unparsed_keys = [
        key for key in required_keys if key not in parsed_watermarks
    ]
    max_observed_lag_minutes: float | None = None
    freshness_stale = False
    if len(parsed_watermarks) >= 2:
        newest = max(parsed_watermarks.values())
        oldest = min(parsed_watermarks.values())
        max_observed_lag_minutes = (newest - oldest).total_seconds() / 60.0
        freshness_stale = max_observed_lag_minutes > PROMOTION_FRESHNESS_MAX_LAG_MINUTES
    if missing_or_unparsed_keys:
        freshness_stale = True
    if freshness_stale:
        reason_codes.append(PROMOTION_FRESHNESS_REASON_CODE)

    leakage_violations_count = max(0, _to_int(leakage_violations, 0))
    if leakage_detected and leakage_violations_count == 0:
        leakage_violations_count = 1

    return {
        "pass": not reason_codes,
        "reason_codes": reason_codes,
        "leakage": {
            "detected": leakage_detected,
            "reason_code": PROMOTION_LEAKAGE_REASON_CODE if leakage_detected else None,
            "violations": leakage_violations_count,
            "route": leakage_route,
            "train_max_as_of_ts": leakage_train_max_as_of_ts,
            "eval_min_as_of_ts": leakage_eval_min_as_of_ts,
        },
        "freshness": {
            "stale": freshness_stale,
            "reason_code": PROMOTION_FRESHNESS_REASON_CODE if freshness_stale else None,
            "max_observed_lag_minutes": round(max_observed_lag_minutes, 3)
            if max_observed_lag_minutes is not None
            else None,
            "max_allowed_lag_minutes": PROMOTION_FRESHNESS_MAX_LAG_MINUTES,
            "parsed_watermark_count": len(parsed_watermarks),
            "missing_or_unparsed_keys": missing_or_unparsed_keys,
            "observed_watermarks": {
                key: observed_watermarks[key] for key in sorted(observed_watermarks)
            },
        },
        "policy": policy,
    }


def _candidate_vs_incumbent_summary(
    *, candidate: dict[str, Any], incumbent: dict[str, Any] | None
) -> dict[str, Any]:
    shadow_policy = _shadow_gate_policy()
    c_mdape = _to_float(candidate.get("avg_mdape"), 1.0)
    c_cov = _to_float(candidate.get("avg_cov"), 0.0)
    candidate_eval_slice_id = str(candidate.get("eval_slice_id") or "")
    incumbent_eval_slice_id = ""
    incumbent_missing = False
    if incumbent is None:
        i_mdape = c_mdape
        i_cov = c_cov
        incumbent_run = "none"
        incumbent_missing = True
    else:
        i_mdape = _to_float(incumbent.get("avg_mdape"), c_mdape)
        i_cov = _to_float(incumbent.get("avg_cov"), c_cov)
        incumbent_run = str(incumbent.get("run_id") or "none")
        incumbent_eval_slice_id = str(incumbent.get("eval_slice_id") or "")
    mdape_delta = i_mdape - c_mdape
    coverage_delta = c_cov - i_cov
    mdape_relative_improvement = 0.0
    if i_mdape > 0.0:
        mdape_relative_improvement = mdape_delta / i_mdape
    mdape_gate_ok = mdape_relative_improvement >= _to_float(
        shadow_policy.get("min_relative_mdape_improvement"), 0.2
    )
    same_eval_slice = (
        bool(candidate_eval_slice_id)
        and bool(incumbent_eval_slice_id)
        and candidate_eval_slice_id == incumbent_eval_slice_id
    )
    shadow_reason_codes: list[str] = []
    if incumbent_missing or str(incumbent_run or "") in {"", "none"}:
        shadow_reason_codes.append(
            str(shadow_policy.get("missing_incumbent_reason_code") or "")
        )
    elif not same_eval_slice:
        shadow_reason_codes.append(
            str(shadow_policy.get("slice_mismatch_reason_code") or "")
        )
    if not mdape_gate_ok:
        shadow_reason_codes.append(str(shadow_policy.get("mdape_reason_code") or ""))
    shadow_reason_codes = [
        code for code in shadow_reason_codes if str(code or "").strip()
    ]
    dedup_shadow_reason_codes: list[str] = []
    for reason_code in shadow_reason_codes:
        if reason_code not in dedup_shadow_reason_codes:
            dedup_shadow_reason_codes.append(reason_code)
    return {
        "candidate_run_id": str(candidate.get("run_id") or ""),
        "incumbent_run_id": incumbent_run,
        "candidate_eval_slice_id": candidate_eval_slice_id,
        "incumbent_eval_slice_id": incumbent_eval_slice_id,
        "candidate_avg_mdape": c_mdape,
        "incumbent_avg_mdape": i_mdape,
        "candidate_avg_interval_coverage": c_cov,
        "incumbent_avg_interval_coverage": i_cov,
        "mdape_improvement": mdape_delta,
        "mdape_relative_improvement": mdape_relative_improvement,
        "coverage_delta": coverage_delta,
        "coverage_floor_ok": c_cov >= MIRAGE_EVAL_CONTRACT.promotion.coverage_floor,
        "shadow_gate": {
            "pass": not dedup_shadow_reason_codes,
            "same_eval_slice": same_eval_slice,
            "incumbent_missing": incumbent_missing,
            "reason_codes": dedup_shadow_reason_codes,
            "min_relative_mdape_improvement": _to_float(
                shadow_policy.get("min_relative_mdape_improvement"),
                PROMOTION_SHADOW_MIN_RELATIVE_MDAPE_IMPROVEMENT,
            ),
            "mdape_relative_improvement": mdape_relative_improvement,
        },
        "shadow_policy": shadow_policy,
        "protected_cohort_policy": _protected_cohort_policy(),
        "integrity_policy": _integrity_gate_policy(),
    }


def _protected_cohort_policy() -> dict[str, Any]:
    return {
        "league": "Mirage",
        "cohort_dimensions": list(PROTECTED_COHORT_DIMENSIONS),
        "minimum_support_count": PROTECTED_COHORT_MIN_SUPPORT_COUNT,
        "eligible_support_buckets": list(PROTECTED_COHORT_ELIGIBLE_SUPPORT_BUCKETS),
        "max_mdape_regression": PROMOTION_PROTECTED_COHORT_MAX_REGRESSION,
        "hold_reason_code": "hold_protected_cohort_regression",
    }


def _protected_cohort_check(
    client: ClickHouseClient,
    *,
    league: str,
    candidate_run_id: str,
    incumbent_run_id: str | None,
) -> dict[str, Any]:
    policy = _protected_cohort_policy()
    if not incumbent_run_id:
        return {
            "regression": False,
            "max_mdape_regression": 0.0,
            "cohort": "none",
            "minimum_support_count": policy["minimum_support_count"],
            "evaluated_cohort_count": 0,
            "reason_code": None,
            "cohort_detail": None,
            "policy": policy,
        }
    candidate_rows = _query_rows(
        client,
        " ".join(
            [
                "SELECT route, family, support_bucket, avg(coalesce(mdape, 1.0)) AS mdape, sum(sample_count) AS support_count",
                "FROM poe_trade.ml_route_eval_v1",
                f"WHERE league = {_quote(league)} AND run_id = {_quote(candidate_run_id)}",
                "GROUP BY route, family, support_bucket",
                "FORMAT JSONEachRow",
            ]
        ),
    )
    if not candidate_rows:
        return {
            "regression": False,
            "max_mdape_regression": 0.0,
            "cohort": "none",
            "minimum_support_count": policy["minimum_support_count"],
            "evaluated_cohort_count": 0,
            "reason_code": None,
            "cohort_detail": None,
            "policy": policy,
        }
    incumbent_rows = _query_rows(
        client,
        " ".join(
            [
                "SELECT route, family, support_bucket, avg(coalesce(mdape, 1.0)) AS mdape, sum(sample_count) AS support_count",
                "FROM poe_trade.ml_route_eval_v1",
                f"WHERE league = {_quote(league)} AND run_id = {_quote(incumbent_run_id)}",
                "GROUP BY route, family, support_bucket",
                "FORMAT JSONEachRow",
            ]
        ),
    )
    incumbent_map: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in incumbent_rows:
        incumbent_route = str(row.get("route") or "")
        family = _route_family_scope(
            incumbent_route,
            {"category": row.get("family")},
        )
        incumbent_map[
            (
                incumbent_route,
                family,
                str(row.get("support_bucket") or ""),
            )
        ] = {
            "mdape": _to_float(row.get("mdape"), 1.0),
            "support_count": _to_int(row.get("support_count"), 0),
        }
    max_regression = 0.0
    worst = "none"
    worst_detail: dict[str, Any] | None = None
    evaluated_cohort_count = 0
    minimum_support = _to_int(policy.get("minimum_support_count"), 0)
    for row in candidate_rows:
        candidate_route = str(row.get("route") or "")
        family = _route_family_scope(
            candidate_route,
            {"category": row.get("family")},
        )
        key = (
            candidate_route,
            family,
            str(row.get("support_bucket") or ""),
        )
        support_bucket = key[2]
        candidate_support_count = _to_int(row.get("support_count"), 0)
        if (
            support_bucket not in PROTECTED_COHORT_ELIGIBLE_SUPPORT_BUCKETS
            or candidate_support_count < minimum_support
        ):
            continue
        evaluated_cohort_count += 1
        candidate_mdape = _to_float(row.get("mdape"), 1.0)
        incumbent_metrics = incumbent_map.get(
            key,
            {
                "mdape": candidate_mdape,
                "support_count": candidate_support_count,
            },
        )
        incumbent_mdape = _to_float(incumbent_metrics.get("mdape"), candidate_mdape)
        regression = max(candidate_mdape - incumbent_mdape, 0.0)
        if regression > max_regression:
            max_regression = regression
            worst = "|".join(key)
            worst_detail = {
                "route": key[0],
                "family": key[1],
                "support_bucket": support_bucket,
                "candidate_support_count": candidate_support_count,
                "incumbent_support_count": _to_int(
                    incumbent_metrics.get("support_count"), 0
                ),
                "candidate_mdape": candidate_mdape,
                "incumbent_mdape": incumbent_mdape,
                "mdape_regression": regression,
            }
    regression = max_regression > PROMOTION_PROTECTED_COHORT_MAX_REGRESSION
    return {
        "regression": regression,
        "max_mdape_regression": max_regression,
        "cohort": worst,
        "minimum_support_count": minimum_support,
        "evaluated_cohort_count": evaluated_cohort_count,
        "reason_code": "hold_protected_cohort_regression" if regression else None,
        "cohort_detail": worst_detail,
        "policy": policy,
    }


def _should_promote(comparison: dict[str, Any]) -> bool:
    shadow_gate = comparison.get("shadow_gate") or {}
    if not bool(shadow_gate.get("pass", True)):
        return False
    integrity = comparison.get("integrity_gate") or {}
    if not bool(integrity.get("pass", True)):
        return False
    protected = comparison.get("protected_cohort_regression") or {}
    if bool(protected.get("regression")):
        return False
    if not bool(comparison.get("coverage_floor_ok")):
        return False
    serving_gate = comparison.get("serving_path_gate") or {}
    if serving_gate:
        if not bool(serving_gate.get("pass", True)):
            return False
        if _to_float(serving_gate.get("overall_rae_improvement_relative"), 0.0) < 0.05:
            return False
        if _to_float(serving_gate.get("overall_extreme_miss_delta"), 0.0) > 0.0:
            return False
        if (
            _to_float(serving_gate.get("sparse_extreme_miss_improvement_relative"), 0.0)
            < 0.10
        ):
            return False
        if _to_float(serving_gate.get("ece_delta"), 0.0) > 0.01:
            return False
        if (
            _to_float(
                serving_gate.get("max_required_cohort_rae_regression_relative"),
                0.0,
            )
            > 0.02
        ):
            return False
        if not bool(serving_gate.get("abstain_spike_justified", True)):
            return False
        if not bool(serving_gate.get("required_dimensions_present", True)):
            return False
        if not bool(serving_gate.get("protected_cohorts_present", True)):
            return False
    return True


def _promotion_hold_reason_codes(comparison: dict[str, Any]) -> list[str]:
    reason_codes: list[str] = []

    shadow_gate = comparison.get("shadow_gate") or {}
    for reason_code in shadow_gate.get("reason_codes") or []:
        normalized = str(reason_code or "").strip()
        if normalized and normalized not in reason_codes:
            reason_codes.append(normalized)

    integrity = comparison.get("integrity_gate") or {}
    for reason_code in integrity.get("reason_codes") or []:
        normalized = str(reason_code or "").strip()
        if normalized and normalized not in reason_codes:
            reason_codes.append(normalized)

    protected = comparison.get("protected_cohort_regression") or {}
    if bool(protected.get("regression")):
        protected_reason = str(
            protected.get("reason_code") or "hold_protected_cohort_regression"
        )
        if protected_reason not in reason_codes:
            reason_codes.append(protected_reason)

    if not bool(comparison.get("coverage_floor_ok")):
        reason_codes.append("hold_coverage_floor")

    deduped: list[str] = []
    for reason_code in reason_codes:
        if reason_code not in deduped:
            deduped.append(reason_code)
    return deduped


def _promotion_stop_reason(comparison: dict[str, Any]) -> str:
    if _should_promote(comparison):
        return "promote"
    reason_codes = _promotion_hold_reason_codes(comparison)
    if reason_codes:
        return reason_codes[0]
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
    _ensure_mod_feature_sql_stage_table(client)
    _ensure_mod_feature_table(client)


def _ensure_mod_feature_table(client: ClickHouseClient) -> None:
    client.execute(
        "CREATE TABLE IF NOT EXISTS poe_trade.ml_item_mod_features_v1(league String, item_id String, mod_features_json String, mod_count UInt8, as_of_ts DateTime64(3, 'UTC'), updated_at DateTime64(3, 'UTC')) ENGINE=ReplacingMergeTree(updated_at) ORDER BY (league, item_id)"
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
        "CREATE TABLE IF NOT EXISTS poe_trade.ml_eval_runs(run_id String, route String, league String, split_kind String, raw_coverage Float64, clean_coverage Float64, outlier_drop_rate Float64, mdape Nullable(Float64), wape Nullable(Float64), rmsle Nullable(Float64), abstain_rate Nullable(Float64), interval_80_coverage Nullable(Float64), leakage_violations UInt64, leakage_audit_path String, dataset_snapshot_id String, eval_slice_id String, source_watermarks_json String, recorded_at DateTime64(3, 'UTC')) ENGINE=MergeTree() PARTITION BY toYYYYMMDD(recorded_at) ORDER BY (league, route, split_kind, recorded_at)"
    )
    client.execute(
        "ALTER TABLE poe_trade.ml_eval_runs ADD COLUMN IF NOT EXISTS dataset_snapshot_id String"
    )
    client.execute(
        "ALTER TABLE poe_trade.ml_eval_runs ADD COLUMN IF NOT EXISTS eval_slice_id String"
    )
    client.execute(
        "ALTER TABLE poe_trade.ml_eval_runs ADD COLUMN IF NOT EXISTS source_watermarks_json String"
    )


def _ensure_train_runs_table(client: ClickHouseClient) -> None:
    client.execute(
        "CREATE TABLE IF NOT EXISTS poe_trade.ml_train_runs(run_id String, league String, stage String, current_route String, routes_done UInt32, routes_total UInt32, rows_processed UInt64, eta_seconds Nullable(UInt32), chosen_backend String, worker_count UInt16, memory_budget_gb Float64, active_model_version String, status String, stop_reason String, tuning_config_id String, eval_run_id String, resume_token String, dataset_snapshot_id String, eval_slice_id String, source_watermarks_json String, started_at DateTime64(3, 'UTC'), updated_at DateTime64(3, 'UTC')) ENGINE=ReplacingMergeTree(updated_at) PARTITION BY toYYYYMMDD(started_at) ORDER BY (league, run_id, updated_at)"
    )
    client.execute(
        "ALTER TABLE poe_trade.ml_train_runs ADD COLUMN IF NOT EXISTS dataset_snapshot_id String"
    )
    client.execute(
        "ALTER TABLE poe_trade.ml_train_runs ADD COLUMN IF NOT EXISTS eval_slice_id String"
    )
    client.execute(
        "ALTER TABLE poe_trade.ml_train_runs ADD COLUMN IF NOT EXISTS source_watermarks_json String"
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


def _write_leakage_artifact(
    output_dir: Path,
    run_id: str,
    league: str,
    *,
    violations: int = 0,
    reason_codes: list[str] | None = None,
    details: dict[str, Any] | None = None,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{run_id}-no-leakage.json"
    payload = {
        "run_id": run_id,
        "league": league,
        "violations": max(0, violations),
        "reason_codes": list(reason_codes or []),
        "details": details or {},
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
    run_manifest: dict[str, Any] | None = None,
) -> None:
    _ensure_train_runs_table(client)
    now = _now_ts()
    manifest = run_manifest or {}
    row = {
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
        "dataset_snapshot_id": str(manifest.get("dataset_snapshot_id") or ""),
        "eval_slice_id": str(manifest.get("eval_slice_id") or ""),
        "source_watermarks_json": _source_watermarks_json(
            manifest.get("source_watermarks")
        ),
        "started_at": now,
        "updated_at": now,
    }
    try:
        _insert_json_rows(client, "poe_trade.ml_train_runs", [row])
    except ClickHouseClientError:
        row.pop("dataset_snapshot_id", None)
        row.pop("eval_slice_id", None)
        row.pop("source_watermarks_json", None)
        _insert_json_rows(client, "poe_trade.ml_train_runs", [row])


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


def rollout_model_versions(
    client: ClickHouseClient, *, league: str
) -> dict[str, str | None]:
    _ensure_supported_league(league)
    rows = _query_rows(
        client,
        " ".join(
            [
                "SELECT model_version, max(promoted_at) AS promoted_at",
                "FROM poe_trade.ml_model_registry_v1",
                f"WHERE league = {_quote(league)} AND promoted = 1",
                "GROUP BY model_version",
                "ORDER BY promoted_at DESC",
                "LIMIT 2",
                "FORMAT JSONEachRow",
            ]
        ),
    )
    versions = [str(row.get("model_version") or "").strip() for row in rows]
    versions = [value for value in versions if value]
    candidate = versions[0] if versions else None
    incumbent = versions[1] if len(versions) > 1 else candidate
    return {
        "candidate_model_version": candidate,
        "incumbent_model_version": incumbent,
    }


def _default_rollout_controls(*, league: str) -> dict[str, Any]:
    return {
        "league": league,
        "shadow_mode": league == "Mirage",
        "cutover_enabled": False,
        "candidate_model_version": None,
        "incumbent_model_version": None,
        "updated_at": None,
        "last_action": "default",
    }


def rollout_controls(client: ClickHouseClient, *, league: str) -> dict[str, Any]:
    _ensure_supported_league(league)
    versions = rollout_model_versions(client, league=league)
    with _ROLLOUT_CONTROL_LOCK:
        state = dict(
            _ROLLOUT_CONTROLS.get(league) or _default_rollout_controls(league=league)
        )

    candidate = (
        str(
            versions.get("candidate_model_version")
            or state.get("candidate_model_version")
            or ""
        ).strip()
        or None
    )
    incumbent = (
        str(
            versions.get("incumbent_model_version")
            or state.get("incumbent_model_version")
            or ""
        ).strip()
        or None
    )
    if candidate and not incumbent:
        incumbent = candidate

    shadow_mode = bool(state.get("shadow_mode", league == "Mirage"))
    cutover_enabled = bool(state.get("cutover_enabled", False))
    if league != "Mirage":
        shadow_mode = False
        cutover_enabled = False

    effective_serving_model_version = (
        candidate if cutover_enabled and candidate else incumbent or candidate
    )
    return {
        "league": league,
        "shadow_mode": shadow_mode,
        "cutover_enabled": cutover_enabled,
        "candidate_model_version": candidate,
        "incumbent_model_version": incumbent,
        "effective_serving_model_version": effective_serving_model_version,
        "updated_at": state.get("updated_at"),
        "last_action": str(state.get("last_action") or "default"),
    }


def update_rollout_controls(
    client: ClickHouseClient,
    *,
    league: str,
    shadow_mode: bool | None = None,
    cutover_enabled: bool | None = None,
    rollback_to_incumbent: bool = False,
) -> dict[str, Any]:
    _ensure_supported_league(league)
    if league != "Mirage":
        raise ValueError("rollout controls are currently Mirage-only")

    current = rollout_controls(client, league=league)
    next_shadow_mode = (
        bool(current.get("shadow_mode")) if shadow_mode is None else bool(shadow_mode)
    )
    next_cutover_enabled = (
        bool(current.get("cutover_enabled"))
        if cutover_enabled is None
        else bool(cutover_enabled)
    )
    next_last_action = "update"
    if rollback_to_incumbent:
        next_cutover_enabled = False
        next_last_action = "rollback_to_incumbent"
    elif cutover_enabled is not None:
        next_last_action = (
            "enable_cutover" if next_cutover_enabled else "disable_cutover"
        )
    elif shadow_mode is not None:
        next_last_action = "enable_shadow" if next_shadow_mode else "disable_shadow"

    versions = rollout_model_versions(client, league=league)
    candidate = (
        str(
            versions.get("candidate_model_version")
            or current.get("candidate_model_version")
            or ""
        ).strip()
        or None
    )
    incumbent = (
        str(
            versions.get("incumbent_model_version")
            or current.get("incumbent_model_version")
            or ""
        ).strip()
        or None
    )
    if candidate and not incumbent:
        incumbent = candidate
    if next_cutover_enabled and not candidate:
        next_cutover_enabled = False

    selected_model_version = (
        candidate if next_cutover_enabled else (incumbent or candidate)
    )
    with _ROLLOUT_CONTROL_LOCK:
        _ROLLOUT_CONTROLS[league] = {
            "league": league,
            "shadow_mode": next_shadow_mode,
            "cutover_enabled": next_cutover_enabled,
            "candidate_model_version": candidate,
            "incumbent_model_version": incumbent,
            "updated_at": _now_ts(),
            "last_action": next_last_action,
        }

    if selected_model_version:
        with _ACTIVE_MODEL_CACHE_LOCK:
            _ACTIVE_MODEL_VERSION_HINT[league] = selected_model_version
    _invalidate_active_model_cache(league=league)
    try:
        warmup_active_models(client, league=league)
    except Exception as exc:
        logger.warning(
            "rollout warmup refresh failed for league=%s: %s",
            league,
            exc,
        )
    return rollout_controls(client, league=league)


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
    with _ACTIVE_MODEL_CACHE_LOCK:
        _ACTIVE_MODEL_VERSION_HINT[league] = model_version
    try:
        versions = rollout_model_versions(client, league=league)
    except Exception:
        versions = {
            "candidate_model_version": model_version,
            "incumbent_model_version": model_version,
        }
    with _ROLLOUT_CONTROL_LOCK:
        current = dict(
            _ROLLOUT_CONTROLS.get(league) or _default_rollout_controls(league=league)
        )
        current["candidate_model_version"] = versions.get("candidate_model_version")
        current["incumbent_model_version"] = versions.get("incumbent_model_version")
        current["updated_at"] = now
        if str(current.get("last_action") or "") == "default":
            current["last_action"] = "promotion_refresh"
        _ROLLOUT_CONTROLS[league] = current
    _invalidate_active_model_cache(league=league)
    try:
        warmup_active_models(client, league=league)
    except Exception as exc:
        logger.warning(
            "model warmup failed after promotion for league=%s route=%s: %s",
            league,
            "all",
            exc,
        )


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

    category = _derive_category(
        "other",
        item_class=item_class,
        base_type=base_type,
        item_type_line=base_type,
    )
    separator_positions = [idx for idx, line in enumerate(lines) if line == "--------"]
    mod_tokens: list[str] = []
    if len(separator_positions) >= 2:
        for line in lines[separator_positions[1] + 1 :]:
            if line == "--------":
                break
            mod_tokens.append(line)
    mod_count = len(mod_tokens) if mod_tokens else max(len(lines) - 5, 0)
    mod_features_json = json.dumps(
        _mod_features_from_tokens(mod_tokens),
        separators=(",", ":"),
    )
    return {
        "rarity": rarity,
        "item_class": item_class,
        "item_name": item_name,
        "item_type_line": base_type,
        "base_type": base_type,
        "category": category,
        "mod_count": mod_count,
        "mod_token_count": mod_count,
        "mod_features_json": mod_features_json,
        "ilvl": ilvl,
        "stack_size": stack_size,
        "corrupted": corrupted,
        "fractured": fractured,
        "synthesised": synthesised,
    }


def _route_for_item(item: dict[str, Any]) -> dict[str, Any]:
    raw_category = str(item.get("category") or "").strip().lower()
    category = _canonical_model_category(raw_category)
    rarity = str(item.get("rarity") or "")
    structured_other_scope = _structured_boosted_other_family_scope_from_fields(
        raw_category,
        base_type=item.get("base_type"),
        item_type_line=item.get("item_type_line"),
    )
    if category in _FUNGIBLE_REFERENCE_EXCLUDED_CATEGORY_SET:
        return {
            "route": "fallback_abstain",
            "route_reason": "noisy_essence_family",
            "support_count_recent": 20,
        }
    if category in _FUNGIBLE_REFERENCE_CATEGORY_SET:
        family_scope = _fungible_reference_family_scope(category)
        return {
            "route": "fungible_reference",
            "route_reason": f"stackable_{family_scope}_family",
            "support_count_recent": 250,
        }
    if rarity == "Unique":
        if structured_other_scope != "other":
            return {
                "route": "structured_boosted_other",
                "route_reason": f"specialized_{structured_other_scope}_unique_family",
                "support_count_recent": 80,
            }
        return {
            "route": "structured_boosted",
            "route_reason": "structured_unique_family",
            "support_count_recent": 80,
        }
    if category == "cluster_jewel":
        return {
            "route": "cluster_jewel_retrieval",
            "route_reason": "cluster_jewel_specialized",
            "support_count_recent": 20,
        }
    if category == "map":
        return {
            "route": "fallback_abstain",
            "route_reason": "map_sparse_guardrail",
            "support_count_recent": 15,
        }
    if rarity == "Rare":
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
                f"FROM {_DEFAULT_DATASET_TABLE}",
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


def _serving_profile_lookup(
    client: ClickHouseClient,
    *,
    league: str,
    category: object,
    base_type: object,
    table: str = _DEFAULT_SERVING_PROFILE_TABLE,
) -> dict[str, Any]:
    cat = str(category)
    btype = str(base_type)
    key = (league, cat, btype)

    with _SERVING_PROFILE_CACHE_LOCK:
        cached = _SERVING_PROFILE_CACHE.get(key)
        if cached is not None:
            cache_age = max(0.0, time.time() - _to_float(cached.get("cached_at"), 0.0))
            if cache_age <= _SERVING_PROFILE_CACHE_MAX_AGE_SECONDS:
                snapshot_meta = _SERVING_PROFILE_SNAPSHOT_META.get(league)
                if snapshot_meta:
                    snapshot_matches = str(
                        snapshot_meta.get("snapshot_window_id") or ""
                    ) == str(cached.get("snapshot_window_id") or "")
                    profile_matches = str(
                        snapshot_meta.get("profile_as_of_ts") or ""
                    ) == str(cached.get("profile_as_of_ts") or "")
                    if snapshot_matches and profile_matches:
                        return {k: v for k, v in cached.items() if k != "cached_at"}
                else:
                    return {k: v for k, v in cached.items() if k != "cached_at"}

    try:
        rows = _query_rows(
            client,
            " ".join(
                [
                    "SELECT support_count_recent, reference_price_p50, snapshot_window_id, profile_as_of_ts",
                    f"FROM {table}",
                    f"WHERE league = {_quote(league)}",
                    f"AND category = {_quote(cat)}",
                    f"AND base_type = {_quote(btype)}",
                    "ORDER BY updated_at DESC",
                    "LIMIT 1",
                    "FORMAT JSONEachRow",
                ]
            ),
        )
    except ClickHouseClientError:
        logger.warning(
            "serving profile lookup query failed; using fallback "
            "league=%s category=%s base_type=%s",
            league,
            cat,
            btype,
        )
        return {
            "hit": False,
            "reason": "profile_query_error",
            "support_count_recent": 0,
            "reference_price": 1.0,
        }

    if not rows:
        return {
            "hit": False,
            "reason": "profile_row_missing",
            "support_count_recent": 0,
            "reference_price": 1.0,
        }

    row = rows[0]
    support_count = _to_int(row.get("support_count_recent"), 0)
    reference_price = _to_float(row.get("reference_price_p50"), 0.0)
    if support_count <= 0 or reference_price <= 0:
        return {
            "hit": False,
            "reason": "profile_row_invalid",
            "support_count_recent": support_count,
            "reference_price": max(0.1, reference_price),
            "snapshot_window_id": str(row.get("snapshot_window_id") or ""),
            "profile_as_of_ts": str(row.get("profile_as_of_ts") or ""),
        }

    profile_row = {
        "hit": True,
        "reason": "profile_hit",
        "support_count_recent": support_count,
        "reference_price": reference_price,
        "snapshot_window_id": str(row.get("snapshot_window_id") or ""),
        "profile_as_of_ts": str(row.get("profile_as_of_ts") or ""),
    }
    with _SERVING_PROFILE_CACHE_LOCK:
        cached_payload = dict(profile_row)
        cached_payload["cached_at"] = time.time()
        _SERVING_PROFILE_CACHE[key] = cached_payload
    return profile_row


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


def _parse_mod_features_json(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return {str(key): feature_value for key, feature_value in value.items()}
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return {}
        raw_value: object = cleaned
    elif isinstance(value, (bytes, bytearray)):
        raw_value = value
    elif value is None:
        return {}
    else:
        return {}
    try:
        parsed = json.loads(raw_value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {str(key): feature_value for key, feature_value in parsed.items()}


def _route_training_predicate(route: str) -> str:
    fungible_categories_sql = _fungible_reference_categories_sql()
    if route == "fungible_reference":
        return f"category IN ({fungible_categories_sql})"
    if route == "structured_boosted":
        return (
            "rarity = 'Unique' AND "
            f"{_structured_boosted_other_family_scope_sql()} = 'other'"
        )
    if route == "structured_boosted_other":
        return (
            "rarity = 'Unique' AND "
            f"{_structured_boosted_other_family_scope_sql()} != 'other'"
        )
    if route == "cluster_jewel_retrieval":
        return "category = 'cluster_jewel'"
    if route == "sparse_retrieval":
        return (
            "rarity = 'Rare' AND "
            f"category NOT IN ({fungible_categories_sql}, 'cluster_jewel', 'map')"
        )
    return (
        f"category NOT IN ({fungible_categories_sql}) "
        "AND ifNull(rarity, '') NOT IN ('Unique', 'Rare') "
        "AND category != 'cluster_jewel'"
    )


def _feature_dict_from_row(
    row: dict[str, Any],
    price_tiers: dict[str, dict[str, float]] | None = None,
    *,
    route: str = "",
) -> dict[str, Any]:
    corrupted = _to_float(row.get("corrupted"), 0.0)
    fractured = _to_float(row.get("fractured"), 0.0)
    synthesised = _to_float(row.get("synthesised"), 0.0)
    result = {
        "category": _model_category_for_route(row.get("category"), route=route),
        "base_type": str(row.get("base_type") or "unknown"),
        "rarity": str(row.get("rarity") or ""),
        "ilvl": _bucket_ilvl(row.get("ilvl")),
        "stack_size": _bucket_stack_size(row.get("stack_size")),
        "corrupted": corrupted,
        "fractured": fractured,
        "synthesised": synthesised,
        "mod_token_count": _bucket_mod_token_count(row.get("mod_token_count")),
    }
    result.update(
        _derived_route_features(
            category=row.get("category"),
            base_type=row.get("base_type"),
            item_type_line=row.get("item_type_line", row.get("base_type")),
            item_name=row.get("item_name"),
            corrupted=corrupted,
            fractured=fractured,
            synthesised=synthesised,
            route=route,
        )
    )
    mod_features = _parse_mod_features_json(row.get("mod_features_json", "{}"))
    discovered = set(_discovered_mod_features)
    # mod_features_json keys are already in format: {ModName}_tier / {ModName}_roll
    for feature_key, value in mod_features.items():
        if feature_key in discovered:
            result[feature_key] = _to_float(value, 0.0)
    for mod_feature in discovered:
        if mod_feature not in result:
            result[mod_feature] = 0.0
    if price_tiers:
        base_type = str(result["base_type"])
        category = str(result["category"])
        result["base_type_price_tier"] = price_tiers.get("base_type", {}).get(
            base_type, 0.5
        )
        result["category_price_tier"] = price_tiers.get("category", {}).get(
            category, 0.5
        )
    return result


def _feature_dict_from_parsed_item(
    item: dict[str, Any],
    price_tiers: dict[str, dict[str, float]] | None = None,
    feature_fields: list[str] | tuple[str, ...] | None = None,
    *,
    route: str = "",
) -> dict[str, Any]:
    corrupted = _to_float(item.get("corrupted"), 0.0)
    fractured = _to_float(item.get("fractured"), 0.0)
    synthesised = _to_float(item.get("synthesised"), 0.0)
    result = {
        "category": _model_category_for_route(item.get("category"), route=route),
        "base_type": str(item.get("base_type") or "unknown"),
        "rarity": str(item.get("rarity") or ""),
        "ilvl": _bucket_ilvl(item.get("ilvl")),
        "stack_size": _bucket_stack_size(item.get("stack_size")),
        "corrupted": corrupted,
        "fractured": fractured,
        "synthesised": synthesised,
        "mod_token_count": _bucket_mod_token_count(
            item.get("mod_token_count", item.get("mod_count"))
        ),
    }
    result.update(
        _derived_route_features(
            category=item.get("category"),
            base_type=item.get("base_type"),
            item_type_line=item.get("item_type_line", item.get("base_type")),
            item_name=item.get("item_name"),
            corrupted=corrupted,
            fractured=fractured,
            synthesised=synthesised,
            route=route,
        )
    )
    mod_features = _parse_mod_features_json(item.get("mod_features_json", "{}"))
    discovered = (
        {feature for feature in feature_fields if feature not in BASE_FEATURE_FIELDS}
        if feature_fields is not None
        else set(_discovered_mod_features)
    )
    for feature_key, value in mod_features.items():
        if feature_key in discovered:
            result[feature_key] = _to_float(value, 0.0)
    for mod_feature in discovered:
        if mod_feature not in result:
            result[mod_feature] = 0.0
    if price_tiers:
        base_type = str(result["base_type"])
        category = str(result["category"])
        result["base_type_price_tier"] = price_tiers.get("base_type", {}).get(
            base_type, 0.5
        )
        result["category_price_tier"] = price_tiers.get("category", {}).get(
            category, 0.5
        )
    else:
        result["base_type_price_tier"] = 0.5
        result["category_price_tier"] = 0.5
    return result


def _route_model_bundle_path(*, model_dir: str, route: str, league: str) -> Path:
    return Path(model_dir) / f"{route}-{league}.joblib"


def _load_active_route_artifact(
    client: ClickHouseClient,
    *,
    league: str,
    route: str,
    model_version: str | None = None,
) -> dict[str, Any]:
    target_model_version = str(model_version or "").strip()
    if target_model_version:
        metadata = _model_metadata_for_route_version(
            client,
            league=league,
            route=route,
            model_version=target_model_version,
        )
    else:
        metadata = _get_cached_model_metadata(client, league=league, route=route)
    model_dir = str(metadata.get("model_dir") or "")
    if not model_dir:
        return {}
    artifact = _load_json_file(
        _route_artifact_path(model_dir=model_dir, route=route, league=league)
    )
    if not artifact:
        return {}
    hydrated = dict(artifact)
    hydrated["active_model_version"] = str(metadata.get("model_version") or "")
    hydrated["active_model_promoted_at"] = str(metadata.get("promoted_at") or "")
    return hydrated


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


def _route_cache_key(league: str, route: str) -> tuple[str, str]:
    return (league, route)


def reset_serving_runtime_caches(*, league: str | None = None) -> None:
    _invalidate_active_model_cache(league=league)
    _invalidate_serving_profile_cache(league=league)
    with _ACTIVE_MODEL_CACHE_LOCK:
        if league is None:
            _ACTIVE_MODEL_VERSION_HINT.clear()
        else:
            _ACTIVE_MODEL_VERSION_HINT.pop(league, None)
    with _WARMUP_LOCK:
        if league is None:
            _WARMUP_STATE.clear()
        else:
            _WARMUP_STATE.pop(league, None)
    with _ROLLOUT_CONTROL_LOCK:
        if league is None:
            _ROLLOUT_CONTROLS.clear()
        else:
            _ROLLOUT_CONTROLS.pop(league, None)


def _invalidate_active_model_cache(*, league: str | None = None) -> None:
    with _ACTIVE_MODEL_CACHE_LOCK:
        if league is None:
            _ACTIVE_ROUTE_MODEL_DIRS.clear()
            _ACTIVE_ROUTE_MODEL_META.clear()
            _ACTIVE_MODEL_VERSION_HINT.clear()
        else:
            for route in ROUTES:
                key = _route_cache_key(league, route)
                _ACTIVE_ROUTE_MODEL_DIRS.pop(key, None)
                _ACTIVE_ROUTE_MODEL_META.pop(key, None)
        _MODEL_BUNDLE_CACHE.clear()


def _invalidate_serving_profile_cache(
    *,
    league: str | None = None,
    snapshot_window_id: str | None = None,
    profile_as_of_ts: str | None = None,
) -> None:
    with _SERVING_PROFILE_CACHE_LOCK:
        if league is None:
            _SERVING_PROFILE_CACHE.clear()
            _SERVING_PROFILE_SNAPSHOT_META.clear()
            return
        stale_keys = [key for key in _SERVING_PROFILE_CACHE if key[0] == league]
        for key in stale_keys:
            _SERVING_PROFILE_CACHE.pop(key, None)
        if snapshot_window_id is None and profile_as_of_ts is None:
            _SERVING_PROFILE_SNAPSHOT_META.pop(league, None)
            return
        _SERVING_PROFILE_SNAPSHOT_META[league] = {
            "snapshot_window_id": str(snapshot_window_id or ""),
            "profile_as_of_ts": str(profile_as_of_ts or ""),
        }


def _active_model_metadata_for_route(
    client: ClickHouseClient, *, league: str, route: str
) -> dict[str, Any]:
    rows = _query_rows(
        client,
        " ".join(
            [
                "SELECT model_dir, model_version, promoted_at",
                "FROM poe_trade.ml_model_registry_v1",
                f"WHERE league = {_quote(league)} AND route = {_quote(route)} AND promoted = 1",
                "ORDER BY promoted_at DESC",
                "LIMIT 1",
                "FORMAT JSONEachRow",
            ]
        ),
    )
    if rows:
        row = rows[0]
        return {
            "model_dir": str(row.get("model_dir") or ""),
            "model_version": str(row.get("model_version") or ""),
            "promoted_at": str(row.get("promoted_at") or ""),
            "checked_at": time.time(),
        }
    default_dir = Path("artifacts/ml") / f"{league.lower()}_v1"
    model_dir = str(default_dir) if default_dir.exists() else ""
    return {
        "model_dir": model_dir,
        "model_version": "",
        "promoted_at": "",
        "checked_at": time.time(),
    }


def _model_metadata_for_route_version(
    client: ClickHouseClient,
    *,
    league: str,
    route: str,
    model_version: str,
) -> dict[str, Any]:
    rows = _query_rows(
        client,
        " ".join(
            [
                "SELECT model_dir, model_version, promoted_at",
                "FROM poe_trade.ml_model_registry_v1",
                f"WHERE league = {_quote(league)} AND route = {_quote(route)} AND promoted = 1 AND model_version = {_quote(model_version)}",
                "ORDER BY promoted_at DESC",
                "LIMIT 1",
                "FORMAT JSONEachRow",
            ]
        ),
    )
    if not rows:
        return {
            "model_dir": "",
            "model_version": model_version,
            "promoted_at": "",
            "checked_at": time.time(),
        }
    row = rows[0]
    return {
        "model_dir": str(row.get("model_dir") or ""),
        "model_version": str(row.get("model_version") or model_version),
        "promoted_at": str(row.get("promoted_at") or ""),
        "checked_at": time.time(),
    }


def _get_cached_model_metadata(
    client: ClickHouseClient, *, league: str, route: str
) -> dict[str, Any]:
    key = _route_cache_key(league, route)
    with _ACTIVE_MODEL_CACHE_LOCK:
        cached = _ACTIVE_ROUTE_MODEL_META.get(key)
        if cached:
            hinted_version = _ACTIVE_MODEL_VERSION_HINT.get(league)
            cached_version = str(cached.get("model_version") or "")
            cache_age = max(0.0, time.time() - _to_float(cached.get("checked_at"), 0.0))
            if (
                not hinted_version or hinted_version == cached_version
            ) and cache_age <= _ACTIVE_MODEL_CACHE_MAX_AGE_SECONDS:
                return dict(cached)

    refreshed = _active_model_metadata_for_route(client, league=league, route=route)
    with _ACTIVE_MODEL_CACHE_LOCK:
        _ACTIVE_ROUTE_MODEL_META[key] = dict(refreshed)
        model_dir = str(refreshed.get("model_dir") or "")
        model_version = str(refreshed.get("model_version") or "")
        if model_dir:
            _ACTIVE_ROUTE_MODEL_DIRS[key] = model_dir
        else:
            _ACTIVE_ROUTE_MODEL_DIRS.pop(key, None)
        if model_version:
            _ACTIVE_MODEL_VERSION_HINT[league] = model_version
    return dict(refreshed)


def _get_cached_model_dir(client: ClickHouseClient, *, league: str, route: str) -> str:
    metadata = _get_cached_model_metadata(client, league=league, route=route)
    return str(metadata.get("model_dir") or "")


def _warmup_status_payload(league: str) -> dict[str, Any]:
    state = _WARMUP_STATE.get(league)
    if state:
        return state.to_dict()
    return {"lastAttemptAt": None, "routes": {}}


def _record_warmup_state(
    league: str, routes: dict[str, str], timestamp: str
) -> dict[str, Any]:
    with _WARMUP_LOCK:
        _WARMUP_STATE[league] = WarmupState(last_attempt=timestamp, routes=dict(routes))
        return _WARMUP_STATE[league].to_dict()


def _refresh_active_route_dirs(
    client: ClickHouseClient, *, league: str
) -> dict[str, str]:
    route_map: dict[str, str] = {}
    try:
        rows = _query_rows(
            client,
            " ".join(
                [
                    "SELECT route, argMax(model_dir, promoted_at) AS model_dir, argMax(model_version, promoted_at) AS model_version, max(promoted_at) AS latest_promoted_at",
                    "FROM poe_trade.ml_model_registry_v1",
                    f"WHERE league = {_quote(league)} AND promoted = 1",
                    "GROUP BY route",
                    "FORMAT JSONEachRow",
                ]
            ),
        )
        for row in rows:
            route = str(row.get("route") or "")
            model_dir = str(row.get("model_dir") or "")
            if route and model_dir:
                route_map[route] = model_dir
                key = _route_cache_key(league, route)
                _ACTIVE_ROUTE_MODEL_DIRS[key] = model_dir
                _ACTIVE_ROUTE_MODEL_META[key] = {
                    "model_dir": model_dir,
                    "model_version": str(row.get("model_version") or ""),
                    "promoted_at": str(row.get("latest_promoted_at") or ""),
                    "checked_at": time.time(),
                }
    except Exception as exc:
        logger.warning(
            "warmup registry lookup failed for league=%s: %s",
            league,
            exc,
        )
    for route in ROUTES:
        if route not in route_map:
            fallback = _active_model_dir_for_route(client, league=league, route=route)
            if fallback:
                route_map[route] = fallback
                key = _route_cache_key(league, route)
                _ACTIVE_ROUTE_MODEL_DIRS[key] = fallback
                _ACTIVE_ROUTE_MODEL_META[key] = {
                    "model_dir": fallback,
                    "model_version": "",
                    "promoted_at": "",
                    "checked_at": time.time(),
                }
    return route_map


def warmup_active_models(client: ClickHouseClient, *, league: str) -> dict[str, Any]:
    _ensure_supported_league(league)
    timestamp = _now_ts()
    route_dirs = _refresh_active_route_dirs(client, league=league)
    route_states: dict[str, str] = {}
    for route in ROUTES:
        model_dir = route_dirs.get(route)
        if not model_dir:
            model_dir = _get_cached_model_dir(client, league=league, route=route)
        if not model_dir:
            route_states[route] = "model_dir_missing"
            continue
        _ACTIVE_ROUTE_MODEL_DIRS[_route_cache_key(league, route)] = model_dir
        artifact_path = _route_artifact_path(
            model_dir=model_dir, route=route, league=league
        )
        artifact = _load_json_file(artifact_path)
        bundle_path = str(artifact.get("model_bundle_path") or "")
        if not bundle_path:
            route_states[route] = "bundle_path_missing"
            continue
        try:
            bundle = _load_model_bundle(bundle_path)
        except Exception as exc:
            logger.warning(
                "warmup bundle load failed league=%s route=%s path=%s: %s",
                league,
                route,
                bundle_path,
                exc,
            )
            route_states[route] = f"bundle_error:{type(exc).__name__}"
            continue
        if bundle is None:
            route_states[route] = "bundle_load_failed"
            continue
        route_states[route] = "warm"
    return _record_warmup_state(league, route_states, timestamp)


def _predict_with_bundle(
    *,
    bundle: dict[str, Any] | None,
    parsed_item: dict[str, Any],
    expected_feature_schema: dict[str, Any] | None = None,
) -> dict[str, float] | None:
    if bundle is None:
        return None
    family_scoped_bundles = bundle.get("family_scoped_bundles")
    if isinstance(family_scoped_bundles, dict):
        route = str(bundle.get("route") or "")
        if route == "fungible_reference":
            scope = _fungible_reference_family_scope(parsed_item.get("category"))
        elif route == "structured_boosted_other":
            scope = _structured_boosted_other_family_scope_from_fields(
                parsed_item.get("category"),
                base_type=parsed_item.get("base_type"),
                item_type_line=parsed_item.get("item_type_line"),
            )
        else:
            scope = "other"
        scoped_bundle = family_scoped_bundles.get(scope)
        if scoped_bundle is None:
            return None
        if not isinstance(scoped_bundle, dict):
            return None
        return _predict_with_bundle(
            bundle=scoped_bundle,
            parsed_item=parsed_item,
            expected_feature_schema=expected_feature_schema,
        )
    vectorizer = bundle.get("vectorizer")
    price_models = bundle.get("price_models") or {}
    if vectorizer is None or not isinstance(price_models, dict):
        return None
    price_tiers = bundle.get("price_tiers") or {}
    schema = expected_feature_schema
    if not isinstance(schema, dict):
        schema = bundle.get("feature_schema")
    expected_fields_obj = schema.get("fields") if isinstance(schema, dict) else None
    expected_fields = (
        [str(field) for field in expected_fields_obj]
        if isinstance(expected_fields_obj, list)
        else None
    )
    route = str(bundle.get("route") or "")
    features = _feature_dict_from_parsed_item(
        parsed_item,
        price_tiers,
        feature_fields=expected_fields,
        route=route,
    )
    _validate_prediction_feature_schema(
        schema=schema,
        features=features,
    )
    X = vectorizer.transform([features])
    p10_model = price_models.get("p10")
    p50_model = price_models.get("p50")
    p90_model = price_models.get("p90")
    if p10_model is None or p50_model is None or p90_model is None:
        return None
    p10 = float(p10_model.predict(X)[0])
    p50 = float(p50_model.predict(X)[0])
    p90 = float(p90_model.predict(X)[0])
    target_transform = str(bundle.get("target_transform") or "identity")
    if target_transform == "log1p_winsorized_p50_anchor":
        p10 = math.expm1(p10)
        p50 = math.expm1(p50)
        p90 = math.expm1(p90)
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
    schema = artifact.get("feature_schema")
    if not isinstance(schema, dict):
        features = artifact.get("features")
        if isinstance(features, list):
            schema = _build_feature_schema([str(field) for field in features])
    return _predict_with_bundle(
        bundle=bundle,
        parsed_item=parsed_item,
        expected_feature_schema=schema if isinstance(schema, dict) else None,
    )


def _validate_prediction_feature_schema(
    *, schema: dict[str, Any] | None, features: dict[str, Any]
) -> None:
    if not isinstance(schema, dict):
        return
    schema_fields_obj = schema.get("fields")
    if not isinstance(schema_fields_obj, list):
        return
    expected_fields = [str(field) for field in schema_fields_obj]
    if not expected_fields:
        return
    runtime_fields = sorted(str(field) for field in features)
    expected_sorted = sorted(expected_fields)
    if runtime_fields == expected_sorted:
        return
    expected_set = set(expected_sorted)
    runtime_set = set(runtime_fields)
    missing = sorted(expected_set - runtime_set)
    unexpected = sorted(runtime_set - expected_set)
    raise FeatureSchemaMismatchError(
        "predict feature schema mismatch: "
        f"version={str(schema.get('version') or FEATURE_SCHEMA_VERSION)} "
        f"missing={missing} unexpected={unexpected}"
    )


def _dataset_row_count(
    client: ClickHouseClient, dataset_table: str, league: str
) -> int:
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
                f"FROM {_DEFAULT_DATASET_TABLE}",
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


def _labels_table_for_dataset(dataset_table: str) -> str:
    if dataset_table.endswith("_dataset_v1"):
        return dataset_table.replace("_dataset_v1", "_labels_v1")
    if dataset_table.endswith("_dataset_v2"):
        return dataset_table.replace("_dataset_v2", "_labels_v2")
    return _DEFAULT_LABELS_TABLE


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
