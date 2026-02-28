import hashlib
import json
import logging
import os
import tempfile
import time
from pathlib import Path
import urllib.error

import pytest

from poe_trade.ingestion.market_harvester import MarketHarvester


class _DummyResponse:
    def __init__(
        self, payload, headers=None, status_code=200, attempts=1, duration_ms=1.0
    ):
        self.payload = payload
        self.headers = headers or {}
        self.status_code = status_code
        self.attempts = attempts
        self.duration_ms = duration_ms


class _DummyPoeClient:
    def __init__(
        self,
        payload,
        metadata=None,
        primary_status_code=200,
        primary_headers=None,
        metadata_status_code=200,
        metadata_headers=None,
    ):
        self.payload = payload
        self.metadata = metadata or {"result": []}
        self.primary_status_code = primary_status_code
        self.primary_headers = primary_headers or {"X-Rate-Limit-Client": "1:5:1"}
        self.metadata_status_code = metadata_status_code
        self.metadata_headers = metadata_headers or {"X-Rate-Limit-Client": "1:5:1"}
        self.calls = []
        self.metadata_calls = []
        self.last_attempts = 1

    def request(self, method, path, params=None, data=None, headers=None):
        self.calls.append((method, path, params))
        return self.payload

    def request_with_metadata(self, method, path, params=None, data=None, headers=None):
        self.calls.append((method, path, params))
        if path.startswith("api/trade/data/"):
            self.metadata_calls.append((path, params))
            return _DummyResponse(
                self.metadata,
                headers=self.metadata_headers,
                status_code=self.metadata_status_code,
                attempts=1,
                duration_ms=5.0,
            )
        return _DummyResponse(
            self.payload,
            headers=self.primary_headers,
            status_code=self.primary_status_code,
            attempts=1,
            duration_ms=5.0,
        )


class _FailingPoeClient:
    def __init__(self, exception):
        self.exception = exception
        self.calls = []
        self.last_attempts = 1

    def request(self, method, path, params=None, data=None, headers=None):
        self.calls.append((method, path, params))
        raise self.exception

    def request_with_metadata(self, method, path, params=None, data=None, headers=None):
        self.calls.append((method, path, params))
        raise self.exception


class _DummyClickHouseClient:
    def __init__(self):
        self.queries = []

    def execute(self, query):
        self.queries.append(query)


class _DummyCheckpointStore:
    def __init__(self, initial=None, base_dir=None):
        self.storage = {key: str(value) for key, value in (initial or {}).items()}
        self.read_calls = []
        self.writes = []
        self._dir = (
            Path(base_dir)
            if base_dir
            else Path(tempfile.mkdtemp(prefix="dummy-checkpoint-"))
        )
        self._dir.mkdir(parents=True, exist_ok=True)
        for key, value in self.storage.items():
            self._persist(key, value)

    def _path_for(self, key: str) -> Path:
        safe = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self._dir / f"{safe}.checkpoint"

    def _persist(self, key: str, value: str) -> Path:
        path = self._path_for(key)
        path.write_text(str(value), encoding="utf-8")
        return path

    def read(self, key):
        self.read_calls.append(key)
        return self.storage.get(key)

    def write(self, key, value):
        self.writes.append((key, value))
        value_str = str(value)
        self.storage[key] = value_str
        self._persist(key, value_str)

    def path(self, key):
        return self._path_for(key)


class _DummyStatusReporter:
    def __init__(self):
        self.reports = []

    def report(self, **kwargs):
        self.reports.append(kwargs)


def _build_harvester(
    payload=None, checkpoint=None, client=None, metadata=None, checkpoint_store=None
):
    client = client or _DummyPoeClient(payload, metadata=metadata)
    clickhouse = _DummyClickHouseClient()
    checkpoint_store = checkpoint_store or _DummyCheckpointStore(initial=checkpoint)
    status_reporter = _DummyStatusReporter()
    harvester = MarketHarvester(client, clickhouse, checkpoint_store, status_reporter)  # type: ignore[arg-type]
    return harvester, clickhouse, checkpoint_store, status_reporter


