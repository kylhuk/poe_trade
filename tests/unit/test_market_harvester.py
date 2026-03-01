import hashlib
import json
import logging
import os
import re
import tempfile
import time
from pathlib import Path
import urllib.error
from datetime import datetime, timezone
from typing import Any, Mapping

import pytest

from poe_trade.db import ClickHouseClient
from poe_trade.ingestion.checkpoints import CheckpointStore
from poe_trade.ingestion.market_harvester import (
    MarketHarvester,
    OAuthClient,
    OAuthToken,
)
from poe_trade.ingestion.poe_client import PoeClient, PoeResponse
from poe_trade.ingestion.rate_limit import RateLimitPolicy
from poe_trade.ingestion.status import StatusReporter


logger = logging.getLogger(__name__)


class _DummyResponse(PoeResponse):
    def __init__(
        self, payload, headers=None, status_code=200, attempts=1, duration_ms=1.0
    ):
        super().__init__(
            payload,
            headers or {},
            status_code,
            attempts,
            duration_ms,
        )


class _DummyAuthClient(OAuthClient):
    def __init__(
        self,
        client: PoeClient,
        client_id: str,
        client_secret: str,
        grant_type: str,
        scope: str,
    ):
        # Pass keyword arguments to super().__init__ as a workaround for LSP issues
        super().__init__(
            client=client,
            client_id=client_id,
            client_secret=client_secret,
            grant_type=grant_type,
            scope=scope,
        )
        self.refresh_calls = []
        self._token = OAuthToken(access_token="dummy_access_token", expires_in=3600)

    def refresh(self) -> OAuthToken:
        self.refresh_calls.append(True)
        return self._token


class _DummyPoeClient(PoeClient):
    def __init__(
        self,
        base_url: str = "http://dummy.url",
        rate_limit_policy: RateLimitPolicy | None = None,
        user_agent: str = "dummy-agent",
        request_timeout: float = 1.0,
        payload=None,
        metadata=None,
        primary_status_code=200,
        primary_headers=None,
        metadata_status_code=200,
        metadata_headers=None,
    ):
        super().__init__(
            base_url,
            rate_limit_policy or RateLimitPolicy(1, 1, 1, 0),
            user_agent,
            request_timeout,
        )
        self.payload = payload
        self.metadata = metadata or {"result": []}
        self.primary_status_code = primary_status_code
        self.primary_headers = primary_headers or {"X-Rate-Limit-Client": "1:5:1"}
        self.metadata_status_code = metadata_status_code
        self.metadata_headers = metadata_headers or {"X-Rate-Limit-Client": "1:5:1"}
        self.calls = []
        self.metadata_calls = []
        self._bearer_token = None

    def request(
        self, method, path, params=None, data=None, headers=None
    ) -> PoeResponse:
        self.calls.append((method, path, params))
        return _DummyResponse(self.payload)

    def request_with_metadata(
        self, method, path, params=None, data=None, headers=None
    ) -> PoeResponse:
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

    def set_bearer_token(self, token: str | None):  # Fix: Accept None
        self._bearer_token = token


class _FailingPoeClient(PoeClient):
    def __init__(
        self,
        exception: Exception,
        base_url: str = "http://dummy.url",
        rate_limit_policy: RateLimitPolicy | None = None,
        user_agent: str = "dummy",
        request_timeout: float = 1.0,
    ):
        super().__init__(
            base_url,
            rate_limit_policy or RateLimitPolicy(1, 1, 1, 0),
            user_agent,
            request_timeout,
        )
        self.exception = exception
        self.calls = []

    def request(
        self, method, path, params=None, data=None, headers=None
    ) -> PoeResponse:
        self.calls.append((method, path, params))
        raise self.exception

    def request_with_metadata(
        self, method, path, params=None, data=None, headers=None
    ) -> PoeResponse:
        self.calls.append((method, path, params))
        raise self.exception


class _DummyClickHouseClient(ClickHouseClient):
    def __init__(
        self,
        endpoint: str = "http://localhost:8123",
        database: str | None = None,
        user: str | None = None,
        password: str | None = None,
        timeout: float = 30.0,
    ):
        super().__init__(
            endpoint=endpoint,
            database=database,
            user=user,
            password=password,
            timeout=timeout,
        )
        self.queries = []

    def execute(self, query: str) -> str:
        self.queries.append(query)
        return ""


