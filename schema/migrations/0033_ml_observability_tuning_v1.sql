ALTER TABLE poe_trade.ml_train_runs
    ADD COLUMN IF NOT EXISTS stop_reason LowCardinality(String) DEFAULT 'unknown';

ALTER TABLE poe_trade.ml_train_runs
    ADD COLUMN IF NOT EXISTS tuning_config_id String DEFAULT '';

ALTER TABLE poe_trade.ml_train_runs
    ADD COLUMN IF NOT EXISTS eval_run_id String DEFAULT '';

CREATE TABLE IF NOT EXISTS poe_trade.ml_promotion_audit_v1 (
    league String,
    candidate_run_id String,
    incumbent_run_id String,
    candidate_model_version String,
    incumbent_model_version String,
    verdict LowCardinality(String),
    avg_mdape_candidate Float64,
    avg_mdape_incumbent Float64,
    coverage_candidate Float64,
    coverage_incumbent Float64,
    stop_reason String,
    recorded_at DateTime64(3, 'UTC')
) ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(recorded_at)
ORDER BY (league, candidate_run_id, recorded_at);

CREATE TABLE IF NOT EXISTS poe_trade.ml_tuning_rounds_v1 (
    league String,
    run_id String,
    fit_round UInt32,
    warm_start_from String,
    tuning_config_id String,
    iteration_budget UInt32,
    wall_clock_budget_seconds UInt32,
    no_improvement_patience UInt32,
    elapsed_seconds UInt32,
    candidate_mdape Float64,
    incumbent_mdape Float64,
    mdape_improvement Float64,
    recorded_at DateTime64(3, 'UTC')
) ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(recorded_at)
ORDER BY (league, run_id, fit_round, recorded_at);

CREATE TABLE IF NOT EXISTS poe_trade.ml_route_hotspots_v1 (
    league String,
    candidate_run_id String,
    incumbent_run_id String,
    route LowCardinality(String),
    family LowCardinality(String),
    support_bucket LowCardinality(String),
    sample_count UInt64,
    candidate_mdape Float64,
    incumbent_mdape Float64,
    mdape_delta Float64,
    candidate_abstain_rate Float64,
    incumbent_abstain_rate Float64,
    abstain_rate_delta Float64,
    recorded_at DateTime64(3, 'UTC')
) ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(recorded_at)
ORDER BY (league, candidate_run_id, route, recorded_at);

GRANT SELECT ON poe_trade.ml_promotion_audit_v1 TO poe_api_reader;
GRANT SELECT ON poe_trade.ml_tuning_rounds_v1 TO poe_api_reader;
GRANT SELECT ON poe_trade.ml_route_hotspots_v1 TO poe_api_reader;
