CREATE TABLE IF NOT EXISTS poe_trade.raw_poeninja_currency_overview (
    sample_time_utc DateTime64(3, 'UTC'),
    league String,
    line_type String,
    currency_type_name String,
    chaos_equivalent Float64,
    listing_count UInt32,
    stale UInt8,
    provenance String,
    payload_json String,
    inserted_at DateTime64(3, 'UTC')
) ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(sample_time_utc)
ORDER BY (league, currency_type_name, sample_time_utc);

CREATE TABLE IF NOT EXISTS poe_trade.ml_listing_events_v1 (
    as_of_ts DateTime64(3, 'UTC'),
    realm String,
    league String,
    stash_id String,
    item_id Nullable(String),
    listing_chain_id String,
    note_value Nullable(String),
    note_edited UInt8,
    relist_event UInt8,
    has_trade_metadata UInt8,
    evidence_source LowCardinality(String)
) ENGINE = ReplacingMergeTree(as_of_ts)
PARTITION BY toYYYYMMDD(as_of_ts)
ORDER BY (league, realm, listing_chain_id, as_of_ts);

CREATE TABLE IF NOT EXISTS poe_trade.ml_execution_labels_v1 (
    as_of_ts DateTime64(3, 'UTC'),
    realm String,
    league String,
    listing_chain_id String,
    sale_probability_label Nullable(Float64),
    time_to_exit_label Nullable(Float64),
    label_source LowCardinality(String),
    label_quality LowCardinality(String),
    is_censored UInt8,
    eligibility_reason String,
    updated_at DateTime64(3, 'UTC')
) ENGINE = ReplacingMergeTree(updated_at)
PARTITION BY toYYYYMMDD(as_of_ts)
ORDER BY (league, realm, listing_chain_id, as_of_ts);

CREATE TABLE IF NOT EXISTS poe_trade.ml_fx_hour_v1 (
    hour_ts DateTime64(0, 'UTC'),
    league String,
    currency String,
    chaos_equivalent Float64,
    fx_source LowCardinality(String),
    sample_time_utc DateTime64(3, 'UTC'),
    stale UInt8,
    updated_at DateTime64(3, 'UTC')
) ENGINE = ReplacingMergeTree(updated_at)
PARTITION BY toYYYYMMDD(hour_ts)
ORDER BY (league, currency, hour_ts);

CREATE TABLE IF NOT EXISTS poe_trade.ml_price_labels_v1 (
    as_of_ts DateTime64(3, 'UTC'),
    realm String,
    league String,
    stash_id String,
    item_id Nullable(String),
    category LowCardinality(String),
    base_type String,
    stack_size UInt32,
    parsed_amount Nullable(Float64),
    parsed_currency Nullable(String),
    price_parse_status LowCardinality(String),
    normalized_price_chaos Nullable(Float64),
    unit_price_chaos Nullable(Float64),
    normalization_source LowCardinality(String),
    fx_hour Nullable(DateTime64(0, 'UTC')),
    fx_source LowCardinality(String),
    outlier_status LowCardinality(String),
    label_source LowCardinality(String),
    label_quality LowCardinality(String),
    updated_at DateTime64(3, 'UTC')
) ENGINE = ReplacingMergeTree(updated_at)
PARTITION BY toYYYYMMDD(as_of_ts)
ORDER BY (league, realm, category, base_type, as_of_ts, item_id);

