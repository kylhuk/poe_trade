from __future__ import annotations

import json
from datetime import date

import pytest

from poe_trade.ml.v3 import backfill


class _RecordingClient:
    def __init__(self, *, bytes_on_disk: int = 1_000_000) -> None:
        self.bytes_on_disk = bytes_on_disk
        self.queries: list[str] = []

    def execute(self, query: str, settings=None) -> str:  # noqa: ANN001
        self.queries.append(query)
        if "FROM system.parts" in query:
            return json.dumps({"bytes_on_disk": self.bytes_on_disk}) + "\n"
        return ""


def test_guard_disk_budget_raises_when_limit_exceeded() -> None:
    client = _RecordingClient(bytes_on_disk=200)

    with pytest.raises(ValueError, match="disk budget exceeded"):
        backfill.guard_disk_budget(client, max_bytes=100)


def test_replay_day_executes_event_label_and_training_queries() -> None:
    client = _RecordingClient(bytes_on_disk=10)

    result = backfill.replay_day(
        client,
        league="Mirage",
        day=date(2026, 3, 20),
        max_bytes=1_000,
    )

    joined = "\n".join(client.queries)
    assert "INSERT INTO poe_trade.silver_v3_item_events" in joined
    assert "INSERT INTO poe_trade.ml_v3_sale_proxy_labels" in joined
    assert "INSERT INTO poe_trade.ml_v3_training_examples" in joined
    assert result.day == "2026-03-20"


def test_backfill_range_processes_all_days_inclusive() -> None:
    client = _RecordingClient(bytes_on_disk=10)

    payload = backfill.backfill_range(
        client,
        league="Mirage",
        start_day="2026-03-20",
        end_day="2026-03-22",
        max_bytes=1_000,
    )

    assert payload["days_requested"] == 3
    assert payload["days_processed"] == 3
    assert [row["day"] for row in payload["results"]] == [
        "2026-03-20",
        "2026-03-21",
        "2026-03-22",
    ]
