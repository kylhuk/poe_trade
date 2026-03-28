from __future__ import annotations

from datetime import date
from typing import Any, Mapping

from poe_trade.ml.contract import PRICING_BENCHMARK_CONTRACT

from .routes import route_sql_expression, select_route as _select_route

OBSERVATIONS_TABLE = "poe_trade.silver_v3_item_observations"
SNAPSHOTS_TABLE = "poe_trade.silver_v3_stash_snapshots"
EVENTS_TABLE = "poe_trade.silver_v3_item_events"
SALE_LABELS_TABLE = "poe_trade.ml_v3_sale_proxy_labels"
LISTING_EPISODES_TABLE = "poe_trade.ml_v3_listing_episodes"
TRAINING_TABLE = "poe_trade.ml_v3_training_examples"
ROLLOUT_STATE_TABLE = "poe_trade.ml_v3_cohort_rollout_state"

BENCHMARK_EXTRACT_TABLE = "poe_trade.ml_v3_pricing_benchmark_v1"
MIRAGE_IRON_RING_BENCHMARK_TABLE = "poe_trade.v_ml_v3_mirage_iron_ring_item_features_v1"
MIRAGE_IRON_RING_AFFIX_CATALOG_TABLE = "poe_trade.ml_ring_mod_catalog_v1"
POE_RARE_ITEM_TRAIN_TABLE = "poe_trade.poe_rare_item_train"

LGBM_NEO_CONTEXT_COLUMNS: tuple[str, ...] = (
    "item_id",
    "observed_at",
    "item_fingerprint",
    "league",
    "category",
    "base_type",
    "price_chaos",
)

LGBM_NEO_LEGACY_FEATURE_BASES: tuple[str, ...] = (
    "exp_mana_flat",
    "exp_item_rarity_pct",
    "exp_life_flat",
    "exp_energy_shield_flat",
    "exp_all_attrs_flat",
    "exp_all_elem_res_pct",
    "exp_fire_res_pct",
    "exp_cold_res_pct",
    "exp_lightning_res_pct",
    "exp_chaos_res_pct",
    "exp_dex_flat",
    "exp_int_flat",
    "exp_str_flat",
    "exp_cast_speed_pct",
    "exp_attack_speed_pct",
    "exp_fire_damage_flat",
    "exp_cold_damage_flat",
    "exp_lightning_damage_flat",
    "exp_phys_damage_flat",
    "imp_armour_pct",
    "imp_evasion_pct",
)

RING_CANONICAL_FAMILIES: tuple[str, ...] = (
    "all_attributes",
    "all_resistances",
    "chance_to_suppress_spells",
    "chaos_resistance",
    "cold_damage",
    "cold_damage_percentage",
    "cold_resistance",
    "damage_taken_gained_as_life",
    "dexterity",
    "energy_shield_delay",
    "energy_shield_regeneration",
    "fire_damage",
    "fire_damage_percentage",
    "fire_resistance",
    "increased_accuracy",
    "increased_attack_speed",
    "increased_cast_speed",
    "increased_energy_shield",
    "increased_evasion_rating",
    "increased_life",
    "increased_mana",
    "increased_weapon_elemental_damage_percent",
    "intelligence",
    "item_found_rarity_increase",
    "life_gain_per_target",
    "life_gained_from_enemy_death",
    "life_leech",
    "life_regeneration",
    "life_regeneration_rate",
    "light_radius_increased_global_accuracy_rating",
    "light_radius_to_accuracy_rating",
    "lightning_damage",
    "lightning_damage_percentage",
    "lightning_resistance",
    "mana_gained_from_enemy_death",
    "mana_leech",
    "mana_regeneration",
    "physical_damage",
    "reduced_physical_damage_taken",
    "strength",
)

LGBM_NEO_SOURCE_PREFIXES: tuple[str, ...] = ("exp", "fract", "craft", "enchant")

LGBM_NEO_FEATURE_BASES: tuple[str, ...] = LGBM_NEO_LEGACY_FEATURE_BASES + tuple(
    f"{source}_{family}"
    for source in LGBM_NEO_SOURCE_PREFIXES
    for family in RING_CANONICAL_FAMILIES
)

LGBM_NEO_COLUMNS: tuple[str, ...] = LGBM_NEO_CONTEXT_COLUMNS + tuple(
    f"{prefix}_{feature}"
    for feature in LGBM_NEO_FEATURE_BASES
    for prefix in ("has", "val", "tier")
)

LGBM_NEO_PREFIX_FEATURES: tuple[str, ...] = (
    "exp_mana_flat",
    "exp_item_rarity_pct",
    "exp_life_flat",
    "exp_energy_shield_flat",
    "exp_all_attrs_flat",
    "exp_all_res_pct",
    "exp_fire_damage_flat",
    "exp_cold_damage_flat",
    "exp_lightning_damage_flat",
    "exp_phys_damage_flat",
)

LGBM_NEO_SUFFIX_FEATURES: tuple[str, ...] = (
    "exp_dex_flat",
    "exp_int_flat",
    "exp_str_flat",
    "exp_fire_res_pct",
    "exp_cold_res_pct",
    "exp_lightning_res_pct",
    "exp_chaos_res_pct",
    "exp_cast_speed_pct",
    "exp_attack_speed_pct",
)

