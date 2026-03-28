from __future__ import annotations

import importlib.util
import json
from pathlib import Path


_SCRIPT_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "benchmark_fast_sale_ideas.py"
)
_SPEC = importlib.util.spec_from_file_location(
    "benchmark_fast_sale_ideas", _SCRIPT_PATH
)
assert _SPEC is not None and _SPEC.loader is not None
benchmark_fast_sale_ideas = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(benchmark_fast_sale_ideas)


def _fake_report() -> dict[str, object]:
    return {
        "benchmark": "fast_sale_24h_price_benchmark_v1",
        "contract": {"name": "fast_sale_24h_price_benchmark_v1", "candidate_count": 3},
        "split": {
            "kind": "grouped_forward",
            "train_rows": 1,
            "validation_rows": 1,
            "test_rows": 1,
            "identity_overlap_count": 0,
        },
        "row_count": 3,
        "candidate_count": 3,
        "best_candidate": {"candidate": "catboost_fast_sale_log"},
        "ranking": [
            {
                "candidate": "catboost_fast_sale_log",
                "validation_mdape": 0.1,
                "test_mdape": 0.1,
                "validation_tail_mdape": 0.1,
                "test_tail_mdape": 0.1,
                "validation_wape": 0.1,
                "test_wape": 0.1,
            }
        ],
    }


def _fake_save_fast_sale_benchmark_artifacts(report, output_path):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.suffix.lower() in {".txt", ".md"}:
        output_path.write_text("# Fast-Sale 24h Benchmark Report\n", encoding="utf-8")
        json_path = output_path.with_suffix(".json")
        json_path.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        markdown_path = output_path
    else:
        output_path.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        markdown_path = output_path.parent / f"{output_path.name}.md"
        markdown_path.write_text("# Fast-Sale 24h Benchmark Report\n", encoding="utf-8")
        json_path = output_path
    joblib_path = output_path.parent / f"{output_path.name}.joblib"
    joblib_path.write_bytes(b"joblib")
    return {
        **report,
        "artifacts": {
            "json": str(json_path),
            "markdown": str(markdown_path),
            "joblib": str(joblib_path),
        },
    }


def test_fast_sale_ideas_cli_writes_artifacts(tmp_path, monkeypatch, capsys) -> None:
    input_path = tmp_path / "iron-ring-wide-10k.jsonl"
    input_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "identity_key": "item-1",
                        "as_of_ts": "2026-03-24 10:00:00.000",
                        "target_price_chaos": 100.0,
                        "target_price_divine": 1.0,
                        "target_fast_sale_24h_price": 90.0,
                        "target_fast_sale_24h_price_divine": 0.9,
                        "fx_chaos_per_divine": 100.0,
                    }
                ),
                json.dumps(
                    {
                        "identity_key": "item-2",
                        "as_of_ts": "2026-03-24 10:00:01.000",
                        "target_price_chaos": 101.0,
                        "target_price_divine": 1.01,
                        "target_fast_sale_24h_price": 91.0,
                        "target_fast_sale_24h_price_divine": 0.91,
                        "fx_chaos_per_divine": 100.0,
                    }
                ),
                json.dumps(
                    {
                        "identity_key": "item-3",
                        "as_of_ts": "2026-03-24 10:00:02.000",
                        "target_price_chaos": 102.0,
                        "target_price_divine": 1.02,
                        "target_fast_sale_24h_price": 92.0,
                        "target_fast_sale_24h_price_divine": 0.92,
                        "fx_chaos_per_divine": 100.0,
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        benchmark_fast_sale_ideas.benchmark,
        "run_fast_sale_benchmark",
        lambda rows: {**_fake_report(), "row_count": len(rows)},
    )
    monkeypatch.setattr(
        benchmark_fast_sale_ideas.benchmark,
        "save_fast_sale_benchmark_artifacts",
        _fake_save_fast_sale_benchmark_artifacts,
    )

    output_path = tmp_path / "fast-sale-benchmark.txt"
    result = benchmark_fast_sale_ideas.main(
        ["--input", str(input_path), "--output", str(output_path)]
    )

    assert result == 0
    assert output_path.exists()
    assert (tmp_path / "fast-sale-benchmark.json").exists()
    assert (tmp_path / "fast-sale-benchmark.txt.joblib").exists()
    summary = json.loads(capsys.readouterr().out)
    assert summary["benchmark"] == "fast_sale_24h_price_benchmark_v1"
    assert summary["candidate_count"] == 3
    assert summary["split"]["identity_overlap_count"] == 0


def test_fast_sale_ideas_cli_rejects_malformed_jsonl(tmp_path) -> None:
    input_path = tmp_path / "broken.jsonl"
    input_path.write_text("{\nnot-json\n", encoding="utf-8")

    result = benchmark_fast_sale_ideas.main(
        ["--input", str(input_path), "--output", str(tmp_path / "out.txt")]
    )

    assert result == 2
