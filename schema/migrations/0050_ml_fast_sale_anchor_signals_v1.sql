-- Additive diagnostics for fast-sale anchor and outlier decisions.
ALTER TABLE poe_trade.ml_price_dataset_v2
    ADD COLUMN IF NOT EXISTS anchor_price Nullable(Float64) AFTER confidence_hint;

ALTER TABLE poe_trade.ml_price_dataset_v2
    ADD COLUMN IF NOT EXISTS credible_low Nullable(Float64) AFTER anchor_price;

ALTER TABLE poe_trade.ml_price_dataset_v2
    ADD COLUMN IF NOT EXISTS credible_high Nullable(Float64) AFTER credible_low;

ALTER TABLE poe_trade.ml_price_dataset_v2
    ADD COLUMN IF NOT EXISTS anchor_support_count UInt32 DEFAULT 0 AFTER credible_high;

ALTER TABLE poe_trade.ml_price_dataset_v2
    ADD COLUMN IF NOT EXISTS trim_low_count UInt16 DEFAULT 0 AFTER anchor_support_count;

ALTER TABLE poe_trade.ml_price_dataset_v2
    ADD COLUMN IF NOT EXISTS trim_high_count UInt16 DEFAULT 0 AFTER trim_low_count;