class _DummyCheckpointStore(CheckpointStore):
    def __init__(
        self, directory: str = ".tmp", initial: Mapping[str, str] | None = None
    ):
        # We need to ensure that the directory argument is passed to the super constructor.
        # But we also want to use a temporary directory for testing.
        # So we create the temporary directory first, then pass its path to super.
        self._temp_dir = Path(tempfile.mkdtemp(prefix="test-checkpoints-"))
        super().__init__(str(self._temp_dir))

        self.storage = {key: str(value) for key, value in (initial or {}).items()}
        self.read_calls = []
        self.writes = []

        # Populate initial checkpoints by writing through the parent method
        for key, value in self.storage.items():
            super().write(key, value)  # Use parent's write to create files

    def __del__(self):
        # Clean up the temporary directory when the object is deleted
        if self._temp_dir.exists():
            for item in self._temp_dir.iterdir():
                if item.is_file():
                    item.unlink()
            self._temp_dir.rmdir()

    def read(self, key: str) -> str | None:
        self.read_calls.append(key)
        return super().read(key)

    def write(self, key: str, value: str):
        self.writes.append((key, value))
        self.storage[key] = str(value)  # Update internal storage
        super().write(key, value)  # Use parent's write to persist to disk


class _DummyStatusReporter(StatusReporter):
    def __init__(
        self,
        client: ClickHouseClient = _DummyClickHouseClient(),
        source: str = "dummy",
    ):
        super().__init__(client, source)
        self.reports = []

    def report(
        self,
        league: str,
        realm: str,
        cursor: str | None,
        next_change_id: str | None,
        last_ingest_at: datetime,
        request_rate: float | None,
        status: str,
        error: str | None = None,
        error_count: int = 0,
        stalled_since: datetime | None = None,
    ) -> None:
        self.reports.append(
            {
                "league": league,
                "realm": realm,
                "cursor": cursor,
                "next_change_id": next_change_id,
                "last_ingest_at": last_ingest_at,
                "request_rate": request_rate,
                "status": status,
                "error": error,
                "error_count": error_count,
                "stalled_since": stalled_since,
            }
        )


def _build_harvester(
    payload=None,
    checkpoint=None,
    client=None,
    metadata=None,
    checkpoint_store=None,
    auth_client=None,
    status_reporter=None,
    bootstrap_until_league: str | None = None,
    bootstrap_from_beginning: bool = False,
):
    # Ensure a PoeClient instance is passed to _DummyAuthClient for its super() call
    dummy_poe_for_auth = _DummyPoeClient(
        base_url="http://dummy.url",
        rate_limit_policy=RateLimitPolicy(1, 1, 1, 0),
        user_agent="auth",
        request_timeout=1.0,
    )
    auth_client = auth_client or _DummyAuthClient(
        client=dummy_poe_for_auth,
        client_id="dummy_id",
        client_secret="dummy_secret",
        grant_type="client_credentials",
        scope="service:psapi",
    )

    client = client or _DummyPoeClient(payload=payload, metadata=metadata)
    clickhouse = _DummyClickHouseClient()
    # Ensure checkpoint_store uses a temporary directory for each test run
    # This logic has been moved to _DummyCheckpointStore.__init__
    checkpoint_store = checkpoint_store or _DummyCheckpointStore(initial=checkpoint)
    status_reporter = status_reporter or _DummyStatusReporter(
        client=clickhouse
    )  # Corrected parameter name
    harvester = MarketHarvester(
        client,
        clickhouse,
        checkpoint_store,
        status_reporter,
        auth_client=auth_client,
        bootstrap_until_league=bootstrap_until_league,
        bootstrap_from_beginning=bootstrap_from_beginning,
    )
    return harvester, clickhouse, checkpoint_store, status_reporter


def test_success_flow_writes_rows_and_advances_checkpoint():
    payload = {
        "next_change_id": "next-1",
        "trade_data_id": "items",
        "stashes": [
            {"id": "stash-a", "league": "Synthesis", "realm": "pc"},
            {"stash_id": "stash-b", "league": "Synthesis", "realm": "pc"},
        ],
    }
    metadata = {"result": [{"trade_id": "trade-1", "item_id": "item-1"}]}
    client = _DummyPoeClient(payload=payload, metadata=metadata)
    harvester, clickhouse, checkpoint, status = _build_harvester(
        payload=payload,
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
    raw_rows = [
        json.loads(row)
        for row in clickhouse.queries[0].splitlines()
        if row.strip().startswith("{")
    ]
    assert len(raw_rows) == 2
    assert {row["stash_id"] for row in raw_rows} == {"stash-a", "stash-b"}
    for row in raw_rows:
        assert "tab_id" not in row
        assert "captured_at" not in row
        assert "snapshot_id" not in row
    assert checkpoint.writes == [("pc:Synthesis", "next-1")]
    assert status.reports[-1]["status"] == "success"


def test_metadata_fetch_skipped_without_identifier(caplog):
    payload = {
        "next_change_id": "next-skip",
        "stashes": [{"id": "stash-skip", "league": "Synthesis", "realm": "pc"}],
    }
    client = _DummyPoeClient(payload=payload)
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
        "Skipping trade metadata fetch" in record.getMessage()
        for record in caplog.records
    )


