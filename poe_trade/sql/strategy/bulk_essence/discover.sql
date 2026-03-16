SELECT
    time_bucket AS time_bucket,
    coalesce(realm, '') AS realm,
    coalesce(league, '') AS league,
    concat(category, ':bulk') AS item_or_market_key,
    concat(category, ':bulk') AS semantic_key,
    'Bulk Essence Premium' AS item_name,
    concat('category=', category, ' bulk_threshold=', toString(bulk_threshold)) AS search_hint,
    (coalesce(median_small_price_amount, 0.0) - coalesce(median_bulk_price_amount, 0.0)) * toFloat64(bulk_threshold) AS expected_profit_chaos,
    if(
        coalesce(median_bulk_price_amount, 0.0) > 0.0,
        (coalesce(median_small_price_amount, 0.0) - coalesce(median_bulk_price_amount, 0.0)) / coalesce(median_bulk_price_amount, 0.0),
        0.0
    ) AS expected_roi,
    least(1.0, toFloat64(bulk_listing_count) / 60.0) AS confidence,
    least(1.0, greatest(toFloat64(bulk_listing_count), toFloat64(small_listing_count)) / 120.0) AS liquidity_score,
    bulk_listing_count AS sample_count,
    coalesce(median_bulk_price_amount, 0.0) * toFloat64(bulk_threshold) AS max_buy,
    'Bulk essence spread between bulk and small listings' AS why_it_fired,
    'Buy bulk essence lots while spread remains above median bulk price' AS buy_plan,
    'Split bulk lots into smaller resale stacks or relist into the exchange premium band' AS transform_plan,
    'Exit once small listings trade under the bulk threshold or ROI drops' AS exit_plan,
    '2h' AS expected_hold_time,
    category,
    bulk_threshold,
    bulk_listing_count,
    small_listing_count,
    median_bulk_price_amount,
    median_small_price_amount
FROM poe_trade.gold_bulk_premium_hour
WHERE category = 'essence';
