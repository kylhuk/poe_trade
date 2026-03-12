SELECT
    time_bucket,
    coalesce(league, '') AS league,
    concat(category, ':set') AS item_or_market_key,
    toFloat64(listing_count) * 0.06 AS expected_profit_chaos,
    if(distinct_base_types > 0, toFloat64(listing_count) / toFloat64(distinct_base_types), 0.0) AS expected_roi,
    least(1.0, toFloat64(distinct_base_types) / 20.0) AS confidence,
    concat('map/logbook package depth for ', category) AS summary
FROM poe_trade.gold_set_ref_hour
WHERE category IN ('map', 'logbook');
