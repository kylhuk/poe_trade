from __future__ import annotations

from poe_trade.ml.v3 import features


def test_canonicalize_mod_features_json_filters_invalid_values() -> None:
    payload = features.canonicalize_mod_features_json(
        '{"MaximumLife_tier":8,"bad":"x","":4,"AttackSpeed_roll":0.42}'
    )

    assert payload == {
        "MaximumLife_tier": 8.0,
        "AttackSpeed_roll": 0.42,
    }


def test_build_feature_row_includes_base_fields_and_mods() -> None:
    row = features.build_feature_row(
        {
            "category": "helmet",
            "base_type": "Hubris Circlet",
            "rarity": "Rare",
            "ilvl": 86,
            "stack_size": 1,
            "corrupted": 0,
            "fractured": 1,
            "synthesised": 0,
            "mod_token_count": 2,
            "mod_features_json": '{"MaximumLife_tier":8}',
        }
    )

    assert row["category"] == "helmet"
    assert row["base_type"] == "Hubris Circlet"
    assert row["MaximumLife_tier"] == 8.0


def test_feature_schema_has_deterministic_fingerprint() -> None:
    one = features.feature_schema({"b": 1, "a": 2})
    two = features.feature_schema({"a": 9, "b": 0})

    assert one["version"] == "v3"
    assert one["fields"] == ["a", "b"]
    assert one["fingerprint"] == two["fingerprint"]


def test_build_feature_row_emits_item_state_key() -> None:
    row = features.build_feature_row(
        {
            "category": "helmet",
            "base_type": "Hubris Circlet",
            "rarity": "Rare",
            "corrupted": 1,
            "fractured": 0,
            "synthesised": 0,
            "mod_features_json": '{"explicit.life":1}',
        }
    )

    assert row["item_state_key"] == "rare|corrupted=1|fractured=0|synthesised=0"


def test_build_feature_row_emits_route_family_and_base_identity_key() -> None:
    one = features.build_feature_row(
        {
            "category": "helmet",
            "base_type": "Hubris Circlet",
            "rarity": "Rare",
            "corrupted": 1,
            "fractured": 0,
            "synthesised": 0,
            "mod_features_json": "{}",
        }
    )
    two = features.build_feature_row(
        {
            "category": "helmet",
            "base_type": "Hubris Circlet",
            "rarity": "Rare",
            "corrupted": 1,
            "fractured": 0,
            "synthesised": 0,
            "mod_features_json": "{}",
        }
    )

    assert one["route_family"] == "sparse_retrieval"
    assert one["base_identity_key"] == (
        "hubris circlet|rare|corrupted=1|fractured=0|synthesised=0"
    )
    assert two["base_identity_key"] == one["base_identity_key"]


def test_build_feature_row_base_identity_changes_for_identity_inputs() -> None:
    base = features.build_feature_row(
        {
            "category": "helmet",
            "base_type": "Hubris Circlet",
            "rarity": "Rare",
            "corrupted": 0,
            "fractured": 0,
            "synthesised": 0,
        }
    )
    changed_base_type = features.build_feature_row(
        {
            "category": "helmet",
            "base_type": "Lion Pelt",
            "rarity": "Rare",
            "corrupted": 0,
            "fractured": 0,
            "synthesised": 0,
        }
    )
    changed_state = features.build_feature_row(
        {
            "category": "helmet",
            "base_type": "Hubris Circlet",
            "rarity": "Rare",
            "corrupted": 1,
            "fractured": 0,
            "synthesised": 0,
        }
    )

    assert changed_base_type["base_identity_key"] != base["base_identity_key"]
    assert changed_state["base_identity_key"] != base["base_identity_key"]


def test_build_feature_row_route_family_changes_for_route_inputs() -> None:
    rare_helmet = features.build_feature_row(
        {
            "category": "helmet",
            "rarity": "Rare",
        }
    )
    unique_helmet = features.build_feature_row(
        {
            "category": "helmet",
            "rarity": "Unique",
        }
    )
    rare_cluster = features.build_feature_row(
        {
            "category": "cluster_jewel",
            "rarity": "Rare",
        }
    )

    assert rare_helmet["route_family"] == "sparse_retrieval"
    assert unique_helmet["route_family"] == "structured_boosted"
    assert rare_cluster["route_family"] == "cluster_jewel_retrieval"
    assert unique_helmet["route_family"] != rare_helmet["route_family"]
    assert rare_cluster["route_family"] != rare_helmet["route_family"]


def test_build_feature_row_handles_stringish_numeric_and_flag_inputs() -> None:
    row = features.build_feature_row(
        {
            "category": "helmet",
            "base_type": "Hubris Circlet",
            "rarity": "Rare",
            "ilvl": "86",
            "stack_size": "2",
            "corrupted": "true",
            "fractured": "0",
            "synthesised": "False",
            "mod_token_count": "3",
        }
    )

    assert row["ilvl"] == 86
    assert row["stack_size"] == 2
    assert row["corrupted"] == 1
    assert row["fractured"] == 0
    assert row["synthesised"] == 0
    assert row["mod_token_count"] == 3


def test_build_feature_row_defaults_on_unparseable_stringish_numeric_inputs() -> None:
    row = features.build_feature_row(
        {
            "ilvl": "oops",
            "stack_size": "",
            "corrupted": "nope",
            "fractured": "n/a",
            "synthesised": None,
            "mod_token_count": "x",
        }
    )

    assert row["ilvl"] == 0
    assert row["stack_size"] == 1
    assert row["corrupted"] == 0
    assert row["fractured"] == 0
    assert row["synthesised"] == 0
    assert row["mod_token_count"] == 0


def test_build_feature_row_defaults_on_overflow_stringish_numeric_inputs() -> None:
    row = features.build_feature_row(
        {
            "ilvl": "inf",
            "stack_size": "1e309",
        }
    )

    assert row["ilvl"] == 0
    assert row["stack_size"] == 1
