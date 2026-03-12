import importlib
import pytest


class _RecordingClient:
    def __init__(self, *, responses=None, fail_on_match=None):
        self.queries = []
        self.responses = responses or {}
        self.fail_on_match = fail_on_match

    def execute(self, query: str) -> str:
        self.queries.append(query)
        if self.fail_on_match and self.fail_on_match in query:
            raise RuntimeError("forced failure")
        for marker, payload in self.responses.items():
            if marker in query:
                return payload
        return ""


def test_get_strategy_pack_returns_registered_pack() -> None:
    backtest = importlib.import_module("poe_trade.strategy.backtest")
    pack = backtest.get_strategy_pack("bulk_essence")

    assert pack.strategy_id == "bulk_essence"
    assert pack.backtest_sql_path.name == "backtest.sql"


def test_run_backtest_records_run_and_results() -> None:
    backtest = importlib.import_module("poe_trade.strategy.backtest")
    client = _RecordingClient(
        responses={
            "FROM poe_trade.research_backtest_detail": '{"opportunity_count":2,"expected_profit_chaos":12.5,"expected_roi":0.4,"confidence":0.8}',
        }
    )

    run_id = backtest.run_backtest(
        client,
        strategy_id="bulk_essence",
        league="Mirage",
        lookback_days=14,
        dry_run=False,
    )

    assert len(run_id) == 32
    assert len(client.queries) == 5
    assert "research_backtest_runs" in client.queries[0]
    assert "research_backtest_detail" in client.queries[1]
    assert "research_backtest_summary" in client.queries[3]
    assert "research_backtest_runs" in client.queries[4]
    assert "bulk_essence" in client.queries[1]
    assert '"completed_at":null' not in client.queries[0]
    assert '"completed_at":"1970-01-01 00:00:00.000"' in client.queries[0]
    assert backtest.BACKTEST_SUMMARY_HEADER == (
        "run_id\tstrategy_id\tleague\tlookback_days\tstatus\topportunity_count\texpected_profit_chaos\texpected_roi\tconfidence\tsummary"
    )


def test_run_backtest_applies_league_and_lookback_filters() -> None:
    backtest = importlib.import_module("poe_trade.strategy.backtest")
    client = _RecordingClient(
        responses={
            "FROM poe_trade.research_backtest_detail": '{"opportunity_count":1,"expected_profit_chaos":4.0,"expected_roi":0.2,"confidence":0.7}',
        }
    )

    backtest.run_backtest(
        client,
        strategy_id="bulk_essence",
        league="Mirage",
        lookback_days=14,
        dry_run=False,
    )

    detail_insert = next(
        query
        for query in client.queries
        if "INSERT INTO poe_trade.research_backtest_detail" in query
    )
    assert "ifNull(scoped_source.league, '') = 'Mirage'" in detail_insert
    assert "time_bucket >= now() - INTERVAL 14 DAY" in detail_insert


def test_run_backtest_dry_run_skips_clickhouse() -> None:
    backtest = importlib.import_module("poe_trade.strategy.backtest")
    client = _RecordingClient()

    run_id = backtest.run_backtest(
        client,
        strategy_id="fragment_sets",
        league="Mirage",
        lookback_days=7,
        dry_run=True,
    )

    assert len(run_id) == 32
    assert client.queries == []


def test_run_backtest_marks_no_data_when_source_window_empty() -> None:
    backtest = importlib.import_module("poe_trade.strategy.backtest")
    client = _RecordingClient(
        responses={
            "FROM poe_trade.research_backtest_detail": '{"opportunity_count":0,"expected_profit_chaos":null,"expected_roi":null,"confidence":null}',
            "AS source_rows": '{"source_rows":0}',
        }
    )

    backtest.run_backtest(
        client,
        strategy_id="bulk_essence",
        league="Mirage",
        lookback_days=14,
        dry_run=False,
    )

    assert any('"status":"no_data"' in query for query in client.queries)


def test_run_backtest_records_failed_status_on_insert_error() -> None:
    backtest = importlib.import_module("poe_trade.strategy.backtest")
    client = _RecordingClient(
        fail_on_match="INSERT INTO poe_trade.research_backtest_detail"
    )

    with pytest.raises(RuntimeError, match="forced failure"):
        backtest.run_backtest(
            client,
            strategy_id="bulk_essence",
            league="Mirage",
            lookback_days=14,
            dry_run=False,
        )

    assert any('"status":"failed"' in query for query in client.queries)
