from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from poe_trade.ml.v3 import benchmark
from poe_trade.ml.v3 import sql


def _row(index: int) -> dict[str, object]:
    price = 50.0 + (index * 4.0)
    return {
        "as_of_ts": f"2026-03-{20 + index:02d} 10:00:00.000",
        "realm": "pc",
        "league": "Mirage",
        "stash_id": f"stash-{index}",
        "item_id": f"item-{index}",
        "identity_key": f"item-{index}",
        "route": "sparse_retrieval",
        "strategy_family": "sparse_retrieval",
        "cohort_key": f"sparse_retrieval|helmet|v1|{index}",
        "parent_cohort_key": f"sparse_retrieval|helmet|v1|{index}",
        "material_state_signature": f"v1|{index}",
        "category": "helmet" if index % 2 == 0 else "ring",
        "item_name": f"Item {index}",
        "item_type_line": "Hubris Circlet",
        "base_type": "Hubris Circlet",
        "rarity": "Rare",
        "ilvl": 80 + (index % 5),
        "stack_size": 1,
        "corrupted": index % 2,
        "fractured": 0,
        "synthesised": 0,
        "mirrored": 0,
        "quality": 20,
        "number_of_sockets": 4,
        "number_of_links": 4,
        "item_state_key": f"rare|corrupted={index % 2}|fractured=0|synthesised=0",
        "support_count_recent": 20 + index * 3,
        "feature_vector_json": json.dumps({"ilvl": 80 + (index % 5), "stack_size": 1}),
        "mod_features_json": json.dumps({"explicit.max_life": 1.0 + (index * 0.1)}),
        "target_price_chaos": price,
        "target_price_divine": price / 100.0,
        "target_fast_sale_24h_price": price * 0.92,
        "target_fast_sale_24h_price_divine": (price * 0.92) / 100.0,
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


def _lgbm_row(index: int) -> dict[str, object]:
    row: dict[str, object] = {column: None for column in sql.LGBM_NEO_COLUMNS}
    row.update(
        {
            "observed_at": f"2026-03-{20 + index:02d} 10:00:00.000",
            "item_id": f"item-{index}",
            "item_fingerprint": f"fingerprint-{index // 2}",
            "league": "Mirage",
            "category": "ring",
            "base_type": "Iron Ring",
            "price_chaos": 50.0 + (index * 2.5),
        }
    )

    feature_values = {
        "exp_mana_flat": 34.0,
        "exp_item_rarity_pct": 11.0,
        "exp_dex_flat": 34.0,
        "exp_lightning_res_pct": 45.0,
        "exp_life_flat": 60.0,
        "exp_all_attrs_flat": 7.0,
        "exp_all_elem_res_pct": 10.0,
        "exp_fire_res_pct": 24.0,
        "exp_cold_res_pct": 19.0,
        "exp_chaos_res_pct": 14.0,
        "exp_int_flat": 18.0,
        "exp_str_flat": 22.0,
        "exp_cast_speed_pct": 6.0,
        "exp_attack_speed_pct": 5.0,
        "exp_fire_damage_flat": 8.0,
        "exp_cold_damage_flat": 9.0,
        "exp_lightning_damage_flat": 10.0,
        "exp_phys_damage_flat": 12.0,
        "exp_energy_shield_flat": 15.0,
        "imp_armour_pct": 11.0,
        "imp_evasion_pct": 4.0,
    }

    for feature_base in sql.LGBM_NEO_FEATURE_BASES:
        value = feature_values.get(feature_base)
        has_key = f"has_{feature_base}"
        val_key = f"val_{feature_base}"
        tier_key = f"tier_{feature_base}"
        if value is None:
            row[has_key] = 0
            row[val_key] = None
            row[tier_key] = None
            continue
        row[has_key] = 1
        row[val_key] = value
        row[tier_key] = 1 if feature_base != "imp_armour_pct" else None

    row["prefix_count"] = sum(
        1
        for feature_base in sql.LGBM_NEO_PREFIX_FEATURES
        if row.get(f"has_{feature_base}") == 1
    )
    row["suffix_count"] = sum(
        1
        for feature_base in sql.LGBM_NEO_SUFFIX_FEATURES
        if row.get(f"has_{feature_base}") == 1
    )
    row["explicit_count"] = row["prefix_count"] + row["suffix_count"]
    row["implicit_count"] = sum(
        1
        for feature_base in sql.LGBM_NEO_IMPLICIT_FEATURES
        if row.get(f"has_{feature_base}") == 1
    )
    return row


def test_split_benchmark_rows_is_forward_and_deterministic() -> None:
    rows = [_row(index) for index in range(12)]

    split = benchmark.split_benchmark_rows(rows)

    assert split["train"][0]["as_of_ts"] < split["validation"][0]["as_of_ts"]
    assert split["validation"][0]["as_of_ts"] < split["test"][0]["as_of_ts"]
    assert len(split["train"]) > 0
    assert len(split["validation"]) > 0
    assert len(split["test"]) > 0


def test_run_pricing_benchmark_ranks_all_candidates() -> None:
    rows = [_row(index) for index in range(12)]

    report = benchmark.run_pricing_benchmark(rows)

    expected_candidates = [
        "elasticnet_log",
        "huber_log",
        "catboost_log",
        "lightgbm_log",
        "xgboost_log",
        "quantile_regressor_log",
        "censored_quantile_log",
        "censored_forest_log",
        "knn_log",
        "stacked_ensemble_log",
    ]

    assert report["contract"]["name"] == "non_exchange_disappearance_benchmark_v1"
    assert report["contract"]["price_units"] == ["chaos", "divine"]
    assert report["split"]["kind"] == "forward"
    assert [
        spec.name for spec in benchmark.BENCHMARK_CANDIDATE_SPECS
    ] == expected_candidates
    assert len(report["ranking"]) == len(expected_candidates)
    assert {row["candidate"] for row in report["ranking"]} == set(expected_candidates)
    assert report["best_candidate"]["candidate"] in {
        spec.name for spec in benchmark.BENCHMARK_CANDIDATE_SPECS
    }
    assert (
        report["ranking"][0]["validation_mdape"]
        <= report["ranking"][-1]["validation_mdape"]
    )


def test_run_pricing_benchmark_prefers_divine_targets_when_present() -> None:
    rows = [_row(index) for index in range(12)]
    rows[0]["target_price_chaos"] = 500.0
    rows[0]["target_price_divine"] = 5.0
    rows[0]["target_fast_sale_24h_price"] = 480.0
    rows[0]["target_fast_sale_24h_price_divine"] = 4.8

    report = benchmark.run_pricing_benchmark(rows)

    assert report["contract"]["price_units"] == ["chaos", "divine"]
    assert benchmark._row_target(rows[0]) == 5.0


def test_run_mirage_iron_ring_branch_benchmark_uses_grouped_split() -> None:
    rows = [
        {**_row(index), "normalized_affix_hash": f"hash-{index}"} for index in range(12)
    ]

    report = benchmark.run_mirage_iron_ring_branch_benchmark(rows)

    assert report["split"]["kind"] == "grouped_forward"
    assert report["split"]["train_identity_count"] > 0
    assert report["split"]["validation_identity_count"] > 0
    assert report["split"]["test_identity_count"] > 0
    assert report["contract"]["split_kind"] == "grouped_forward"
    assert report["contract"]["price_units"] == ["chaos", "divine"]


def test_split_grouped_forward_benchmark_rows_by_field_groups_on_custom_key() -> None:
    rows = [
        {**_row(0), "normalized_affix_hash": "same"},
        {**_row(1), "normalized_affix_hash": "same"},
        {**_row(2), "normalized_affix_hash": "other-1"},
        {**_row(3), "normalized_affix_hash": "other-2"},
    ]

    split = benchmark.split_grouped_forward_benchmark_rows_by_field(
        rows, group_field="normalized_affix_hash"
    )

    assert len(split["train"]) > 0
    assert len(split["validation"]) > 0
    assert len(split["test"]) > 0


def test_format_benchmark_report_includes_table_and_winner() -> None:
    rows = [_row(index) for index in range(12)]
    report = benchmark.run_pricing_benchmark(rows)

    text = benchmark.format_benchmark_report(report)

    assert "# ML Pricing Benchmark Report" in text
    assert "- Price units: chaos, divine" in text
    assert "| Candidate | Val MDAPE | Test MDAPE |" in text
    assert "stacked_ensemble_log" in text
    assert report["best_candidate"]["candidate"] in text
    assert "Top single-model:" in text


def test_save_benchmark_artifacts_writes_text_report_for_txt_output(tmp_path) -> None:
    rows = [_row(index) for index in range(12)]
    output_path = tmp_path / "task-13-final-mdape-report.txt"

    artifacts = benchmark.save_benchmark_artifacts(rows, output_path)

    assert output_path.read_text(encoding="utf-8").startswith(
        "# ML Pricing Benchmark Report"
    )
    assert (tmp_path / "task-13-final-mdape-report.json").exists()
    assert (tmp_path / "task-13-final-mdape-report.txt.joblib").exists()
    assert artifacts["artifacts"]["markdown"] == str(output_path)


def test_normalize_mirage_iron_ring_branch_row_builds_sparse_mod_features() -> None:
    affix_catalog = benchmark.build_mirage_affix_catalog(
        [
            {
                "mod_text_pattern": "+({N}-{N}) to maximum Life",
                "mod_base_name": "IncreasedLife",
                "mod_max_value": 9.0,
            },
            {
                "mod_text_pattern": "+({N}-{N}) to maximum Life",
                "mod_base_name": "IncreasedLife",
                "mod_max_value": 189.0,
            },
            {
                "mod_text_pattern": "+({N}-{N})% to Fire Resistance",
                "mod_base_name": "FireResistance",
                "mod_max_value": 11.0,
            },
            {
                "mod_text_pattern": "+({N}-{N})% to Fire Resistance",
                "mod_base_name": "FireResistance",
                "mod_max_value": 48.0,
            },
        ]
    )
    row = benchmark.normalize_mirage_iron_ring_branch_row(
        {
            "as_of_ts": "2026-03-24 10:00:00.000",
            "identity_key": "item-1",
            "item_id": "item-1",
            "category": "ring",
            "item_name": "Iron Ring",
            "item_type_line": "Iron Ring",
            "base_type": "Iron Ring",
            "rarity": "Rare",
            "ilvl": 84,
            "stack_size": 1,
            "corrupted": 0,
            "fractured": 0,
            "synthesised": 0,
            "target_price_chaos": 123.0,
            "affix_count": 2,
            "affixes": [
                ("explicit", '"+84 to maximum Life"'),
                ("implicit", '"+48% to Fire Resistance"'),
            ],
            "support_count_recent": 7,
        },
        affix_catalog=affix_catalog,
    )

    assert row["target_price_chaos"] == 123.0
    assert row["target_fast_sale_24h_price"] == 116.85
    assert row["sale_confidence_flag"] == 1
    assert row["label_weight"] == 1.0
    assert row["mod_token_count"] == 2
    assert row["strategy_family"] == "sparse_retrieval"
    assert row["cohort_key"].startswith("sparse_retrieval|")
    assert "affixes" not in row
    payload = json.loads(row["mod_features_json"])
    assert "increased_life_present" in payload
    assert "increased_life_quality_roll" in payload
    assert "fire_resistance_present" in payload
    assert "fire_resistance_quality_roll" in payload
    assert payload["increased_life_present"] == 1.0
    assert payload["fire_resistance_present"] == 1.0
    assert payload["increased_life_quality_roll"] == pytest.approx(
        (84.0 - 9.0) / (189.0 - 9.0)
    )
    assert payload["fire_resistance_quality_roll"] == pytest.approx(1.0)


def test_normalize_mirage_iron_ring_branch_row_falls_back_to_target_price() -> None:
    affix_catalog = benchmark.build_mirage_affix_catalog([])
    row = benchmark.normalize_mirage_iron_ring_branch_row(
        {
            "as_of_ts": "2026-03-24 10:00:00.000",
            "identity_key": "item-2",
            "item_id": "item-2",
            "category": "ring",
            "item_name": "Iron Ring",
            "item_type_line": "Iron Ring",
            "base_type": "Iron Ring",
            "rarity": "Rare",
            "ilvl": 84,
            "stack_size": 1,
            "corrupted": 0,
            "fractured": 0,
            "synthesised": 0,
            "target_price_chaos": 77.0,
            "support_count_recent": 7,
        },
        affix_catalog=affix_catalog,
    )

    assert row["target_price_chaos"] == 77.0
    assert row["target_fast_sale_24h_price"] == pytest.approx(73.15)


def test_normalize_mirage_iron_ring_branch_row_rejects_invalid_parser_rows() -> None:
    affix_catalog = benchmark.build_mirage_affix_catalog(
        [
            {
                "mod_text_pattern": "+({N}-{N}) to Strength",
                "mod_base_name": "Shaper",
                "mod_max_value": 10.0,
            }
        ]
    )

    with pytest.raises(ValueError, match="ring parser invariant violation"):
        benchmark.normalize_mirage_iron_ring_branch_row(
            {
                "as_of_ts": "2026-03-24 10:00:00.000",
                "identity_key": "item-2",
                "item_id": "item-2",
                "category": "ring",
                "item_name": "Iron Ring",
                "item_type_line": "Iron Ring",
                "base_type": "Iron Ring",
                "rarity": "Rare",
                "ilvl": 84,
                "stack_size": 1,
                "corrupted": 0,
                "fractured": 0,
                "synthesised": 0,
                "target_price_chaos": 77.0,
                "support_count_recent": 7,
                "affixes": [("implicit", "+5 to Strength")],
            },
            affix_catalog=affix_catalog,
        )


def test_mirage_feature_projection_drops_metadata_fields() -> None:
    affix_catalog = benchmark.build_mirage_affix_catalog(
        [
            {
                "mod_text_pattern": "+({N}-{N}) to maximum Life",
                "mod_base_name": "IncreasedLife",
                "mod_max_value": 9.0,
            },
            {
                "mod_text_pattern": "+({N}-{N}) to maximum Life",
                "mod_base_name": "IncreasedLife",
                "mod_max_value": 189.0,
            },
        ]
    )
    row = benchmark.normalize_mirage_iron_ring_branch_row(
        {
            "as_of_ts": "2026-03-24 10:00:00.000",
            "identity_key": "item-3",
            "item_id": "item-3",
            "category": "ring",
            "item_name": "Iron Ring",
            "item_type_line": "Iron Ring",
            "base_type": "Iron Ring",
            "rarity": "Rare",
            "ilvl": 84,
            "stack_size": 1,
            "corrupted": 0,
            "fractured": 0,
            "synthesised": 0,
            "target_price_chaos": 123.0,
            "affix_count": 1,
            "affixes": [("explicit", '"+84 to maximum Life"')],
            "support_count_recent": 7,
        },
        affix_catalog=affix_catalog,
    )

    features = benchmark._mirage_feature_dict(row)

    assert "stack_size" not in features
    assert "route_family" not in features
    assert "strategy_family" not in features
    assert "cohort_key" not in features
    assert "parent_cohort_key" not in features
    assert "material_state_signature" not in features
    assert "item_state_key" not in features
    assert "base_identity_key" not in features
    assert "item_name" not in features
    assert "item_type_line" not in features
    assert "category" not in features
    assert "base_type" not in features
    assert "mod_token_count" not in features
    assert features["ilvl"] == 84
    assert features["corrupted"] == 0
    assert features["fractured"] == 0
    assert features["synthesised"] == 0
    assert features["support_count_recent"] == 7
    assert features["increased_life_present"] == 1.0
    assert features["increased_life_quality_roll"] == pytest.approx(
        (84.0 - 9.0) / (189.0 - 9.0)
    )


def test_run_lgbm_neo_benchmark_uses_time_split_and_categorical_columns() -> None:
    frame = pd.DataFrame([_lgbm_row(index) for index in range(12)])

    report = benchmark.run_lgbm_neo_benchmark(frame, min_rows=10)

    assert report["benchmark_number"] == 11
    assert report["benchmark"] == "lgbm_neo_benchmark_v1"
    assert report["row_count"] == 12
    assert report["split"]["kind"] == "grouped_forward"
    assert report["split"]["train_rows"] > 0
    assert report["split"]["validation_rows"] > 0
    assert report["split"]["test_rows"] > 0
    assert report["split"]["group_field"] == "item_fingerprint"
    assert report["model"]["name"] == "LGBM-neo"
    assert report["model"]["zero_as_missing"] is False
    assert report["model"]["feature_pre_filter"] is False
    assert report["model"]["min_child_samples"] == 10
    assert (
        report["contract"]["row_grain"] == "one row per item observation at observed_at"
    )
    assert report["contract"]["split_kind"] == "grouped_forward"
    assert report["contract"]["categorical_columns"] == []
    assert (
        report["validation_metrics"]["sample_count"]
        == report["split"]["validation_rows"]
    )
    assert report["test_metrics"]["sample_count"] == report["split"]["test_rows"]
    assert report["validation_metrics"]["mdape"] >= 0.0
    assert report["test_metrics"]["mdape"] >= 0.0


def test_lgbm_neo_prepare_features_keeps_variable_context_as_categorical() -> None:
    train = pd.DataFrame(
        {
            "has_exp_mana_flat": [1, 0],
            "val_exp_mana_flat": [34.0, None],
            "tier_exp_mana_flat": [1, 2],
            "league": ["Mirage", "Standard"],
            "category": ["ring", "amulet"],
            "base_type": ["Iron Ring", "Coral Ring"],
        }
    )
    valid = pd.DataFrame(
        {
            "has_exp_mana_flat": [0, 1],
            "val_exp_mana_flat": [None, 11.0],
            "tier_exp_mana_flat": [3, 4],
            "league": ["Mirage", "Standard"],
            "category": ["ring", "amulet"],
            "base_type": ["Iron Ring", "Coral Ring"],
        }
    )
    test = pd.DataFrame(
        {
            "has_exp_mana_flat": [1, 1],
            "val_exp_mana_flat": [7.0, 8.0],
            "tier_exp_mana_flat": [5, 6],
            "league": ["Mirage", "Standard"],
            "category": ["ring", "amulet"],
            "base_type": ["Iron Ring", "Coral Ring"],
        }
    )

    X_train, X_valid, X_test, categorical_columns = (
        benchmark._lgbm_neo_prepare_features(train, valid, test)
    )

    assert "tier_exp_mana_flat" not in X_train.columns
    assert "tier_exp_mana_flat" not in X_valid.columns
    assert "tier_exp_mana_flat" not in X_test.columns
    assert categorical_columns == ["league", "category", "base_type"]
    assert str(X_train["league"].dtype) == "category"
    assert str(X_valid["category"].dtype) == "category"
    assert str(X_test["base_type"].dtype) == "category"


def _family_report(family: str, offset: float) -> dict[str, object]:
    ranking = []
    for index, spec in enumerate(benchmark.BENCHMARK_CANDIDATE_SPECS):
        ranking.append(
            {
                "candidate": spec.name,
                "validation_mdape": round(offset + (index * 0.01), 4),
                "test_mdape": round(offset + (index * 0.015), 4),
                "validation_wape": round(offset + (index * 0.02), 4),
                "test_wape": round(offset + (index * 0.025), 4),
                "validation_interval_80_coverage": round(0.7 - (index * 0.01), 4),
                "test_interval_80_coverage": round(0.65 - (index * 0.01), 4),
            }
        )
    return {
        "contract": {
            "name": "non_exchange_disappearance_benchmark_v1",
            "price_units": ["chaos", "divine"],
        },
        "split": {"kind": "forward"},
        "ranking": ranking,
        "best_candidate": ranking[0],
        "candidate_results": [],
        "family": family,
    }


def test_build_item_family_benchmark_report_combines_all_families() -> None:
    family_reports = {
        "flask": _family_report("flask", 0.10),
        "map": _family_report("map", 0.20),
        "cluster_jewel": _family_report("cluster_jewel", 0.30),
        "boots": _family_report("boots", 0.40),
    }

    report = benchmark.build_item_family_benchmark_report(
        family_reports,
        league="Mirage",
        as_of_ts="2026-03-24 10:00:00",
        sample_size=10_000,
    )
    text = benchmark.format_item_family_benchmark_report(report)

    assert report["benchmark"] == "item_family_pricing_benchmark_v1"
    assert report["row_count"] == 40
    assert report["families"] == ["flask", "map", "cluster_jewel", "boots"]
    assert len(report["rows"]) == 40
    assert sum(1 for row in report["rows"] if row["is_family_winner"]) == 4
    assert report["family_winners"]["boots"]["candidate"] == "elasticnet_log"
    assert "# ML Item Family Benchmark Report" in text
    assert "| Family | Candidate | Val MDAPE | Test MDAPE |" in text
    assert "Family winners:" in text


def test_save_item_family_benchmark_artifacts_writes_report_bundle(
    tmp_path: Path,
) -> None:
    family_reports = {
        "flask": _family_report("flask", 0.10),
        "map": _family_report("map", 0.20),
        "cluster_jewel": _family_report("cluster_jewel", 0.30),
        "boots": _family_report("boots", 0.40),
    }
    report = benchmark.build_item_family_benchmark_report(
        family_reports,
        league="Mirage",
        as_of_ts="2026-03-24 10:00:00",
        sample_size=10_000,
    )
    output_path = tmp_path / "benchmark-item-families.txt"

    artifacts = benchmark.save_item_family_benchmark_artifacts(report, output_path)

    assert output_path.exists()
    assert (tmp_path / "benchmark-item-families.json").exists()
    assert (tmp_path / "benchmark-item-families.txt.joblib").exists()
    assert artifacts["artifacts"]["markdown"] == str(output_path)


def test_build_item_family_benchmark_report_rejects_missing_family() -> None:
    with pytest.raises(ValueError, match="missing family benchmark results"):
        benchmark.build_item_family_benchmark_report(
            {"flask": _family_report("flask", 0.10)},
            league="Mirage",
            as_of_ts="2026-03-24 10:00:00",
        )
