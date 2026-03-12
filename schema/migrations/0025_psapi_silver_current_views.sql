CREATE TABLE IF NOT EXISTS poe_trade.silver_ps_stash_changes (
    observed_at DateTime64(3, 'UTC'),
    realm LowCardinality(String),
    league Nullable(String),
    stash_id String,
    public_flag UInt8,
    account_name Nullable(String),
    stash_name Nullable(String),
    stash_type Nullable(String),
    checkpoint String,
    next_change_id String,
    payload_json String CODEC(ZSTD(6))
) ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(observed_at)
ORDER BY (realm, stash_id, observed_at);

CREATE MATERIALIZED VIEW IF NOT EXISTS poe_trade.mv_ps_stash_changes
TO poe_trade.silver_ps_stash_changes AS
SELECT
    ingested_at AS observed_at,
    realm,
    league,
    stash_id,
    toUInt8(ifNull(JSONExtractBool(payload_json, 'public'), 1)) AS public_flag,
    nullIf(JSONExtractString(payload_json, 'accountName'), '') AS account_name,
    nullIf(JSONExtractString(payload_json, 'stash'), '') AS stash_name,
    nullIf(JSONExtractString(payload_json, 'stashType'), '') AS stash_type,
    checkpoint,
    next_change_id,
    payload_json
FROM poe_trade.raw_public_stash_pages;

CREATE TABLE IF NOT EXISTS poe_trade.silver_ps_items_raw (
    observed_at DateTime64(3, 'UTC'),
    realm LowCardinality(String),
    league Nullable(String),
    stash_id String,
    public_flag UInt8,
    account_name Nullable(String),
    stash_name Nullable(String),
    stash_type Nullable(String),
    checkpoint String,
    next_change_id String,
    item_id Nullable(String),
    item_name String,
    item_type_line String,
    base_type String,
    rarity Nullable(String),
    ilvl UInt16,
    stack_size UInt32,
    note Nullable(String),
    forum_note Nullable(String),
    corrupted UInt8,
    fractured UInt8,
    synthesised UInt8,
    item_json String CODEC(ZSTD(6))
) ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(observed_at)
ORDER BY (realm, league, stash_id, observed_at, item_id);

CREATE MATERIALIZED VIEW IF NOT EXISTS poe_trade.mv_ps_items_raw
TO poe_trade.silver_ps_items_raw AS
SELECT
    base.ingested_at AS observed_at,
    base.realm,
    base.league,
    base.stash_id,
    toUInt8(ifNull(JSONExtractBool(base.payload_json, 'public'), 1)) AS public_flag,
    nullIf(JSONExtractString(base.payload_json, 'accountName'), '') AS account_name,
    nullIf(JSONExtractString(base.payload_json, 'stash'), '') AS stash_name,
    nullIf(JSONExtractString(base.payload_json, 'stashType'), '') AS stash_type,
    base.checkpoint,
    base.next_change_id,
    nullIf(JSONExtractString(item_json, 'id'), '') AS item_id,
    JSONExtractString(item_json, 'name') AS item_name,
    JSONExtractString(item_json, 'typeLine') AS item_type_line,
    JSONExtractString(item_json, 'baseType') AS base_type,
    nullIf(JSONExtractString(item_json, 'rarity'), '') AS rarity,
    toUInt16(ifNull(JSONExtractInt(item_json, 'ilvl'), 0)) AS ilvl,
    greatest(1, toUInt32(ifNull(JSONExtractInt(item_json, 'stackSize'), 1))) AS stack_size,
    nullIf(JSONExtractString(item_json, 'note'), '') AS note,
    nullIf(JSONExtractString(item_json, 'forum_note'), '') AS forum_note,
    toUInt8(ifNull(JSONExtractBool(item_json, 'corrupted'), 0)) AS corrupted,
    toUInt8(ifNull(JSONExtractBool(item_json, 'fractured'), 0)) AS fractured,
    toUInt8(ifNull(JSONExtractBool(item_json, 'synthesised'), 0)) AS synthesised,
    item_json
FROM poe_trade.raw_public_stash_pages AS base
ARRAY JOIN JSONExtractArrayRaw(base.payload_json, 'items') AS item_json;

