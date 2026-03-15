from __future__ import annotations

from collections.abc import Mapping

import pytest

from poe_trade.api.ops import (
    analytics_backtests,
    analytics_report,
    analytics_scanner,
    dashboard_payload,
    scanner_recommendations_payload,
    scanner_summary_payload,
)
from poe_trade.api.service_control import ServiceSnapshot
from poe_trade.db import ClickHouseClient


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


def test_analytics_scanner_query_does_not_require_status_column() -> None:
    client = _RecordingClickHouse()

    result = analytics_scanner(client)

    assert result == {"rows": []}
    assert len(client.queries) == 1
    assert "scanner_recommendations.status" not in client.queries[0]
    assert "GROUP BY status" not in client.queries[0]
    assert "GROUP BY strategy_id" in client.queries[0]
    assert "recommendation_count" in client.queries[0]


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
                '"item_or_market_key":"legacy-key","why_it_fired":"spread>10",'
                '"buy_plan":"buy <= 10c","max_buy":10.0,"transform_plan":"none",'
                '"exit_plan":"list @ 15c","execution_venue":"manual_trade",'
                '"expected_profit_chaos":5.0,"expected_roi":0.5,"expected_hold_time":"~20m",'
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
    assert recommendation["expectedHoldMinutes"] == 20
    assert recommendation["liquidityScore"] == 0.8
    assert recommendation["freshnessMinutes"] == 3
    assert recommendation["goldCost"] == 12.5
    assert (
        recommendation["evidenceSnapshot"]["search_hint"]
        == "Screaming Essence of Greed"
    )
    assert recommendation["expectedHoldTime"] == "~20m"


def test_scanner_recommendations_payload_rejects_invalid_sort() -> None:
    client = _FixtureClickHouse({})

    with pytest.raises(ValueError, match="sort"):
        scanner_recommendations_payload(client, sort_by="not_a_field")


def test_dashboard_payload_sources_from_scanner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FixtureClickHouse({})

    mock_opportunities = [{"itemName": "Scanner Item 1"}]
    mock_messages = [{"message": "Message Alert", "severity": "critical"}]

    monkeypatch.setattr(
        "poe_trade.api.ops.scanner_recommendations_payload",
        lambda _client, **kwargs: {"recommendations": mock_opportunities},
    )
    monkeypatch.setattr(
        "poe_trade.api.ops.messages_payload",
        lambda _client: mock_messages,
    )

    result = dashboard_payload(client, snapshots=[])

    assert result["topOpportunities"] == mock_opportunities
    assert result["summary"]["criticalAlerts"] == 1
    assert all("message" not in opt for opt in result["topOpportunities"])


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
