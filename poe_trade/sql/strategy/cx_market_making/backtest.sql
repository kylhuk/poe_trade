SELECT
    time_bucket,
    league,
    concat(base_code, '/', quote_code) AS item_or_market_key,
    (toFloat64(has_highest_ratio) - toFloat64(has_lowest_ratio)) * 5.0 AS expected_profit_chaos,
    if(has_lowest_ratio = 1, 0.1, 0.0) AS expected_roi,
    least(1.0, toFloat64(sample_count) / 120.0) AS confidence,
    concat('currency spread for ', base_code, '/', quote_code) AS summary
FROM poe_trade.gold_currency_ref_hour;
