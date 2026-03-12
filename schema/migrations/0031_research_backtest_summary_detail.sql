CREATE TABLE IF NOT EXISTS poe_trade.research_backtest_summary (
    run_id String,
    strategy_id String,
    league String,
    lookback_days UInt32,
    status LowCardinality(String),
    opportunity_count UInt32,
    expected_profit_chaos Nullable(Float64),
    expected_roi Nullable(Float64),
    confidence Nullable(Float64),
    summary String,
    recorded_at DateTime64(3, 'UTC')
) ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(recorded_at)
ORDER BY (strategy_id, run_id, recorded_at);

CREATE TABLE IF NOT EXISTS poe_trade.research_backtest_detail (
    run_id String,
    strategy_id String,
    league String,
    lookback_days UInt32,
    status LowCardinality(String),
    recorded_at DateTime64(3, 'UTC'),
    item_or_market_key String,
    expected_profit_chaos Nullable(Float64),
    expected_roi Nullable(Float64),
    confidence Nullable(Float64),
    summary String,
    detail_json String
) ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(recorded_at)
ORDER BY (strategy_id, run_id, item_or_market_key, recorded_at);

GRANT SELECT ON poe_trade.research_backtest_summary TO poe_api_reader;
GRANT SELECT ON poe_trade.research_backtest_detail TO poe_api_reader;