CREATE VIEW IF NOT EXISTS poe_trade.v_ps_items_enriched AS
SELECT
    *,
    coalesce(note, forum_note, if(match(ifNull(stash_name, ''), '^~'), stash_name, NULL)) AS effective_price_note,
    toFloat64OrNull(extract(coalesce(note, forum_note, if(match(ifNull(stash_name, ''), '^~'), stash_name, '')), '^~(?:b/o|price)\\s+([0-9]+(?:\\.[0-9]+)?)')) AS price_amount,
    nullIf(extract(coalesce(note, forum_note, if(match(ifNull(stash_name, ''), '^~'), stash_name, '')), '^~(?:b/o|price)\\s+[0-9]+(?:\\.[0-9]+)?\\s+(.+)$'), '') AS price_currency,
    multiIf(
        match(base_type, 'Essence'), 'essence',
        match(base_type, 'Fossil'), 'fossil',
        match(base_type, 'Scarab'), 'scarab',
        match(base_type, 'Cluster Jewel'), 'cluster_jewel',
        match(item_type_line, ' Map$'), 'map',
        match(base_type, 'Logbook'), 'logbook',
        match(base_type, 'Flask'), 'flask',
        'other'
    ) AS category
FROM poe_trade.silver_ps_items_raw;

CREATE VIEW IF NOT EXISTS poe_trade.v_ps_current_stashes AS
SELECT
    stash_id,
    argMax(realm, observed_at) AS realm,
    argMax(league, observed_at) AS league,
    argMax(public_flag, observed_at) AS public_flag,
    argMax(account_name, observed_at) AS account_name,
    argMax(stash_name, observed_at) AS stash_name,
    argMax(stash_type, observed_at) AS stash_type,
    argMax(checkpoint, observed_at) AS checkpoint,
    argMax(next_change_id, observed_at) AS next_change_id,
    max(observed_at) AS observed_at,
    argMax(payload_json, observed_at) AS payload_json
FROM poe_trade.silver_ps_stash_changes
GROUP BY stash_id;

CREATE VIEW IF NOT EXISTS poe_trade.v_ps_current_items AS
SELECT
    current_stash.observed_at,
    current_stash.realm,
    current_stash.league,
    current_stash.stash_id,
    current_stash.account_name,
    current_stash.stash_name,
    current_stash.stash_type,
    current_stash.checkpoint,
    current_stash.next_change_id,
    nullIf(JSONExtractString(item_json, 'id'), '') AS item_id,
    JSONExtractString(item_json, 'name') AS item_name,
    JSONExtractString(item_json, 'typeLine') AS item_type_line,
    JSONExtractString(item_json, 'baseType') AS base_type,
    nullIf(JSONExtractString(item_json, 'rarity'), '') AS rarity,
    toUInt16(ifNull(JSONExtractInt(item_json, 'ilvl'), 0)) AS ilvl,
    greatest(1, toUInt32(ifNull(JSONExtractInt(item_json, 'stackSize'), 1))) AS stack_size,
    nullIf(JSONExtractString(item_json, 'note'), '') AS note,
    nullIf(JSONExtractString(item_json, 'forum_note'), '') AS forum_note,
    toUInt8(ifNull(JSONExtractBool(item_json, 'corrupted'), 0)) AS corrupted,
    toUInt8(ifNull(JSONExtractBool(item_json, 'fractured'), 0)) AS fractured,
    toUInt8(ifNull(JSONExtractBool(item_json, 'synthesised'), 0)) AS synthesised,
    item_json
FROM poe_trade.v_ps_current_stashes AS current_stash
ARRAY JOIN JSONExtractArrayRaw(current_stash.payload_json, 'items') AS item_json
WHERE current_stash.public_flag = 1;

GRANT SELECT ON poe_trade.silver_ps_stash_changes TO poe_api_reader;
GRANT SELECT ON poe_trade.silver_ps_items_raw TO poe_api_reader;
GRANT SELECT ON poe_trade.v_ps_items_enriched TO poe_api_reader;
GRANT SELECT ON poe_trade.v_ps_current_stashes TO poe_api_reader;
GRANT SELECT ON poe_trade.v_ps_current_items TO poe_api_reader;
