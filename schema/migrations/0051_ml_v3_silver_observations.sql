CREATE TABLE IF NOT EXISTS poe_trade.silver_v3_item_observations (
    observed_at DateTime64(3, 'UTC') CODEC(Delta(8), ZSTD(1)),
    realm LowCardinality(String),
    league LowCardinality(String),
    stash_id String CODEC(ZSTD(6)),
    account_name Nullable(String),
    stash_name Nullable(String),
    checkpoint String,
    next_change_id String,
    item_id Nullable(String),
    identity_key String,
    fingerprint_v3 String,
    item_name String,
    item_type_line String,
    base_type String,
    rarity LowCardinality(String),
    category LowCardinality(String),
    ilvl UInt16,
    stack_size UInt32,
    corrupted UInt8,
    fractured UInt8,
    synthesised UInt8,
    note Nullable(String),
    forum_note Nullable(String),
    effective_price_note Nullable(String),
    parsed_amount Nullable(Float64),
    parsed_currency Nullable(String),
    normalized_affix_hash String,
    affix_payload_json String CODEC(ZSTD(6)),
    item_json String CODEC(ZSTD(6)),
    inserted_at DateTime64(3, 'UTC') DEFAULT now64(3) CODEC(Delta(8), ZSTD(1))
) ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(observed_at)
ORDER BY (league, realm, stash_id, identity_key, observed_at)
SETTINGS index_granularity = 8192;

CREATE MATERIALIZED VIEW IF NOT EXISTS poe_trade.mv_raw_public_stash_to_silver_v3_item_observations
TO poe_trade.silver_v3_item_observations
AS
WITH
    JSONExtractArrayRaw(base.payload_json, 'items') AS items,
    ifNull(JSONExtractString(base.payload_json, 'accountName'), '') AS account_name_raw,
    ifNull(JSONExtractString(base.payload_json, 'stash'), '') AS stash_name_raw
