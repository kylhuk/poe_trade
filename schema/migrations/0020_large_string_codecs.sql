-- 0020: add stronger codecs to large strings (performance/storage mutation; may be heavy)

ALTER TABLE poe_trade.raw_public_stash_pages
MODIFY COLUMN payload_json String CODEC(ZSTD(6));

ALTER TABLE poe_trade.raw_public_stash_pages
MODIFY COLUMN stash_id String CODEC(ZSTD(6));

ALTER TABLE poe_trade.raw_account_stash_snapshot
MODIFY COLUMN payload_json String CODEC(ZSTD(6));

ALTER TABLE poe_trade.raw_account_stash_snapshot
MODIFY COLUMN snapshot_id String CODEC(ZSTD(6));

ALTER TABLE poe_trade.raw_account_stash_snapshot
MODIFY COLUMN tab_id String CODEC(ZSTD(6));