@pytest.mark.parametrize(
    "payload, expected_checkpoint_writes, expected_status, expected_query_count, expect_raw_insert",  # Track raw inserts and query counts
    [
        ({}, [], "error", 1, False),  # No next_change_id
        ({"next_change_id": "", "stashes": []}, [], "error", 1, False),  # Empty next_change_id
        (
            {"next_change_id": "abc", "stashes": "oops"},
            [],
            "error",
            1,
            False,
        ),  # Malformed stashes, but next_change_id is present, but no write happens due to exception
        # Null league entries now emit a row (league stored as None) while the checkpoint still advances.
        (
            {
                "next_change_id": "abc",
                "stashes": [{"id": "bad-stash", "league": None, "realm": "pc"}],
            },
            [("pc:Synthesis", "abc")],
            "success",
            2,
            True,
        ),
    ],
)
def test_malformed_payload_sets_error_without_writes(
    payload,
    expected_checkpoint_writes,
    expected_status,
    expected_query_count,
    expect_raw_insert,
):
    harvester, clickhouse, checkpoint, status = _build_harvester(
        payload=payload, checkpoint={"pc:Synthesis": "cursor-2"}
    )

    harvester._harvest("pc", "Synthesis", dry_run=False)

    assert len(clickhouse.queries) == expected_query_count
    assert any("bronze_ingest_checkpoints" in query for query in clickhouse.queries)
    if expect_raw_insert:
        assert any("raw_public_stash_pages" in query for query in clickhouse.queries)
    else:
        assert all("raw_public_stash_pages" not in query for query in clickhouse.queries)
    assert (
        checkpoint.writes == expected_checkpoint_writes
    )  # Use expected_checkpoint_writes
    assert status.reports[-1]["status"] == expected_status  # Use expected_status
    if expected_status == "success":
        assert status.reports[-1]["error"] is None
    else:
        assert status.reports[-1]["error"] is not None


def test_stale_cursor_does_not_advance_checkpoint():
    payload = {
        "next_change_id": "cursor-3",
        "stashes": [{"id": "stash-stale", "league": "Synthesis", "realm": "pc"}],
    }
    harvester, clickhouse, checkpoint, status = _build_harvester(
        payload=payload, checkpoint={"pc:Synthesis": "cursor-3"}
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
            {"id": "stash-dup", "league": "Synthesis", "realm": "pc"},
            {"id": "stash-dup", "league": "Synthesis", "realm": "pc"},
            {"id": "stash-unique", "league": "Synthesis", "realm": "pc"},
        ],
    }
    harvester, clickhouse, checkpoint, status = _build_harvester(
        payload=payload, checkpoint={"pc:Synthesis": "cursor-dup"}
    )

    harvester._harvest("pc", "Synthesis", dry_run=False)

    assert len(clickhouse.queries) == 2
    raw_rows = [
        json.loads(row)
        for row in clickhouse.queries[0].splitlines()
        if row.strip().startswith("{")
    ]
    emitted_ids = [row["stash_id"] for row in raw_rows]
    assert set(emitted_ids) == {"stash-dup", "stash-unique"}
    assert len(emitted_ids) == 2
    for row in raw_rows:
        assert "tab_id" not in row
        assert "captured_at" not in row
        assert "snapshot_id" not in row
    assert "bronze_ingest_checkpoints" in clickhouse.queries[1]
    assert checkpoint.writes == [("pc:Synthesis", "next-dup")]
    assert status.reports[-1]["status"] == "success"


def test_write_normalizes_legacy_row_to_new_insert_shape():
    clickhouse = _DummyClickHouseClient()
    checkpoint_store = _DummyCheckpointStore()
    status_reporter = _DummyStatusReporter(client=clickhouse)
    harvester = MarketHarvester(
        _DummyPoeClient(),
        clickhouse,
        checkpoint_store,
        status_reporter,
    )

    legacy_row = {
        "captured_at": "2026-03-01 12:00:00.000",
        "tab_id": "legacy-tab",
        "snapshot_id": "service:legacy-tab:2026-03-01",
        "league": "Synthesis",
        "realm": "pc",
        "payload_json": "{}",
        "next_change_id": "cursor-legacy",
    }

    harvester._write([legacy_row], checkpoint="cursor-123")

    raw_rows = [
        json.loads(row)
        for row in clickhouse.queries[0].splitlines()
        if row.strip().startswith("{")
    ]
    assert len(raw_rows) == 1
    normalized_row = raw_rows[0]
    assert normalized_row["ingested_at"] == legacy_row["captured_at"]
    assert normalized_row["stash_id"] == legacy_row["tab_id"]
    assert normalized_row["checkpoint"] == "cursor-123"
    assert "captured_at" not in normalized_row
    assert "tab_id" not in normalized_row
    assert "snapshot_id" not in normalized_row


