CREATE VIEW IF NOT EXISTS poe_trade.v_ops_ingest_health AS
SELECT
    service,
    realm,
    league,
    endpoint,
    last_checkpoint_at,
    lag_seconds,

    CASE
        WHEN lag_seconds > 60 THEN 'red'
        WHEN lag_seconds > 20 THEN 'amber'
        ELSE 'green'
    END AS severity,

    if(lag_seconds > 20, 1, 0) AS divines_per_attention_minute_risk_flag
FROM (
    SELECT
        service,
        realm,
        league,
        endpoint,
        max(retrieved_at) AS last_checkpoint_at,
        greatest(0, dateDiff('second', max(retrieved_at), now())) AS lag_seconds
    FROM poe_trade.bronze_ingest_checkpoints
    GROUP BY
        service,
        realm,
        league,
        endpoint
) AS latest_checkpoints;

GRANT SELECT ON poe_trade.v_ops_ingest_health TO poe_api_reader;
