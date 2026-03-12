INSERT INTO poe_trade.gold_liquidity_ref_hour
SELECT
    toStartOfHour(observed_at) AS time_bucket,
    realm,
    league,
    category,
    count() AS listing_count,
    countIf(price_amount IS NOT NULL) AS priced_listing_count,
    toUInt32(quantileExact(0.5)(stack_size)) AS median_stack_size,
    now64(3) AS updated_at
FROM poe_trade.v_ps_items_enriched
GROUP BY
    time_bucket,
    realm,
    league,
    category;