def test_null_entry_league_is_preserved_as_null_row():
    payload = {
        "next_change_id": "null-league",
        "stashes": [{"id": "stash-null", "league": None, "realm": "pc"}],
    }
    harvester, clickhouse, checkpoint, status = _build_harvester(payload=payload)

    harvester._harvest("pc", "Synthesis", dry_run=False)

    raw_rows = [
        json.loads(row)
        for row in clickhouse.queries[0].splitlines()
        if row.strip().startswith("{")
    ]
    assert len(raw_rows) == 1
    assert raw_rows[0]["league"] is None
    assert checkpoint.writes[-1] == ("pc:Synthesis", "null-league")
    assert status.reports[-1]["status"] == "success"


def test_row_league_comes_from_api_entry_league():
    payload = {
        "next_change_id": "entry-league",
        "stashes": [{"id": "stash-league", "league": "Delirium", "realm": "pc"}],
    }
    harvester, clickhouse, checkpoint, status = _build_harvester(payload=payload)

    harvester._harvest("pc", "Synthesis", dry_run=False)

    raw_rows = [
        json.loads(row)
        for row in clickhouse.queries[0].splitlines()
        if row.strip().startswith("{")
    ]
    assert len(raw_rows) == 1
    assert raw_rows[0]["league"] == "Delirium"
    assert raw_rows[0]["league"] != "Synthesis"
    assert checkpoint.writes[-1] == ("pc:Synthesis", "entry-league")
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
    # _ensure_token now also writes a checkpoint entry if it fails to authorize
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
    store = _DummyCheckpointStore(directory=str(tmp_path), initial={key: "cursor-old"})
    stale_ts = (
        time.time() - 301
    )  # FIX: more than _CHECKPOINT_LAG_THRESHOLD_SECONDS (300s)
    os.utime(store.path(key), (stale_ts, stale_ts))
    # FIX: provide a minimal valid payload for _build_harvester
    harvester, *_ = _build_harvester(
        payload={
            "next_change_id": "fresh-id",
            "stashes": [{"id": "stash-a", "league": "Synthesis", "realm": "pc"}],
        },
        checkpoint_store=store,
    )
    harvester._harvest("pc", "Synthesis", dry_run=False)
    pattern = (
        r"^checkpoint lag risk for "
        + re.escape(key)
        + r" checkpoint_lag_seconds=\d+\.\d divines_per_attention_minute_estimate=\d+\.\d{3}$"
    )
    assert any(re.search(pattern, record.getMessage()) for record in caplog.records)


def test_checkpoint_lag_risk_skips_when_checkpoint_missing(caplog):
    caplog.set_level(logging.WARNING, logger="poe_trade.ingestion.market_harvester")
    caplog.clear()
    # FIX: provide a minimal valid payload for _build_harvester
    harvester, *_ = _build_harvester(
        payload={
            "next_change_id": "fresh-id",
            "stashes": [{"id": "s1", "league": "Syn", "realm": "pc"}],
        },
        checkpoint=None,
    )
    harvester._harvest("pc", "Synthesis", dry_run=False)
    assert not any(
        "checkpoint lag risk for" in record.getMessage() for record in caplog.records
    )


def test_checkpoint_lag_risk_skips_when_within_threshold(tmp_path, caplog):
    caplog.set_level(logging.WARNING, logger="poe_trade.ingestion.market_harvester")
    caplog.clear()
    key = "pc:Synthesis"
    store = _DummyCheckpointStore(
        directory=str(tmp_path), initial={key: "cursor-fresh"}
    )
    fresh_ts = time.time()
    os.utime(store.path(key), (fresh_ts, fresh_ts))
    # FIX: provide a minimal valid payload for _build_harvester
    harvester, *_ = _build_harvester(
        payload={
            "next_change_id": "fresh-id",
            "stashes": [{"id": "stash-a", "league": "Synthesis", "realm": "pc"}],
        },
        checkpoint_store=store,
    )
    harvester._harvest("pc", "Synthesis", dry_run=False)
    assert not any(
        "checkpoint lag risk for" in record.getMessage() for record in caplog.records
    )


def test_rate_limited_status_pauses_polling_and_logs_bronze_requests():
    payload = {"next_change_id": "next-rate", "stashes": []}
    client = _DummyPoeClient(
        payload=payload,
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
