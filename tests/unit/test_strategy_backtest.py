import importlib
import json
from types import SimpleNamespace

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


def _candidate_row_payload(**overrides) -> str:
    base_key = overrides.get("item_or_market_key", "essence:bulk")
    payload = {
        "time_bucket": "2026-03-01 00:00:00",
        "league": "Mirage",
        "item_or_market_key": base_key,
        "semantic_key": overrides.get("semantic_key", base_key),
        "expected_profit_chaos": 6.25,
        "expected_roi": 0.4,
        "confidence": 0.8,
        "sample_count": 48,
        "why_it_fired": "Bulk essence spread between bulk and small listings",
    }
    payload.update(overrides)
    return json.dumps(payload, separators=(",", ":"))


def _stub_pack(**overrides):
    pack = {
        "strategy_id": "bulk_essence",
        "min_expected_profit_chaos": None,
        "min_expected_roi": None,
        "min_confidence": None,
        "min_sample_count": None,
        "cooldown_minutes": 0,
        "requires_journal": False,
        "backtest_sql_path": SimpleNamespace(
            read_text=lambda encoding="utf-8": (_ for _ in ()).throw(
                AssertionError("raw backtest SQL should not be read")
            )
        ),
    }
    pack.update(overrides)
    return SimpleNamespace(**pack)


def test_fetch_source_rows_uses_stable_compat_hash() -> None:
    backtest = importlib.import_module("poe_trade.strategy.backtest")
    client = _RecordingClient()
    _ = backtest._fetch_source_rows(
        client, sql="SELECT 'sem' AS semantic_key, 'legacy' AS item_or_market_key"
    )
    query = client.queries[0]
    assert (
        "cityHash64(concat(ifNull(source.semantic_key, ''), '|', ifNull(source.item_or_market_key, '')))"
        in query
    )
    assert "cityHash64(formatRowNoNewline('JSONEachRow', source.*))" not in query


def test_get_strategy_pack_returns_registered_pack() -> None:
    backtest = importlib.import_module("poe_trade.strategy.backtest")
    pack = backtest.get_strategy_pack("bulk_essence")

    assert pack.strategy_id == "bulk_essence"
    assert pack.backtest_sql_path.name == "backtest.sql"


