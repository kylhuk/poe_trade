CREATE TABLE IF NOT EXISTS poe_trade.silver_account_stash_items (
    observed_at DateTime64(3, 'UTC'),
    realm String,
    league String,
    tab_id String,
    tab_name String,
    tab_type String,
    item_id String,
    item_name String,
    item_class String,
    rarity LowCardinality(String),
    x UInt16,
    y UInt16,
    w UInt16,
    h UInt16,
    listed_price Nullable(Float64),
    estimated_price Float64,
    estimated_price_confidence UInt8,
    currency LowCardinality(String),
    icon_url String,
    payload_json String
) ENGINE = MergeTree()
PARTITION BY (league, toYYYYMMDD(observed_at))
ORDER BY (league, realm, tab_id, observed_at, item_id)
TTL observed_at + INTERVAL 30 DAY;

GRANT INSERT ON poe_trade.silver_account_stash_items TO poe_ingest_writer;
GRANT SELECT ON poe_trade.silver_account_stash_items TO poe_api_reader;