LGBM_NEO_IMPLICIT_FEATURES: tuple[str, ...] = (
    "imp_armour_pct",
    "imp_evasion_pct",
)
ITEM_FAMILY_NAMES: tuple[str, ...] = (
    "flask",
    "map",
    "cluster_jewel",
    "boots",
)
BENCHMARK_EXTRACT_COLUMNS: tuple[str, ...] = (
    "as_of_ts",
    "realm",
    "league",
    "stash_id",
    "item_id",
    "listing_episode_id",
    "identity_key",
    "first_seen",
    "last_seen",
    "snapshot_count",
    "latest_price",
    "min_price",
    "route",
    "strategy_family",
    "cohort_key",
    "material_state_signature",
    "category",
    "item_name",
    "item_type_line",
    "base_type",
    "rarity",
    "ilvl",
    "stack_size",
    "corrupted",
    "fractured",
    "synthesised",
    "item_state_key",
    "support_count_recent",
    "fx_hour",
    "fx_source",
    "fx_chaos_per_divine",
    "feature_vector_json",
    "mod_features_json",
    "target_price_chaos",
    "target_price_divine",
    "target_fast_sale_24h_price",
    "target_fast_sale_24h_price_divine",
    "target_sale_probability_24h",
    "target_likely_sold",
    "sale_confidence_flag",
    "target_time_to_exit_hours",
    "target_sale_price_anchor_chaos",
    "label_weight",
    "label_source",
    "split_bucket",
)

BENCHMARK_FORBIDDEN_FEATURE_PATTERNS: tuple[str, ...] = (
    "future_",
    "post_cutoff_",
    "future_snapshot",
    "future_exchange_rate",
    "next_listing",
)
ITEM_FAMILY_TEXT_SQL = (
    "lowerUTF8(concat(ifNull(item_type_line, ''), ' ', ifNull(base_type, '')))"
)
ITEM_FAMILY_PREDICATES: dict[str, str] = {
    "flask": f"match({ITEM_FAMILY_TEXT_SQL}, '(^|\\\\W)flask(\\\\W|$)')",
    "map": f"match({ITEM_FAMILY_TEXT_SQL}, '(^|\\\\W)map(\\\\W|$)')",
    "cluster_jewel": f"match({ITEM_FAMILY_TEXT_SQL}, '(^|\\\\W)cluster\\\\s+jewel(\\\\W|$)')",
    "boots": f"match({ITEM_FAMILY_TEXT_SQL}, '(^|\\\\W)boots(\\\\W|$)')",
}


def _quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _route_sql() -> str:
    return route_sql_expression()


def _normalized_currency_sql(currency_expr: str) -> str:
    normalized = f"replaceRegexpAll(replaceRegexpAll(lowerUTF8(trimBoth({currency_expr})), '\\s+', ' '), '\\s+orbs?$', '')"
    return (
        "multiIf("
        + ", ".join(
            [
                f"{normalized} IN ('div', 'divine', 'divines'), 'divine'",
                f"{normalized} IN ('exa', 'exalt', 'exalted', 'exalts'), 'exalted'",
                f"{normalized} IN ('alch', 'alchemy'), 'orb of alchemy'",
                f"{normalized} IN ('gcp', 'gemcutter', 'gemcutters', 'gemcutter''s prism'), 'gemcutter''s prism'",
                f"{normalized} IN ('alt', 'alteration'), 'orb of alteration'",
                f"{normalized} IN ('scour', 'scouring'), 'orb of scouring'",
                f"{normalized} IN ('wisdom', 'wisdom scroll'), 'scroll of wisdom'",
                f"{normalized} IN ('annul', 'annulment'), 'orb of annulment'",
                f"{normalized} IN ('chrome', 'chromatic'), 'chromatic'",
                f"{normalized} IN ('fusing',), 'orb of fusing'",
                f"{normalized} IN ('portal',), 'portal scroll'",
                f"{normalized} IN ('bauble',), 'glassblower''s bauble'",
                f"{normalized} IN ('aug', 'augmentation'), 'orb of augmentation'",
                f"{normalized} IN ('transmute', 'transmutation'), 'orb of transmutation'",
                f"{normalized} IN ('mirror',), 'mirror of kalandra'",
                normalized,
            ]
        )
        + ")"
    )


def _item_state_sql(
    *, rarity_expr: str, corrupted_expr: str, fractured_expr: str, synthesised_expr: str
) -> str:
    return (
        "concat("
        f"lowerUTF8(ifNull({rarity_expr}, '')),"
        "'|corrupted=', toString(toUInt8(ifNull(" + corrupted_expr + ", 0) != 0)),"
        "'|fractured=', toString(toUInt8(ifNull(" + fractured_expr + ", 0) != 0)),"
        "'|synthesised=', toString(toUInt8(ifNull(" + synthesised_expr + ", 0) != 0))"
        ")"
    )


def _material_state_signature_sql(
    *, rarity_expr: str, corrupted_expr: str, fractured_expr: str, synthesised_expr: str
) -> str:
    return (
        "concat("
        "'v1|rarity=', lowerUTF8(ifNull(" + rarity_expr + ", 'unknown')),"
        "'|corrupted=', toString(toUInt8(ifNull(" + corrupted_expr + ", 0) != 0)),"
        "'|fractured=', toString(toUInt8(ifNull(" + fractured_expr + ", 0) != 0)),"
        "'|synthesised=', toString(toUInt8(ifNull(" + synthesised_expr + ", 0) != 0))"
        ")"
    )


def select_route(parsed: Mapping[str, Any]) -> str:
    return _select_route(parsed)


def _normalize_item_family(family: str) -> str:
    normalized = str(family or "").strip().lower()
    if normalized not in ITEM_FAMILY_NAMES:
        raise ValueError(
            "unknown item family {!r}; expected one of: {}".format(
                family, ", ".join(ITEM_FAMILY_NAMES)
            )
        )
    return normalized


def _item_family_predicate_sql(family: str) -> str:
    normalized = _normalize_item_family(family)
    return ITEM_FAMILY_PREDICATES[normalized]


