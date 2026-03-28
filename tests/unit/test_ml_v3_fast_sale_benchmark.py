from __future__ import annotations

import json
from pathlib import Path

import pytest

from poe_trade.ml.v3 import benchmark


def _fast_sale_row(index: int) -> dict[str, object]:
    group = index % 4
    price = 60.0 + (group * 10.0) + (index * 1.5)
    return {
        "as_of_ts": f"2026-03-{20 + index:02d} 10:00:00.000",
        "realm": "pc",
        "league": "Mirage",
        "stash_id": f"stash-{index}",
        "item_id": f"item-{index}",
        "identity_key": f"identity-{group}",
        "route": "sparse_retrieval",
        "strategy_family": "sparse_retrieval",
        "cohort_key": f"sparse_retrieval|ring|v1|{group}",
        "parent_cohort_key": f"sparse_retrieval|ring|v1|{group}",
        "material_state_signature": f"v1|{group}",
        "category": "ring",
        "item_name": f"Item {index}",
        "item_type_line": "Iron Ring",
        "base_type": "Iron Ring",
        "rarity": "Rare",
        "ilvl": 80 + (index % 5),
        "stack_size": 1,
        "corrupted": index % 2,
        "fractured": 0,
        "synthesised": 0,
        "item_state_key": f"rare|corrupted={index % 2}|fractured=0|synthesised=0",
        "support_count_recent": 20 + index * 2,
        "feature_vector_json": json.dumps({"ilvl": 80 + (index % 5), "stack_size": 1}),
        "mod_features_json": json.dumps({"explicit.max_life": 1.0 + (index * 0.1)}),
        "target_price_chaos": price,
        "target_price_divine": price / 100.0,
        "target_fast_sale_24h_price": price * 0.9,
        "target_fast_sale_24h_price_divine": (price * 0.9) / 100.0,
        "fx_chaos_per_divine": 100.0,
        "target_sale_probability_24h": 0.75,
        "target_likely_sold": 1,
        "sale_confidence_flag": 1,
        "target_time_to_exit_hours": 8.0,
        "target_sale_price_anchor_chaos": price * 0.95,
        "label_weight": 0.8,
        "label_source": "benchmark_disappearance_proxy_h48_v1",
        "split_bucket": "train",
    }


def test_build_fast_sale_feature_row_focuses_on_signal_fields() -> None:
    row = benchmark.build_fast_sale_feature_row(_fast_sale_row(0))

    assert "item_name" not in row
    assert "item_type_line" not in row
    assert "fast_sale_stat_signature" in row
    assert row["fast_sale_signal_count"] > 0
    assert row["recognized_affix_count"] >= 0
    assert row["support_count_recent"] >= 0


def test_split_grouped_forward_benchmark_rows_is_identity_safe() -> None:
    rows = [_fast_sale_row(index) for index in range(12)]

    split = benchmark.split_grouped_forward_benchmark_rows(rows)

    assert len(split["train"]) > 0
    assert len(split["validation"]) > 0
    assert len(split["test"]) > 0
    assert split["train"][0]["as_of_ts"] < split["validation"][0]["as_of_ts"]
    assert split["validation"][0]["as_of_ts"] < split["test"][0]["as_of_ts"]
    train_ids = {row["identity_key"] for row in split["train"]}
    validation_ids = {row["identity_key"] for row in split["validation"]}
    test_ids = {row["identity_key"] for row in split["test"]}
    assert train_ids.isdisjoint(validation_ids)
    assert train_ids.isdisjoint(test_ids)
    assert validation_ids.isdisjoint(test_ids)


def test_run_fast_sale_benchmark_ranks_three_candidates() -> None:
    rows = [_fast_sale_row(index) for index in range(12)]

    report = benchmark.run_fast_sale_benchmark(rows)

    assert report["contract"]["name"] == "fast_sale_24h_price_benchmark_v1"
    assert report["contract"]["candidate_count"] == 3
    assert report["contract"]["price_units"] == ["chaos", "divine"]
    assert report["split"]["kind"] == "grouped_forward"
    assert report["split"]["identity_overlap_count"] == 0
    assert len(report["ranking"]) == 3
    assert {row["candidate"] for row in report["ranking"]} == {
        spec.name for spec in benchmark.FAST_SALE_BENCHMARK_CANDIDATE_SPECS
    }
    assert "validation_tail_mdape" in report["ranking"][0]
    assert "test_tail_mdape" in report["ranking"][0]


def test_run_fast_sale_benchmark_prefers_divine_fast_sale_targets() -> None:
    rows = [_fast_sale_row(index) for index in range(12)]
    rows[0]["target_fast_sale_24h_price"] = 500.0
    rows[0]["target_fast_sale_24h_price_divine"] = 5.0

    report = benchmark.run_fast_sale_benchmark(rows)

    assert report["contract"]["price_units"] == ["chaos", "divine"]
    assert benchmark._fast_sale_log1p_price_targets([rows[0]])[0] == pytest.approx(
        1.791759469228055
    )


def test_run_fast_sale_benchmark_uses_sold_rows_when_available() -> None:
    rows = [_fast_sale_row(index) for index in range(4)]
    rows[3]["target_likely_sold"] = 0
    rows[3]["sale_confidence_flag"] = 0

    report = benchmark.run_fast_sale_benchmark(rows)

    assert report["row_count"] == 3
    assert report["split"]["identity_overlap_count"] == 0


def test_format_and_save_fast_sale_benchmark_artifacts_writes_bundle(
    tmp_path: Path,
) -> None:
    rows = [_fast_sale_row(index) for index in range(12)]
    report = benchmark.run_fast_sale_benchmark(rows)

    text = benchmark.format_fast_sale_benchmark_report(report)
    output_path = tmp_path / "fast-sale-benchmark.txt"
    artifacts = benchmark.save_fast_sale_benchmark_artifacts(report, output_path)

    assert "# Fast-Sale 24h Benchmark Report" in text
    assert (
        "| Candidate | Val MDAPE | Test MDAPE | Val Tail MDAPE | Test Tail MDAPE | Val WAPE | Test WAPE |"
        in text
    )
    assert output_path.exists()
    assert (tmp_path / "fast-sale-benchmark.json").exists()
    assert (tmp_path / "fast-sale-benchmark.txt.joblib").exists()
    assert artifacts["artifacts"]["markdown"] == str(output_path)


def test_run_fast_sale_benchmark_rejects_extra_candidates() -> None:
    rows = [_fast_sale_row(index) for index in range(12)]

    with pytest.raises(ValueError, match="exactly 3 candidates"):
        benchmark.run_fast_sale_benchmark(
            rows,
            candidate_specs=benchmark.FAST_SALE_BENCHMARK_CANDIDATE_SPECS[:2],
        )
