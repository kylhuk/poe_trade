CREATE ROLE IF NOT EXISTS poe_ingest_writer;
CREATE ROLE IF NOT EXISTS poe_api_reader;
CREATE ROLE IF NOT EXISTS atlas_writer;
CREATE ROLE IF NOT EXISTS atlas_reader;

GRANT INSERT ON poe_trade.raw_public_stash_pages TO poe_ingest_writer;
GRANT INSERT ON poe_trade.raw_currency_exchange_hour TO poe_ingest_writer;
GRANT INSERT ON poe_trade.raw_account_stash_snapshot TO poe_ingest_writer;
GRANT INSERT, UPDATE ON poe_trade.poe_ingest_status TO poe_ingest_writer;
GRANT SELECT ON poe_trade.poe_ingest_status TO poe_ingest_writer;

GRANT SELECT ON poe_trade.* TO poe_api_reader;
GRANT SELECT ON poe_trade.* TO atlas_reader;

GRANT INSERT ON poe_trade.atlas_build_genome TO atlas_writer;
GRANT INSERT ON poe_trade.atlas_build_eval TO atlas_writer;
GRANT INSERT ON poe_trade.atlas_build_cost TO atlas_writer;
GRANT INSERT ON poe_trade.atlas_build_difficulty TO atlas_writer;
GRANT INSERT ON poe_trade.atlas_build_rank TO atlas_writer;
GRANT INSERT ON poe_trade.atlas_coach_plan TO atlas_writer;
GRANT SELECT ON poe_trade.price_stats_1h TO atlas_writer;

CREATE USER IF NOT EXISTS poe_ingest IDENTIFIED WITH no_password
    DEFAULT ROLE poe_ingest_writer;
CREATE USER IF NOT EXISTS poe_reader IDENTIFIED WITH no_password
    DEFAULT ROLE poe_api_reader;
CREATE USER IF NOT EXISTS poe_atlas_writer IDENTIFIED WITH no_password
    DEFAULT ROLE atlas_writer;
CREATE USER IF NOT EXISTS poe_atlas_reader IDENTIFIED WITH no_password
    DEFAULT ROLE atlas_reader;