def pricing_benchmark_contract_spec() -> dict[str, Any]:
    return {
        "name": PRICING_BENCHMARK_CONTRACT.name,
        "confirmation_horizon_hours": PRICING_BENCHMARK_CONTRACT.confirmation_horizon_hours,
        "exchange_routes": list(PRICING_BENCHMARK_CONTRACT.exchange_routes),
        "non_exchange_routes": list(PRICING_BENCHMARK_CONTRACT.non_exchange_routes),
        "label_source": PRICING_BENCHMARK_CONTRACT.label_source,
        "row_grain": "one row per listing episode at first_seen",
        "allowed_columns": list(BENCHMARK_EXTRACT_COLUMNS),
        "forbidden_feature_patterns": list(BENCHMARK_FORBIDDEN_FEATURE_PATTERNS),
    }


def fast_sale_benchmark_contract_spec() -> dict[str, Any]:
    spec = pricing_benchmark_contract_spec()
    spec.update(
        {
            "name": "fast_sale_24h_price_benchmark_v1",
            "benchmark_name": "fast_sale_24h_price_benchmark_v1",
            "target_name": "target_fast_sale_24h_price",
            "candidate_count": 3,
            "split_kind": "grouped_forward",
            "row_grain": "one row per item observation at as_of_ts with identity-safe split",
            "tail_metric_quantile": 0.9,
        }
    )
    return spec


def build_pricing_benchmark_extract_query(
    *,
    league: str,
    as_of_ts: str,
    output_table: str = BENCHMARK_EXTRACT_TABLE,
) -> str:
    league_sql = _quote(league)
    as_of_ts_sql = _quote(as_of_ts)
    select_columns = ",\n".join(f"    {column}" for column in BENCHMARK_EXTRACT_COLUMNS)
    non_exchange_routes_sql = ", ".join(
        _quote(route) for route in PRICING_BENCHMARK_CONTRACT.non_exchange_routes
    )
    return " ".join(
        [
            f"INSERT INTO {output_table}",
            "SELECT",
            select_columns,
            f"FROM {TRAINING_TABLE}",
            f"WHERE league = {league_sql}",
            f"AND route IN ({non_exchange_routes_sql})",
            f"AND as_of_ts <= toDateTime64({as_of_ts_sql}, 3, 'UTC')",
            "AND target_price_chaos > 0",
            "ORDER BY as_of_ts ASC, identity_key ASC, item_id ASC",
        ]
    )


def build_mirage_iron_ring_benchmark_sample_query(
    *,
    league: str,
    sample_size: int = 10_000,
    source_table: str = MIRAGE_IRON_RING_BENCHMARK_TABLE,
) -> str:
    league_sql = _quote(league)
    safe_limit = max(1, int(sample_size))
    select_columns = "\n".join(
        [
            "    item.observed_at AS as_of_ts,",
            "    item.identity_key,",
            "    item.item_id,",
            "    item.realm,",
            "    item.league,",
            "    item.stash_id,",
            "    item.category,",
            "    item.item_name,",
            "    item.item_type_line,",
            "    item.base_type,",
            "    item.rarity,",
            "    item.ilvl,",
            "    item.stack_size,",
            "    item.corrupted,",
            "    item.fractured,",
            "    item.synthesised,",
            "    item.influence_mask,",
            "    item.catalyst_type,",
            "    item.catalyst_quality,",
            "    item.synth_imp_count,",
            "    item.synth_implicit_mods_json,",
            "    item.corrupted_implicit_mods_json,",
            "    item.veiled_count,",
            "    item.crafted_count,",
            "    item.prefix_count,",
            "    item.suffix_count,",
            "    item.open_prefixes,",
            "    item.open_suffixes,",
            "    item.normalized_affix_hash,",
            "    item.affix_count,",
            "    item.affixes,",
            "    item.parsed_amount AS target_price_chaos,",
            "    toUInt32(count() OVER (PARTITION BY item.league, item.base_type)) AS support_count_recent,",
            "    toUInt16(0) AS split_bucket",
        ]
    )
    item_subquery = " ".join(
        [
            "SELECT",
            select_columns,
            ",",
            "    row_number() OVER (PARTITION BY item.normalized_affix_hash ORDER BY item.observed_at DESC, item.identity_key ASC, item.item_id ASC) AS hash_rank",
            f"FROM {source_table} AS item",
            f"WHERE item.league = {league_sql}",
            "AND item.category = 'ring'",
            "AND item.base_type = 'Iron Ring'",
            "AND item.parsed_amount IS NOT NULL",
            "AND item.parsed_amount > 0",
        ]
    )

    return " ".join(
        [
            "SELECT",
            "    item.as_of_ts,",
            "    item.identity_key,",
            "    item.item_id,",
            "    item.realm,",
            "    item.league,",
            "    item.stash_id,",
            "    item.category,",
            "    item.item_name,",
            "    item.item_type_line,",
            "    item.base_type,",
            "    item.rarity,",
            "    item.ilvl,",
            "    item.stack_size,",
            "    item.corrupted,",
            "    item.fractured,",
            "    item.synthesised,",
            "    item.normalized_affix_hash,",
            "    item.affix_count,",
            "    item.affixes,",
            "    item.support_count_recent,",
            "    item.target_price_chaos,",
            "    toFloat64(item.target_price_chaos * 0.95) AS target_fast_sale_24h_price,",
            "    toFloat32(1.0) AS target_sale_probability_24h,",
            "    toUInt8(1) AS target_likely_sold,",
            "    toUInt8(1) AS sale_confidence_flag,",
            "    toFloat32(1.0) AS label_weight,",
            "    'branch_mirage_iron_ring_v1' AS label_source,",
            "    toUInt16(0) AS split_bucket,",
            "    toJSONString(mapFromArrays(",
            "        arrayMap(affix -> concat(tupleElement(affix, 1), '::', lowerUTF8(replaceAll(trimBoth(replaceAll(tupleElement(affix, 2), '\"', '')), '  ', ' '))), item.affixes),",
            "        arrayMap(_ -> 1.0, item.affixes)",
            "    )) AS mod_features_json",
            "FROM (",
            item_subquery,
            ") AS item",
            "WHERE item.hash_rank = 1",
            f"ORDER BY item.as_of_ts ASC, item.identity_key ASC, item.item_id ASC",
            f"LIMIT {safe_limit}",
            "FORMAT JSONEachRow",
        ]
    )


