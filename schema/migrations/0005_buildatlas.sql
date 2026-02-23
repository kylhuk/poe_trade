CREATE TABLE IF NOT EXISTS poe_trade.atlas_build_genome (
    build_id String,
    created_at DateTime64(3, 'UTC'),
    league String,
    genome_json String,
    pob_xml String,
    tags Array(String),
    creator String,
    status String
) ENGINE = MergeTree()
PARTITION BY (league, toYYYYMMDD(created_at))
ORDER BY (league, created_at, build_id)
TTL created_at + INTERVAL 365 DAY;

CREATE TABLE IF NOT EXISTS poe_trade.atlas_build_eval (
    build_id String,
    scenario_id String,
    evaluated_at DateTime64(3, 'UTC'),
    metrics_map Map(String, Float64),
    valid UInt8,
    warnings Array(String)
) ENGINE = MergeTree()
PARTITION BY (toYYYYMMDD(evaluated_at))
ORDER BY (build_id, scenario_id, evaluated_at)
TTL evaluated_at + INTERVAL 365 DAY;

CREATE TABLE IF NOT EXISTS poe_trade.atlas_build_cost (
    build_id String,
    estimated_at DateTime64(3, 'UTC'),
    cost_p10 Float64,
    cost_p50 Float64,
    cost_p90 Float64,
    confidence Float64,
    breakdown Array(String)
) ENGINE = MergeTree()
PARTITION BY (toYYYYMMDD(estimated_at))
ORDER BY (build_id, estimated_at)
TTL estimated_at + INTERVAL 365 DAY;

CREATE TABLE IF NOT EXISTS poe_trade.atlas_build_difficulty (
    build_id String,
    scored_at DateTime64(3, 'UTC'),
    score UInt16,
    reason_codes Array(String),
    details_map Map(String, String)
) ENGINE = MergeTree()
PARTITION BY (toYYYYMMDD(scored_at))
ORDER BY (build_id, scored_at)
TTL scored_at + INTERVAL 365 DAY;

CREATE TABLE IF NOT EXISTS poe_trade.atlas_build_rank (
    build_id String,
    scenario_id String,
    rank_ts DateTime64(3, 'UTC'),
    power_score Float64,
    value_score Float64,
    pareto_rank UInt32,
    meta_risk Float64
) ENGINE = MergeTree()
PARTITION BY (toYYYYMMDD(rank_ts))
ORDER BY (build_id, scenario_id, rank_ts)
TTL rank_ts + INTERVAL 365 DAY;

CREATE TABLE IF NOT EXISTS poe_trade.atlas_coach_plan (
    plan_id String,
    character_id String,
    created_at DateTime64(3, 'UTC'),
    target_profile String,
    steps Array(String),
    total_cost_est Float64,
    status String
) ENGINE = MergeTree()
PARTITION BY (toYYYYMMDD(created_at))
ORDER BY (character_id, created_at, plan_id)
TTL created_at + INTERVAL 365 DAY;
