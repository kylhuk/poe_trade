CREATE TABLE IF NOT EXISTS poe_trade.journal_events (
    event_id String,
    strategy_id String,
    league String,
    item_or_market_key String,
    action LowCardinality(String),
    quantity Float64,
    price_chaos Float64,
    notes String,
    event_ts DateTime64(3, 'UTC')
) ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(event_ts)
ORDER BY (strategy_id, item_or_market_key, event_ts);

CREATE TABLE IF NOT EXISTS poe_trade.journal_positions (
    strategy_id String,
    league String,
    item_or_market_key String,
    net_quantity Float64,
    avg_entry_price_chaos Nullable(Float64),
    realized_pnl_chaos Float64,
    last_action LowCardinality(String),
    updated_at DateTime64(3, 'UTC')
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (strategy_id, item_or_market_key, updated_at);

GRANT SELECT ON poe_trade.journal_events TO poe_api_reader;
GRANT SELECT ON poe_trade.journal_positions TO poe_api_reader;