SELECT
    base.ingested_at AS observed_at,
    base.realm AS realm,
    ifNull(base.league, 'unknown') AS league,
    ifNull(base.stash_id, '') AS stash_id,
    nullIf(account_name_raw, '') AS account_name,
    nullIf(stash_name_raw, '') AS stash_name,
    base.checkpoint AS checkpoint,
    base.next_change_id AS next_change_id,
    nullIf(JSONExtractString(item_json, 'id'), '') AS item_id,
    if(
        nullIf(JSONExtractString(item_json, 'id'), '') IS NOT NULL,
        nullIf(JSONExtractString(item_json, 'id'), ''),
        lower(hex(SHA256(concat(
            ifNull(account_name_raw, ''),
            '|',
            ifNull(base.stash_id, ''),
            '|',
            ifNull(JSONExtractString(item_json, 'baseType'), ''),
            '|',
            ifNull(JSONExtractString(item_json, 'rarity'), ''),
            '|',
            toString(ifNull(JSONExtractInt(item_json, 'ilvl'), 0)),
            '|',
            ifNull(JSONExtractRaw(item_json, 'explicitMods'), '[]'),
            '|',
            ifNull(JSONExtractRaw(item_json, 'implicitMods'), '[]'),
            '|',
            ifNull(JSONExtractRaw(item_json, 'craftedMods'), '[]'),
            '|',
            ifNull(JSONExtractRaw(item_json, 'fracturedMods'), '[]'),
            '|',
            ifNull(JSONExtractRaw(item_json, 'enchantMods'), '[]')
        ))))
    ) AS identity_key,
    lower(hex(SHA256(concat(
        ifNull(account_name_raw, ''),
        '|',
        ifNull(base.stash_id, ''),
        '|',
        ifNull(JSONExtractString(item_json, 'baseType'), ''),
        '|',
        ifNull(JSONExtractString(item_json, 'rarity'), ''),
        '|',
        toString(ifNull(JSONExtractInt(item_json, 'ilvl'), 0)),
        '|',
        ifNull(JSONExtractRaw(item_json, 'explicitMods'), '[]'),
        '|',
        ifNull(JSONExtractRaw(item_json, 'implicitMods'), '[]'),
        '|',
        ifNull(JSONExtractRaw(item_json, 'craftedMods'), '[]'),
        '|',
        ifNull(JSONExtractRaw(item_json, 'fracturedMods'), '[]'),
        '|',
        ifNull(JSONExtractRaw(item_json, 'enchantMods'), '[]')
    )))) AS fingerprint_v3,
    ifNull(JSONExtractString(item_json, 'name'), '') AS item_name,
    ifNull(JSONExtractString(item_json, 'typeLine'), '') AS item_type_line,
    ifNull(JSONExtractString(item_json, 'baseType'), '') AS base_type,
    ifNull(nullIf(JSONExtractString(item_json, 'rarity'), ''), 'unknown') AS rarity,
    multiIf(
        match(lowerUTF8(ifNull(JSONExtractString(item_json, 'baseType'), '')), 'essence'), 'essence',
        match(lowerUTF8(ifNull(JSONExtractString(item_json, 'baseType'), '')), 'fossil'), 'fossil',
        match(lowerUTF8(ifNull(JSONExtractString(item_json, 'baseType'), '')), 'scarab'), 'scarab',
        match(lowerUTF8(ifNull(JSONExtractString(item_json, 'baseType'), '')), 'cluster\\s+jewel'), 'cluster_jewel',
        match(lowerUTF8(ifNull(JSONExtractString(item_json, 'typeLine'), '')), ' map$'), 'map',
        match(lowerUTF8(ifNull(JSONExtractString(item_json, 'baseType'), '')), 'logbook'), 'logbook',
        match(lowerUTF8(ifNull(JSONExtractString(item_json, 'baseType'), '')), 'ring'), 'ring',
        match(lowerUTF8(ifNull(JSONExtractString(item_json, 'baseType'), '')), 'amulet'), 'amulet',
        match(lowerUTF8(ifNull(JSONExtractString(item_json, 'baseType'), '')), 'belt'), 'belt',
        'other'
    ) AS category,
    toUInt16(greatest(0, ifNull(JSONExtractInt(item_json, 'ilvl'), 0))) AS ilvl,
    toUInt32(greatest(1, ifNull(JSONExtractInt(item_json, 'stackSize'), 1))) AS stack_size,
    toUInt8(ifNull(JSONExtractBool(item_json, 'corrupted'), 0)) AS corrupted,
    toUInt8(ifNull(JSONExtractBool(item_json, 'fractured'), 0)) AS fractured,
    toUInt8(ifNull(JSONExtractBool(item_json, 'synthesised'), 0)) AS synthesised,
    nullIf(JSONExtractString(item_json, 'note'), '') AS note,
    nullIf(JSONExtractString(item_json, 'forum_note'), '') AS forum_note,
    coalesce(
        nullIf(JSONExtractString(item_json, 'note'), ''),
        nullIf(JSONExtractString(item_json, 'forum_note'), ''),
        if(match(ifNull(stash_name_raw, ''), '^~'), nullIf(stash_name_raw, ''), NULL)
    ) AS effective_price_note,
    toFloat64OrNull(extract(
        coalesce(
            nullIf(JSONExtractString(item_json, 'note'), ''),
            nullIf(JSONExtractString(item_json, 'forum_note'), ''),
            if(match(ifNull(stash_name_raw, ''), '^~'), stash_name_raw, '')
        ),
        '^~(?:b/o|price)\\s+([0-9]+(?:\\.[0-9]+)?)'
    )) AS parsed_amount,
    nullIf(extract(
        coalesce(
            nullIf(JSONExtractString(item_json, 'note'), ''),
            nullIf(JSONExtractString(item_json, 'forum_note'), ''),
            if(match(ifNull(stash_name_raw, ''), '^~'), stash_name_raw, '')
        ),
        '^~(?:b/o|price)\\s+[0-9]+(?:\\.[0-9]+)?\\s+(.+)$'
    ), '') AS parsed_currency,
    lower(hex(SHA256(concat(
        ifNull(JSONExtractRaw(item_json, 'explicitMods'), '[]'),
        '|',
        ifNull(JSONExtractRaw(item_json, 'implicitMods'), '[]'),
        '|',
        ifNull(JSONExtractRaw(item_json, 'craftedMods'), '[]'),
        '|',
        ifNull(JSONExtractRaw(item_json, 'fracturedMods'), '[]'),
        '|',
        ifNull(JSONExtractRaw(item_json, 'enchantMods'), '[]')
    )))) AS normalized_affix_hash,
    concat(
        '{"explicit":', ifNull(JSONExtractRaw(item_json, 'explicitMods'), '[]'),
        ',"implicit":', ifNull(JSONExtractRaw(item_json, 'implicitMods'), '[]'),
        ',"crafted":', ifNull(JSONExtractRaw(item_json, 'craftedMods'), '[]'),
        ',"fractured":', ifNull(JSONExtractRaw(item_json, 'fracturedMods'), '[]'),
        ',"enchant":', ifNull(JSONExtractRaw(item_json, 'enchantMods'), '[]'),
        '}'
    ) AS affix_payload_json,
    item_json,
    now64(3) AS inserted_at
FROM poe_trade.raw_public_stash_pages AS base
ARRAY JOIN items AS item_json;

GRANT SELECT ON poe_trade.silver_v3_item_observations TO poe_api_reader;
