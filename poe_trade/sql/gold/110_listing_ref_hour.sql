INSERT INTO poe_trade.gold_listing_ref_hour
SELECT
    toStartOfHour(observed_at) AS time_bucket,
    realm,
    league,
    category,
    base_type,
    price_currency,
    count() AS listing_count,
    quantileExactIf(0.5)(price_amount, price_amount IS NOT NULL) AS median_price_amount,
    now64(3) AS updated_at
FROM poe_trade.v_ps_items_enriched
GROUP BY
    time_bucket,
    realm,
    league,
    category,
    base_type,
    price_currency;