def build_mirage_iron_ring_affix_catalog_query(
    *,
    source_table: str = MIRAGE_IRON_RING_AFFIX_CATALOG_TABLE,
) -> str:
    return " ".join(
        [
            "SELECT",
            "    mod_text_pattern,",
            "    mod_base_name,",
            "    mod_max_value",
            f"FROM {source_table}",
            "ORDER BY mod_base_name ASC, mod_tier ASC",
            "FORMAT JSONEachRow",
        ]
    )


def build_lgbm_neo_training_query(
    *,
    source_table: str = POE_RARE_ITEM_TRAIN_TABLE,
) -> str:
    select_columns = ",\n".join(f"    {column}" for column in LGBM_NEO_COLUMNS)
    return " ".join(
        [
            "SELECT",
            select_columns,
            f"FROM {source_table}",
            "WHERE price_chaos > 0",
            "ORDER BY observed_at ASC, item_fingerprint ASC, item_id ASC",
        ]
    )


def build_item_family_sample_count_query(
    *,
    league: str,
    as_of_ts: str,
    family: str,
    source_table: str = TRAINING_TABLE,
) -> str:
    league_sql = _quote(league)
    as_of_ts_sql = _quote(as_of_ts)
    family_sql = _item_family_predicate_sql(family)
    non_exchange_routes_sql = ", ".join(
        _quote(route) for route in PRICING_BENCHMARK_CONTRACT.non_exchange_routes
    )
    return " ".join(
        [
            "SELECT count() AS row_count",
            f"FROM {source_table}",
            f"WHERE league = {league_sql}",
            f"AND route IN ({non_exchange_routes_sql})",
            f"AND as_of_ts <= toDateTime64({as_of_ts_sql}, 3, 'UTC')",
            "AND target_price_chaos > 0",
            f"AND {family_sql}",
            "FORMAT JSONEachRow",
        ]
    )


def build_item_family_sample_query(
    *,
    league: str,
    as_of_ts: str,
    family: str,
    sample_size: int = 10_000,
    source_table: str = TRAINING_TABLE,
) -> str:
    league_sql = _quote(league)
    as_of_ts_sql = _quote(as_of_ts)
    family_sql = _item_family_predicate_sql(family)
    non_exchange_routes_sql = ", ".join(
        _quote(route) for route in PRICING_BENCHMARK_CONTRACT.non_exchange_routes
    )
    safe_limit = max(1, int(sample_size))
    select_columns = ",\n".join(
        [
            "    as_of_ts",
            "    realm",
            "    league",
            "    stash_id",
            "    item_id",
            "    identity_key",
            "    route",
            "    strategy_family",
            "    cohort_key",
            "    material_state_signature",
            "    category",
            "    item_name",
            "    item_type_line",
            "    base_type",
            "    rarity",
            "    ilvl",
            "    stack_size",
            "    corrupted",
            "    fractured",
            "    synthesised",
            "    item_state_key",
            "    support_count_recent",
            "    fx_hour",
            "    fx_source",
            "    fx_chaos_per_divine",
            "    feature_vector_json",
            "    mod_features_json",
            "    target_price_chaos",
            "    target_price_divine",
            "    target_fast_sale_24h_price",
            "    target_fast_sale_24h_price_divine",
            "    target_sale_probability_24h",
            "    target_likely_sold",
            "    ifNull(toFloat32(target_likely_sold), 0.0) AS sale_confidence_flag",
            "    NULL AS target_time_to_exit_hours",
            "    NULL AS target_sale_price_anchor_chaos",
            "    label_weight",
            "    label_source",
            "    split_bucket",
        ]
    )
    return " ".join(
        [
            "SELECT",
            select_columns,
            f"FROM {source_table}",
            f"WHERE league = {league_sql}",
            f"AND route IN ({non_exchange_routes_sql})",
            f"AND as_of_ts <= toDateTime64({as_of_ts_sql}, 3, 'UTC')",
            "AND target_price_chaos > 0",
            f"AND {family_sql}",
            "ORDER BY as_of_ts ASC, identity_key ASC, item_id ASC",
            f"LIMIT {safe_limit}",
            "FORMAT JSONEachRow",
        ]
    )


def disk_usage_query() -> str:
    return (
        "SELECT toUInt64(sum(bytes_on_disk)) AS bytes_on_disk "
        "FROM system.parts WHERE database = 'poe_trade' AND active = 1 "
        "FORMAT JSONEachRow"
    )


