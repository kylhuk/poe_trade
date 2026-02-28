GRANT INSERT ON poe_trade.bronze_ingest_checkpoints TO poe_ingest_writer;
GRANT INSERT ON poe_trade.bronze_trade_metadata TO poe_ingest_writer;
GRANT SELECT ON poe_trade.v_latest_bronze_checkpoints TO poe_api_reader;