def test_success_flow_writes_rows_and_advances_checkpoint():
    payload = {
        "next_change_id": "next-1",
        "trade_data_id": "items",
        "stashes": [{"id": "stash-a"}, {"stash_id": "stash-b"}],
    }
    metadata = {"result": [{"trade_id": "trade-1", "item_id": "item-1"}]}
    client = _DummyPoeClient(payload, metadata=metadata)
    harvester, clickhouse, checkpoint, status = _build_harvester(
        payload,
        checkpoint={"pc:Synthesis": "cursor-1"},
        client=client,
    )

    harvester._harvest("pc", "Synthesis", dry_run=False)
    assert client.metadata_calls == [("api/trade/data/items", None)]

    assert len(clickhouse.queries) == 3
    assert "next-1" in clickhouse.queries[0]
    metadata_query = clickhouse.queries[2]
    metadata_rows = [
        line for line in metadata_query.splitlines() if line.strip().startswith("{")
    ]
    assert len(metadata_rows) == 1
    metadata_row = json.loads(metadata_rows[0])
    assert metadata_row["cursor"] == "items"
    assert metadata_row["trade_id"] == "trade-1"
    assert json.loads(metadata_row["rate_limit_raw"]) == {
        "X-Rate-Limit-Client": "1:5:1"
    }
    assert json.loads(metadata_row["rate_limit_parsed"]) == {
        "x-rate-limit-limit": 1,
        "x-rate-limit-remaining": 1,
        "x-rate-limit-reset": 5,
    }
    assert checkpoint.writes == [("pc:Synthesis", "next-1")]
    assert status.reports[-1]["status"] == "success"


def test_metadata_fetch_skipped_without_identifier(caplog):
    payload = {
        "next_change_id": "next-skip",
        "stashes": [{"id": "stash-skip"}],
    }
    client = _DummyPoeClient(payload)
    harvester, clickhouse, checkpoint, status = _build_harvester(
        payload=payload,
        checkpoint={"pc:Synthesis": "cursor-skip"},
        client=client,
    )
    caplog.set_level(logging.INFO, logger="poe_trade.ingestion.market_harvester")
    caplog.clear()
    harvester._harvest("pc", "Synthesis", dry_run=False)
    assert client.metadata_calls == []
    assert len(clickhouse.queries) == 2
    assert status.reports[-1]["status"] == "success"
    assert any(
        "Skipping trade metadata fetch" in record.getMessage() for record in caplog.records
    )

@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"next_change_id": "", "stashes": []},
        {"next_change_id": "abc", "stashes": "oops"},
    ],
)
def test_malformed_payload_sets_error_without_writes(payload):
    harvester, clickhouse, checkpoint, status = _build_harvester(
        payload, checkpoint={"pc:Synthesis": "cursor-2"}
    )

    harvester._harvest("pc", "Synthesis", dry_run=False)

    assert len(clickhouse.queries) == 1
    assert "bronze_ingest_checkpoints" in clickhouse.queries[0]
    assert checkpoint.writes == []
    assert status.reports[-1]["status"] == "error"
    assert status.reports[-1]["error"] is not None


def test_stale_cursor_does_not_advance_checkpoint():
    payload = {
        "next_change_id": "cursor-3",
        "stashes": [{"id": "stash-stale"}],
    }
    harvester, clickhouse, checkpoint, status = _build_harvester(
        payload, checkpoint={"pc:Synthesis": "cursor-3"}
    )

    harvester._harvest("pc", "Synthesis", dry_run=False)

    assert len(clickhouse.queries) == 1
    assert "bronze_ingest_checkpoints" in clickhouse.queries[0]
    assert checkpoint.writes == []
    assert status.reports[-1]["status"] == "stale cursor"


def test_duplicate_stash_ids_emit_only_unique_rows():
    payload = {
        "next_change_id": "next-dup",
        "stashes": [
            {"id": "stash-dup"},
            {"id": "stash-dup"},
            {"id": "stash-unique"},
        ],
    }
    harvester, clickhouse, checkpoint, status = _build_harvester(
        payload, checkpoint={"pc:Synthesis": "cursor-dup"}
    )

    harvester._harvest("pc", "Synthesis", dry_run=False)

    assert len(clickhouse.queries) == 2
    query_rows = clickhouse.queries[0].splitlines()[2:]
    emitted_ids = [json.loads(row)["stash_id"] for row in query_rows if row.strip()]
    assert set(emitted_ids) == {"stash-dup", "stash-unique"}
    assert len(emitted_ids) == 2
    assert "bronze_ingest_checkpoints" in clickhouse.queries[1]
    assert checkpoint.writes == [("pc:Synthesis", "next-dup")]
    assert status.reports[-1]["status"] == "success"


