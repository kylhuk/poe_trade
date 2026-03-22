from __future__ import annotations

from collections.abc import Mapping

import pytest

from poe_trade.api.ops import (
    analytics_backtests,
    analytics_gold_diagnostics,
    analytics_opportunities,
    analytics_pricing_outliers,
    analytics_report,
    analytics_scanner,
    analytics_search_history,
    analytics_search_suggestions,
    dashboard_payload,
    scanner_recommendations_payload,
    scanner_summary_payload,
)
from poe_trade.api.service_control import ServiceSnapshot
from poe_trade.db import ClickHouseClient
from poe_trade.db.clickhouse import ClickHouseClientError


class _RecordingClickHouse(ClickHouseClient):
    def __init__(self) -> None:
        super().__init__(endpoint="http://clickhouse")
        self.queries: list[str] = []

    def execute(  # pyright: ignore[reportImplicitOverride]
        self, query: str, settings: Mapping[str, str] | None = None
    ) -> str:
        self.queries.append(query)
        return ""


class _FixtureClickHouse(ClickHouseClient):
    def __init__(self, responses: dict[str, str]) -> None:
        super().__init__(endpoint="http://clickhouse")
        self.responses: dict[str, str] = responses
        self.queries: list[str] = []

    def execute(  # pyright: ignore[reportImplicitOverride]
        self, query: str, settings: Mapping[str, str] | None = None
    ) -> str:
        del settings
        self.queries.append(query)
        for needle, response in self.responses.items():
            if needle in query:
                return response
        return ""


class _SequentialFixtureClickHouse(ClickHouseClient):
    def __init__(self, responses: list[str]) -> None:
        super().__init__(endpoint="http://clickhouse")
        self.responses = list(responses)
        self.queries: list[str] = []

    def execute(  # pyright: ignore[reportImplicitOverride]
        self, query: str, settings: Mapping[str, str] | None = None
    ) -> str:
        del settings
        self.queries.append(query)
        if self.responses:
            return self.responses.pop(0)
        return ""


class _LegacyFallbackClickHouse(ClickHouseClient):
    def __init__(self, legacy_response: str) -> None:
        super().__init__(endpoint="http://clickhouse")
        self.legacy_response = legacy_response
        self.queries: list[str] = []

    def execute(  # pyright: ignore[reportImplicitOverride]
        self, query: str, settings: Mapping[str, str] | None = None
    ) -> str:
        del settings
        self.queries.append(query)
        if "complexity_tier" in query:
            raise ClickHouseClientError("Unknown column complexity_tier")
        if "estimated_searches" in query:
            raise ClickHouseClientError(
                "Unknown expression identifier `estimated_searches`"
            )
        return self.legacy_response


class _LegacyFallbackSequentialClickHouse(ClickHouseClient):
    def __init__(self, legacy_responses: list[str]) -> None:
        super().__init__(endpoint="http://clickhouse")
        self.legacy_responses = list(legacy_responses)
        self.queries: list[str] = []

    def execute(  # pyright: ignore[reportImplicitOverride]
        self, query: str, settings: Mapping[str, str] | None = None
    ) -> str:
        del settings
        self.queries.append(query)
        if "complexity_tier" in query:
            raise ClickHouseClientError("Unknown column complexity_tier")
        if self.legacy_responses:
            return self.legacy_responses.pop(0)
        return ""


class _AnalyticsCompatibilityClickHouse(ClickHouseClient):
    def __init__(self, responses: dict[str, str]) -> None:
        super().__init__(endpoint="http://clickhouse")
        self.responses = responses
        self.queries: list[str] = []

    def execute(  # pyright: ignore[reportImplicitOverride]
        self, query: str, settings: Mapping[str, str] | None = None
    ) -> str:
        del settings
        self.queries.append(query)
        lowered = query.lower()
        if "from poe_trade.scanner_candidate_decisions" in lowered:
            raise ClickHouseClientError(
                "Table poe_trade.scanner_candidate_decisions doesn't exist"
            )
        if "ifnull(opportunity_type" in lowered:
            raise ClickHouseClientError(
                "Unknown column opportunity_type in table scanner_recommendations"
            )
        if (
            "select complexity_tier, count() as tier_count" in lowered
            or "ifnull(complexity_tier, '') as complexity_tier" in lowered
        ):
            raise ClickHouseClientError(
                "Unknown column complexity_tier in table scanner_recommendations"
            )
        for needle, response in self.responses.items():
            if needle in query:
                return response
        return ""


def test_analytics_scanner_query_does_not_require_status_column() -> None:
    client = _FixtureClickHouse(
        {
            "count() AS recommendation_count": '{"strategy_id":"bulk_essence","recommendation_count":4}\n',
            "count() AS rejection_count": '{"decision_reason":"rejected_min_confidence","rejection_count":2}\n',
            "count() AS tier_count": '{"complexity_tier":"medium","tier_count":3}\n',
        }
    )

    result = analytics_scanner(client)

    assert result["rows"] == [
        {"strategy_id": "bulk_essence", "recommendation_count": 4}
    ]
    assert result["gateRejections"] == [
        {"decision_reason": "rejected_min_confidence", "rejection_count": 2}
    ]
    assert result["complexityTiers"] == [{"complexity_tier": "medium", "tier_count": 3}]
    assert len(client.queries) == 3
    assert "scanner_recommendations.status" not in client.queries[0]
    assert "GROUP BY status" not in client.queries[0]
    assert "GROUP BY strategy_id" in client.queries[0]
    assert "recommendation_count" in client.queries[0]


def test_analytics_opportunities_includes_distributions_and_decision_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FixtureClickHouse(
        {
            "AS opportunity_type": '{"opportunity_type":"bulk_flip","count":5}\n',
            "AS complexity_tier": '{"complexity_tier":"medium","count":4}\n',
            "WHERE accepted = 0": (
                '{"decision_reason":"rejected_cooldown_active","count":3}\n'
                '{"decision_reason":"suppressed_duplicate","count":2}\n'
            ),
        }
    )
    captured: dict[str, object] = {}

    def _mock_scanner_recommendations(
        _client: ClickHouseClient, **kwargs: object
    ) -> dict[str, object]:
        captured.update(kwargs)
        return {
            "recommendations": [
                {"scannerRunId": "scan-1", "expectedProfitPerOperationChaos": 9.0}
            ],
            "meta": {"hasMore": False, "nextCursor": None},
        }

    monkeypatch.setattr(
        "poe_trade.api.ops.scanner_recommendations_payload",
        _mock_scanner_recommendations,
    )

    result = analytics_opportunities(client)

    assert result["distributions"] == {
        "opportunityType": [{"opportunity_type": "bulk_flip", "count": 5}],
        "complexityTier": [{"complexity_tier": "medium", "count": 4}],
    }
    assert result["decisionLog"] == {
        "rejections": [{"decision_reason": "rejected_cooldown_active", "count": 3}],
        "suppressions": [{"decision_reason": "suppressed_duplicate", "count": 2}],
    }
    assert result["topOpportunities"] == [
        {"scannerRunId": "scan-1", "expectedProfitPerOperationChaos": 9.0}
    ]
    assert captured == {
        "limit": 20,
        "sort_by": "expected_profit_per_operation_chaos",
    }