def build_events_insert_query(*, league: str, day: date) -> str:
    day_sql = _quote(day.isoformat())
    league_sql = _quote(league)
    return " ".join(
        [
            f"INSERT INTO {EVENTS_TABLE}",
            "SELECT",
            "current_observed_at AS event_ts,",
            "realm,",
            "league,",
            "stash_id,",
            "item_id,",
            "identity_key,",
            "fingerprint_v3,",
            "multiIf(prev_observed_at IS NULL, 'listed', prev_price_note != current_price_note, 'repriced', 'relisted') AS event_type,",
            "prev_observed_at AS previous_observed_at,",
            "current_observed_at,",
            "prev_price_note AS previous_price_note,",
            "current_price_note,",
            "prev_parsed_amount AS previous_parsed_amount,",
            "current_parsed_amount,",
            "toFloat32(multiIf(prev_observed_at IS NULL, 0.55, prev_price_note != current_price_note, 0.75, 0.35)) AS event_weight,",
            "toJSONString(map('source','observation_diff','kind',multiIf(prev_observed_at IS NULL, 'listed', prev_price_note != current_price_note, 'repriced', 'relisted'))) AS event_payload_json,",
            "now64(3) AS inserted_at",
            "FROM (",
            "SELECT",
            "realm,",
            "league,",
            "stash_id,",
            "item_id,",
            "identity_key,",
            "fingerprint_v3,",
            "observed_at AS current_observed_at,",
            "effective_price_note AS current_price_note,",
            "parsed_amount AS current_parsed_amount,",
            "lagInFrame(observed_at) OVER w AS prev_observed_at,",
            "lagInFrame(effective_price_note) OVER w AS prev_price_note,",
            "lagInFrame(parsed_amount) OVER w AS prev_parsed_amount",
            f"FROM {OBSERVATIONS_TABLE}",
            f"WHERE league = {league_sql}",
            f"AND toDate(observed_at) = toDate({day_sql})",
            "WINDOW w AS (PARTITION BY league, realm, stash_id, identity_key ORDER BY observed_at)",
            ")",
        ]
    )


def build_disappearance_events_insert_query(*, league: str, day: date) -> str:
    day_sql = _quote(day.isoformat())
    league_sql = _quote(league)
    return " ".join(
        [
            f"INSERT INTO {EVENTS_TABLE}",
            "SELECT",
            "snapshot_ts AS event_ts,",
            "realm,",
            "league,",
            "stash_id,",
            "CAST(NULL AS Nullable(String)) AS item_id,",
            "disappeared_identity_key AS identity_key,",
            "disappeared_identity_key AS fingerprint_v3,",
            "'disappeared' AS event_type,",
            "prev_snapshot_ts AS previous_observed_at,",
            "snapshot_ts AS current_observed_at,",
            "CAST(NULL AS Nullable(String)) AS previous_price_note,",
            "CAST(NULL AS Nullable(String)) AS current_price_note,",
            "CAST(NULL AS Nullable(Float64)) AS previous_parsed_amount,",
            "CAST(NULL AS Nullable(Float64)) AS current_parsed_amount,",
            "toFloat32(0.85) AS event_weight,",
            "toJSONString(map('source','snapshot_delta','kind','disappeared')) AS event_payload_json,",
            "now64(3) AS inserted_at",
            "FROM (",
            "SELECT",
            "snapshot_ts,",
            "realm,",
            "league,",
            "stash_id,",
            "lagInFrame(snapshot_ts) OVER w AS prev_snapshot_ts,",
            "arrayJoin(arrayExcept(lagInFrame(item_identity_keys) OVER w, item_identity_keys)) AS disappeared_identity_key",
            f"FROM {SNAPSHOTS_TABLE}",
            f"WHERE league = {league_sql}",
            f"AND toDate(snapshot_ts) = toDate({day_sql})",
            "WINDOW w AS (PARTITION BY league, realm, stash_id ORDER BY snapshot_ts)",
            ")",
            "WHERE disappeared_identity_key != ''",
        ]
    )


def build_sale_proxy_labels_insert_query(*, league: str, day: date) -> str:
    day_sql = _quote(day.isoformat())
    league_sql = _quote(league)
    return " ".join(
        [
            f"INSERT INTO {SALE_LABELS_TABLE}",
            "SELECT",
            "event_ts AS as_of_ts,",
            "realm,",
            "league,",
            "stash_id,",
            "item_id,",
            "identity_key,",
            "toUInt8(event_type = 'disappeared') AS likely_sold,",
            "toFloat32(multiIf(event_type = 'disappeared', 0.82, event_type = 'repriced', 0.52, event_type = 'listed', 0.35, 0.25)) AS sold_probability,",
            "toFloat32(greatest(0.1, least(1.0, event_weight))) AS label_weight,",
            f"'{PRICING_BENCHMARK_CONTRACT.label_source}' AS label_source,",
            "if(previous_observed_at IS NULL, CAST(NULL AS Nullable(Float32)), toFloat32(greatest(0.0, dateDiff('minute', previous_observed_at, current_observed_at) / 60.0))) AS time_to_exit_hours,",
            "current_parsed_amount AS sale_price_anchor_chaos,",
            "now64(3) AS inserted_at",
            f"FROM {EVENTS_TABLE}",
            f"WHERE league = {league_sql}",
            f"AND toDate(event_ts) = toDate({day_sql})",
        ]
    )


def create_listing_episodes_table_query(
    *,
    table: str = LISTING_EPISODES_TABLE,
) -> str:
    return (
        f"CREATE TABLE IF NOT EXISTS {table}("
        "as_of_ts DateTime64(3, 'UTC'), realm String, league String, stash_id String, "
        "item_id Nullable(String), identity_key String, listing_episode_id String, "
        "first_seen DateTime64(3, 'UTC'), last_seen DateTime64(3, 'UTC'), "
        "snapshot_count UInt32, latest_price Nullable(Float64), min_price Nullable(Float64), "
        "latest_price_divine Nullable(Float64), min_price_divine Nullable(Float64), "
        "fx_hour Nullable(DateTime64(0, 'UTC')), fx_source LowCardinality(String), "
        "fx_chaos_per_divine Nullable(Float64), "
        "category String, route String, strategy_family String, cohort_key String, "
        "material_state_signature String, item_name String, item_type_line String, "
        "base_type String, rarity Nullable(String), ilvl UInt16, stack_size UInt32, "
        "corrupted UInt8, fractured UInt8, synthesised UInt8, item_state_key String, "
        "support_count_recent UInt32, feature_vector_json String, mod_features_json String, "
        "target_price_chaos Nullable(Float64), target_fast_sale_24h_price Nullable(Float64), "
        "target_price_divine Nullable(Float64), target_fast_sale_24h_price_divine Nullable(Float64), "
        "target_sale_probability_24h Nullable(Float32), target_likely_sold UInt8, "
        "sale_confidence_flag UInt8, target_time_to_exit_hours Nullable(Float64), "
        "target_sale_price_anchor_chaos Nullable(Float64), label_weight Float32, "
        "label_source String, label_quality String, split_bucket UInt16, inserted_at DateTime64(3, 'UTC')"
        ") ENGINE=ReplacingMergeTree(inserted_at) PARTITION BY toYYYYMMDD(as_of_ts) "
        "ORDER BY (league, realm, stash_id, listing_episode_id, as_of_ts)"
    )


