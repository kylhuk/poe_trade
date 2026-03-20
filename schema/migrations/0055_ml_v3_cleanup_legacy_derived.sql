-- Legacy pipeline cleanup.
-- Keep all poe_trade.raw_* tables untouched.

DROP TABLE IF EXISTS poe_trade.mv_raw_poeninja_to_ml_fx_hour_v2;
DROP TABLE IF EXISTS poe_trade.mv_silver_ps_items_to_price_labels_v2;
DROP TABLE IF EXISTS poe_trade.mv_price_labels_to_dataset_v2;
DROP TABLE IF EXISTS poe_trade.mv_ml_item_mod_features_sql_stage_v1;
DROP TABLE IF EXISTS poe_trade.mv_item_mod_rollups_v1;
DROP TABLE IF EXISTS poe_trade.mv_ps_stash_changes;
DROP TABLE IF EXISTS poe_trade.mv_ps_items_raw;

DROP VIEW IF EXISTS poe_trade.v_ps_current_items;
DROP VIEW IF EXISTS poe_trade.v_ps_current_stashes;
DROP VIEW IF EXISTS poe_trade.v_ps_items_enriched;
DROP VIEW IF EXISTS poe_trade.ml_latest_items_v1;

DROP TABLE IF EXISTS poe_trade.silver_ps_stash_changes;
DROP TABLE IF EXISTS poe_trade.silver_ps_items_raw;

DROP TABLE IF EXISTS poe_trade.ml_listing_events_v1;
DROP TABLE IF EXISTS poe_trade.ml_execution_labels_v1;
DROP TABLE IF EXISTS poe_trade.ml_fx_hour_v1;
DROP TABLE IF EXISTS poe_trade.ml_fx_hour_v2;
DROP TABLE IF EXISTS poe_trade.ml_price_labels_v1;
DROP TABLE IF EXISTS poe_trade.ml_price_labels_v2;
DROP TABLE IF EXISTS poe_trade.ml_price_dataset_v1;
DROP TABLE IF EXISTS poe_trade.ml_price_dataset_v2;
DROP TABLE IF EXISTS poe_trade.ml_route_candidates_v1;
DROP TABLE IF EXISTS poe_trade.ml_comps_v1;
DROP TABLE IF EXISTS poe_trade.ml_route_eval_v1;
DROP TABLE IF EXISTS poe_trade.ml_eval_runs;
DROP TABLE IF EXISTS poe_trade.ml_train_runs;
DROP TABLE IF EXISTS poe_trade.ml_model_registry_v1;
DROP TABLE IF EXISTS poe_trade.ml_price_predictions_v1;
DROP TABLE IF EXISTS poe_trade.ml_mod_catalog_v1;
DROP TABLE IF EXISTS poe_trade.ml_item_mod_tokens_v1;
DROP TABLE IF EXISTS poe_trade.ml_item_mod_features_v1;
DROP TABLE IF EXISTS poe_trade.ml_item_mod_features_sql_stage_v1;
DROP TABLE IF EXISTS poe_trade.ml_item_mod_feature_states_v1;
DROP TABLE IF EXISTS poe_trade.ml_item_mod_rollups_v1;
DROP TABLE IF EXISTS poe_trade.ml_route_hotspots_v1;
DROP TABLE IF EXISTS poe_trade.ml_promotion_audit_v1;
DROP TABLE IF EXISTS poe_trade.ml_tuning_rounds_v1;
DROP TABLE IF EXISTS poe_trade.ml_serving_profile_v1;
