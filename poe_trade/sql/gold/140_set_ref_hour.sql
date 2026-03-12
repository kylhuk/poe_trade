INSERT INTO poe_trade.gold_set_ref_hour
SELECT
    toStartOfHour(observed_at) AS time_bucket,
    realm,
    league,
    category,
    uniqExact(base_type) AS distinct_base_types,
    count() AS listing_count,
    now64(3) AS updated_at
FROM poe_trade.v_ps_items_enriched
WHERE category IN ('map', 'logbook', 'other')
GROUP BY
    time_bucket,
    realm,
    league,
    category;