def build_listing_episodes_insert_query(*, league: str, day: date) -> str:
    day_sql = _quote(day.isoformat())
    league_sql = _quote(league)
    return " ".join(
        [
            f"INSERT INTO {LISTING_EPISODES_TABLE} (",
            "as_of_ts,",
            "realm,",
            "league,",
            "stash_id,",
            "item_id,",
            "listing_episode_id,",
            "first_seen,",
            "last_seen,",
            "snapshot_count,",
            "latest_price,",
            "min_price,",
            "latest_price_divine,",
            "min_price_divine,",
            "identity_key,",
            "category,",
            "route,",
            "strategy_family,",
            "cohort_key,",
            "material_state_signature,",
            "item_name,",
            "item_type_line,",
            "base_type,",
            "rarity,",
            "ilvl,",
            "stack_size,",
            "corrupted,",
            "fractured,",
            "synthesised,",
            "item_state_key,",
            "support_count_recent,",
            "feature_vector_json,",
            "mod_features_json,",
            "fx_hour,",
            "fx_source,",
            "fx_chaos_per_divine,",
            "target_sale_probability_24h,",
            "target_price_chaos,",
            "target_price_divine,",
            "target_fast_sale_24h_price,",
            "target_fast_sale_24h_price_divine,",
            "target_likely_sold,",
            "sale_confidence_flag,",
            "target_time_to_exit_hours,",
            "target_sale_price_anchor_chaos,",
            "label_weight,",
            "label_source,",
            "label_quality,",
            "split_bucket,",
            "inserted_at",
            ")",
            "WITH base AS (",
            "SELECT",
            "observed_at,",
            "realm,",
            "ifNull(league, '') AS league,",
            "stash_id,",
            "item_id,",
            "identity_key,",
            "item_name,",
            "item_type_line,",
            "base_type,",
            "rarity,",
            "ilvl,",
            "stack_size,",
            "corrupted,",
            "fractured,",
            "synthesised,",
            "ifNull(category, 'other') AS category,",
            f"{_route_sql()} AS route,",
            "ifNull(strategy_family, 'default') AS strategy_family,",
            "ifNull(cohort_key, concat(route, '|', ifNull(category, 'other'), '|', ifNull(material_state_signature, 'v1|rarity=unknown|corrupted=0|fractured=0|synthesised=0'))) AS cohort_key,",
            "ifNull(material_state_signature, 'v1|rarity=unknown|corrupted=0|fractured=0|synthesised=0') AS material_state_signature,",
            "ifNull(item_state_key, concat(lowerUTF8(ifNull(rarity, '')), '|corrupted=', toString(toUInt8(ifNull(corrupted, 0) != 0)), '|fractured=', toString(toUInt8(ifNull(fractured, 0) != 0)), '|synthesised=', toString(toUInt8(ifNull(synthesised, 0) != 0)))) AS item_state_key,",
            f"{_normalized_currency_sql('parsed_currency')} AS normalized_currency,",
            "toUInt32(count() OVER (PARTITION BY league, realm, stash_id, identity_key)) AS support_count_recent,",
            "toJSONString(map('ilvl', toFloat64(ilvl), 'stack_size', toFloat64(stack_size), 'corrupted', toFloat64(corrupted), 'fractured', toFloat64(fractured), 'synthesised', toFloat64(synthesised), 'price', toFloat64OrNull(parsed_amount))) AS feature_vector_json,",
            "ifNull(mod_features_json, '{}') AS mod_features_json,",
            "parsed_amount,",
            "parsed_currency,",
            "lagInFrame(observed_at) OVER w AS prev_observed_at,",
            "if(lagInFrame(observed_at) OVER w IS NULL, 1, if(dateDiff('second', lagInFrame(observed_at) OVER w, observed_at) > 300, 1, 0)) AS is_new_episode",
            f"FROM {OBSERVATIONS_TABLE}",
            f"WHERE ifNull(league, '') = {league_sql}",
            f"AND toDate(observed_at) = toDate({day_sql})",
            "WINDOW w AS (PARTITION BY league, realm, stash_id, identity_key ORDER BY observed_at)",
            ")",
            ", priced AS (",
            "SELECT",
            "base.*",
            ", fx_price.hour_ts AS fx_hour",
            ", coalesce(fx_divine.fx_source, fx_price.fx_source, 'missing') AS fx_source",
            ", fx_divine.chaos_equivalent AS fx_chaos_per_divine",
            ", if(base.parsed_amount IS NULL, NULL, multiIf(base.normalized_currency IN ('chaos', 'chaos orb', 'chaos orbs', ''), base.parsed_amount, fx_price.chaos_equivalent > 0, base.parsed_amount * fx_price.chaos_equivalent, NULL)) AS normalized_price_chaos",
            ", if(base.parsed_amount IS NULL OR fx_divine.chaos_equivalent <= 0, NULL, multiIf(base.normalized_currency IN ('chaos', 'chaos orb', 'chaos orbs', ''), base.parsed_amount, fx_price.chaos_equivalent > 0, base.parsed_amount * fx_price.chaos_equivalent, NULL) / fx_divine.chaos_equivalent) AS normalized_price_divine",
            "FROM base",
            "LEFT JOIN poe_trade.ml_fx_hour_latest_v2 AS fx_price",
            "ON fx_price.league = base.league",
            f"AND {_normalized_currency_sql('fx_price.currency')} = base.normalized_currency",
            "AND fx_price.hour_ts = toStartOfHour(base.observed_at)",
            "LEFT JOIN poe_trade.ml_fx_hour_latest_v2 AS fx_divine",
            "ON fx_divine.league = base.league",
            f"AND {_normalized_currency_sql('fx_divine.currency')} = 'divine'",
            "AND fx_divine.hour_ts = toStartOfHour(base.observed_at)",
            ")",
            ", marked AS (",
            "SELECT",
            "*,",
            "sum(is_new_episode) OVER (PARTITION BY league, realm, stash_id, identity_key ORDER BY observed_at) AS episode_index",
            "FROM priced",
            ")",
            "SELECT",
            "min(observed_at) AS as_of_ts,",
            "any(realm) AS realm,",
            "any(league) AS league,",
            "any(stash_id) AS stash_id,",
            "any(item_id) AS item_id,",
            "concat(any(realm), '|', any(league), '|', any(stash_id), '|', ifNull(any(item_id), any(base_type)), '|', toString(any(episode_index))) AS listing_episode_id,",
            "min(observed_at) AS first_seen,",
            "max(observed_at) AS last_seen,",
            "count() AS snapshot_count,",
            "argMax(normalized_price_chaos, observed_at) AS latest_price,",
            "minIf(normalized_price_chaos, normalized_price_chaos > 0) AS min_price,",
            "toFloat64(argMax(normalized_price_divine, observed_at)) AS latest_price_divine,",
            "toFloat64(minIf(normalized_price_divine, normalized_price_divine > 0)) AS min_price_divine,",
            "any(identity_key) AS identity_key,",
            "argMax(category, observed_at) AS category,",
            "argMax(route, observed_at) AS route,",
            "argMax(strategy_family, observed_at) AS strategy_family,",
            "argMax(cohort_key, observed_at) AS cohort_key,",
            "argMax(material_state_signature, observed_at) AS material_state_signature,",
            "argMax(item_name, observed_at) AS item_name,",
            "argMax(item_type_line, observed_at) AS item_type_line,",
            "argMax(base_type, observed_at) AS base_type,",
            "argMax(rarity, observed_at) AS rarity,",
            "argMax(ilvl, observed_at) AS ilvl,",
            "argMax(stack_size, observed_at) AS stack_size,",
            "argMax(corrupted, observed_at) AS corrupted,",
            "argMax(fractured, observed_at) AS fractured,",
            "argMax(synthesised, observed_at) AS synthesised,",
            "argMax(item_state_key, observed_at) AS item_state_key,",
            "argMax(support_count_recent, observed_at) AS support_count_recent,",
            "argMax(feature_vector_json, observed_at) AS feature_vector_json,",
            "argMax(mod_features_json, observed_at) AS mod_features_json,",
            "argMax(fx_hour, observed_at) AS fx_hour,",
            "argMax(fx_source, observed_at) AS fx_source,",
            "argMax(fx_chaos_per_divine, observed_at) AS fx_chaos_per_divine,",
            "toFloat32(multiIf(count() >= 4, 0.9, count() >= 2, 0.75, 0.5)) AS target_sale_probability_24h,",
            "toFloat64(argMax(normalized_price_chaos, observed_at)) AS target_price_chaos,",
            "toFloat64(argMax(normalized_price_divine, observed_at)) AS target_price_divine,",
            "toFloat64(minIf(normalized_price_chaos, normalized_price_chaos > 0)) AS target_fast_sale_24h_price,",
            "toFloat64(minIf(normalized_price_divine, normalized_price_divine > 0)) AS target_fast_sale_24h_price_divine,",
            "toUInt8(count() >= 2) AS target_likely_sold,",
            "toUInt8(count() >= 2) AS sale_confidence_flag,",
            "CAST(NULL AS Nullable(Float64)) AS target_time_to_exit_hours,",
            "toFloat64(minIf(normalized_price_chaos, normalized_price_chaos > 0)) AS target_sale_price_anchor_chaos,",
            "toFloat32(greatest(0.25, least(1.0, count() / 5.0))) AS label_weight,",
            "'listing_episode' AS label_source,",
            "if(count() >= 2, 'high', 'low') AS label_quality,",
            "toUInt16(cityHash64(concat(any(realm), '|', any(league), '|', any(stash_id), '|', ifNull(any(item_id), any(base_type)), '|', toString(any(episode_index)))) % 1000) AS split_bucket,",
            "now64(3) AS inserted_at",
            "FROM priced",
            "GROUP BY league, realm, stash_id, item_id, identity_key, episode_index",
        ]
    )


