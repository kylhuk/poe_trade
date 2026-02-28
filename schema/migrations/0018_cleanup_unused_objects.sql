-- 0018: remove ClickHouse objects unused by market_harvester & stash_scribe
-- Views must go first so dependencies disappear before dropping tables.

DROP VIEW IF EXISTS poe_trade.v_ops_alerts;
DROP VIEW IF EXISTS poe_trade.v_async_alerts;
DROP VIEW IF EXISTS poe_trade.v_liquidity;
DROP VIEW IF EXISTS poe_trade.v_liquidity_timeline;
DROP VIEW IF EXISTS poe_trade.v_bronze_public_stash_items;
DROP VIEW IF EXISTS poe_trade.v_bronze_trade_metadata_dedup_24h;
DROP VIEW IF EXISTS poe_trade.v_ops_ingest_health;
DROP VIEW IF EXISTS poe_trade.v_latest_bronze_checkpoints;
DROP VIEW IF EXISTS poe_trade.v_slo_metrics;

DROP TABLE IF EXISTS poe_trade.ops_alert_log;
DROP TABLE IF EXISTS poe_trade.overlay_event_log;
DROP TABLE IF EXISTS poe_trade.ops_drift_log;
DROP TABLE IF EXISTS poe_trade.ops_signal_mute_log;
DROP TABLE IF EXISTS poe_trade.fallback_drill_log;
DROP TABLE IF EXISTS poe_trade.atlas_build_genome;
DROP TABLE IF EXISTS poe_trade.atlas_build_eval;
DROP TABLE IF EXISTS poe_trade.atlas_build_cost;
DROP TABLE IF EXISTS poe_trade.atlas_build_difficulty;
DROP TABLE IF EXISTS poe_trade.atlas_build_rank;
DROP TABLE IF EXISTS poe_trade.atlas_coach_plan;
DROP TABLE IF EXISTS poe_trade.price_stats_1h;
DROP TABLE IF EXISTS poe_trade.stash_price_suggestions;
DROP TABLE IF EXISTS poe_trade.flip_opportunities;
DROP TABLE IF EXISTS poe_trade.craft_opportunities;
DROP TABLE IF EXISTS poe_trade.farming_sessions;
DROP TABLE IF EXISTS poe_trade.item_canonical;
DROP TABLE IF EXISTS poe_trade.listing_canonical;
DROP TABLE IF EXISTS poe_trade.currency_rates;
DROP TABLE IF EXISTS poe_trade.raw_currency_exchange_hour;