@pytest.mark.parametrize(
    "exc",
    [
        RuntimeError("PoE client error 429: too many requests"),
        RuntimeError("Generic failure"),
        urllib.error.URLError("network unreachable"),
    ],
)
def test_harvest_records_error_state_on_client_exceptions(exc):
    key = "pc:Synthesis"
    checkpoint_data = {key: "cursor-before"}
    harvester, clickhouse, checkpoint, status = _build_harvester(
        checkpoint=checkpoint_data, client=_FailingPoeClient(exc)
    )

    harvester._harvest("pc", "Synthesis", dry_run=False)

    is_rate_limited = "429" in str(exc)
    expected_query_count = 2 if is_rate_limited else 1
    assert len(clickhouse.queries) == expected_query_count
    assert any("bronze_ingest_checkpoints" in query for query in clickhouse.queries)
    if is_rate_limited:
        assert any("bronze_requests" in query for query in clickhouse.queries)
    assert checkpoint.writes == []
    assert checkpoint.storage[key] == "cursor-before"
    report = status.reports[-1]
    if is_rate_limited:
        assert report["status"] == "rate_limited"
        assert report["error"]
    else:
        assert report["status"] == "error"
        assert report["error"]
    assert report["error_count"] == 1
    assert report["stalled_since"] is not None


def test_checkpoint_lag_logs_risk_when_stale_file(tmp_path, caplog):
    caplog.set_level(logging.WARNING, logger="poe_trade.ingestion.market_harvester")
    caplog.clear()
    key = "pc:Synthesis"
    store = _DummyCheckpointStore(initial={key: "cursor-old"}, base_dir=tmp_path)
    stale_ts = time.time() - 30
    os.utime(store.path(key), (stale_ts, stale_ts))
    harvester, *_ = _build_harvester(payload={}, checkpoint_store=store)
    harvester._harvest("pc", "Synthesis", dry_run=False)
    assert any(
        "checkpoint_lag_seconds" in record.getMessage()
        and "divines_per_attention_minute_estimate" in record.getMessage()
        for record in caplog.records
    )


def test_checkpoint_lag_risk_skips_when_checkpoint_missing(caplog):
    caplog.set_level(logging.WARNING, logger="poe_trade.ingestion.market_harvester")
    caplog.clear()
    harvester, *_ = _build_harvester(payload={}, checkpoint=None)
    harvester._harvest("pc", "Synthesis", dry_run=False)
    assert not any(
        "checkpoint_lag_seconds" in record.getMessage() for record in caplog.records
    )


def test_checkpoint_lag_risk_skips_when_within_threshold(tmp_path, caplog):
    caplog.set_level(logging.WARNING, logger="poe_trade.ingestion.market_harvester")
    caplog.clear()
    key = "pc:Synthesis"
    store = _DummyCheckpointStore(initial={key: "cursor-fresh"}, base_dir=tmp_path)
    fresh_ts = time.time()
    os.utime(store.path(key), (fresh_ts, fresh_ts))
    harvester, *_ = _build_harvester(payload={}, checkpoint_store=store)
    harvester._harvest("pc", "Synthesis", dry_run=False)
    assert not any(
        "checkpoint_lag_seconds" in record.getMessage() for record in caplog.records
    )


def test_rate_limited_status_pauses_polling_and_logs_bronze_requests():
    payload = {"next_change_id": "next-rate", "stashes": []}
    client = _DummyPoeClient(
        payload,
        primary_status_code=429,
        primary_headers={"Retry-After": "30", "X-Rate-Limit-Client": "1:5:1"},
    )
    harvester, clickhouse, checkpoint, status = _build_harvester(
        checkpoint={"pc:Synthesis": "cursor-rate"},
        client=client,
    )

    harvester._harvest("pc", "Synthesis", dry_run=False)
    first_report = status.reports[-1]
    assert first_report["status"] == "rate_limited"
    request_queries = [q for q in clickhouse.queries if "bronze_requests" in q]
    assert len(request_queries) == 1
    request_rows = [
        line for line in request_queries[0].splitlines() if line.strip().startswith("{")
    ]
    assert len(request_rows) == 1
    request_row = json.loads(request_rows[0])
    assert request_row["status"] == 429
    assert request_row["retry_after_seconds"] == 30.0
    assert "Retry-After" in request_row["rate_limit_raw"]

    calls_before_second = len(client.calls)
    harvester._harvest("pc", "Synthesis", dry_run=False)
    second_report = status.reports[-1]
    assert second_report["status"] == "rate_limited"
    assert len(client.calls) == calls_before_second
