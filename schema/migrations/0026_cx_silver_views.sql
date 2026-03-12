CREATE TABLE IF NOT EXISTS poe_trade.silver_cx_markets_hour (
    recorded_at DateTime64(3, 'UTC'),
    realm LowCardinality(String),
    hour_ts DateTime64(0, 'UTC'),
    league String,
    market_id String,
    base_code String,
    quote_code String,
    volume_traded_json String,
    lowest_stock_json String,
    highest_stock_json String,
    lowest_ratio_json String,
    highest_ratio_json String
) ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(hour_ts)
ORDER BY (realm, league, market_id, hour_ts);

CREATE MATERIALIZED VIEW IF NOT EXISTS poe_trade.mv_cx_markets_hour
TO poe_trade.silver_cx_markets_hour AS
SELECT
    recorded_at,
    realm,
    requested_hour AS hour_ts,
    JSONExtractString(market_json, 'league') AS league,
    JSONExtractString(market_json, 'market_id') AS market_id,
    splitByChar('|', JSONExtractString(market_json, 'market_id'))[1] AS base_code,
    splitByChar('|', JSONExtractString(market_json, 'market_id'))[2] AS quote_code,
    coalesce(JSONExtractRaw(market_json, 'volume_traded'), '{}') AS volume_traded_json,
    coalesce(JSONExtractRaw(market_json, 'lowest_stock'), '{}') AS lowest_stock_json,
    coalesce(JSONExtractRaw(market_json, 'highest_stock'), '{}') AS highest_stock_json,
    coalesce(JSONExtractRaw(market_json, 'lowest_ratio'), '{}') AS lowest_ratio_json,
    coalesce(JSONExtractRaw(market_json, 'highest_ratio'), '{}') AS highest_ratio_json
FROM poe_trade.raw_currency_exchange_hour
ARRAY JOIN JSONExtractArrayRaw(payload_json, 'markets') AS market_json;

CREATE VIEW IF NOT EXISTS poe_trade.v_cx_markets_enriched AS
SELECT
    *,
    concat(base_code, '->', quote_code) AS market_pair,
    length(volume_traded_json) > 2 AS has_volume_traded,
    length(lowest_ratio_json) > 2 AS has_lowest_ratio,
    length(highest_ratio_json) > 2 AS has_highest_ratio
FROM poe_trade.silver_cx_markets_hour;

GRANT SELECT ON poe_trade.silver_cx_markets_hour TO poe_api_reader;
GRANT SELECT ON poe_trade.v_cx_markets_enriched TO poe_api_reader;
