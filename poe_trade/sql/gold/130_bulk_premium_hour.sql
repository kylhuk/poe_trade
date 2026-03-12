INSERT INTO poe_trade.gold_bulk_premium_hour
SELECT
    toStartOfHour(observed_at) AS time_bucket,
    realm,
    league,
    category,
    toUInt32(10) AS bulk_threshold,
    countIf(stack_size >= 10) AS bulk_listing_count,
    countIf(stack_size < 10) AS small_listing_count,
    quantileExactIf(0.5)(price_amount, stack_size >= 10 AND price_amount IS NOT NULL) AS median_bulk_price_amount,
    quantileExactIf(0.5)(price_amount, stack_size < 10 AND price_amount IS NOT NULL) AS median_small_price_amount,
    now64(3) AS updated_at
FROM poe_trade.v_ps_items_enriched
GROUP BY
    time_bucket,
    realm,
    league,
    category;
