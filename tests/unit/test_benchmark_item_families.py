from __future__ import annotations

import importlib.util
import json
from collections.abc import Mapping
from pathlib import Path

from poe_trade.ml.v3 import benchmark


_SCRIPT_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "benchmark_item_families.py"
)
_SPEC = importlib.util.spec_from_file_location("benchmark_item_families", _SCRIPT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
benchmark_item_families = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(benchmark_item_families)


def _fake_query_rows(_client, query: str):
    if "count() AS row_count" in query:
        return [{"row_count": 3}]
    return [
        {
            "as_of_ts": "2026-03-24 10:00:00.000",
            "identity_key": "item-1",
            "item_id": "item-1",
            "league": "Mirage",
            "route": "sparse_retrieval",
            "target_price_chaos": 100.0,
            "target_price_divine": 1.0,
            "target_fast_sale_24h_price": 90.0,
            "target_fast_sale_24h_price_divine": 0.9,
            "fx_chaos_per_divine": 100.0,
        },
        {
            "as_of_ts": "2026-03-24 10:00:01.000",
            "identity_key": "item-2",
            "item_id": "item-2",
            "league": "Mirage",
            "route": "sparse_retrieval",
            "target_price_chaos": 101.0,
            "target_price_divine": 1.01,
            "target_fast_sale_24h_price": 91.0,
            "target_fast_sale_24h_price_divine": 0.91,
            "fx_chaos_per_divine": 100.0,
        },
        {
            "as_of_ts": "2026-03-24 10:00:02.000",
            "identity_key": "item-3",
            "item_id": "item-3",
            "league": "Mirage",
            "route": "sparse_retrieval",
            "target_price_chaos": 102.0,
            "target_price_divine": 1.02,
            "target_fast_sale_24h_price": 92.0,
            "target_fast_sale_24h_price_divine": 0.92,
            "fx_chaos_per_divine": 100.0,
        },
    ]


def _write_report_bundle(
    output_path: Path, report: Mapping[str, object]
) -> dict[str, str]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.suffix.lower() in {".txt", ".md"}:
        output_path.write_text("# ML Pricing Benchmark Report\n", encoding="utf-8")
        output_path.with_suffix(".json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        markdown_path = output_path
        json_path = output_path.with_suffix(".json")
    else:
        output_path.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        markdown_path = output_path.parent / f"{output_path.name}.md"
        markdown_path.write_text("# ML Pricing Benchmark Report\n", encoding="utf-8")
        json_path = output_path
    joblib_path = output_path.parent / f"{output_path.name}.joblib"
    joblib_path.write_bytes(b"joblib")
    return {
        "json": str(json_path),
        "markdown": str(markdown_path),
        "joblib": str(joblib_path),
    }


def _fake_save_benchmark_artifacts(rows, output_path):
    output_path = Path(output_path)
    ranking = []
    for index, spec in enumerate(benchmark.BENCHMARK_CANDIDATE_SPECS):
        ranking.append(
            {
                "candidate": spec.name,
                "validation_mdape": round(0.10 + (index * 0.01), 4),
                "test_mdape": round(0.20 + (index * 0.01), 4),
                "validation_wape": round(0.30 + (index * 0.01), 4),
                "test_wape": round(0.40 + (index * 0.01), 4),
                "validation_interval_80_coverage": round(0.70 - (index * 0.01), 4),
                "test_interval_80_coverage": round(0.65 - (index * 0.01), 4),
            }
        )
    report = {
        "contract": benchmark.benchmark_contract(),
        "split": {
            "kind": "forward",
            "train_rows": 1,
            "validation_rows": 1,
            "test_rows": 1,
        },
        "ranking": ranking,
        "best_candidate": ranking[0],
        "candidate_results": [],
        "rows_seen": len(rows),
    }
    artifacts = _write_report_bundle(output_path, report)
    return {**report, "artifacts": artifacts}


def test_cli_writes_family_and_aggregate_artifacts(
    tmp_path, monkeypatch, capsys
) -> None:
    query_calls: list[str] = []

    class _FakeSettings:
        clickhouse_url = "http://clickhouse.invalid"

    class _FakeClient:
        pass

    monkeypatch.setattr(
        benchmark_item_families.settings, "get_settings", lambda: _FakeSettings()
    )
    monkeypatch.setattr(
        benchmark_item_families.ClickHouseClient,
        "from_env",
        staticmethod(lambda _url: _FakeClient()),
    )

    def _recording_query_rows(_client, query: str):
        query_calls.append(query)
        return _fake_query_rows(_client, query)

    monkeypatch.setattr(benchmark_item_families, "_query_rows", _recording_query_rows)
    monkeypatch.setattr(
        benchmark_item_families.benchmark,
        "save_benchmark_artifacts",
        _fake_save_benchmark_artifacts,
    )

    output_dir = tmp_path / "benchmark-item-families"
    result = benchmark_item_families.main(
        [
            "--league",
            "Mirage",
            "--as-of-ts",
            "2026-03-24 10:00:00",
            "--sample-size",
            "3",
            "--families",
            "flask,map,cluster_jewel,boots",
            "--output-dir",
            str(output_dir),
        ]
    )

    assert result == 0
    assert len(query_calls) == 8
    assert "LIMIT 3" in query_calls[1]
    assert "LIMIT 3" in query_calls[3]
    assert "LIMIT 3" in query_calls[5]
    assert "LIMIT 3" in query_calls[7]
    assert (output_dir / "flask" / "benchmark.txt").exists()
    assert (output_dir / "map" / "benchmark.txt").exists()
    assert (output_dir / "cluster_jewel" / "benchmark.txt").exists()
    assert (output_dir / "boots" / "benchmark.txt").exists()
    assert (output_dir / "benchmark-item-families.txt").exists()
    assert (output_dir / "benchmark-item-families.json").exists()
    assert (output_dir / "benchmark-item-families.txt.joblib").exists()
    summary = json.loads(capsys.readouterr().out)
    assert summary["sample_size"] == 3
    assert summary["family_sample_counts"] == {
        "flask": 3,
        "map": 3,
        "cluster_jewel": 3,
        "boots": 3,
    }
    assert summary["row_count"] == 40


def test_cli_fails_loudly_on_family_shortfall(tmp_path, monkeypatch, capsys) -> None:
    query_calls: list[str] = []

    class _FakeSettings:
        clickhouse_url = "http://clickhouse.invalid"

    class _FakeClient:
        pass

    monkeypatch.setattr(
        benchmark_item_families.settings, "get_settings", lambda: _FakeSettings()
    )
    monkeypatch.setattr(
        benchmark_item_families.ClickHouseClient,
        "from_env",
        staticmethod(lambda _url: _FakeClient()),
    )

    def _shortfall_query_rows(_client, query: str):
        query_calls.append(query)
        if "count() AS row_count" in query:
            return [{"row_count": 2}]
        return []

    monkeypatch.setattr(benchmark_item_families, "_query_rows", _shortfall_query_rows)

    result = benchmark_item_families.main(
        [
            "--league",
            "Mirage",
            "--as-of-ts",
            "2026-03-24 10:00:00",
            "--sample-size",
            "3",
            "--families",
            "flask,map,cluster_jewel,boots",
            "--output-dir",
            str(tmp_path / "out"),
        ]
    )

    assert result == 2
    assert len(query_calls) == 1
    assert "flask family shortfall: available=2 required=3" in capsys.readouterr().err
