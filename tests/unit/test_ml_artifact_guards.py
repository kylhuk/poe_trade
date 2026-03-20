from __future__ import annotations

import json

import joblib
from types import SimpleNamespace

from poe_trade.ml import workflows


def test_validate_route_artifact_requires_bundle_path(tmp_path) -> None:
    model_dir = tmp_path / "artifacts" / "ml" / "mirage_v2"
    model_dir.mkdir(parents=True)
    artifact_path = model_dir / "structured_boosted-Mirage.json"
    artifact_path.write_text(
        json.dumps({"route": "structured_boosted", "model_bundle_path": None}),
        encoding="utf-8",
    )

    result = workflows._validate_route_artifact(
        model_dir=str(model_dir),
        route="structured_boosted",
        league="Mirage",
    )

    assert result["valid"] is False
    assert result["reason"] == "bundle_path_missing"


def test_validate_route_artifact_accepts_existing_bundle(tmp_path) -> None:
    model_dir = tmp_path / "artifacts" / "ml" / "mirage_v2"
    model_dir.mkdir(parents=True)
    bundle_path = model_dir / "structured_boosted-Mirage.joblib"
    joblib.dump(
        {"route": "structured_boosted", "price_models": {}},
        bundle_path,
    )
    artifact_path = model_dir / "structured_boosted-Mirage.json"
    artifact_path.write_text(
        json.dumps(
            {
                "route": "structured_boosted",
                "model_bundle_path": str(bundle_path),
                "train_row_count": 10,
            }
        ),
        encoding="utf-8",
    )

    result = workflows._validate_route_artifact(
        model_dir=str(model_dir),
        route="structured_boosted",
        league="Mirage",
    )

    assert result["valid"] is True
    assert result["reason"] == "validated"


def test_route_for_item_uses_real_support_for_uniques() -> None:
    low_support = workflows._route_for_item(
        {
            "category": "helmet",
            "rarity": "Unique",
            "base_type": "Hubris Circlet",
            "item_type_line": "Hubris Circlet",
            "support_count_recent": 10,
        }
    )
    high_support = workflows._route_for_item(
        {
            "category": "helmet",
            "rarity": "Unique",
            "base_type": "Hubris Circlet",
            "item_type_line": "Hubris Circlet",
            "support_count_recent": 80,
        }
    )

    assert low_support["route"] == "fallback_abstain"
    assert low_support["route_reason"] == "fallback_due_to_support"
    assert high_support["route"] == "structured_boosted"


def test_promote_models_only_writes_selected_routes(monkeypatch) -> None:
    inserted: list[dict[str, object]] = []
    monkeypatch.setattr(
        workflows,
        "_insert_json_rows",
        lambda _client, _table, rows: inserted.extend(rows),
    )
    monkeypatch.setattr(
        workflows,
        "rollout_model_versions",
        lambda _client, *, league: {
            "candidate_model_version": f"{league.lower()}-candidate",
            "incumbent_model_version": f"{league.lower()}-incumbent",
        },
    )
    monkeypatch.setattr(workflows, "warmup_active_models", lambda *_args, **_kwargs: {})

    workflows._promote_models(
        object(),
        league="Mirage",
        model_dir="artifacts/ml/mirage_v2",
        model_version="mirage-v2-123",
        routes=["structured_boosted", "fungible_reference"],
    )

    assert [row["route"] for row in inserted] == [
        "structured_boosted",
        "fungible_reference",
    ]


def test_fallback_abstain_does_not_require_bundle() -> None:
    assert workflows._route_requires_bundle("fallback_abstain") is False
    assert workflows._route_requires_bundle("structured_boosted") is True


def test_predict_one_keeps_deterministic_fallback_route(monkeypatch) -> None:
    monkeypatch.setattr(
        workflows,
        "_parse_clipboard_item",
        lambda _text: {
            "category": "map",
            "base_type": "Mesa Map",
            "rarity": "Normal",
            "item_type_line": "Mesa Map",
        },
    )
    monkeypatch.setattr(
        workflows,
        "_serving_profile_lookup",
        lambda *_args, **_kwargs: {
            "hit": True,
            "support_count_recent": 10,
            "reference_price": 5.0,
        },
    )
    monkeypatch.setattr(
        workflows, "_load_active_route_artifact", lambda *_args, **_kwargs: {}
    )
    monkeypatch.setattr(
        workflows, "_safe_incumbent_model_version", lambda *_args, **_kwargs: ""
    )

    result = workflows.predict_one(
        SimpleNamespace(),
        league="Mirage",
        clipboard_text="ignored",
    )

    assert result["route"] == "fallback_abstain"
    assert result["fallback_reason"] == "deterministic_fallback_route"
    assert result["price_p50"] == 5.0
