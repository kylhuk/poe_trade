SELECT
    realm,
    ifNull(league, 'unknown') AS league,
    count() AS stash_change_rows,
    max(observed_at) AS latest_observed_at
FROM poe_trade.silver_ps_stash_changes
GROUP BY
    realm,
    league
ORDER BY realm, league;

SELECT
    realm,
    ifNull(league, 'unknown') AS league,
    category,
    count() AS item_rows,
    max(observed_at) AS latest_observed_at
FROM poe_trade.v_ps_items_enriched
GROUP BY
    realm,
    league,
    category
ORDER BY item_rows DESC
LIMIT 20;

SELECT
    stash_id,
    realm,
    ifNull(league, 'unknown') AS league,
    observed_at
FROM poe_trade.v_ps_current_stashes
ORDER BY observed_at DESC
LIMIT 10;

SELECT
    realm,
    league,
    market_pair,
    count() AS market_rows,
    max(hour_ts) AS latest_hour
FROM poe_trade.v_cx_markets_enriched
GROUP BY
    realm,
    league,
    market_pair
ORDER BY latest_hour DESC
LIMIT 20;

SELECT
    stash_id,
    item_id,
    sold_at,
    price
FROM poe_trade.v_account_stash_sold_items
ORDER BY sold_at DESC
LIMIT 20;
