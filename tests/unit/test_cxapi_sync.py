from datetime import datetime, timezone
from typing import Any, cast

from poe_trade.ingestion.cxapi_sync import (
    CxapiSync,
    cxapi_endpoint,
    initial_backfill_window,
    last_completed_hour,
    next_hour_cursor,
    truncate_to_hour,
)
from poe_trade.ingestion.poe_client import PoeResponse


class _DummyResponse(PoeResponse):
    def __init__(self, payload):
        super().__init__(payload, {"Retry-After": "15"}, 200, 1, 5.0)


class _DummyPoeClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []
        self.bearer_token = None

    def request_with_metadata(self, method, path, params=None, data=None, headers=None):
        self.calls.append((method, path, params))
        return _DummyResponse(self.payload)

    def set_bearer_token(self, token):
        self.bearer_token = token


class _DummyClickHouseClient:
    def __init__(self):
        self.queries = []

    def execute(self, query):
        self.queries.append(query)
        return ""


class _DummySyncStateStore:
    pass


class _DummyStatusReporter:
    def __init__(self):
        self.reports = []

    def report(self, **kwargs):
        self.reports.append(kwargs)


class _DummyToken:
    def __init__(self, access_token: str):
        self.access_token = access_token

    def is_expired(self) -> bool:
        return False


class _DummyAuthClient:
    def __init__(self):
        self.refresh_calls = 0

    def refresh(self):
        self.refresh_calls += 1
        return _DummyToken("cx-token")


def test_truncate_to_hour_uses_utc() -> None:
    value = datetime(2026, 3, 10, 21, 47, 33, tzinfo=timezone.utc)
    assert truncate_to_hour(value) == datetime(2026, 3, 10, 21, 0, tzinfo=timezone.utc)


def test_last_completed_hour_respects_safety_offset() -> None:
    value = datetime(2026, 3, 10, 21, 0, 10, tzinfo=timezone.utc)
    assert last_completed_hour(value, offset_seconds=15) == datetime(
        2026, 3, 10, 19, 0, tzinfo=timezone.utc
    )


def test_cxapi_endpoint_for_pc_omits_realm_segment() -> None:
    hour = datetime(2026, 3, 10, 20, 0, tzinfo=timezone.utc)
    assert cxapi_endpoint("pc", hour) == f"currency-exchange/{int(hour.timestamp())}"


def test_cxapi_endpoint_for_console_includes_realm_segment() -> None:
    hour = datetime(2026, 3, 10, 20, 0, tzinfo=timezone.utc)
    assert (
        cxapi_endpoint("xbox", hour)
        == f"currency-exchange/xbox/{int(hour.timestamp())}"
    )


def test_next_hour_cursor_advances_by_one_hour() -> None:
    hour = datetime(2026, 3, 10, 20, 45, tzinfo=timezone.utc)
    assert next_hour_cursor(hour) == datetime(2026, 3, 10, 21, 0, tzinfo=timezone.utc)


def test_initial_backfill_window_uses_last_completed_hour() -> None:
    plan = initial_backfill_window(
        datetime(2026, 3, 10, 21, 12, tzinfo=timezone.utc),
        backfill_hours=3,
        offset_seconds=15,
    )
    assert plan.current_end_hour == datetime(2026, 3, 10, 20, 0, tzinfo=timezone.utc)
    assert plan.start_hour == datetime(2026, 3, 10, 18, 0, tzinfo=timezone.utc)


def test_sync_hour_writes_cx_bronze_and_telemetry() -> None:
    requested = datetime(2026, 3, 10, 20, 0, tzinfo=timezone.utc)
    payload = {
        "next_change_id": int(requested.timestamp()),
        "markets": [{"league": "Mirage"}],
    }
    client = _DummyPoeClient(payload)
    clickhouse = _DummyClickHouseClient()
    status = _DummyStatusReporter()
    sync = CxapiSync(
        cast(Any, client),
        cast(Any, clickhouse),
        cast(Any, _DummySyncStateStore()),
        cast(Any, status),
    )

    result = sync.sync_hour("pc", requested, dry_run=False)

    assert client.calls == [
        ("GET", f"currency-exchange/{int(requested.timestamp())}", None)
    ]
    assert len(clickhouse.queries) == 3
    assert "raw_currency_exchange_hour" in clickhouse.queries[0]
    assert "bronze_requests" in clickhouse.queries[1]
    assert "bronze_ingest_checkpoints" in clickhouse.queries[2]
    assert result["queue_key"] == "cxapi:pc"
    assert status.reports[-1]["feed_kind"] == "cxapi"


def test_sync_hour_marks_idle_when_next_change_matches_requested_hour() -> None:
    requested = datetime(2026, 3, 10, 20, 0, tzinfo=timezone.utc)
    payload = {"next_change_id": int(requested.timestamp()), "markets": []}
    sync = CxapiSync(
        cast(Any, _DummyPoeClient(payload)),
        cast(Any, _DummyClickHouseClient()),
        cast(Any, _DummySyncStateStore()),
        cast(Any, _DummyStatusReporter()),
    )

    result = sync.sync_hour("xbox", requested, dry_run=True)

    assert result["status"] == "idle"


def test_sync_hour_refreshes_auth_token_when_auth_client_configured() -> None:
    requested = datetime(2026, 3, 10, 20, 0, tzinfo=timezone.utc)
    payload = {
        "next_change_id": int(requested.timestamp()),
        "markets": [{"league": "Mirage"}],
    }
    client = _DummyPoeClient(payload)
    auth = _DummyAuthClient()
    sync = CxapiSync(
        cast(Any, client),
        cast(Any, _DummyClickHouseClient()),
        cast(Any, _DummySyncStateStore()),
        cast(Any, _DummyStatusReporter()),
        auth_client=cast(Any, auth),
    )

    sync.sync_hour("pc", requested, dry_run=True)

    assert auth.refresh_calls == 1
    assert client.bearer_token == "cx-token"