def test_analytics_scanner_remains_compatible_before_0057() -> None:
    client = _AnalyticsCompatibilityClickHouse(
        {
            "count() AS recommendation_count": '{"strategy_id":"bulk_essence","recommendation_count":4}\n',
            "JSONExtractString(evidence_snapshot, 'complexity_tier')": '{"complexity_tier":"medium","tier_count":3}\n',
        }
    )

    result = analytics_scanner(client)

    assert result == {
        "rows": [{"strategy_id": "bulk_essence", "recommendation_count": 4}],
        "gateRejections": [],
        "complexityTiers": [{"complexity_tier": "medium", "tier_count": 3}],
    }


def test_analytics_opportunities_remains_compatible_before_0057(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _AnalyticsCompatibilityClickHouse(
        {
            "JSONExtractString(evidence_snapshot, 'opportunity_type')": '{"opportunity_type":"bulk_flip","count":5}\n',
            "JSONExtractString(evidence_snapshot, 'complexity_tier')": '{"complexity_tier":"medium","count":4}\n',
        }
    )

    monkeypatch.setattr(
        "poe_trade.api.ops.scanner_recommendations_payload",
        lambda _client, **_kwargs: {
            "recommendations": [
                {"scannerRunId": "scan-1", "expectedProfitPerOperationChaos": 9.0}
            ],
            "meta": {"hasMore": False, "nextCursor": None},
        },
    )

    result = analytics_opportunities(client)

    assert result["distributions"] == {
        "opportunityType": [{"opportunity_type": "bulk_flip", "count": 5}],
        "complexityTier": [{"complexity_tier": "medium", "count": 4}],
    }
    assert result["decisionLog"] == {"rejections": [], "suppressions": []}
    assert result["topOpportunities"] == [
        {"scannerRunId": "scan-1", "expectedProfitPerOperationChaos": 9.0}
    ]


def test_analytics_pricing_outliers_league_all_does_not_pin_affix_join_league() -> None:
    client = _FixtureClickHouse({})

    analytics_pricing_outliers(
        client,
        query_params={"league": ["all"]},
        default_league="Mirage",
    )

    assert len(client.queries) == 2
    assert "t.league = 'all'" not in client.queries[0]


def test_analytics_search_history_rejects_invalid_price_min() -> None:
    client = _FixtureClickHouse({})

    with pytest.raises(ValueError, match="price_min"):
        analytics_search_history(
            client,
            query_params={"price_min": ["abc"]},
            default_league="Mirage",
        )

    assert client.queries == []


def test_analytics_search_history_rejects_invalid_time_from() -> None:
    client = _FixtureClickHouse({})

    with pytest.raises(ValueError, match="time_from"):
        analytics_search_history(
            client,
            query_params={"time_from": ["bad"]},
            default_league="Mirage",
        )

    assert client.queries == []


def test_analytics_pricing_outliers_rejects_invalid_limit() -> None:
    client = _FixtureClickHouse({})

    with pytest.raises(ValueError, match="limit"):
        analytics_pricing_outliers(
            client,
            query_params={"limit": ["oops"]},
            default_league="Mirage",
        )

    assert client.queries == []


def test_analytics_backtests_returns_truthful_empty_payload() -> None:
    client = _FixtureClickHouse(
        {
            "FROM poe_trade.research_backtest_summary": "",
            "FROM poe_trade.research_backtest_detail": "",
        }
    )

    result = analytics_backtests(client)

    assert result == {
        "rows": [],
        "summaryRows": [],
        "detailRows": [],
        "totals": {"summary": 0, "detail": 0},
    }
    assert any(
        "FROM poe_trade.research_backtest_summary" in query for query in client.queries
    )
    assert any(
        "FROM poe_trade.research_backtest_detail" in query for query in client.queries
    )


def test_analytics_backtests_returns_summary_and_detail_counts() -> None:
    client = _FixtureClickHouse(
        {
            "FROM poe_trade.research_backtest_summary": (
                '{"status":"completed","count":2}\n{"status":"no_data","count":1}\n'
            ),
            "FROM poe_trade.research_backtest_detail": (
                '{"status":"completed","count":5}\n'
            ),
        }
    )

    result = analytics_backtests(client)

    assert result["rows"] == [
        {"status": "completed", "count": 2},
        {"status": "no_data", "count": 1},
    ]
    assert result["summaryRows"] == result["rows"]
    assert result["detailRows"] == [{"status": "completed", "count": 5}]
    assert result["totals"] == {"summary": 3, "detail": 5}


def test_analytics_report_returns_empty_status_when_all_counts_are_zero() -> None:
    client = _FixtureClickHouse(
        {
            "FORMAT JSONEachRow": (
                '{"league":"Mirage","recommendations":0,"alerts":0,'
                '"journal_events":0,"journal_positions":0,'
                '"backtest_summary_rows":0,"backtest_detail_rows":0,'
                '"gold_currency_ref_hour_rows":0,"gold_listing_ref_hour_rows":0,'
                '"gold_liquidity_ref_hour_rows":0,"gold_bulk_premium_hour_rows":0,'
                '"gold_set_ref_hour_rows":0,"realized_pnl_chaos":0.0}\n'
            )
        }
    )

    result = analytics_report(client, league="Mirage")

    assert result["status"] == "empty"
    assert result["report"]["league"] == "Mirage"
    assert result["report"]["gold_set_ref_hour_rows"] == 0
    assert result["report"]["backtest_detail_rows"] == 0


def test_analytics_gold_diagnostics_distinguishes_stale_empty_and_league_gap() -> None:
    client = _FixtureClickHouse(
        {
            "FROM poe_trade.v_gold_mart_diagnostics": (
                '{"mart_name":"gold_bulk_premium_hour","source_name":"v_ps_items_enriched",'
                '"source_row_count":220,"source_latest_at":"2026-03-15 12:00:00",'
                '"source_distinct_league_count":2,"source_blank_or_null_league_rows":0,'
                '"gold_row_count":40,"gold_latest_at":"2026-03-15 09:00:00",'
                '"gold_distinct_league_count":2,"gold_blank_or_null_league_rows":0,'
                '"gold_freshness_minutes":180,"source_to_gold_lag_minutes":180,'
                '"diagnostic_state":"gold_stale_vs_source"}\n'
                '{"mart_name":"gold_currency_ref_hour","source_name":"v_cx_markets_enriched",'
                '"source_row_count":0,"source_latest_at":null,'
                '"source_distinct_league_count":0,"source_blank_or_null_league_rows":0,'
                '"gold_row_count":0,"gold_latest_at":null,'
                '"gold_distinct_league_count":0,"gold_blank_or_null_league_rows":0,'
                '"gold_freshness_minutes":null,"source_to_gold_lag_minutes":null,'
                '"diagnostic_state":"source_empty"}\n'
                '{"mart_name":"gold_listing_ref_hour","source_name":"v_ps_items_enriched",'
                '"source_row_count":300,"source_latest_at":"2026-03-15 12:00:00",'
                '"source_distinct_league_count":2,"source_blank_or_null_league_rows":0,'
                '"gold_row_count":0,"gold_latest_at":null,'
                '"gold_distinct_league_count":0,"gold_blank_or_null_league_rows":0,'
                '"gold_freshness_minutes":null,"source_to_gold_lag_minutes":null,'
                '"diagnostic_state":"gold_empty"}\n'
            ),
            "source_league_rows": (
                '{"mart_name":"gold_bulk_premium_hour","source_league_rows":120,"gold_league_rows":30}\n'
                '{"mart_name":"gold_currency_ref_hour","source_league_rows":0,"gold_league_rows":0}\n'
                '{"mart_name":"gold_listing_ref_hour","source_league_rows":150,"gold_league_rows":0}\n'
            ),
        }
    )

    result = analytics_gold_diagnostics(client, league="Mirage")

    assert result["league"] == "Mirage"
    assert result["summary"]["status"] == "league_gap"
    assert result["summary"]["martCount"] == 3
    assert result["summary"]["problemMarts"] == 3
    assert result["summary"]["goldEmptyMarts"] == 1
    assert result["summary"]["staleMarts"] == 1
    assert result["summary"]["missingLeagueMarts"] == 1
    assert result["marts"][0]["martName"] == "gold_bulk_premium_hour"
    assert result["marts"][0]["diagnosticState"] == "gold_stale_vs_source"
    assert result["marts"][0]["leagueVisibility"] == "visible"
    assert result["marts"][1]["leagueVisibility"] == "absent_upstream"
    assert result["marts"][2]["leagueVisibility"] == "missing_in_gold"


def test_analytics_report_includes_gold_diagnostics_payload() -> None:
    client = _FixtureClickHouse(
        {
            "SELECT 'Mirage' AS league": (
                '{"league":"Mirage","recommendations":0,"alerts":0,'
                '"journal_events":0,"journal_positions":0,'
                '"backtest_summary_rows":0,"backtest_detail_rows":0,'
                '"gold_currency_ref_hour_rows":0,"gold_listing_ref_hour_rows":0,'
                '"gold_liquidity_ref_hour_rows":0,"gold_bulk_premium_hour_rows":0,'
                '"gold_set_ref_hour_rows":0,"realized_pnl_chaos":0.0}\n'
            ),
            "FROM poe_trade.v_gold_mart_diagnostics": (
                '{"mart_name":"gold_listing_ref_hour","source_name":"v_ps_items_enriched",'
                '"source_row_count":100,"source_latest_at":"2026-03-15 12:00:00",'
                '"source_distinct_league_count":1,"source_blank_or_null_league_rows":0,'
                '"gold_row_count":0,"gold_latest_at":null,'
                '"gold_distinct_league_count":0,"gold_blank_or_null_league_rows":0,'
                '"gold_freshness_minutes":null,"source_to_gold_lag_minutes":null,'
                '"diagnostic_state":"gold_empty"}\n'
            ),
            "source_league_rows": (
                '{"mart_name":"gold_listing_ref_hour","source_league_rows":100,"gold_league_rows":0}\n'
            ),
        }
    )

    result = analytics_report(client, league="Mirage")

    assert result["status"] == "empty"
    assert result["goldDiagnostics"]["summary"]["status"] == "league_gap"
    assert result["goldDiagnostics"]["marts"][0]["martName"] == "gold_listing_ref_hour"


def test_analytics_report_returns_ok_status_when_any_count_is_present() -> None:
    client = _FixtureClickHouse(
        {
            "FORMAT JSONEachRow": (
                '{"league":"Mirage","recommendations":4,"alerts":1,'
                '"journal_events":9,"journal_positions":2,'
                '"backtest_summary_rows":3,"backtest_detail_rows":11,'
                '"gold_currency_ref_hour_rows":7,"gold_listing_ref_hour_rows":6,'
                '"gold_liquidity_ref_hour_rows":5,"gold_bulk_premium_hour_rows":4,'
                '"gold_set_ref_hour_rows":3,"realized_pnl_chaos":42.5}\n'
            )
        }
    )

    result = analytics_report(client, league="Mirage")

    assert result["status"] == "ok"
    assert result["report"]["backtest_summary_rows"] == 3
    assert result["report"]["gold_currency_ref_hour_rows"] == 7
    assert result["report"]["realized_pnl_chaos"] == 42.5


def test_scanner_recommendations_payload_exposes_contract_fields() -> None:
    client = _FixtureClickHouse(
        {
            "FROM poe_trade.scanner_recommendations": (
                '{"scanner_run_id":"scan-1","strategy_id":"bulk_essence","league":"Mirage",'
                '"recommendation_source":"ml_anomaly","recommendation_contract_version":2,'
                '"producer_version":"mirage-model-v2","producer_run_id":"train-42",'
                '"item_or_market_key":"legacy-key","why_it_fired":"spread>10",'
                '"buy_plan":"buy <= 10c","max_buy":10.0,"transform_plan":"none",'
                '"exit_plan":"list @ 15c","execution_venue":"manual_trade",'
                '"expected_profit_chaos":5.0,"expected_roi":0.5,"expected_hold_time":"~20m",'
                '"expected_hold_minutes":20.0,"expected_profit_per_minute_chaos":0.25,'
                '"confidence":0.7,"evidence_snapshot":"{\\"search_hint\\":\\"Screaming Essence of Greed\\",\\"item_name\\":\\"Screaming Essence of Greed\\",\\"expected_hold_minutes\\":20,\\"liquidity_score\\":0.8,\\"freshness_minutes\\":3,\\"gold_cost\\":12.5}",'
                '"recorded_at":"2026-03-14 10:00:00"}\n'
            )
        }
    )

    payload = scanner_recommendations_payload(
        client,
        limit=10,
        sort_by="expected_profit_chaos",
        min_confidence=0.65,
        league="Mirage",
        strategy_id="bulk_essence",
    )

    recommendation = payload["recommendations"][0]
    assert payload["meta"]["source"] == "scanner_recommendations"
    assert recommendation["semanticKey"] == (
        "mirage|bulk_essence|manual_trade|screaming essence of greed|"
        "screaming essence of greed|buy <= 10c|10.0|none|list @ 15c"
    )
    assert recommendation["searchHint"] == "Screaming Essence of Greed"
    assert recommendation["itemName"] == "Screaming Essence of Greed"
    assert recommendation["recommendationSource"] == "ml_anomaly"
    assert recommendation["contractVersion"] == 2
    assert recommendation["producerVersion"] == "mirage-model-v2"
    assert recommendation["producerRunId"] == "train-42"
    assert recommendation["expectedHoldMinutes"] == 20
    assert recommendation["expectedProfitChaos"] == 5.0
    assert recommendation["expectedProfitPerMinuteChaos"] == 0.25
    assert recommendation["liquidityScore"] == 0.8
    assert recommendation["freshnessMinutes"] == 3
    assert recommendation["goldCost"] == 12.5
    assert (
        recommendation["evidenceSnapshot"]["search_hint"]
        == "Screaming Essence of Greed"
    )
    assert recommendation["expectedHoldTime"] == "~20m"
    assert recommendation["effectiveConfidence"] == recommendation["confidence"]
    assert recommendation["mlInfluenceScore"] is None
    assert recommendation["mlInfluenceReason"] is None


def test_scanner_recommendations_payload_exposes_opportunity_fields() -> None:
    client = _FixtureClickHouse(
        {
            "FROM poe_trade.scanner_recommendations": (
                '{"scanner_run_id":"scan-opportunity","strategy_id":"bulk_essence","league":"Mirage",'
                '"recommendation_source":"ml_anomaly","recommendation_contract_version":2,'
                '"producer_version":"mirage-model-v2","producer_run_id":"train-42",'
                '"item_or_market_key":"legacy-key","why_it_fired":"spread>10",'
                '"buy_plan":"buy <= 10c","max_buy":10.0,"transform_plan":"upgrade to Deafening",'
                '"exit_plan":"list @ 15c","execution_venue":"manual_trade",'
                '"expected_profit_chaos":24.0,"expected_profit_per_operation_chaos":8.0,'
                '"expected_roi":0.5,"expected_hold_time":"~20m",'
                '"expected_hold_minutes":20.0,"expected_profit_per_minute_chaos":1.2,'
                '"confidence":0.7,"complexity_tier":"medium","required_capital_chaos":36.0,'
                '"estimated_operations":3,"estimated_whispers":5,"feasibility_score":0.81,'
                '"evidence_snapshot":"{\\"search_hint\\":\\"Screaming Essence of Greed\\",\\"item_name\\":\\"Screaming Essence of Greed\\",\\"opportunity_type\\":\\"bulk_flip\\",\\"estimated_searches\\":2,\\"freshness_minutes\\":3,\\"estimated_time_to_acquire_minutes\\":12,\\"estimated_time_to_exit_minutes\\":8,\\"estimated_total_cycle_minutes\\":20,\\"liquidity_score\\":0.8,\\"risk_score\\":0.2,\\"competition_score\\":0.35,\\"why_now\\":\\"spread widened after reset\\",\\"warnings\\":[\\"thin supply\\"],\\"evidence_snapshot\\":{\\"supply\\":\\"tight\\"}}",'
                '"recorded_at":"2026-03-14 10:00:00"}\n'
            )
        }
    )

    payload = scanner_recommendations_payload(client)

    recommendation = payload["recommendations"][0]
    assert recommendation["opportunityType"] == "bulk_flip"
    assert recommendation["complexityTier"] == "medium"
    assert recommendation["requiredCapitalChaos"] == 36.0
    assert recommendation["estimatedOperations"] == 3
    assert recommendation["estimatedSearches"] == 2
    assert recommendation["estimatedWhispers"] == 5
    assert recommendation["freshnessMinutes"] == 3
    assert recommendation["estimatedTimeToAcquireMinutes"] == 12
    assert recommendation["estimatedTimeToExitMinutes"] == 8
    assert recommendation["estimatedTotalCycleMinutes"] == 20
    assert recommendation["expectedProfitPerOperationChaos"] == 8.0
    assert recommendation["feasibilityScore"] == 0.81
    assert recommendation["liquidityScore"] == 0.8
    assert recommendation["riskScore"] == 0.2
    assert recommendation["competitionScore"] == 0.35
    assert recommendation["whyNow"] == "spread widened after reset"
    assert recommendation["warnings"] == ["thin supply"]
    assert recommendation["executionPlan"] == {
        "buyPlan": "buy <= 10c",
        "transformPlan": "upgrade to Deafening",
        "exitPlan": "list @ 15c",
        "executionVenue": "manual_trade",
    }
    assert recommendation["evidence"] == {
        "searchHint": "Screaming Essence of Greed",
        "itemName": "Screaming Essence of Greed",
        "whyItFired": "spread>10",
        "snapshot": {"supply": "tight"},
    }


def test_scanner_recommendations_payload_keeps_legacy_rows_readable() -> None:
    client = _LegacyFallbackClickHouse(
        '{"scanner_run_id":"scan-legacy","strategy_id":"bulk_essence","league":"Mirage",'
        '"item_or_market_key":"legacy-key","why_it_fired":"spread>10",'
        '"buy_plan":"buy <= 10c","max_buy":10.0,"transform_plan":"none",'
        '"exit_plan":"list @ 15c","execution_venue":"manual_trade",'
        '"expected_profit_chaos":5.0,"expected_roi":0.5,"expected_hold_time":"~20m",'
        '"confidence":0.7,"evidence_snapshot":"{}",'
        '"recorded_at":"2026-03-14 10:00:00"}\n'
    )

    payload = scanner_recommendations_payload(client)

    recommendation = payload["recommendations"][0]
    assert recommendation["recommendationSource"] == "strategy_pack"
    assert recommendation["contractVersion"] == 1
    assert recommendation["producerVersion"] is None
    assert recommendation["producerRunId"] == "scan-legacy"
    assert recommendation["opportunityType"] is None
    assert recommendation["complexityTier"] is None
    assert recommendation["requiredCapitalChaos"] is None
    assert recommendation["estimatedOperations"] is None
    assert recommendation["estimatedSearches"] is None
    assert recommendation["estimatedWhispers"] is None
    assert recommendation["estimatedTimeToAcquireMinutes"] is None
    assert recommendation["estimatedTimeToExitMinutes"] is None
    assert recommendation["estimatedTotalCycleMinutes"] == 20
    assert recommendation["expectedProfitPerOperationChaos"] is None
    assert recommendation["feasibilityScore"] is None
    assert recommendation["liquidityScore"] is None
    assert recommendation["riskScore"] is None
    assert recommendation["competitionScore"] is None
    assert recommendation["whyNow"] == "spread>10"
    assert recommendation["warnings"] == []
    assert recommendation["executionPlan"] == {
        "buyPlan": "buy <= 10c",
        "transformPlan": "none",
        "exitPlan": "list @ 15c",
        "executionVenue": "manual_trade",
    }
    assert recommendation["evidence"] == {
        "searchHint": "legacy-key",
        "itemName": "legacy-key",
        "whyItFired": "spread>10",
        "snapshot": {},
    }
    assert len(client.queries) == 2
    assert "complexity_tier" in client.queries[0]
    assert "complexity_tier" not in client.queries[1]


def test_scanner_recommendations_payload_falls_back_on_unknown_identifier() -> None:
    client = _LegacyFallbackClickHouse(
        '{"scanner_run_id":"scan-legacy","strategy_id":"bulk_essence","league":"Mirage",'
        '"item_or_market_key":"legacy-key","why_it_fired":"spread>10",'
        '"buy_plan":"buy <= 10c","max_buy":10.0,"transform_plan":"none",'
        '"exit_plan":"list @ 15c","execution_venue":"manual_trade",'
        '"expected_profit_chaos":5.0,"expected_roi":0.5,"expected_hold_time":"~20m",'
        '"confidence":0.7,"evidence_snapshot":"{}",'
        '"recorded_at":"2026-03-14 10:00:00"}\n'
    )

    payload = scanner_recommendations_payload(client)

    assert payload["recommendations"][0]["scannerRunId"] == "scan-legacy"
    assert len(client.queries) == 2
    assert "estimated_searches" in client.queries[0]
    assert "estimated_searches" not in client.queries[1]


class _MissingAnalyticsTablesClickHouse(ClickHouseClient):
    def __init__(self) -> None:
        super().__init__(endpoint="http://clickhouse")

    def execute(  # pyright: ignore[reportImplicitOverride]
        self, query: str, settings: Mapping[str, str] | None = None
    ) -> str:
        del settings
        lowered = query.lower()
        if "from poe_trade.v_ps_items_enriched" in lowered:
            raise ClickHouseClientError(
                "Unknown table expression identifier 'poe_trade.v_ps_items_enriched'"
            )
        if "from poe_trade.ml_price_dataset_v1" in lowered:
            raise ClickHouseClientError(
                "Unknown table expression identifier 'poe_trade.ml_price_dataset_v1'"
            )
        return ""


def test_analytics_search_suggestions_returns_empty_when_dataset_missing() -> None:
    payload = analytics_search_suggestions(
        _MissingAnalyticsTablesClickHouse(),
        query="Divine",
    )

    assert payload == {"query": "Divine", "suggestions": []}


def test_analytics_search_history_returns_empty_payload_when_dataset_missing() -> None:
    payload = analytics_search_history(
        _MissingAnalyticsTablesClickHouse(),
        query_params={"query": ["Divine"]},
        default_league="Mirage",
    )

    assert payload["query"]["text"] == "Divine"
    assert payload["filters"]["leagueOptions"] == []
    assert payload["rows"] == []


def test_analytics_pricing_outliers_returns_empty_payload_when_dataset_missing() -> (
    None
):
    payload = analytics_pricing_outliers(
        _MissingAnalyticsTablesClickHouse(),
        query_params={"query": ["Divine"]},
        default_league="Mirage",
    )

    assert payload["query"]["league"] == "Mirage"
    assert payload["rows"] == []
    assert payload["weekly"] == []


def test_analytics_gold_diagnostics_handles_missing_source_view() -> None:
    payload = analytics_gold_diagnostics(
        _MissingAnalyticsTablesClickHouse(), league="Mirage"
    )

    assert payload["league"] == "Mirage"
    assert payload["summary"]["status"] == "empty"
    assert payload["summary"]["martCount"] == 0
    assert payload["marts"] == []


def test_scanner_recommendations_payload_legacy_fallback_supports_operation_sort() -> (
    None
):
    client = _LegacyFallbackClickHouse(
        '{"scanner_run_id":"scan-legacy","strategy_id":"bulk_essence","league":"Mirage",'
        '"item_or_market_key":"legacy-key","why_it_fired":"spread>10",'
        '"buy_plan":"buy <= 10c","max_buy":10.0,"transform_plan":"none",'
        '"exit_plan":"list @ 15c","execution_venue":"manual_trade",'
        '"expected_profit_chaos":5.0,"expected_roi":0.5,"expected_hold_time":"~20m",'
        '"confidence":0.7,"evidence_snapshot":"{}",'
        '"recorded_at":"2026-03-14 10:00:00"}\n'
    )

    payload = scanner_recommendations_payload(
        client,
        sort_by="expected_profit_per_operation_chaos",
    )

    assert payload["recommendations"][0]["scannerRunId"] == "scan-legacy"
    assert len(client.queries) == 2
    assert "expected_profit_per_operation_chaos DESC" in client.queries[0]
    assert "expected_profit_per_operation_chaos" not in client.queries[1]
    assert "expected_profit_chaos DESC" in client.queries[1]


def test_scanner_recommendations_payload_legacy_fallback_supports_operation_sort_cursor() -> (
    None
):
    client = _LegacyFallbackSequentialClickHouse(
        legacy_responses=[
            (
                '{"scanner_run_id":"scan-1","strategy_id":"bulk_essence","league":"Mirage",'
                '"item_or_market_key":"k1","why_it_fired":"spread",'
                '"buy_plan":"buy <= 1c","max_buy":1.0,"transform_plan":"none",'
                '"exit_plan":"list @ 11c","execution_venue":"manual_trade",'
                '"expected_profit_chaos":11.0,"expected_roi":1.1,"expected_hold_time":"~10m",'
                '"confidence":0.9,"evidence_snapshot":"{}",'
                '"recorded_at":"2026-03-15 12:00:00"}\n'
                '{"scanner_run_id":"scan-2","strategy_id":"bulk_essence","league":"Mirage",'
                '"item_or_market_key":"k2","why_it_fired":"spread",'
                '"buy_plan":"buy <= 2c","max_buy":2.0,"transform_plan":"none",'
                '"exit_plan":"list @ 10c","execution_venue":"manual_trade",'
                '"expected_profit_chaos":10.0,"expected_roi":1.0,"expected_hold_time":"~10m",'
                '"confidence":0.8,"evidence_snapshot":"{}",'
                '"recorded_at":"2026-03-15 11:00:00"}\n'
                '{"scanner_run_id":"scan-3","strategy_id":"bulk_essence","league":"Mirage",'
                '"item_or_market_key":"k3","why_it_fired":"spread",'
                '"buy_plan":"buy <= 3c","max_buy":3.0,"transform_plan":"none",'
                '"exit_plan":"list @ 9c","execution_venue":"manual_trade",'
                '"expected_profit_chaos":9.0,"expected_roi":0.9,"expected_hold_time":"~10m",'
                '"confidence":0.7,"evidence_snapshot":"{}",'
                '"recorded_at":"2026-03-15 10:00:00"}\n'
            ),
            (
                '{"scanner_run_id":"scan-3","strategy_id":"bulk_essence","league":"Mirage",'
                '"item_or_market_key":"k3","why_it_fired":"spread",'
                '"buy_plan":"buy <= 3c","max_buy":3.0,"transform_plan":"none",'
                '"exit_plan":"list @ 9c","execution_venue":"manual_trade",'
                '"expected_profit_chaos":9.0,"expected_roi":0.9,"expected_hold_time":"~10m",'
                '"confidence":0.7,"evidence_snapshot":"{}",'
                '"recorded_at":"2026-03-15 10:00:00"}\n'
            ),
        ]
    )

    first_payload = scanner_recommendations_payload(
        client,
        limit=2,
        sort_by="expected_profit_per_operation_chaos",
        league="Mirage",
    )

    second_payload = scanner_recommendations_payload(
        client,
        limit=2,
        sort_by="expected_profit_per_operation_chaos",
        league="Mirage",
        cursor=first_payload["meta"]["nextCursor"],
    )

    assert first_payload["meta"]["hasMore"] is True
    assert second_payload["meta"]["hasMore"] is False
    assert [row["scannerRunId"] for row in second_payload["recommendations"]] == [
        "scan-3"
    ]
    assert "expected_profit_per_operation_chaos" in client.queries[0]
    assert "expected_profit_per_operation_chaos" not in client.queries[1]
    assert "expected_profit_per_operation_chaos" in client.queries[2]
    assert "expected_profit_per_operation_chaos" not in client.queries[3]
    assert "expected_profit_chaos" in client.queries[3]


def test_scanner_recommendations_payload_nulls_invalid_hold_minutes() -> None:
    client = _FixtureClickHouse(
        {
            "FROM poe_trade.scanner_recommendations": (
                '{"scanner_run_id":"scan-invalid","strategy_id":"bulk_essence","league":"Mirage",'
                '"item_or_market_key":"legacy-invalid","why_it_fired":"spread>10",'
                '"buy_plan":"buy <= 10c","max_buy":10.0,"transform_plan":"none",'
                '"exit_plan":"list @ 15c","execution_venue":"manual_trade",'
                '"expected_profit_chaos":5.0,"expected_roi":0.5,"expected_hold_time":"soon",'
                '"expected_hold_minutes":null,"expected_profit_per_minute_chaos":null,'
                '"confidence":0.7,"evidence_snapshot":"{\\"expected_hold_minutes\\":0}",'
                '"recorded_at":"2026-03-14 10:00:00"}\n'
            )
        }
    )

    payload = scanner_recommendations_payload(client)

    recommendation = payload["recommendations"][0]
    assert recommendation["expectedHoldTime"] == "soon"
    assert recommendation["expectedHoldMinutes"] is None
    assert recommendation["expectedProfitPerMinuteChaos"] is None


def test_scanner_recommendations_payload_carries_ml_influence_when_present() -> None:
    client = _FixtureClickHouse(
        {
            "FROM poe_trade.scanner_recommendations": (
                '{"scanner_run_id":"scan-2","strategy_id":"bulk_essence","league":"Mirage",'
                '"item_or_market_key":"legacy-key-2","why_it_fired":"spread>10",'
                '"buy_plan":"buy <= 10c","max_buy":10.0,"transform_plan":"none",'
                '"exit_plan":"list @ 15c","execution_venue":"manual_trade",'
                '"expected_profit_chaos":5.0,"expected_roi":0.5,"expected_hold_time":"~20m",'
                '"confidence":0.4,"evidence_snapshot":"{\\"ml_influence_score\\":0.8,\\"ml_influence_reason\\":\\"mirage_model_v1\\"}",'
                '"recorded_at":"2026-03-14 10:00:00"}\n'
            )
        }
    )

    payload = scanner_recommendations_payload(client)

    recommendation = payload["recommendations"][0]
    assert recommendation["confidence"] == 0.4
    assert recommendation["mlInfluenceScore"] == 0.8
    assert recommendation["mlInfluenceReason"] == "mirage_model_v1"
    assert recommendation["effectiveConfidence"] == 0.6


def test_scanner_recommendations_payload_rejects_invalid_sort() -> None:
    client = _FixtureClickHouse({})

    with pytest.raises(ValueError, match="sort"):
        scanner_recommendations_payload(client, sort_by="not_a_field")


def test_scanner_recommendations_global_top_uses_sql_sort_not_recent_window() -> None:
    client = _FixtureClickHouse(
        {
            "FROM poe_trade.scanner_recommendations": (
                '{"scanner_run_id":"old-top","strategy_id":"bulk_essence","league":"Mirage",'
                '"item_or_market_key":"legacy-old","why_it_fired":"spread",'
                '"buy_plan":"buy <= 20c","max_buy":20.0,"transform_plan":"none",'
                '"exit_plan":"list @ 100c","execution_venue":"manual_trade",'
                '"expected_profit_chaos":80.0,"expected_roi":4.0,"expected_hold_time":"~30m",'
                '"confidence":0.9,"evidence_snapshot":"{}",'
                '"recorded_at":"2026-03-10 10:00:00"}\n'
                '{"scanner_run_id":"newer-low","strategy_id":"bulk_essence","league":"Mirage",'
                '"item_or_market_key":"legacy-new","why_it_fired":"spread",'
                '"buy_plan":"buy <= 10c","max_buy":10.0,"transform_plan":"none",'
                '"exit_plan":"list @ 12c","execution_venue":"manual_trade",'
                '"expected_profit_chaos":2.0,"expected_roi":0.2,"expected_hold_time":"~5m",'
                '"confidence":0.95,"evidence_snapshot":"{}",'
                '"recorded_at":"2026-03-15 10:00:00"}\n'
            )
        }
    )

    payload = scanner_recommendations_payload(
        client,
        sort_by="expected_profit_chaos",
        league="Mirage",
        limit=10,
    )

    assert payload["recommendations"][0]["scannerRunId"] == "old-top"
    assert payload["recommendations"][1]["scannerRunId"] == "newer-low"
    assert "ORDER BY if(isNull(expected_profit_chaos), 0, 1) DESC" in client.queries[0]
    assert "expected_profit_chaos DESC" in client.queries[0]


def test_scanner_recommendations_per_minute_sort_nulls_last() -> None:
    client = _FixtureClickHouse(
        {
            "FROM poe_trade.scanner_recommendations": (
                '{"scanner_run_id":"fast-win","strategy_id":"bulk_essence","league":"Mirage",'
                '"item_or_market_key":"ppm-fast","why_it_fired":"spread",'
                '"buy_plan":"buy <= 5c","max_buy":5.0,"transform_plan":"none",'
                '"exit_plan":"list @ 35c","execution_venue":"manual_trade",'
                '"expected_profit_chaos":30.0,"expected_roi":6.0,"expected_hold_time":"~30m",'
                '"expected_hold_minutes":30.0,"expected_profit_per_minute_chaos":1.0,'
                '"confidence":0.9,"evidence_snapshot":"{}",'
                '"recorded_at":"2026-03-15 10:00:00"}\n'
                '{"scanner_run_id":"slow-win","strategy_id":"bulk_essence","league":"Mirage",'
                '"item_or_market_key":"ppm-slow","why_it_fired":"spread",'
                '"buy_plan":"buy <= 10c","max_buy":10.0,"transform_plan":"none",'
                '"exit_plan":"list @ 22c","execution_venue":"manual_trade",'
                '"expected_profit_chaos":12.0,"expected_roi":1.2,"expected_hold_time":"2h",'
                '"expected_hold_minutes":120.0,"expected_profit_per_minute_chaos":0.1,'
                '"confidence":0.8,"evidence_snapshot":"{}",'
                '"recorded_at":"2026-03-15 09:00:00"}\n'
                '{"scanner_run_id":"unknown-hold","strategy_id":"bulk_essence","league":"Mirage",'
                '"item_or_market_key":"ppm-null","why_it_fired":"spread",'
                '"buy_plan":"buy <= 10c","max_buy":10.0,"transform_plan":"none",'
                '"exit_plan":"list @ 18c","execution_venue":"manual_trade",'
                '"expected_profit_chaos":8.0,"expected_roi":0.8,"expected_hold_time":"soon",'
                '"expected_hold_minutes":null,"expected_profit_per_minute_chaos":null,'
                '"confidence":0.7,"evidence_snapshot":"{}",'
                '"recorded_at":"2026-03-15 08:00:00"}\n'
            )
        }
    )

    payload = scanner_recommendations_payload(
        client,
        sort_by="expected_profit_per_minute_chaos",
        league="Mirage",
        limit=10,
    )

    assert [row["scannerRunId"] for row in payload["recommendations"]] == [
        "fast-win",
        "slow-win",
        "unknown-hold",
    ]
    assert payload["recommendations"][2]["expectedProfitPerMinuteChaos"] is None
    assert (
        "ORDER BY if(isNull(expected_profit_per_minute_chaos), 0, 1) DESC"
        in client.queries[0]
    )
    assert "expected_profit_per_minute_chaos DESC" in client.queries[0]
    assert "AS expected_hold_minutes" in client.queries[0]
    assert "AS expected_profit_per_minute_chaos" in client.queries[0]


def test_scanner_recommendations_filters_are_applied_in_sql_before_limit() -> None:
    client = _FixtureClickHouse(
        {
            "FROM poe_trade.scanner_recommendations": (
                '{"scanner_run_id":"scan-1","strategy_id":"bulk_essence","league":"Mirage",'
                '"item_or_market_key":"legacy-key","why_it_fired":"spread",'
                '"buy_plan":"buy <= 10c","max_buy":10.0,"transform_plan":"none",'
                '"exit_plan":"list @ 15c","execution_venue":"manual_trade",'
                '"expected_profit_chaos":5.0,"expected_roi":0.5,"expected_hold_time":"~20m",'
                '"confidence":0.8,"evidence_snapshot":"{}",'
                '"recorded_at":"2026-03-14 10:00:00"}\n'
            )
        }
    )

    scanner_recommendations_payload(
        client,
        limit=2,
        sort_by="expected_profit_chaos",
        min_confidence=0.75,
        league="Mirage",
        strategy_id="bulk_essence",
    )

    query = client.queries[0]
    assert "WHERE" in query
    assert "league = 'Mirage'" in query
    assert "strategy_id = 'bulk_essence'" in query
    assert "isNotNull(confidence) AND confidence >= 0.75" in query
    assert "LIMIT 3 FORMAT JSONEachRow" in query


def test_scanner_recommendations_cursor_pagination_has_more_and_next_cursor() -> None:
    client = _SequentialFixtureClickHouse(
        responses=[
            (
                '{"scanner_run_id":"scan-1","strategy_id":"bulk_essence","league":"Mirage",'
                '"item_or_market_key":"k1","why_it_fired":"spread",'
                '"buy_plan":"buy <= 1c","max_buy":1.0,"transform_plan":"none",'
                '"exit_plan":"list @ 11c","execution_venue":"manual_trade",'
                '"expected_profit_chaos":11.0,"expected_roi":1.1,"expected_hold_time":"~10m",'
                '"confidence":0.9,"evidence_snapshot":"{}",'
                '"recorded_at":"2026-03-15 12:00:00"}\n'
                '{"scanner_run_id":"scan-2","strategy_id":"bulk_essence","league":"Mirage",'
                '"item_or_market_key":"k2","why_it_fired":"spread",'
                '"buy_plan":"buy <= 2c","max_buy":2.0,"transform_plan":"none",'
                '"exit_plan":"list @ 10c","execution_venue":"manual_trade",'
                '"expected_profit_chaos":10.0,"expected_roi":1.0,"expected_hold_time":"~10m",'
                '"confidence":0.8,"evidence_snapshot":"{}",'
                '"recorded_at":"2026-03-15 11:00:00"}\n'
                '{"scanner_run_id":"scan-3","strategy_id":"bulk_essence","league":"Mirage",'
                '"item_or_market_key":"k3","why_it_fired":"spread",'
                '"buy_plan":"buy <= 3c","max_buy":3.0,"transform_plan":"none",'
                '"exit_plan":"list @ 9c","execution_venue":"manual_trade",'
                '"expected_profit_chaos":9.0,"expected_roi":0.9,"expected_hold_time":"~10m",'
                '"confidence":0.7,"evidence_snapshot":"{}",'
                '"recorded_at":"2026-03-15 10:00:00"}\n'
            ),
            (
                '{"scanner_run_id":"scan-3","strategy_id":"bulk_essence","league":"Mirage",'
                '"item_or_market_key":"k3","why_it_fired":"spread",'
                '"buy_plan":"buy <= 3c","max_buy":3.0,"transform_plan":"none",'
                '"exit_plan":"list @ 9c","execution_venue":"manual_trade",'
                '"expected_profit_chaos":9.0,"expected_roi":0.9,"expected_hold_time":"~10m",'
                '"confidence":0.7,"evidence_snapshot":"{}",'
                '"recorded_at":"2026-03-15 10:00:00"}\n'
            ),
        ]
    )

    first_payload = scanner_recommendations_payload(
        client,
        limit=2,
        sort_by="expected_profit_chaos",
        league="Mirage",
    )

    assert first_payload["meta"]["hasMore"] is True
    assert isinstance(first_payload["meta"]["nextCursor"], str)
    assert [row["scannerRunId"] for row in first_payload["recommendations"]] == [
        "scan-1",
        "scan-2",
    ]

    second_payload = scanner_recommendations_payload(
        client,
        limit=2,
        sort_by="expected_profit_chaos",
        league="Mirage",
        cursor=first_payload["meta"]["nextCursor"],
    )

    assert second_payload["meta"]["hasMore"] is False
    assert second_payload["meta"]["nextCursor"] is None
    assert [row["scannerRunId"] for row in second_payload["recommendations"]] == [
        "scan-3"
    ]
    assert "< (" in client.queries[1]


def test_scanner_recommendations_rejects_malformed_cursor() -> None:
    client = _FixtureClickHouse({})

    with pytest.raises(ValueError, match="invalid scanner cursor"):
        scanner_recommendations_payload(
            client,
            sort_by="expected_profit_chaos",
            cursor="not-a-cursor",
        )


def test_scanner_recommendations_rejects_cursor_with_signature_mismatch() -> None:
    client = _SequentialFixtureClickHouse(
        responses=[
            (
                '{"scanner_run_id":"scan-1","strategy_id":"bulk_essence","league":"Mirage",'
                '"item_or_market_key":"k1","why_it_fired":"spread",'
                '"buy_plan":"buy <= 1c","max_buy":1.0,"transform_plan":"none",'
                '"exit_plan":"list @ 11c","execution_venue":"manual_trade",'
                '"expected_profit_chaos":11.0,"expected_roi":1.1,"expected_hold_time":"~10m",'
                '"confidence":0.9,"evidence_snapshot":"{}",'
                '"recorded_at":"2026-03-15 12:00:00"}\n'
                '{"scanner_run_id":"scan-2","strategy_id":"bulk_essence","league":"Mirage",'
                '"item_or_market_key":"k2","why_it_fired":"spread",'
                '"buy_plan":"buy <= 2c","max_buy":2.0,"transform_plan":"none",'
                '"exit_plan":"list @ 10c","execution_venue":"manual_trade",'
                '"expected_profit_chaos":10.0,"expected_roi":1.0,"expected_hold_time":"~10m",'
                '"confidence":0.8,"evidence_snapshot":"{}",'
                '"recorded_at":"2026-03-15 11:00:00"}\n'
            )
        ]
    )

    first_payload = scanner_recommendations_payload(
        client,
        limit=1,
        sort_by="expected_profit_chaos",
        league="Mirage",
    )

    with pytest.raises(ValueError, match="does not match"):
        scanner_recommendations_payload(
            client,
            limit=2,
            sort_by="expected_profit_chaos",
            league="Mirage",
            cursor=first_payload["meta"]["nextCursor"],
        )


def test_dashboard_payload_sources_from_scanner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FixtureClickHouse({})

    captured_kwargs: dict[str, object] = {}
    mock_opportunities = [{"itemName": "Scanner Item 1"}]
    mock_messages = [{"message": "Message Alert", "severity": "critical"}]

    def _mock_scanner_recommendations(
        _client: ClickHouseClient, **kwargs: object
    ) -> dict[str, object]:
        captured_kwargs.update(kwargs)
        return {
            "recommendations": mock_opportunities,
            "meta": {"hasMore": False, "nextCursor": None},
        }

    monkeypatch.setattr(
        "poe_trade.api.ops.scanner_recommendations_payload",
        _mock_scanner_recommendations,
    )
    monkeypatch.setattr(
        "poe_trade.api.ops.messages_payload",
        lambda _client: mock_messages,
    )

    result = dashboard_payload(client, snapshots=[])

    assert result["topOpportunities"] == mock_opportunities
    assert result["deployment"] == {
        "backendVersion": "0.1.0",
        "backendSha": None,
        "frontendBuildSha": None,
        "recommendationContractVersion": 3,
        "contractMatchState": "unknown",
    }
    assert result["summary"]["criticalAlerts"] == 1
    assert all("message" not in opt for opt in result["topOpportunities"])
    assert captured_kwargs == {
        "limit": 3,
        "sort_by": "expected_profit_per_operation_chaos",
    }


def test_dashboard_payload_summary_excludes_optional_and_oneshot_services(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FixtureClickHouse({})
    monkeypatch.setattr(
        "poe_trade.api.ops.scanner_recommendations_payload",
        lambda _client, **kwargs: {"recommendations": []},
    )
    monkeypatch.setattr("poe_trade.api.ops.messages_payload", lambda _client: [])
    snapshots = [
        ServiceSnapshot(
            id="clickhouse",
            name="ClickHouse",
            description="",
            status="running",
            uptime=None,
            last_crawl=None,
            rows_in_db=None,
            container_info="clickhouse",
            type="docker",
            allowed_actions=(),
        ),
        ServiceSnapshot(
            id="market_harvester",
            name="Market Harvester",
            description="",
            status="running",
            uptime=None,
            last_crawl=None,
            rows_in_db=None,
            container_info="market_harvester",
            type="crawler",
            allowed_actions=("start", "stop", "restart"),
        ),
        ServiceSnapshot(
            id="scanner_worker",
            name="Scanner Worker",
            description="",
            status="error",
            uptime=None,
            last_crawl=None,
            rows_in_db=None,
            container_info="scanner_worker",
            type="worker",
            allowed_actions=("start", "stop", "restart"),
        ),
        ServiceSnapshot(
            id="ml_trainer",
            name="ML Trainer",
            description="",
            status="running",
            uptime=None,
            last_crawl=None,
            rows_in_db=None,
            container_info="ml_trainer",
            type="worker",
            allowed_actions=("start", "stop", "restart"),
        ),
        ServiceSnapshot(
            id="api",
            name="API",
            description="",
            status="running",
            uptime=None,
            last_crawl=None,
            rows_in_db=None,
            container_info="api",
            type="analytics",
            allowed_actions=(),
        ),
        ServiceSnapshot(
            id="schema_migrator",
            name="Schema Migrator",
            description="",
            status="stopped",
            uptime=None,
            last_crawl=None,
            rows_in_db=None,
            container_info="schema_migrator",
            type="worker",
            allowed_actions=(),
        ),
        ServiceSnapshot(
            id="account_stash_harvester",
            name="Account Stash Harvester",
            description="",
            status="stopped",
            uptime=None,
            last_crawl=None,
            rows_in_db=None,
            container_info="account_stash_harvester",
            type="crawler",
            allowed_actions=("start", "stop", "restart"),
        ),
    ]

    result = dashboard_payload(client, snapshots=snapshots)

    assert result["summary"]["total"] == 5
    assert result["summary"]["running"] == 4
    assert result["summary"]["errors"] == 1


def test_scanner_summary_payload_marks_recent_scan_ok() -> None:
    client = _FixtureClickHouse(
        {
            "FROM poe_trade.scanner_recommendations": (
                '{"last_run_at":"2099-01-01 00:00:00","recommendation_count":3}\n'
            )
        }
    )

    payload = scanner_summary_payload(client)

    assert payload["status"] == "ok"
    assert payload["lastRunAt"] == "2099-01-01T00:00:00Z"
    assert payload["recommendationCount"] == 3
    assert payload["freshnessMinutes"] == 0.0


def test_scanner_summary_payload_marks_old_scan_stale() -> None:
    client = _FixtureClickHouse(
        {
            "FROM poe_trade.scanner_recommendations": (
                '{"last_run_at":"2020-01-01 00:00:00","recommendation_count":3}\n'
            )
        }
    )

    payload = scanner_summary_payload(client)

    assert payload["status"] == "stale"
    assert payload["lastRunAt"] == "2020-01-01T00:00:00Z"
    assert payload["recommendationCount"] == 3
    assert isinstance(payload["freshnessMinutes"], float)


def test_scanner_summary_payload_keeps_empty_when_no_runs() -> None:
    client = _FixtureClickHouse(
        {
            "FROM poe_trade.scanner_recommendations": (
                '{"last_run_at":null,"recommendation_count":0}\n'
            )
        }
    )

    payload = scanner_summary_payload(client)

    assert payload == {
        "status": "empty",
        "lastRunAt": None,
        "recommendationCount": 0,
        "freshnessMinutes": None,
    }