def build_training_examples_insert_query(*, league: str, day: date) -> str:
    day_sql = _quote(day.isoformat())
    league_sql = _quote(league)
    route_expr = _route_sql()
    return " ".join(
        [
            f"INSERT INTO {TRAINING_TABLE} (",
            "as_of_ts,",
            "realm,",
            "league,",
            "stash_id,",
            "item_id,",
            "identity_key,",
            "listing_episode_id,",
            "first_seen,",
            "last_seen,",
            "snapshot_count,",
            "route,",
            "strategy_family,",
            "cohort_key,",
            "material_state_signature,",
            "category,",
            "item_name,",
            "item_type_line,",
            "base_type,",
            "rarity,",
            "ilvl,",
            "stack_size,",
            "corrupted,",
            "fractured,",
            "synthesised,",
            "item_state_key,",
            "support_count_recent,",
            "fx_hour,",
            "fx_source,",
            "fx_chaos_per_divine,",
            "feature_vector_json,",
            "mod_features_json,",
            "target_price_chaos,",
            "target_price_divine,",
            "target_fast_sale_24h_price,",
            "target_fast_sale_24h_price_divine,",
            "target_sale_probability_24h,",
            "target_likely_sold,",
            "sale_confidence_flag,",
            "target_time_to_exit_hours,",
            "target_sale_price_anchor_chaos,",
            "label_weight,",
            "label_source,",
            "split_bucket,",
            "inserted_at",
            ")",
            "SELECT",
            "episode.as_of_ts AS as_of_ts,",
            "episode.realm AS realm,",
            "episode.league AS league,",
            "episode.stash_id AS stash_id,",
            "episode.item_id AS item_id,",
            "episode.listing_episode_id AS identity_key,",
            "episode.listing_episode_id AS listing_episode_id,",
            "episode.first_seen AS first_seen,",
            "episode.last_seen AS last_seen,",
            "episode.snapshot_count AS snapshot_count,",
            f"{route_expr} AS route,",
            "episode.strategy_family AS strategy_family,",
            "episode.cohort_key AS cohort_key,",
            "episode.material_state_signature AS material_state_signature,",
            "episode.category AS category,",
            "episode.item_name AS item_name,",
            "episode.item_type_line AS item_type_line,",
            "episode.base_type AS base_type,",
            "episode.rarity AS rarity,",
            "episode.ilvl AS ilvl,",
            "episode.stack_size AS stack_size,",
            "episode.corrupted AS corrupted,",
            "episode.fractured AS fractured,",
            "episode.synthesised AS synthesised,",
            "episode.item_state_key AS item_state_key,",
            "episode.support_count_recent AS support_count_recent,",
            "episode.fx_hour AS fx_hour,",
            "episode.fx_source AS fx_source,",
            "episode.fx_chaos_per_divine AS fx_chaos_per_divine,",
            "episode.feature_vector_json AS feature_vector_json,",
            "episode.mod_features_json AS mod_features_json,",
            "episode.latest_price AS target_price_chaos,",
            "episode.latest_price_divine AS target_price_divine,",
            "episode.min_price AS target_fast_sale_24h_price,",
            "episode.min_price_divine AS target_fast_sale_24h_price_divine,",
            "toFloat32(multiIf(episode.snapshot_count >= 4, 0.9, episode.snapshot_count >= 2, 0.75, 0.5)) AS target_sale_probability_24h,",
            "toUInt8(episode.snapshot_count >= 2) AS target_likely_sold,",
            "toUInt8(episode.snapshot_count >= 2) AS sale_confidence_flag,",
            "CAST(NULL AS Nullable(Float64)) AS target_time_to_exit_hours,",
            "episode.min_price AS target_sale_price_anchor_chaos,",
            "toFloat32(greatest(0.25, least(1.0, episode.snapshot_count / 5.0))) AS label_weight,",
            "'listing_episode' AS label_source,",
            "if(episode.snapshot_count >= 2, 'high', 'low') AS label_quality,",
            "toUInt16(cityHash64(episode.listing_episode_id) % 1000) AS split_bucket,",
            "now64(3) AS inserted_at",
            f"FROM {LISTING_EPISODES_TABLE} AS episode",
            f"WHERE episode.league = {league_sql}",
            f"AND toDate(episode.as_of_ts) = toDate({day_sql})",
            "AND episode.latest_price IS NOT NULL",
            "AND episode.latest_price > 0",
        ]
    )


