CREATE TABLE IF NOT EXISTS poe_trade.scanner_recommendations (
    scanner_run_id String,
    strategy_id String,
    league String,
    item_or_market_key String,
    why_it_fired String,
    buy_plan String,
    max_buy Nullable(Float64),
    transform_plan String,
    exit_plan String,
    execution_venue String,
    expected_profit_chaos Nullable(Float64),
    expected_roi Nullable(Float64),
    expected_hold_time String,
    confidence Nullable(Float64),
    evidence_snapshot String,
    recorded_at DateTime64(3, 'UTC')
) ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(recorded_at)
ORDER BY (strategy_id, scanner_run_id, recorded_at);

CREATE TABLE IF NOT EXISTS poe_trade.scanner_alert_log (
    alert_id String,
    scanner_run_id String,
    strategy_id String,
    league String,
    item_or_market_key String,
    status LowCardinality(String),
    evidence_snapshot String,
    recorded_at DateTime64(3, 'UTC')
) ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(recorded_at)
ORDER BY (strategy_id, scanner_run_id, recorded_at);

GRANT SELECT ON poe_trade.scanner_recommendations TO poe_api_reader;
GRANT SELECT ON poe_trade.scanner_alert_log TO poe_api_reader;
