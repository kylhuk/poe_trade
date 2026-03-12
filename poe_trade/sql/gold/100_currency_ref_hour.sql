INSERT INTO poe_trade.gold_currency_ref_hour
SELECT
    hour_ts AS time_bucket,
    realm,
    league,
    market_id,
    base_code,
    quote_code,
    count() AS sample_count,
    max(toUInt8(has_lowest_ratio)) AS has_lowest_ratio,
    max(toUInt8(has_highest_ratio)) AS has_highest_ratio,
    now64(3) AS updated_at
FROM poe_trade.v_cx_markets_enriched
GROUP BY
    time_bucket,
    realm,
    league,
    market_id,
    base_code,
    quote_code;
