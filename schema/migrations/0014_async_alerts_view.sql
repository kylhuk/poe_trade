CREATE VIEW IF NOT EXISTS poe_trade.v_async_alerts AS
SELECT
    base.alert_id,
    base.item_id,
    base.league,
    base.realm,
    base.last_seen_at,
    base.last_price_amount,
    base.last_price_currency,
    base.listings_6h,
    base.cadence_minutes,
    base.time_to_sell_median_seconds,
    base.expected_delay_hours,
    base.sell_through_6hr,
    base.divines_per_attention_minute_estimate,
    base.gold_tax_rate,
    round(
        greatest(
            0.0,
            (1.0 - base.sell_through_6hr)
                + base.gold_tax_rate
                + least(1.0, base.cadence_minutes / 360.0)
        ),
        3
    ) AS expected_drawdown,
    multiIf(
        base.expected_delay_hours <= 3
            AND base.sell_through_6hr >= 0.95
            AND base.divines_per_attention_minute_estimate >= 0.45,
        'red',
        base.expected_delay_hours <= 6
            AND base.sell_through_6hr >= 0.90
            AND base.divines_per_attention_minute_estimate >= 0.30,
        'amber',
        'green'
    ) AS severity,
    toUInt8(
        (
            base.expected_delay_hours <= 3
                AND base.sell_through_6hr >= 0.95
                AND base.divines_per_attention_minute_estimate >= 0.45
        ) OR (
            base.expected_delay_hours <= 6
                AND base.sell_through_6hr >= 0.90
                AND base.divines_per_attention_minute_estimate >= 0.30
        )
    ) AS alert_eligible,
    if(
        (
            base.expected_delay_hours <= 3
                AND base.sell_through_6hr >= 0.95
                AND base.divines_per_attention_minute_estimate >= 0.45
        ) OR (
            base.expected_delay_hours <= 6
                AND base.sell_through_6hr >= 0.90
                AND base.divines_per_attention_minute_estimate >= 0.30
        ),
        base.last_seen_at,
        NULL
    ) AS fired_at
FROM (
    SELECT
        concat('async:', liq.league, ':', liq.item_id) AS alert_id,
        liq.item_id,
        liq.league,
        agg.realm,
        agg.last_seen_at,
        agg.last_price_amount,
        agg.last_price_currency,
        coalesce(agg.listings_6h, 0) AS listings_6h,
        round(
            if(coalesce(agg.listings_6h, 0) > 0, 360.0 / coalesce(agg.listings_6h, 0), 360.0),
            2
        ) AS cadence_minutes,
        liq.time_to_sell_median_seconds,
        round(coalesce(liq.time_to_sell_median_seconds, 86400) / 3600.0, 2) AS expected_delay_hours,
        liq.sell_through_6hr,
        liq.divines_per_attention_minute_estimate,
        0.05 AS gold_tax_rate
    FROM poe_trade.v_liquidity AS liq
    LEFT JOIN (
        SELECT
            league,
            item_id,
            argMax(realm, listing_ts) AS realm,
            max(listing_ts) AS last_seen_at,
            argMax(listing_price_amount, listing_ts) AS last_price_amount,
            argMax(listing_price_currency, listing_ts) AS last_price_currency,
            -- now() keeps this window dynamic by design for alert recency.
            countIf(ingested_at > now() - INTERVAL 6 HOUR) AS listings_6h
        FROM poe_trade.v_liquidity_timeline
        GROUP BY
            league,
            item_id
    ) AS agg
        ON liq.league = agg.league
        AND liq.item_id = agg.item_id
) AS base;

GRANT SELECT ON poe_trade.v_async_alerts TO poe_api_reader;
