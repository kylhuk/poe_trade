from __future__ import annotations

from typing import cast

import pytest

from poe_trade.ml import workflows


@pytest.mark.parametrize(
    ("item_class", "base_type", "expected"),
    [
        ("Jewels", "Crimson Jewel", "jewel"),
        ("Abyss Jewels", "Searching Eye Jewel", "jewel"),
        ("Rings", "Two-Stone Ring", "ring"),
        ("Amulets", "Onyx Amulet", "amulet"),
        ("Belts", "Leather Belt", "belt"),
        ("Maps", "Cemetery Map", "map"),
    ],
)
def test_derive_category_splits_dominant_other_families(
    item_class: str, base_type: str, expected: str
) -> None:
    assert (
        workflows._derive_category(
            "other",
            item_class=item_class,
            base_type=base_type,
            item_type_line=base_type,
        )
        == expected
    )


def test_derive_category_keeps_cluster_jewel_specificity() -> None:
    assert (
        workflows._derive_category(
            "other",
            item_class="Jewels",
            base_type="Large Cluster Jewel",
            item_type_line="Large Cluster Jewel",
        )
        == "cluster_jewel"
    )


def test_parse_clipboard_item_uses_derived_category_for_jewel_family() -> None:
    parsed = workflows._parse_clipboard_item(
        "\n".join(
            [
                "Item Class: Jewels",
                "Rarity: Magic",
                "Crimson Jewel",
                "--------",
                "Item Level: 84",
            ]
        )
    )

    assert parsed["category"] == "jewel"


