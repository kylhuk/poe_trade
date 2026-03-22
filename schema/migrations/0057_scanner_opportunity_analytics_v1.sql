ALTER TABLE poe_trade.scanner_recommendations
    ADD COLUMN IF NOT EXISTS complexity_tier Nullable(String) AFTER confidence;

ALTER TABLE poe_trade.scanner_recommendations
    ADD COLUMN IF NOT EXISTS required_capital_chaos Nullable(Float64) AFTER complexity_tier;

ALTER TABLE poe_trade.scanner_recommendations
    ADD COLUMN IF NOT EXISTS opportunity_type Nullable(String) AFTER required_capital_chaos;

ALTER TABLE poe_trade.scanner_recommendations
    ADD COLUMN IF NOT EXISTS estimated_operations Nullable(UInt16) AFTER opportunity_type;

ALTER TABLE poe_trade.scanner_recommendations
    ADD COLUMN IF NOT EXISTS estimated_whispers Nullable(UInt16) AFTER estimated_operations;

ALTER TABLE poe_trade.scanner_recommendations
    ADD COLUMN IF NOT EXISTS expected_profit_per_operation_chaos Nullable(Float64) AFTER expected_profit_chaos;

ALTER TABLE poe_trade.scanner_recommendations
    ADD COLUMN IF NOT EXISTS feasibility_score Nullable(Float64) AFTER expected_profit_per_operation_chaos;

CREATE TABLE IF NOT EXISTS poe_trade.scanner_candidate_decisions (
    scanner_run_id String,
    accepted UInt8,
    decision_reason LowCardinality(String),
    strategy_id String,
    league String,
    recommendation_source Nullable(String),
    recommendation_contract_version Nullable(UInt32),
    producer_version Nullable(String),
    producer_run_id Nullable(String),
    item_or_market_key String,
    complexity_tier Nullable(String),
    required_capital_chaos Nullable(Float64),
    estimated_operations Nullable(UInt16),
    estimated_whispers Nullable(UInt16),
    expected_profit_chaos Nullable(Float64),
    expected_profit_per_operation_chaos Nullable(Float64),
    feasibility_score Nullable(Float64),
    evidence_snapshot String,
    recorded_at DateTime64(3, 'UTC')
) ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(recorded_at)
ORDER BY (strategy_id, scanner_run_id, recorded_at, item_or_market_key)
TTL recorded_at + INTERVAL 30 DAY;

GRANT SELECT ON poe_trade.scanner_candidate_decisions TO poe_api_reader;
