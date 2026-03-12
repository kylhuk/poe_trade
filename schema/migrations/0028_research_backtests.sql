CREATE TABLE IF NOT EXISTS poe_trade.research_backtest_runs (
    run_id String,
    strategy_id String,
    league String,
    lookback_days UInt32,
    started_at DateTime64(3, 'UTC'),
    completed_at DateTime64(3, 'UTC') DEFAULT toDateTime64(0, 3, 'UTC'),
    status LowCardinality(String),
    notes String
) ENGINE = ReplacingMergeTree(completed_at)
ORDER BY (strategy_id, started_at, run_id);

CREATE TABLE IF NOT EXISTS poe_trade.research_backtest_results (
    run_id String,
    strategy_id String,
    league String,
    recorded_at DateTime64(3, 'UTC'),
    result_json String
) ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(recorded_at)
ORDER BY (strategy_id, run_id, recorded_at);

GRANT SELECT ON poe_trade.research_backtest_runs TO poe_api_reader;
GRANT SELECT ON poe_trade.research_backtest_results TO poe_api_reader;
