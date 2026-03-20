CREATE TABLE IF NOT EXISTS poe_trade.ml_v3_training_examples (
    as_of_ts DateTime64(3, 'UTC') CODEC(Delta(8), ZSTD(1)),
    realm LowCardinality(String),
    league LowCardinality(String),
    stash_id String CODEC(ZSTD(6)),
    item_id Nullable(String),
    identity_key String,
    route LowCardinality(String),
    category LowCardinality(String),
    item_name String,
    item_type_line String,
    base_type String,
    rarity LowCardinality(String),
    ilvl UInt16,
    stack_size UInt32,
    corrupted UInt8,
    fractured UInt8,
    synthesised UInt8,
    support_count_recent UInt32,
    feature_vector_json String CODEC(ZSTD(6)),
    mod_features_json String CODEC(ZSTD(6)),
    target_price_chaos Float64,
    target_fast_sale_24h_price Nullable(Float64),
    target_sale_probability_24h Nullable(Float32),
    label_weight Float32,
    label_source LowCardinality(String),
    split_bucket UInt16,
    inserted_at DateTime64(3, 'UTC') DEFAULT now64(3) CODEC(Delta(8), ZSTD(1))
) ENGINE = ReplacingMergeTree(inserted_at)
PARTITION BY toYYYYMMDD(as_of_ts)
ORDER BY (league, route, as_of_ts, identity_key)
SETTINGS index_granularity = 8192;

CREATE TABLE IF NOT EXISTS poe_trade.ml_v3_retrieval_candidates (
    as_of_ts DateTime64(3, 'UTC') CODEC(Delta(8), ZSTD(1)),
    league LowCardinality(String),
    route LowCardinality(String),
    target_identity_key String,
    candidate_identity_key String,
    candidate_base_type String,
    candidate_rarity LowCardinality(String),
    candidate_price_chaos Float64,
    distance_score Float32,
    support_rank UInt16,
    inserted_at DateTime64(3, 'UTC') DEFAULT now64(3) CODEC(Delta(8), ZSTD(1))
) ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(as_of_ts)
ORDER BY (league, route, target_identity_key, distance_score, candidate_identity_key)
SETTINGS index_granularity = 8192;

CREATE TABLE IF NOT EXISTS poe_trade.ml_v3_model_registry (
    league LowCardinality(String),
    route LowCardinality(String),
    model_version String,
    model_dir String,
    promoted UInt8,
    promoted_at DateTime64(3, 'UTC') CODEC(Delta(8), ZSTD(1)),
    metadata_json String CODEC(ZSTD(6))
) ENGINE = ReplacingMergeTree(promoted_at)
ORDER BY (league, route, promoted_at)
SETTINGS index_granularity = 8192;

CREATE TABLE IF NOT EXISTS poe_trade.ml_v3_price_predictions (
    prediction_id String,
    run_id String,
    prediction_as_of_ts DateTime64(3, 'UTC') CODEC(Delta(8), ZSTD(1)),
    league LowCardinality(String),
    route LowCardinality(String),
    item_id Nullable(String),
    identity_key String,
    fair_value_p10 Nullable(Float64),
    fair_value_p50 Nullable(Float64),
    fair_value_p90 Nullable(Float64),
    fast_sale_24h_price Nullable(Float64),
    sale_probability_24h Nullable(Float32),
    confidence Nullable(Float32),
    support_count_recent Nullable(UInt32),
    prediction_source LowCardinality(String),
    uncertainty_tier LowCardinality(String),
    fallback_reason String,
    prediction_explainer_json String CODEC(ZSTD(6)),
    recorded_at DateTime64(3, 'UTC') CODEC(Delta(8), ZSTD(1))
) ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(prediction_as_of_ts)
ORDER BY (league, route, prediction_as_of_ts, identity_key)
SETTINGS index_granularity = 8192;

GRANT SELECT ON poe_trade.ml_v3_training_examples TO poe_api_reader;
GRANT SELECT ON poe_trade.ml_v3_retrieval_candidates TO poe_api_reader;
GRANT SELECT ON poe_trade.ml_v3_model_registry TO poe_api_reader;
GRANT SELECT ON poe_trade.ml_v3_price_predictions TO poe_api_reader;
