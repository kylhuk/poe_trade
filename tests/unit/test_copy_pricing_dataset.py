from __future__ import annotations

import importlib.util
import json
from pathlib import Path


_SCRIPT_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "copy_pricing_dataset.py"
)
_SPEC = importlib.util.spec_from_file_location("copy_pricing_dataset", _SCRIPT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
copy_pricing_dataset = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(copy_pricing_dataset)


def _row(
    index: int, *, as_of_ts: str, identity_key: str, item_id: str
) -> dict[str, object]:
    return {
        "as_of_ts": as_of_ts,
        "identity_key": identity_key,
        "item_id": item_id,
        "league": "Mirage",
        "route": "sparse_retrieval",
        "target_price_chaos": 100.0 + index,
    }


def test_half_sample_export_sorts_and_selects_floor_half(tmp_path, monkeypatch) -> None:
    rows = [
        _row(
            0,
            as_of_ts="2026-03-22 10:00:00.000",
            identity_key="item-c",
            item_id="item-c",
        ),
        _row(
            1,
            as_of_ts="2026-03-20 10:00:00.000",
            identity_key="item-a",
            item_id="item-a",
        ),
        _row(
            2,
            as_of_ts="2026-03-21 10:00:00.000",
            identity_key="item-b",
            item_id="item-b",
        ),
        _row(
            3,
            as_of_ts="2026-03-20 10:00:00.000",
            identity_key="item-b",
            item_id="item-b-2",
        ),
        _row(
            4,
            as_of_ts="2026-03-22 10:00:00.000",
            identity_key="item-a",
            item_id="item-a-2",
        ),
    ]
    query_calls: list[str] = []
    ordered_rows = sorted(
        rows,
        key=lambda row: (
            str(row.get("as_of_ts") or ""),
            str(row.get("identity_key") or row.get("item_id") or ""),
            str(row.get("item_id") or ""),
        ),
    )

    def _fake_query_rows(_client, query: str):
        query_calls.append(query)
        if "count() AS row_count" in query:
            return [{"row_count": 5}]
        limit_fragment = int(query.split("LIMIT ", 1)[1].split(" ", 1)[0])
        if "SELECT as_of_ts" in query:
            return sorted(rows, key=lambda row: str(row.get("as_of_ts") or ""))[
                :limit_fragment
            ]
        return ordered_rows[:limit_fragment]

    class _FakeSettings:
        clickhouse_url = "http://clickhouse.invalid"

    class _FakeClient:
        pass

    monkeypatch.setattr(
        copy_pricing_dataset.settings, "get_settings", lambda: _FakeSettings()
    )
    monkeypatch.setattr(
        copy_pricing_dataset.ClickHouseClient,
        "from_env",
        staticmethod(lambda _url: _FakeClient()),
    )
    monkeypatch.setattr(copy_pricing_dataset, "_query_rows", _fake_query_rows)

    output_path = tmp_path / "half-sample.jsonl"
    monkeypatch.setattr(
        "sys.argv",
        [
            "copy_pricing_dataset.py",
            "--league",
            "Mirage",
            "--source-table",
            "poe_trade.ml_v3_training_examples",
            "--half-sample",
            "--output",
            str(output_path),
        ],
    )

    result = copy_pricing_dataset.main()

    assert result == 0
    assert len(query_calls) == 3
    assert "count() AS row_count" in query_calls[0]
    assert "SELECT as_of_ts" in query_calls[1]
    assert "ORDER BY as_of_ts ASC" in query_calls[1]
    assert "LIMIT 2" in query_calls[1]
    assert "SELECT *" in query_calls[2]
    assert "as_of_ts <= toDateTime64(" in query_calls[2]
    assert "ORDER BY as_of_ts ASC, identity_key ASC, item_id ASC" in query_calls[2]
    assert "LIMIT 2" in query_calls[2]
    written_rows = [
        json.loads(line)
        for line in output_path.read_text(encoding="utf-8").splitlines()
    ]
    expected_rows = ordered_rows[:2]
    assert written_rows == expected_rows


def test_half_sample_export_keeps_one_row_for_single_eligible_row(
    tmp_path, monkeypatch
) -> None:
    rows = [
        _row(
            0,
            as_of_ts="2026-03-20 10:00:00.000",
            identity_key="item-a",
            item_id="item-a",
        ),
    ]
    query_calls: list[str] = []
    ordered_rows = sorted(
        rows,
        key=lambda row: (
            str(row.get("as_of_ts") or ""),
            str(row.get("identity_key") or row.get("item_id") or ""),
            str(row.get("item_id") or ""),
        ),
    )

    def _fake_query_rows(_client, query: str):
        query_calls.append(query)
        if "count() AS row_count" in query:
            return [{"row_count": 1}]
        limit_fragment = int(query.split("LIMIT ", 1)[1].split(" ", 1)[0])
        if "SELECT as_of_ts" in query:
            return sorted(rows, key=lambda row: str(row.get("as_of_ts") or ""))[
                :limit_fragment
            ]
        return ordered_rows[:limit_fragment]

    class _FakeSettings:
        clickhouse_url = "http://clickhouse.invalid"

    class _FakeClient:
        pass

    monkeypatch.setattr(
        copy_pricing_dataset.settings, "get_settings", lambda: _FakeSettings()
    )
    monkeypatch.setattr(
        copy_pricing_dataset.ClickHouseClient,
        "from_env",
        staticmethod(lambda _url: _FakeClient()),
    )
    monkeypatch.setattr(copy_pricing_dataset, "_query_rows", _fake_query_rows)

    output_path = tmp_path / "single.jsonl"
    monkeypatch.setattr(
        "sys.argv",
        [
            "copy_pricing_dataset.py",
            "--league",
            "Mirage",
            "--half-sample",
            "--output",
            str(output_path),
        ],
    )

    result = copy_pricing_dataset.main()

    assert result == 0
    assert len(query_calls) == 3
    assert "LIMIT 1" in query_calls[1]
    assert "LIMIT 1" in query_calls[2]
    written_rows = [
        json.loads(line)
        for line in output_path.read_text(encoding="utf-8").splitlines()
    ]
    assert written_rows == ordered_rows[:1]


def test_full_export_retains_existing_descending_query(tmp_path, monkeypatch) -> None:
    rows = [
        _row(
            0,
            as_of_ts="2026-03-20 10:00:00.000",
            identity_key="item-a",
            item_id="item-a",
        ),
        _row(
            1,
            as_of_ts="2026-03-21 10:00:00.000",
            identity_key="item-b",
            item_id="item-b",
        ),
        _row(
            2,
            as_of_ts="2026-03-22 10:00:00.000",
            identity_key="item-c",
            item_id="item-c",
        ),
    ]
    query_calls: list[str] = []

    def _fake_query_rows(_client, query: str):
        query_calls.append(query)
        return list(rows)

    class _FakeSettings:
        clickhouse_url = "http://clickhouse.invalid"

    class _FakeClient:
        pass

    monkeypatch.setattr(
        copy_pricing_dataset.settings, "get_settings", lambda: _FakeSettings()
    )
    monkeypatch.setattr(
        copy_pricing_dataset.ClickHouseClient,
        "from_env",
        staticmethod(lambda _url: _FakeClient()),
    )
    monkeypatch.setattr(copy_pricing_dataset, "_query_rows", _fake_query_rows)

    output_path = tmp_path / "full.jsonl"
    monkeypatch.setattr(
        "sys.argv",
        [
            "copy_pricing_dataset.py",
            "--league",
            "Mirage",
            "--output",
            str(output_path),
        ],
    )

    result = copy_pricing_dataset.main()

    assert result == 0
    assert query_calls
    assert "ORDER BY as_of_ts DESC" in query_calls[0]
    assert "LIMIT 5000" in query_calls[0]
    written_rows = [
        json.loads(line)
        for line in output_path.read_text(encoding="utf-8").splitlines()
    ]
    assert written_rows == rows