def test_build_dataset_uses_derived_category_sql(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executed_queries: list[str] = []

    class StubClient:
        def execute(self, query: str, settings=None) -> str:
            del settings
            executed_queries.append(query)
            return ""

    client = cast(workflows.ClickHouseClient, cast(object, StubClient()))

    monkeypatch.setattr(workflows, "_ensure_supported_league", lambda _league: None)
    monkeypatch.setattr(workflows, "_ensure_dataset_table", lambda *_args: None)
    monkeypatch.setattr(workflows, "_ensure_mod_tables", lambda *_args: None)
    monkeypatch.setattr(
        workflows, "_ensure_route_candidates_table", lambda *_args: None
    )
    monkeypatch.setattr(workflows, "_ensure_no_leakage_audit", lambda *_args: None)
    monkeypatch.setattr(workflows, "_write_leakage_audit", lambda *_args: None)
    monkeypatch.setattr(
        workflows,
        "_env_bool",
        lambda key, default: (
            False if key == "POE_ML_DATASET_CHUNK_BY_HOUR" else default
        ),
    )
    monkeypatch.setattr(
        workflows,
        "_populate_item_mod_features_from_tokens",
        lambda *_args, **_kwargs: {"rows_written": 0, "non_empty_rows": 0},
    )
    monkeypatch.setattr(workflows, "_scalar_count", lambda *_args, **_kwargs: 0)

    workflows.build_dataset(
        client,
        league="Mirage",
        as_of_ts="2026-03-10T12:00:00Z",
        output_table="poe_trade.ml_price_dataset_v1",
    )

    dataset_queries = [
        query
        for query in executed_queries
        if "INSERT INTO poe_trade.ml_price_dataset_v1" in query
    ]
    assert dataset_queries
    assert " AS category," in dataset_queries[0]
    assert "AS category, labels.normalized_price_chaos" in dataset_queries[0]
    assert "'jewel'" in dataset_queries[0]
    assert "'ring'" in dataset_queries[0]
    assert "'amulet'" in dataset_queries[0]
    assert "'belt'" in dataset_queries[0]
    assert "'map'" in dataset_queries[0]


@pytest.mark.parametrize(
    ("raw_category", "expected"),
    [
        ("jewel", "other"),
        ("ring", "other"),
        ("amulet", "other"),
        ("belt", "other"),
        ("cluster_jewel", "cluster_jewel"),
        ("map", "map"),
        ("other", "other"),
    ],
)
def test_canonical_model_category_soft_reverts_split_families(
    raw_category: str, expected: str
) -> None:
    assert workflows._canonical_model_category(raw_category) == expected


def test_feature_dict_from_row_uses_canonical_model_category() -> None:
    row = {
        "category": "jewel",
        "base_type": "Crimson Jewel",
        "rarity": "Rare",
        "ilvl": 84,
        "stack_size": 1,
        "corrupted": 0,
        "fractured": 0,
        "synthesised": 0,
        "mod_token_count": 4,
        "mod_features_json": "{}",
    }
    features = workflows._feature_dict_from_row(row)
    assert features["category"] == "other"


def test_feature_dict_from_row_keeps_split_family_for_structured_boosted() -> None:
    row = {
        "category": "ring",
        "base_type": "Two-Stone Ring",
        "rarity": "Unique",
        "ilvl": 84,
        "stack_size": 1,
        "corrupted": 0,
        "fractured": 0,
        "synthesised": 0,
        "mod_token_count": 4,
        "mod_features_json": "{}",
    }

    features = workflows._feature_dict_from_row(row, route="structured_boosted")

    assert features["category"] == "ring"


def test_feature_dict_from_parsed_item_keeps_split_family_for_structured_boosted() -> (
    None
):
    parsed_item = {
        "category": "amulet",
        "base_type": "Onyx Amulet",
        "rarity": "Unique",
        "ilvl": 84,
        "stack_size": 1,
        "corrupted": 0,
        "fractured": 0,
        "synthesised": 0,
        "mod_token_count": 4,
        "mod_features_json": "{}",
    }

    features = workflows._feature_dict_from_parsed_item(
        parsed_item,
        route="structured_boosted",
    )

    assert features["category"] == "amulet"


def test_feature_dict_from_row_adds_map_text_and_unique_state_interactions() -> None:
    row = {
        "category": "map",
        "base_type": "Blight-Ravaged Constrictor Map T17",
        "item_type_line": "Blight-Ravaged Constrictor Map (T17)",
        "item_name": "Elder Echo",
        "rarity": "Unique",
        "ilvl": 84,
        "stack_size": 1,
        "corrupted": 1,
        "fractured": 1,
        "synthesised": 1,
        "mod_token_count": 4,
        "mod_features_json": "{}",
    }

    features = workflows._feature_dict_from_row(row, route="structured_boosted")

    assert features["map_family_flag"] == 1.0
    assert features["map_blighted_flag"] == 1.0
    assert features["map_blight_ravaged_flag"] == 1.0
    assert features["map_elder_guardian_flag"] == 1.0
    assert features["map_t17_flag"] == 1.0
    assert features["unique_state_pair_count"] == 3.0
    assert features["unique_state_all_three_flag"] == 1.0
    assert features["text_has_influence_flag"] == 1.0
    assert features["text_has_parentheses_flag"] == 1.0
    assert features["text_has_hyphen_flag"] == 1.0


def test_feature_dict_from_parsed_item_adds_family_scope_for_structured_routes() -> (
    None
):
    parsed_item = {
        "category": "other",
        "base_type": "Onyx Amulet",
        "item_type_line": "Onyx Amulet",
        "rarity": "Unique",
        "ilvl": 84,
        "stack_size": 1,
        "corrupted": 0,
        "fractured": 0,
        "synthesised": 0,
        "mod_token_count": 4,
        "mod_features_json": "{}",
    }

    features = workflows._feature_dict_from_parsed_item(
        parsed_item,
        route="structured_boosted",
    )

    assert features["family_scope"] == "amulet"
    assert features["family_scope_is_other"] == 0.0


def test_dataset_rebuild_window_is_stable_for_unchanged_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class StubClient:
        def execute(self, query: str, settings=None) -> str:
            del query, settings
            return ""

    client = cast(workflows.ClickHouseClient, cast(object, StubClient()))

    label_row = {
        "row_count": 200,
        "min_as_of_ts": "2026-03-10 00:00:00",
        "max_as_of_ts": "2026-03-10 01:00:00",
        "digest_sum": "111",
        "digest_max": "222",
    }
    trade_row = {
        "row_count": 20,
        "max_retrieved_at": "2026-03-10 01:30:00",
    }

    def _fake_query_rows(_client, query: str):
        if "FROM poe_trade.ml_price_labels_v2" in query:
            return [dict(label_row)]
        if "FROM poe_trade.bronze_trade_metadata" in query:
            return [dict(trade_row)]
        return []

    monkeypatch.setattr(workflows, "_ensure_supported_league", lambda _league: None)
    monkeypatch.setattr(
        workflows,
        "_ensure_price_labels_table",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(workflows, "_query_rows", _fake_query_rows)

    first = workflows.dataset_rebuild_window(client, league="Mirage")
    second = workflows.dataset_rebuild_window(client, league="Mirage")

    assert first["window_id"] == second["window_id"]
    assert first["label_rows"] == 200
    assert first["trade_metadata_rows"] == 20


def test_dataset_rebuild_window_changes_when_snapshot_digest_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class StubClient:
        def execute(self, query: str, settings=None) -> str:
            del query, settings
            return ""

    client = cast(workflows.ClickHouseClient, cast(object, StubClient()))

    label_row = {
        "row_count": 200,
        "min_as_of_ts": "2026-03-10 00:00:00",
        "max_as_of_ts": "2026-03-10 01:00:00",
        "digest_sum": "111",
        "digest_max": "222",
    }
    trade_row = {
        "row_count": 20,
        "max_retrieved_at": "2026-03-10 01:30:00",
    }

    def _fake_query_rows(_client, query: str):
        if "FROM poe_trade.ml_price_labels_v2" in query:
            return [dict(label_row)]
        if "FROM poe_trade.bronze_trade_metadata" in query:
            return [dict(trade_row)]
        return []

    monkeypatch.setattr(workflows, "_ensure_supported_league", lambda _league: None)
    monkeypatch.setattr(
        workflows,
        "_ensure_price_labels_table",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(workflows, "_query_rows", _fake_query_rows)

    before = workflows.dataset_rebuild_window(client, league="Mirage")
    label_row["digest_sum"] = "999"
    after = workflows.dataset_rebuild_window(client, league="Mirage")

    assert before["window_id"] != after["window_id"]


def test_route_slice_id_changes_when_holdout_content_changes() -> None:
    rows_a = [
        {
            "as_of_ts": "2026-03-10 00:00:00",
            "category": "map",
            "base_type": "Cemetery Map",
            "rarity": "Rare",
            "ilvl": 80,
            "stack_size": 1,
            "corrupted": 0,
            "fractured": 0,
            "synthesised": 0,
            "mod_token_count": 2,
            "normalized_price_chaos": 10.0,
            "sale_probability_label": 0.5,
        },
        {
            "as_of_ts": "2026-03-10 01:00:00",
            "category": "map",
            "base_type": "Cemetery Map",
            "rarity": "Rare",
            "ilvl": 80,
            "stack_size": 1,
            "corrupted": 0,
            "fractured": 0,
            "synthesised": 0,
            "mod_token_count": 2,
            "normalized_price_chaos": 11.0,
            "sale_probability_label": 0.5,
        },
    ]
    rows_b = [dict(row) for row in rows_a]
    rows_b[1]["normalized_price_chaos"] = 99.0

    slice_a = workflows._route_slice_id("structured_boosted", rows_a)
    slice_b = workflows._route_slice_id("structured_boosted", rows_b)

    assert slice_a != slice_b


def test_sparse_route_training_predicate_excludes_fungible_families() -> None:
    predicate = workflows._route_training_predicate("sparse_retrieval")

    assert "rarity = 'Rare'" in predicate
    assert "cluster_jewel" in predicate
    assert (
        "category NOT IN ('fossil', 'scarab', 'logbook', 'cluster_jewel', 'map')"
        in predicate
    )


def test_route_for_item_assigns_rare_maps_to_guardrailed_fallback() -> None:
    routed = workflows._route_for_item(
        {
            "category": "map",
            "rarity": "Rare",
        }
    )

    assert routed["route"] == "fallback_abstain"
    assert routed["route_reason"] == "map_sparse_guardrail"


def test_cluster_jewel_route_training_predicate_targets_cluster_jewel_only() -> None:
    predicate = workflows._route_training_predicate("cluster_jewel_retrieval")

    assert predicate == "category = 'cluster_jewel'"


def test_fungible_route_training_predicate_excludes_maps() -> None:
    predicate = workflows._route_training_predicate("fungible_reference")

    assert predicate == "category IN ('fossil', 'scarab', 'logbook')"


def test_route_for_item_assigns_fungible_family_specific_reason() -> None:
    routed = workflows._route_for_item(
        {
            "category": "scarab",
            "rarity": "",
        }
    )

    assert routed["route"] == "fungible_reference"
    assert routed["route_reason"] == "stackable_scarab_family"


def test_fungible_route_uses_family_scoped_objective() -> None:
    assert (
        workflows._route_objective("fungible_reference")
        == "reference_quantiles_family_scoped"
    )


def test_fit_route_bundle_from_aggregates_splits_fungible_family_scopes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_categories: list[set[str]] = []

    def _fake_fit_single(usable_rows, *, route, trained_at):
        del trained_at
        captured_categories.append(
            {str(row.get("category") or "") for row in usable_rows}
        )
        train_row_count = sum(int(row.get("sample_count") or 0) for row in usable_rows)
        if not usable_rows:
            return None, {
                "train_row_count": 0,
                "feature_row_count": 0,
                "support_reference_p50": 0.0,
                "sale_model_available": False,
                "model_backend": "heuristic_fallback",
            }
        return {
            "route": route,
            "vectorizer": object(),
            "price_models": {"p10": object(), "p50": object(), "p90": object()},
            "sale_model": None,
        }, {
            "train_row_count": train_row_count,
            "feature_row_count": len(usable_rows),
            "support_reference_p50": 10.0,
            "sale_model_available": False,
            "model_backend": "sklearn_gradient_boosting",
        }

    monkeypatch.setattr(
        workflows,
        "_fit_single_route_bundle_from_usable_rows",
        _fake_fit_single,
    )

    aggregate_rows = [
        {"category": "fossil", "target_p50": 10.0, "sample_count": 30},
        {"category": "scarab", "target_p50": 11.0, "sample_count": 30},
        {"category": "logbook", "target_p50": 12.0, "sample_count": 30},
    ]

    bundle, stats = workflows._fit_route_bundle_from_aggregates(
        aggregate_rows,
        route="fungible_reference",
        trained_at="2026-03-20 00:00:00.000",
    )

    assert bundle is not None
    assert set(bundle["family_scoped_bundles"]) == {"fossil", "scarab", "logbook"}
    assert {frozenset(categories) for categories in captured_categories} == {
        frozenset({"fossil"}),
        frozenset({"scarab"}),
        frozenset({"logbook"}),
    }
    assert stats["model_backend"] == "sklearn_gradient_boosting_family_scoped"


def test_fit_route_bundle_from_aggregates_splits_structured_other_family_scopes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_categories: list[set[str]] = []

    def _fake_fit_single(usable_rows, *, route, trained_at):
        del trained_at
        captured_categories.append(
            {str(row.get("category") or "") for row in usable_rows}
        )
        train_row_count = sum(int(row.get("sample_count") or 0) for row in usable_rows)
        if not usable_rows:
            return None, {
                "train_row_count": 0,
                "feature_row_count": 0,
                "support_reference_p50": 0.0,
                "sale_model_available": False,
                "model_backend": "heuristic_fallback",
            }
        return {
            "route": route,
            "vectorizer": object(),
            "price_models": {"p10": object(), "p50": object(), "p90": object()},
            "sale_model": None,
        }, {
            "train_row_count": train_row_count,
            "feature_row_count": len(usable_rows),
            "support_reference_p50": 10.0,
            "sale_model_available": False,
            "model_backend": "sklearn_gradient_boosting",
        }

    monkeypatch.setattr(
        workflows,
        "_fit_single_route_bundle_from_usable_rows",
        _fake_fit_single,
    )

    aggregate_rows = [
        {"category": "ring", "target_p50": 10.0, "sample_count": 30},
        {"category": "amulet", "target_p50": 11.0, "sample_count": 30},
        {"category": "belt", "target_p50": 12.0, "sample_count": 30},
        {"category": "jewel", "target_p50": 13.0, "sample_count": 30},
    ]

    bundle, stats = workflows._fit_route_bundle_from_aggregates(
        aggregate_rows,
        route="structured_boosted_other",
        trained_at="2026-03-20 00:00:00.000",
    )

    assert bundle is not None
    assert set(bundle["family_scoped_bundles"]) == {"ring", "amulet", "belt", "jewel"}
    assert {frozenset(categories) for categories in captured_categories} == {
        frozenset({"ring"}),
        frozenset({"amulet"}),
        frozenset({"belt"}),
        frozenset({"jewel"}),
    }
    assert stats["model_backend"] == "sklearn_gradient_boosting_family_scoped"


def test_predict_with_bundle_uses_fungible_family_scope_model() -> None:
    class _DummyVectorizer:
        def transform(self, _rows):
            return [[1.0]]

    class _DummyModel:
        def __init__(self, value: float) -> None:
            self._value = value

        def predict(self, _X):
            return [self._value]

    def _scope_bundle(base: float) -> dict[str, object]:
        return {
            "route": "fungible_reference",
            "vectorizer": _DummyVectorizer(),
            "price_models": {
                "p10": _DummyModel(base - 1.0),
                "p50": _DummyModel(base),
                "p90": _DummyModel(base + 1.0),
            },
            "sale_model": _DummyModel(0.6),
            "price_tiers": {},
        }

    bundle = {
        "route": "fungible_reference",
        "family_scoped_bundles": {
            "fossil": _scope_bundle(20.0),
            "scarab": _scope_bundle(50.0),
            "logbook": _scope_bundle(80.0),
        },
    }
    predicted = workflows._predict_with_bundle(
        bundle=bundle,
        parsed_item={
            "category": "scarab",
            "base_type": "Winged Scarab",
            "rarity": "",
            "ilvl": 0,
            "stack_size": 1,
            "corrupted": 0,
            "fractured": 0,
            "synthesised": 0,
            "mod_token_count": 0,
            "mod_features_json": "{}",
        },
    )

    assert predicted is not None
    assert predicted["price_p50"] == 50.0


def test_predict_with_bundle_uses_structured_other_family_scope_model() -> None:
    class _DummyVectorizer:
        def transform(self, _rows):
            return [[1.0]]

    class _DummyModel:
        def __init__(self, value: float) -> None:
            self._value = value

        def predict(self, _X):
            return [self._value]

    def _scope_bundle(base: float) -> dict[str, object]:
        return {
            "route": "structured_boosted_other",
            "vectorizer": _DummyVectorizer(),
            "price_models": {
                "p10": _DummyModel(base - 1.0),
                "p50": _DummyModel(base),
                "p90": _DummyModel(base + 1.0),
            },
            "sale_model": _DummyModel(0.6),
            "price_tiers": {},
        }

    bundle = {
        "route": "structured_boosted_other",
        "family_scoped_bundles": {
            "ring": _scope_bundle(20.0),
            "amulet": _scope_bundle(50.0),
            "belt": _scope_bundle(80.0),
            "jewel": _scope_bundle(100.0),
        },
    }
    predicted = workflows._predict_with_bundle(
        bundle=bundle,
        parsed_item={
            "category": "other",
            "base_type": "Onyx Amulet",
            "item_type_line": "Onyx Amulet",
            "rarity": "Unique",
            "ilvl": 0,
            "stack_size": 1,
            "corrupted": 0,
            "fractured": 0,
            "synthesised": 0,
            "mod_token_count": 0,
            "mod_features_json": "{}",
        },
    )

    assert predicted is not None
    assert predicted["price_p50"] == 50.0


def test_route_for_item_assigns_essence_to_fallback_due_to_noise() -> None:
    routed = workflows._route_for_item(
        {
            "category": "essence",
            "rarity": "",
        }
    )

    assert routed["route"] == "fallback_abstain"
    assert routed["route_reason"] == "noisy_essence_family"


def test_route_for_item_assigns_unique_ring_to_structured_boosted_other() -> None:
    routed = workflows._route_for_item(
        {
            "category": "ring",
            "rarity": "Unique",
            "support_count_recent": 120,
        }
    )

    assert routed["route"] == "structured_boosted_other"
    assert routed["route_reason"] == "specialized_ring_unique_family"


def test_route_for_item_assigns_unique_onyx_amulet_to_structured_boosted_other() -> (
    None
):
    routed = workflows._route_for_item(
        {
            "category": "other",
            "base_type": "Onyx Amulet",
            "rarity": "Unique",
            "support_count_recent": 120,
        }
    )

    assert routed["route"] == "structured_boosted_other"
    assert routed["route_reason"] == "specialized_amulet_unique_family"


def test_route_for_item_assigns_cluster_jewel_dedicated_route() -> None:
    routed = workflows._route_for_item(
        {
            "category": "cluster_jewel",
            "rarity": "Rare",
        }
    )

    assert routed["route"] == "cluster_jewel_retrieval"
    assert routed["route_reason"] == "cluster_jewel_specialized"


def test_structured_boosted_training_predicate_excludes_split_other_families() -> None:
    predicate = workflows._route_training_predicate("structured_boosted")

    assert "rarity = 'Unique'" in predicate
    assert "= 'other'" in predicate


def test_structured_boosted_other_training_predicate_targets_split_other_families() -> (
    None
):
    predicate = workflows._route_training_predicate("structured_boosted_other")

    assert "rarity = 'Unique'" in predicate
    assert "!= 'other'" in predicate


def test_prediction_records_canonicalize_split_family_labels() -> None:
    rows = [
        {
            "category": "ring",
            "family": "ring",
            "normalized_price_chaos": 10.0,
        },
        {
            "category": "cluster_jewel",
            "family": "cluster_jewel",
            "normalized_price_chaos": 20.0,
        },
    ]

    records = workflows._prediction_records_from_rows(
        rows,
        bundle=None,
        reference_price=5.0,
    )

    assert records[0]["family"] == "other"
    assert records[1]["family"] == "cluster_jewel"


def test_prediction_records_keep_structured_other_family_labels() -> None:
    rows = [
        {
            "category": "other",
            "base_type": "Two-Stone Ring",
            "item_type_line": "Two-Stone Ring",
            "family": "ring",
            "normalized_price_chaos": 10.0,
        },
        {
            "category": "other",
            "base_type": "Onyx Amulet",
            "item_type_line": "Onyx Amulet",
            "family": "amulet",
            "normalized_price_chaos": 20.0,
        },
    ]

    records = workflows._prediction_records_from_rows(
        rows,
        bundle=None,
        reference_price=5.0,
        route="structured_boosted_other",
    )

    assert records[0]["family"] == "ring"
    assert records[1]["family"] == "amulet"


def test_training_aggregate_rows_selects_route_family_scope_sql(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = {"query": ""}

    def _fake_query_rows(_client, query: str):
        captured["query"] = query
        return []

    monkeypatch.setattr(workflows, "_query_rows", _fake_query_rows)

    workflows._training_aggregate_rows(
        cast(workflows.ClickHouseClient, cast(object, object())),
        route="structured_boosted_other",
        league="Mirage",
        dataset_table="poe_trade.ml_price_dataset_v2",
    )

    assert " AS family" in captured["query"]
    assert " AS item_type_line," in captured["query"]
    assert "match(lowerUTF8(concat" in captured["query"]
    assert "GROUP BY" in captured["query"]
    assert "item_type_line" in captured["query"]
    assert ", family" in captured["query"]


def test_evaluation_rows_selects_route_family_scope_sql(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = {"query": ""}

    def _fake_query_rows(_client, query: str):
        captured["query"] = query
        return []

    monkeypatch.setattr(workflows, "_query_rows", _fake_query_rows)

    workflows._evaluation_rows(
        cast(workflows.ClickHouseClient, cast(object, object())),
        route="structured_boosted_other",
        league="Mirage",
        dataset_table="poe_trade.ml_price_dataset_v2",
        limit=100,
    )

    assert " AS family" in captured["query"]
    assert " AS item_type_line," in captured["query"]
    assert "match(lowerUTF8(concat" in captured["query"]
