-- 0021: rebuild raw_public_stash_pages to allow nullable league payloads
-- NOTE: This is a heavy, non-additive rebuild; the backup table is intentionally retained for rollback

CREATE TABLE IF NOT EXISTS poe_trade.raw_public_stash_pages_shadow_0021 (
    ingested_at DateTime64(3, 'UTC') CODEC(Delta, ZSTD(1)),
    realm String,
    league Nullable(String),
    stash_id String CODEC(ZSTD(6)),
    checkpoint String,
    next_change_id String,
    payload_json String CODEC(ZSTD(6))
) ENGINE = MergeTree()
PARTITION BY (ifNull(league, 'missing_league'), toYYYYMMDD(ingested_at))
ORDER BY (ifNull(league, 'missing_league'), ingested_at)
TTL ingested_at + INTERVAL 14 DAY;

RENAME TABLE
    poe_trade.raw_public_stash_pages TO poe_trade.raw_public_stash_pages_backup_0021,
    poe_trade.raw_public_stash_pages_shadow_0021 TO poe_trade.raw_public_stash_pages;

INSERT INTO poe_trade.raw_public_stash_pages
SELECT
    ingested_at,
    realm,
    CAST(league AS Nullable(String)) AS league,
    stash_id,
    checkpoint,
    next_change_id,
    payload_json
FROM poe_trade.raw_public_stash_pages_backup_0021;
