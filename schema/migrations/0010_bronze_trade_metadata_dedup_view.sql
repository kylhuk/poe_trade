CREATE VIEW IF NOT EXISTS poe_trade.v_bronze_trade_metadata_dedup_24h AS
SELECT
    service,
    realm,
    league,
    trade_id,
    bucket_start_utc,
    argMax(item_id, retrieved_at) AS item_id,
    argMax(listing_ts, retrieved_at) AS listing_ts,
    argMax(delist_ts, retrieved_at) AS delist_ts,
    argMax(trade_data_hash, retrieved_at) AS trade_data_hash,
    argMax(payload_json, retrieved_at) AS payload_json,
    max(retrieved_at) AS last_retrieved_at,
    toUInt8(uniqExact(ifNull(metadata.trade_data_hash, '')) > 1) AS price_change_flag
FROM (
    SELECT
        *,
        toStartOfDay(coalesce(listing_ts, retrieved_at), 'UTC') AS bucket_start_utc
    FROM poe_trade.bronze_trade_metadata
) AS metadata
GROUP BY
    service,
    realm,
    league,
    trade_id,
    bucket_start_utc;

GRANT SELECT ON poe_trade.v_bronze_trade_metadata_dedup_24h TO poe_api_reader;
