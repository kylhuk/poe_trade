from __future__ import annotations

from datetime import date

OBSERVATIONS_TABLE = "poe_trade.silver_v3_item_observations"
SNAPSHOTS_TABLE = "poe_trade.silver_v3_stash_snapshots"
EVENTS_TABLE = "poe_trade.silver_v3_item_events"
SALE_LABELS_TABLE = "poe_trade.ml_v3_sale_proxy_labels"
TRAINING_TABLE = "poe_trade.ml_v3_training_examples"


def _quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _route_sql() -> str:
    return (
        "multiIf("
        "category IN ('essence'), 'fallback_abstain', "
        "category IN ('fossil','scarab','logbook'), 'fungible_reference', "
        "rarity = 'Unique' AND category IN ('ring','amulet','belt','jewel'), 'structured_boosted_other', "
        "rarity = 'Unique', 'structured_boosted', "
        "category = 'cluster_jewel', 'cluster_jewel_retrieval', "
        "rarity = 'Rare', 'sparse_retrieval', "
        "'fallback_abstain'"
        ")"
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
            "'lifecycle_proxy_v3' AS label_source,",
            "if(previous_observed_at IS NULL, CAST(NULL AS Nullable(Float32)), toFloat32(greatest(0.0, dateDiff('minute', previous_observed_at, current_observed_at) / 60.0))) AS time_to_exit_hours,",
            "current_parsed_amount AS sale_price_anchor_chaos,",
            "now64(3) AS inserted_at",
            f"FROM {EVENTS_TABLE}",
            f"WHERE league = {league_sql}",
            f"AND toDate(event_ts) = toDate({day_sql})",
        ]
    )


def build_training_examples_insert_query(*, league: str, day: date) -> str:
    day_sql = _quote(day.isoformat())
    league_sql = _quote(league)
    route_expr = _route_sql()
    return " ".join(
        [
            f"INSERT INTO {TRAINING_TABLE}",
            "SELECT",
            "obs.observed_at AS as_of_ts,",
            "obs.realm AS realm,",
            "obs.league AS league,",
            "obs.stash_id AS stash_id,",
            "obs.item_id AS item_id,",
            "obs.identity_key AS identity_key,",
            f"{route_expr} AS route,",
            "obs.category AS category,",
            "obs.item_name AS item_name,",
            "obs.item_type_line AS item_type_line,",
            "obs.base_type AS base_type,",
            "obs.rarity AS rarity,",
            "obs.ilvl AS ilvl,",
            "obs.stack_size AS stack_size,",
            "obs.corrupted AS corrupted,",
            "obs.fractured AS fractured,",
            "obs.synthesised AS synthesised,",
            "toUInt32(count() OVER (PARTITION BY obs.league, obs.base_type)) AS support_count_recent,",
            "toJSONString(map('ilvl', toFloat64(obs.ilvl), 'stack_size', toFloat64(obs.stack_size), 'corrupted', toFloat64(obs.corrupted), 'fractured', toFloat64(obs.fractured), 'synthesised', toFloat64(obs.synthesised))) AS feature_vector_json,",
            "obs.affix_payload_json AS mod_features_json,",
            "obs.parsed_amount AS target_price_chaos,",
            "if(labels.sold_probability >= 0.75, obs.parsed_amount * 0.95, obs.parsed_amount * 0.88) AS target_fast_sale_24h_price,",
            "labels.sold_probability AS target_sale_probability_24h,",
            "ifNull(labels.label_weight, toFloat32(0.25)) AS label_weight,",
            "ifNull(labels.label_source, 'observation_only') AS label_source,",
            "toUInt16(cityHash64(obs.identity_key) % 1000) AS split_bucket,",
            "now64(3) AS inserted_at",
            f"FROM {OBSERVATIONS_TABLE} AS obs",
            f"LEFT JOIN {SALE_LABELS_TABLE} AS labels",
            "ON labels.league = obs.league",
            "AND labels.realm = obs.realm",
            "AND labels.stash_id = obs.stash_id",
            "AND labels.identity_key = obs.identity_key",
            "AND labels.as_of_ts = obs.observed_at",
            f"WHERE obs.league = {league_sql}",
            f"AND toDate(obs.observed_at) = toDate({day_sql})",
            "AND obs.parsed_amount IS NOT NULL",
            "AND obs.parsed_amount > 0",
        ]
    )
