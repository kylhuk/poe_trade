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