def build_retrieval_candidate_query(
    *,
    league: str,
    route: str,
    item_state_key: str,
    limit: int = 2000,
) -> str:
    league_sql = _quote(league)
    route_sql = _quote(route)
    item_state_key_sql = _quote(item_state_key)
    safe_limit = max(1, int(limit))
    return " ".join(
        [
            "SELECT",
            "as_of_ts,",
            "league,",
            "route,",
            "identity_key,",
            "item_state_key,",
            "base_type,",
            "rarity,",
            "target_price_chaos,",
            "target_price_divine,",
            "target_fast_sale_24h_price,",
            "target_fast_sale_24h_price_divine,",
            "target_sale_probability_24h,",
            "support_count_recent,",
            "fx_hour,",
            "fx_source,",
            "fx_chaos_per_divine,",
            "mod_features_json",
            "FROM (",
            "SELECT",
            "as_of_ts,",
            "league,",
            "route,",
            "identity_key,",
            "item_state_key,",
            "base_type,",
            "rarity,",
            "target_price_chaos,",
            "target_price_divine,",
            "target_fast_sale_24h_price,",
            "target_fast_sale_24h_price_divine,",
            "target_sale_probability_24h,",
            "support_count_recent,",
            "fx_hour,",
            "fx_source,",
            "fx_chaos_per_divine,",
            "mod_features_json,",
            "row_number() OVER (",
            "PARTITION BY league, route, item_state_key",
            "ORDER BY as_of_ts DESC, identity_key ASC",
            ") AS candidate_rank",
            f"FROM {TRAINING_TABLE}",
            f"WHERE league = {league_sql}",
            f"AND route = {route_sql}",
            f"AND item_state_key = {item_state_key_sql}",
            ")",
            f"WHERE candidate_rank <= {safe_limit}",
            "FORMAT JSONEachRow",
        ]
    )
