CREATE TABLE IF NOT EXISTS poe_trade.ml_v3_route_eval (
    run_id String,
    league LowCardinality(String),
    route LowCardinality(String),
    family LowCardinality(String),
    support_bucket LowCardinality(String),
    split_kind LowCardinality(String),
    sample_count UInt64,
    fair_value_mdape Nullable(Float64),
    fair_value_wape Nullable(Float64),
    fast_sale_24h_hit_rate Nullable(Float64),
    sale_probability_calibration_error Nullable(Float64),
    confidence_calibration_error Nullable(Float64),
    abstain_rate Nullable(Float64),
    recorded_at DateTime64(3, 'UTC') CODEC(Delta(8), ZSTD(1))
) ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(recorded_at)
ORDER BY (league, run_id, route, family, support_bucket, recorded_at)
SETTINGS index_granularity = 8192;

CREATE TABLE IF NOT EXISTS poe_trade.ml_v3_eval_runs (
    run_id String,
    league LowCardinality(String),
    model_version String,
    split_kind LowCardinality(String),
    total_sample_count UInt64,
    global_fair_value_mdape Nullable(Float64),
    global_fast_sale_24h_hit_rate Nullable(Float64),
    global_sale_probability_calibration_error Nullable(Float64),
    global_confidence_calibration_error Nullable(Float64),
    worst_slice_mdape Nullable(Float64),
    worst_slice_route LowCardinality(String),
    serving_path_parity_ok UInt8,
    gate_passed UInt8,
    gate_reason String,
    recorded_at DateTime64(3, 'UTC') CODEC(Delta(8), ZSTD(1))
) ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(recorded_at)
ORDER BY (league, run_id, recorded_at)
SETTINGS index_granularity = 8192;

CREATE TABLE IF NOT EXISTS poe_trade.ml_v3_promotion_audit (
    league LowCardinality(String),
    candidate_run_id String,
    incumbent_run_id String,
    candidate_model_version String,
    incumbent_model_version String,
    verdict LowCardinality(String),
    stop_reason String,
    global_fair_value_mdape_candidate Nullable(Float64),
    global_fair_value_mdape_incumbent Nullable(Float64),
    global_fast_sale_hit_rate_candidate Nullable(Float64),
    global_fast_sale_hit_rate_incumbent Nullable(Float64),
    worst_slice_mdape_candidate Nullable(Float64),
    worst_slice_mdape_incumbent Nullable(Float64),
    recorded_at DateTime64(3, 'UTC') CODEC(Delta(8), ZSTD(1))
) ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(recorded_at)
ORDER BY (league, candidate_run_id, recorded_at)
SETTINGS index_granularity = 8192;

GRANT SELECT ON poe_trade.ml_v3_route_eval TO poe_api_reader;
GRANT SELECT ON poe_trade.ml_v3_eval_runs TO poe_api_reader;
GRANT SELECT ON poe_trade.ml_v3_promotion_audit TO poe_api_reader;
