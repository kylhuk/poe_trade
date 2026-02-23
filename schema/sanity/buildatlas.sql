-- BuildAtlas sanity queries
SELECT
    league,
    count() AS builds,
    max(created_at) AS newest_build
FROM poe_trade.atlas_build_genome
GROUP BY league
ORDER BY league;

SELECT
    build_id,
    max(evaluated_at) AS last_eval
FROM poe_trade.atlas_build_eval
GROUP BY build_id
ORDER BY last_eval DESC
LIMIT 5;

SELECT
    character_id,
    count() AS plans,
    max(created_at) AS refreshed
FROM poe_trade.atlas_coach_plan
WHERE created_at >= now() - INTERVAL 30 DAY
GROUP BY character_id
ORDER BY plans DESC
LIMIT 5;
