import json
import urllib.error
import pytest

from poe_trade.ingestion.market_harvester import MarketHarvester


class _DummyPoeClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def request(self, method, path, params=None, data=None, headers=None):
        self.calls.append((method, path, params))
        return self.payload


class _FailingPoeClient:
    def __init__(self, exception):
        self.exception = exception
        self.calls = []

    def request(self, method, path, params=None, data=None, headers=None):
        self.calls.append((method, path, params))
        raise self.exception


class _DummyClickHouseClient:
    def __init__(self):
        self.queries = []

    def execute(self, query):
        self.queries.append(query)


class _DummyCheckpointStore:
    def __init__(self, initial=None):
        self.storage = dict(initial or {})
        self.read_calls = []
        self.writes = []

    def read(self, key):
        self.read_calls.append(key)
        return self.storage.get(key)

    def write(self, key, value):
        self.writes.append((key, value))
        self.storage[key] = value


class _DummyStatusReporter:
    def __init__(self):
        self.reports = []

    def report(self, **kwargs):
        self.reports.append(kwargs)


def _build_harvester(payload=None, checkpoint=None, client=None):
    client = client or _DummyPoeClient(payload)
    clickhouse = _DummyClickHouseClient()
    checkpoint_store = _DummyCheckpointStore(checkpoint)
    status_reporter = _DummyStatusReporter()
    harvester = MarketHarvester(client, clickhouse, checkpoint_store, status_reporter)  # type: ignore[arg-type]
    return harvester, clickhouse, checkpoint_store, status_reporter


def test_success_flow_writes_rows_and_advances_checkpoint():
    payload = {
        "next_change_id": "next-1",
        "stashes": [{"id": "stash-a"}, {"stash_id": "stash-b"}],
    }
    harvester, clickhouse, checkpoint, status = _build_harvester(
        payload, checkpoint={"pc:Synthesis": "cursor-1"}
    )

    harvester._harvest("pc", "Synthesis", dry_run=False)

    assert len(clickhouse.queries) == 1
    assert "next-1" in clickhouse.queries[0]
    assert checkpoint.writes == [("pc:Synthesis", "next-1")]
    assert status.reports[-1]["status"] == "success"


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

    assert clickhouse.queries == []
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

    assert clickhouse.queries == []
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

    assert len(clickhouse.queries) == 1
    query_rows = clickhouse.queries[0].splitlines()[2:]
    emitted_ids = [json.loads(row)["stash_id"] for row in query_rows if row.strip()]
    assert set(emitted_ids) == {"stash-dup", "stash-unique"}
    assert len(emitted_ids) == 2
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

    assert clickhouse.queries == []
    assert checkpoint.writes == []
    assert checkpoint.storage[key] == "cursor-before"
    report = status.reports[-1]
    assert report["status"] == "error"
    assert report["error"]
    assert report["error_count"] == 1
    assert report["stalled_since"] is not None
