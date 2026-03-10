CREATE TABLE stash_events
(
    event_time DateTime,
    item_id String,
    account String,
    league String,
    price Float64,
    currency String,
    raw_json String
)
ENGINE = MergeTree
ORDER BY (event_time);

CREATE TABLE parsed_items
(
    item_id String,
    base_type String,
    item_level UInt16,
    rarity String,
    sockets UInt8,
    links UInt8,
    influence String
)
ENGINE = MergeTree
ORDER BY (item_id);

CREATE TABLE active_listings
(
    item_id String,
    price Float64,
    currency String,
    listed_at DateTime,
    account String
)
ENGINE = MergeTree
ORDER BY (listed_at);

CREATE MATERIALIZED VIEW listings_mv
TO active_listings
AS
SELECT
    item_id,
    price,
    currency,
    event_time AS listed_at,
    account
FROM stash_events
WHERE price > 0;