def test_run_backtest_records_run_and_results(monkeypatch) -> None:
    backtest = importlib.import_module("poe_trade.strategy.backtest")
    monkeypatch.setattr(
        backtest,
        "get_strategy_pack",
        lambda strategy_id: _stub_pack(strategy_id=strategy_id),
    )
    monkeypatch.setattr(
        backtest,
        "load_candidate_sql",
        lambda pack: (
            "SELECT toDateTime('2026-03-01 00:00:00') AS time_bucket, "
            "'Mirage' AS league, "
            "'essence:bulk:a' AS item_or_market_key, "
            "6.25 AS expected_profit_chaos, "
            "0.5 AS expected_roi, "
            "0.7 AS confidence, "
            "48 AS sample_count, "
            "'record-results-marker' AS why_it_fired"
        ),
    )
    client = _RecordingClient(
        responses={
            "record-results-marker": "\n".join(
                [
                    _candidate_row_payload(
                        item_or_market_key="essence:bulk:a",
                        expected_profit_chaos=6.25,
                        expected_roi=0.5,
                        confidence=0.7,
                    ),
                    _candidate_row_payload(
                        item_or_market_key="essence:bulk:b",
                        expected_profit_chaos=6.25,
                        expected_roi=0.3,
                        confidence=0.9,
                    ),
                ]
            ),
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
    assert len(client.queries) == 6
    assert "research_backtest_runs" in client.queries[0]
    assert "record-results-marker" in client.queries[1]
    assert "scanner_alert_log" in client.queries[2]
    assert "research_backtest_detail" in client.queries[3]
    assert "research_backtest_summary" in client.queries[4]
    assert "research_backtest_runs" in client.queries[5]
    assert "bulk_essence" in client.queries[3]
    assert '"opportunity_count":2' in client.queries[4]
    assert '"expected_profit_chaos":12.5' in client.queries[4]
    assert '"expected_roi":0.4' in client.queries[4]
    assert '"confidence":0.8' in client.queries[4]
    assert '"completed_at":null' not in client.queries[0]
    assert '"completed_at":"1970-01-01 00:00:00.000"' in client.queries[0]
    assert backtest.BACKTEST_SUMMARY_HEADER == (
        "run_id\tstrategy_id\tleague\tlookback_days\tstatus\topportunity_count\texpected_profit_chaos\texpected_roi\tconfidence\tsummary"
    )


def test_run_backtest_persists_semantic_key_in_detail_rows(monkeypatch) -> None:
    backtest = importlib.import_module("poe_trade.strategy.backtest")
    monkeypatch.setattr(
        backtest,
        "get_strategy_pack",
        lambda strategy_id: _stub_pack(strategy_id=strategy_id),
    )
    monkeypatch.setattr(
        backtest,
        "load_candidate_sql",
        lambda pack: (
            "SELECT toDateTime('2026-03-01 00:00:00') AS time_bucket, "
            "'Mirage' AS league, "
            "'legacy:essence:bulk' AS item_or_market_key, "
            "6.25 AS expected_profit_chaos, "
            "0.5 AS expected_roi, "
            "0.7 AS confidence, "
            "48 AS sample_count, "
            "'semantic-source-marker' AS why_it_fired"
        ),
    )
    client = _RecordingClient(
        responses={
            "semantic-source-marker": _candidate_row_payload(
                item_or_market_key="legacy:essence:bulk",
                semantic_key="sem:essence:bulk",
                legacy_item_or_market_keys=["legacy:essence:bulk"],
                legacy_hashed_item_or_market_key="legacy-hash",
                expected_profit_chaos=6.25,
                expected_roi=0.5,
                confidence=0.7,
                sample_count=48,
                why_it_fired="semantic-source-marker",
            )
        }
    )

    backtest.run_backtest(
        client,
        strategy_id="bulk_essence",
        league="Mirage",
        lookback_days=14,
        dry_run=False,
    )

    detail_query = next(
        query for query in client.queries if "research_backtest_detail" in query
    )
    payload = detail_query.split("FORMAT JSONEachRow\n", 1)[1]
    rows = [json.loads(line) for line in payload.splitlines() if line.strip()]
    assert rows[0]["item_or_market_key"] == "sem:essence:bulk"
    detail_payload = json.loads(rows[0]["detail_json"])
    assert detail_payload["item_or_market_key"] == "legacy:essence:bulk"
    assert detail_payload["semantic_key"] == "sem:essence:bulk"


def test_run_backtest_deduplicates_same_snapshot_candidates(monkeypatch) -> None:
    backtest = importlib.import_module("poe_trade.strategy.backtest")
    monkeypatch.setattr(
        backtest,
        "get_strategy_pack",
        lambda strategy_id: _stub_pack(strategy_id=strategy_id),
    )
    monkeypatch.setattr(
        backtest,
        "load_candidate_sql",
        lambda pack: (
            "SELECT toDateTime('2026-03-01 00:00:00') AS time_bucket, "
            "'Mirage' AS league, "
            "'dup-key' AS item_or_market_key, "
            "6.25 AS expected_profit_chaos, "
            "0.2 AS expected_roi, "
            "0.5 AS confidence, "
            "12 AS sample_count, "
            "'duplicate-source-marker' AS why_it_fired"
        ),
    )
    client = _RecordingClient(
        responses={
            "duplicate-source-marker": "\n".join(
                [
                    _candidate_row_payload(
                        item_or_market_key="dup-key",
                        expected_profit_chaos=6.25,
                        expected_roi=0.2,
                        confidence=0.5,
                        sample_count=12,
                        why_it_fired="duplicate-source-marker-a",
                    ),
                    _candidate_row_payload(
                        item_or_market_key="dup-key",
                        expected_profit_chaos=8.0,
                        expected_roi=0.6,
                        confidence=0.9,
                        sample_count=42,
                        why_it_fired="duplicate-source-marker-b",
                    ),
                ]
            )
        }
    )

    backtest.run_backtest(
        client,
        strategy_id="bulk_essence",
        league="Mirage",
        lookback_days=14,
        dry_run=False,
    )

    summary_query = next(
        query for query in client.queries if "research_backtest_summary" in query
    )
    assert '"opportunity_count":1' in summary_query
    assert '"expected_profit_chaos":8.0' in summary_query
    assert '"confidence":0.9' in summary_query


def test_run_backtest_loads_canonical_candidate_sql_and_applies_runtime_filters(
    monkeypatch,
) -> None:
    backtest = importlib.import_module("poe_trade.strategy.backtest")
    monkeypatch.setattr(
        backtest,
        "get_strategy_pack",
        lambda strategy_id: _stub_pack(strategy_id=strategy_id),
    )
    monkeypatch.setattr(
        backtest,
        "load_candidate_sql",
        lambda pack: (
            "SELECT toDateTime('2026-03-01 00:00:00') AS time_bucket, "
            "'Mirage' AS league, "
            "'marker-key' AS item_or_market_key, "
            "4.0 AS expected_profit_chaos, "
            "0.2 AS expected_roi, "
            "0.7 AS confidence, "
            "12 AS sample_count, "
            "'candidate-source-marker' AS why_it_fired"
        ),
    )
    client = _RecordingClient(
        responses={
            "candidate-source-marker": _candidate_row_payload(
                item_or_market_key="marker-key",
                expected_profit_chaos=4.0,
                expected_roi=0.2,
                confidence=0.7,
                why_it_fired="candidate-source-marker",
            ),
        }
    )

    backtest.run_backtest(
        client,
        strategy_id="bulk_essence",
        league="Mirage",
        lookback_days=14,
        dry_run=False,
    )

    source_query = next(
        query
        for query in client.queries
        if "FORMAT JSONEachRow" in query and "candidate-source-marker" in query
    )
    assert "candidate-source-marker" in source_query
    assert "ifNull(scoped_source.league, '') = 'Mirage'" in source_query
    assert "time_bucket >= now() - INTERVAL 14 DAY" in source_query


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
            "gold_bulk_premium_hour": "",
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
    assert not any("research_backtest_detail" in query for query in client.queries)


def test_run_backtest_marks_no_opportunities_when_policy_rejects_all_candidates(
    monkeypatch,
) -> None:
    backtest = importlib.import_module("poe_trade.strategy.backtest")
    monkeypatch.setattr(
        backtest,
        "get_strategy_pack",
        lambda strategy_id: _stub_pack(
            strategy_id=strategy_id,
            min_expected_profit_chaos=10.0,
        ),
    )
    monkeypatch.setattr(
        backtest,
        "load_candidate_sql",
        lambda pack: (
            "SELECT toDateTime('2026-03-01 00:00:00') AS time_bucket, "
            "'Mirage' AS league, "
            "'policy-key' AS item_or_market_key, "
            "3.0 AS expected_profit_chaos, "
            "0.2 AS expected_roi, "
            "0.7 AS confidence, "
            "12 AS sample_count, "
            "'policy-source-marker' AS why_it_fired"
        ),
    )
    client = _RecordingClient(
        responses={
            "policy-source-marker": _candidate_row_payload(
                item_or_market_key="policy-key",
                expected_profit_chaos=3.0,
                expected_roi=0.2,
                confidence=0.7,
                why_it_fired="policy-source-marker",
            ),
        }
    )

    backtest.run_backtest(
        client,
        strategy_id="bulk_essence",
        league="Mirage",
        lookback_days=14,
        dry_run=False,
    )

    assert any('"status":"no_opportunities"' in query for query in client.queries)
    assert any(
        '"summary":"source data exists but no strategy opportunities"' in query
        for query in client.queries
    )
    assert not any("research_backtest_detail" in query for query in client.queries)


def test_run_backtest_marks_no_opportunities_when_journal_gate_blocks_candidates(
    monkeypatch,
) -> None:
    backtest = importlib.import_module("poe_trade.strategy.backtest")
    monkeypatch.setattr(
        backtest,
        "get_strategy_pack",
        lambda strategy_id: _stub_pack(
            strategy_id=strategy_id,
            requires_journal=True,
        ),
    )
    monkeypatch.setattr(
        backtest,
        "load_candidate_sql",
        lambda pack: (
            "SELECT toDateTime('2026-03-01 00:00:00') AS time_bucket, "
            "'Mirage' AS league, "
            "'journal-key' AS item_or_market_key, "
            "8.0 AS expected_profit_chaos, "
            "0.4 AS expected_roi, "
            "0.9 AS confidence, "
            "20 AS sample_count, "
            "'journal-source-marker' AS why_it_fired"
        ),
    )
    client = _RecordingClient(
        responses={
            "journal-source-marker": _candidate_row_payload(
                item_or_market_key="journal-key",
                expected_profit_chaos=8.0,
                expected_roi=0.4,
                confidence=0.9,
                why_it_fired="journal-source-marker",
            ),
        }
    )

    backtest.run_backtest(
        client,
        strategy_id="bulk_essence",
        league="Mirage",
        lookback_days=14,
        dry_run=False,
    )

    assert any('"status":"no_opportunities"' in query for query in client.queries)
    assert any("journal state" in query for query in client.queries)
    assert not any("research_backtest_detail" in query for query in client.queries)


def test_run_backtest_records_failed_status_on_insert_error(monkeypatch) -> None:
    backtest = importlib.import_module("poe_trade.strategy.backtest")
    monkeypatch.setattr(
        backtest,
        "get_strategy_pack",
        lambda strategy_id: _stub_pack(strategy_id=strategy_id),
    )
    monkeypatch.setattr(
        backtest,
        "load_candidate_sql",
        lambda pack: (
            "SELECT toDateTime('2026-03-01 00:00:00') AS time_bucket, "
            "'Mirage' AS league, "
            "'failure-key' AS item_or_market_key, "
            "6.25 AS expected_profit_chaos, "
            "0.4 AS expected_roi, "
            "0.8 AS confidence, "
            "48 AS sample_count, "
            "'failure-source-marker' AS why_it_fired"
        ),
    )
    client = _RecordingClient(
        responses={
            "failure-source-marker": _candidate_row_payload(
                item_or_market_key="failure-key",
                why_it_fired="failure-source-marker",
            ),
        },
        fail_on_match="INSERT INTO poe_trade.research_backtest_detail",
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