CREATE TABLE IF NOT EXISTS poe_trade.ml_mod_catalog_v1 (
    mod_token String,
    mod_text String,
    observed_count UInt64,
    scope LowCardinality(String),
    updated_at DateTime64(3, 'UTC')
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (mod_token);

CREATE TABLE IF NOT EXISTS poe_trade.ml_item_mod_tokens_v1 (
    league String,
    item_id String,
    mod_token String,
    as_of_ts DateTime64(3, 'UTC')
) ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(as_of_ts)
ORDER BY (league, item_id, mod_token, as_of_ts);

CREATE TABLE IF NOT EXISTS poe_trade.ml_price_dataset_v1 (
    as_of_ts DateTime64(3, 'UTC'),
    realm String,
    league String,
    stash_id String,
    item_id Nullable(String),
    item_name String,
    item_type_line String,
    base_type String,
    rarity Nullable(String),
    ilvl UInt16,
    stack_size UInt32,
    corrupted UInt8,
    fractured UInt8,
    synthesised UInt8,
    category LowCardinality(String),
    normalized_price_chaos Nullable(Float64),
    sale_probability_label Nullable(Float64),
    label_source LowCardinality(String),
    label_quality LowCardinality(String),
    outlier_status LowCardinality(String),
    route_candidate LowCardinality(String),
    support_count_recent UInt64,
    support_bucket LowCardinality(String),
    route_reason String,
    fallback_parent_route LowCardinality(String),
    fx_freshness_minutes Nullable(Float64),
    mod_token_count UInt16,
    confidence_hint Nullable(Float64),
    updated_at DateTime64(3, 'UTC')
) ENGINE = ReplacingMergeTree(updated_at)
PARTITION BY toYYYYMMDD(as_of_ts)
ORDER BY (league, category, base_type, as_of_ts, item_id);

CREATE TABLE IF NOT EXISTS poe_trade.ml_route_candidates_v1 (
    as_of_ts DateTime64(3, 'UTC'),
    league String,
    item_id Nullable(String),
    category LowCardinality(String),
    base_type String,
    rarity Nullable(String),
    route LowCardinality(String),
    route_reason String,
    support_count_recent UInt64,
    support_bucket LowCardinality(String),
    fallback_parent_route LowCardinality(String),
    updated_at DateTime64(3, 'UTC')
) ENGINE = ReplacingMergeTree(updated_at)
PARTITION BY toYYYYMMDD(as_of_ts)
ORDER BY (league, route, category, base_type, as_of_ts, item_id);

CREATE TABLE IF NOT EXISTS poe_trade.ml_comps_v1 (
    as_of_ts DateTime64(3, 'UTC'),
    league String,
    target_item_id String,
    comp_item_id String,
    target_base_type String,
    comp_base_type String,
    distance_score Float64,
    comp_price_chaos Float64,
    retrieval_window_hours UInt16,
    updated_at DateTime64(3, 'UTC')
) ENGINE = ReplacingMergeTree(updated_at)
PARTITION BY toYYYYMMDD(as_of_ts)
ORDER BY (league, target_item_id, distance_score, comp_item_id);

CREATE TABLE IF NOT EXISTS poe_trade.ml_route_eval_v1 (
    run_id String,
    route LowCardinality(String),
    family LowCardinality(String),
    variant LowCardinality(String),
    league String,
    split_kind LowCardinality(String),
    sample_count UInt64,
    mdape Nullable(Float64),
    wape Nullable(Float64),
    rmsle Nullable(Float64),
    abstain_rate Nullable(Float64),
    interval_80_coverage Nullable(Float64),
    freshness_minutes Nullable(Float64),
    support_bucket LowCardinality(String),
    recorded_at DateTime64(3, 'UTC')
) ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(recorded_at)
ORDER BY (league, route, family, variant, recorded_at);

CREATE TABLE IF NOT EXISTS poe_trade.ml_eval_runs (
    run_id String,
    route LowCardinality(String),
    league String,
    split_kind LowCardinality(String),
    raw_coverage Float64,
    clean_coverage Float64,
    outlier_drop_rate Float64,
    mdape Nullable(Float64),
    wape Nullable(Float64),
    rmsle Nullable(Float64),
    abstain_rate Nullable(Float64),
    interval_80_coverage Nullable(Float64),
    leakage_violations UInt64,
    leakage_audit_path String,
    recorded_at DateTime64(3, 'UTC')
) ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(recorded_at)
ORDER BY (league, route, split_kind, recorded_at);

CREATE TABLE IF NOT EXISTS poe_trade.ml_train_runs (
    run_id String,
    league String,
    stage LowCardinality(String),
    current_route LowCardinality(String),
    routes_done UInt32,
    routes_total UInt32,
    rows_processed UInt64,
    eta_seconds Nullable(UInt32),
    chosen_backend LowCardinality(String),
    worker_count UInt16,
    memory_budget_gb Float64,
    active_model_version String,
    status LowCardinality(String),
    resume_token String,
    started_at DateTime64(3, 'UTC'),
    updated_at DateTime64(3, 'UTC')
) ENGINE = ReplacingMergeTree(updated_at)
PARTITION BY toYYYYMMDD(started_at)
ORDER BY (league, run_id, updated_at);

CREATE TABLE IF NOT EXISTS poe_trade.ml_model_registry_v1 (
    league String,
    route LowCardinality(String),
    model_version String,
    model_dir String,
    promoted UInt8,
    promoted_at DateTime64(3, 'UTC'),
    metadata_json String
) ENGINE = ReplacingMergeTree(promoted_at)
ORDER BY (league, route, promoted_at);

CREATE TABLE IF NOT EXISTS poe_trade.ml_price_predictions_v1 (
    prediction_id String,
    prediction_as_of_ts DateTime64(3, 'UTC'),
    league String,
    source_kind LowCardinality(String),
    item_id Nullable(String),
    route LowCardinality(String),
    price_chaos Nullable(Float64),
    price_p10 Nullable(Float64),
    price_p50 Nullable(Float64),
    price_p90 Nullable(Float64),
    sale_probability_24h Nullable(Float64),
    sale_probability Nullable(Float64),
    confidence Nullable(Float64),
    comp_count Nullable(UInt32),
    support_count_recent Nullable(UInt64),
    freshness_minutes Nullable(Float64),
    base_comp_price_p50 Nullable(Float64),
    residual_adjustment Nullable(Float64),
    fallback_reason String,
    prediction_explainer_json String,
    recorded_at DateTime64(3, 'UTC')
) ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(prediction_as_of_ts)
ORDER BY (league, source_kind, route, prediction_as_of_ts, item_id);

CREATE VIEW IF NOT EXISTS poe_trade.ml_latest_items_v1 AS
SELECT
    observed_at,
    realm,
    league,
    stash_id,
    item_id,
    item_name,
    item_type_line,
    base_type,
    rarity,
    ilvl,
    stack_size,
    note,
    forum_note,
    corrupted,
    fractured,
    synthesised,
    item_json,
    effective_price_note,
    price_amount,
    price_currency,
    category
FROM (
    SELECT
        *,
        row_number() OVER (
            PARTITION BY coalesce(item_id, concat(stash_id, '|', base_type, '|', item_type_line))
            ORDER BY observed_at DESC
        ) AS rn
    FROM poe_trade.v_ps_items_enriched
)
WHERE rn = 1;

GRANT SELECT ON poe_trade.raw_poeninja_currency_overview TO poe_api_reader;
GRANT SELECT ON poe_trade.ml_listing_events_v1 TO poe_api_reader;
GRANT SELECT ON poe_trade.ml_execution_labels_v1 TO poe_api_reader;
GRANT SELECT ON poe_trade.ml_fx_hour_v1 TO poe_api_reader;
GRANT SELECT ON poe_trade.ml_price_labels_v1 TO poe_api_reader;
GRANT SELECT ON poe_trade.ml_mod_catalog_v1 TO poe_api_reader;
GRANT SELECT ON poe_trade.ml_item_mod_tokens_v1 TO poe_api_reader;
GRANT SELECT ON poe_trade.ml_price_dataset_v1 TO poe_api_reader;
GRANT SELECT ON poe_trade.ml_route_candidates_v1 TO poe_api_reader;
GRANT SELECT ON poe_trade.ml_comps_v1 TO poe_api_reader;
GRANT SELECT ON poe_trade.ml_route_eval_v1 TO poe_api_reader;
GRANT SELECT ON poe_trade.ml_eval_runs TO poe_api_reader;
GRANT SELECT ON poe_trade.ml_train_runs TO poe_api_reader;
GRANT SELECT ON poe_trade.ml_model_registry_v1 TO poe_api_reader;
GRANT SELECT ON poe_trade.ml_price_predictions_v1 TO poe_api_reader;
GRANT SELECT ON poe_trade.ml_latest_items_v1 TO poe_api_reader;
