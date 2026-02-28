CREATE VIEW IF NOT EXISTS poe_trade.v_bronze_public_stash_items AS
SELECT
    stage.ingested_at,
    stage.realm,
    stage.league,
    stage.stash_id,
    -- listing_id is expected to match the trade_id exposed by bronze metadata.
    nullIf(coalesce(JSONExtractString(stage.listing_json, 'id'), ''), '') AS listing_id,
    coalesce(
        ifNull(JSONExtractString(stage.item_json, 'item_id'), ''),
        ifNull(JSONExtractString(stage.item_json, 'id'), ''),
        ''
    ) AS item_id,
        greatest(
            1,
            toUInt32OrZero(
                toString(ifNull(JSONExtractInt(stage.item_json, 'stackSize'), 0))
            )
        ) AS stack_size,
    ifNull(JSONExtractFloat(stage.price_json, 'amount'), 0.0) AS listing_price_amount,
    ifNull(JSONExtractString(stage.price_json, 'currency'), 'unknown') AS listing_price_currency
FROM (
    SELECT
        base.ingested_at,
        base.realm,
        base.league,
        base.stash_id,
        arrayJoin(
            JSONExtract(
                coalesce(JSONExtractRaw(base.stash_json, 'items'), '[]'),
                'Array(String)'
            )
        ) AS item_json,
        coalesce(JSONExtractRaw(item_json, 'listing'), '{}') AS listing_json,
        coalesce(
            JSONExtractRaw(
                coalesce(JSONExtractRaw(item_json, 'listing'), '{}'),
                'price'
            ),
            '{}'
        ) AS price_json
    FROM (
        SELECT
            raw.ingested_at,
            raw.realm,
            raw.league,
            raw.stash_id,
            arrayJoin(
                JSONExtract(
                    coalesce(JSONExtractRaw(raw.payload_json, 'stashes'), '[]'),
                    'Array(String)'
                )
            ) AS stash_json
        FROM poe_trade.raw_public_stash_pages AS raw
    ) AS base
) AS stage;

GRANT SELECT ON poe_trade.v_bronze_public_stash_items TO poe_api_reader;

CREATE VIEW IF NOT EXISTS poe_trade.v_liquidity_timeline AS
SELECT
    items.ingested_at,
    items.realm,
    items.league,
    items.stash_id,
    items.listing_id,
    items.item_id,
    items.stack_size,
    items.listing_price_amount,
    items.listing_price_currency,
    listing_ts,
    delist_ts,
    trade_data_hash,
    last_retrieved_at,
    bucket_start_utc,
    price_change_flag,
    service AS metadata_service
FROM poe_trade.v_bronze_public_stash_items AS items
-- listing_id is expected to match trade_id in v_bronze_trade_metadata_dedup_24h; adjust if that contract changes.
LEFT JOIN poe_trade.v_bronze_trade_metadata_dedup_24h AS trade_metadata
    ON items.listing_id = trade_metadata.trade_id
    AND items.league = trade_metadata.league
    AND items.realm = trade_metadata.realm
WHERE items.listing_id IS NOT NULL;

GRANT SELECT ON poe_trade.v_liquidity_timeline TO poe_api_reader;

CREATE VIEW IF NOT EXISTS poe_trade.v_liquidity AS
SELECT
    base.item_id,
    base.league,
    base.total_listings,
    base.sell_through_6hr,
    base.time_to_sell_median_seconds AS time_to_sell_median_seconds,
    round(
        greatest(
            0.0,
            least(
                1.0,
                0.5
                    + 0.4 * base.sell_through_6hr
                    - 0.0003 * least(coalesce(base.time_to_sell_median_seconds, 7200), 7200)
            )
        ),
        3
    ) AS divines_per_attention_minute_estimate
FROM (
    SELECT
        item_id,
        league,
        countIf(listing_ts IS NOT NULL) AS total_listings,
        toFloat64(
            sumIf(
                1,
                listing_ts IS NOT NULL
                    AND delist_ts IS NOT NULL
                    AND delist_ts <= listing_ts + INTERVAL 6 HOUR
            )
        )
            / greatest(toFloat64(countIf(listing_ts IS NOT NULL)), 1.0)
            AS sell_through_6hr,
        quantileExactIf(0.5)(
            dateDiff('second', listing_ts, delist_ts),
            listing_ts IS NOT NULL AND delist_ts IS NOT NULL
        ) AS time_to_sell_median_seconds
    FROM poe_trade.v_liquidity_timeline
    WHERE item_id != ''
    GROUP BY
        item_id,
        league
) AS base;

GRANT SELECT ON poe_trade.v_liquidity TO poe_api_reader;
