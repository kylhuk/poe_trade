from __future__ import annotations

import json

from poe_trade.ml.v3 import serve
from poe_trade.ml.v3.hybrid_search import SearchResult


class _Client:
    def execute(self, query: str, settings=None) -> str:  # noqa: ANN001
        if "quantileTDigest(0.5)(target_price_chaos)" in query:
            return json.dumps({"p50": 120.0, "rows": 32}) + "\n"
        return ""


class _DummyVectorizer:
    def transform(self, _rows):  # noqa: ANN001
        return [[1.0]]


class _DummyRegressor:
    def __init__(self, value: float) -> None:
        self.value = value

    def predict(self, _X):  # noqa: ANN001
        return [self.value]


class _RaisingRegressor:
    def predict(self, _X):  # noqa: ANN001
        raise ValueError("model runtime failure")


class _DummyClassifier:
    def predict_proba(self, _X):  # noqa: ANN001
        return [[0.2, 0.8]]


def _parsed_payload() -> dict[str, object]:
    return {
        "category": "helmet",
        "base_type": "Hubris Circlet",
        "rarity": "Rare",
        "ilvl": 86,
        "stack_size": 1,
        "corrupted": 0,
        "fractured": 0,
        "synthesised": 0,
        "mod_token_count": 2,
        "mod_features_json": "{}",
    }


def test_predict_one_v3_fallback_returns_dual_prices(monkeypatch) -> None:
    monkeypatch.setattr(
        serve.workflows,
        "_parse_clipboard_item",
        lambda _text: _parsed_payload(),
    )

    payload = serve.predict_one_v3(
        _Client(),
        league="Mirage",
        clipboard_text="dummy",
        model_dir="/does/not/exist",
    )

    assert payload["route"] == "sparse_retrieval"
    assert payload["fair_value_p50"] == 120.0
    assert payload["fast_sale_24h_price"] == 108.0
    assert payload["prediction_source"] == "v3_median_fallback"
    assert payload["uncertainty_tier"] == "high"
    assert payload["price_recommendation_eligible"] is False


def test_predict_one_v3_uses_direct_fast_sale_model_when_bundle_exists(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        serve.workflows,
        "_parse_clipboard_item",
        lambda _text: _parsed_payload(),
    )
    monkeypatch.setattr(
        serve,
        "_load_bundle_if_present",
        lambda **_kwargs: {
            "vectorizer": _DummyVectorizer(),
            "models": {
                "p10": _DummyRegressor(95.0),
                "p50": _DummyRegressor(120.0),
                "p90": _DummyRegressor(140.0),
                "fast_sale_24h": _DummyRegressor(109.0),
                "sale_probability": _DummyClassifier(),
            },
            "fallback_fast_sale_multiplier": 0.9,
            "metadata": {"row_count": 1200},
        },
    )

    payload = serve.predict_one_v3(
        _Client(),
        league="Mirage",
        clipboard_text="dummy",
        model_dir="/unused",
    )

    assert payload["prediction_source"] == "v3_model"
    assert payload["fair_value_p50"] == 120.0
    assert payload["fast_sale_24h_price"] == 109.0
    assert payload["sale_probability_24h"] == 0.8
    assert payload["confidence"] == 0.1


def test_predict_one_v3_falls_back_when_bundle_schema_is_incomplete(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        serve.workflows,
        "_parse_clipboard_item",
        lambda _text: _parsed_payload(),
    )
    monkeypatch.setattr(
        serve,
        "_load_bundle_if_present",
        lambda **_kwargs: {
            "vectorizer": object(),
            "models": {},
        },
    )

    payload = serve.predict_one_v3(
        _Client(),
        league="Mirage",
        clipboard_text="dummy",
        model_dir="/unused",
    )

    assert payload["prediction_source"] == "v3_median_fallback"


def test_predict_one_v3_ignores_malformed_fast_sale_model(monkeypatch) -> None:
    monkeypatch.setattr(
        serve.workflows,
        "_parse_clipboard_item",
        lambda _text: _parsed_payload(),
    )
    monkeypatch.setattr(
        serve,
        "_load_bundle_if_present",
        lambda **_kwargs: {
            "vectorizer": _DummyVectorizer(),
            "models": {
                "p10": _DummyRegressor(95.0),
                "p50": _DummyRegressor(120.0),
                "p90": _DummyRegressor(140.0),
                "fast_sale_24h": object(),
            },
            "fallback_fast_sale_multiplier": 0.9,
            "metadata": {"row_count": 1200},
        },
    )

    payload = serve.predict_one_v3(
        _Client(),
        league="Mirage",
        clipboard_text="dummy",
        model_dir="/unused",
    )

    assert payload["prediction_source"] == "v3_model"
    assert payload["fast_sale_24h_price"] == 108.0


def test_predict_one_v3_ignores_malformed_sale_probability_model(monkeypatch) -> None:
    monkeypatch.setattr(
        serve.workflows,
        "_parse_clipboard_item",
        lambda _text: _parsed_payload(),
    )
    monkeypatch.setattr(
        serve,
        "_load_bundle_if_present",
        lambda **_kwargs: {
            "vectorizer": _DummyVectorizer(),
            "models": {
                "p10": _DummyRegressor(95.0),
                "p50": _DummyRegressor(120.0),
                "p90": _DummyRegressor(140.0),
                "sale_probability": object(),
            },
            "fallback_fast_sale_multiplier": 0.9,
            "metadata": {"row_count": 1200},
        },
    )

    payload = serve.predict_one_v3(
        _Client(),
        league="Mirage",
        clipboard_text="dummy",
        model_dir="/unused",
    )

    assert payload["prediction_source"] == "v3_model"
    assert payload["sale_probability_24h"] == 0.5


def test_predict_one_v3_defaults_on_malformed_fast_sale_multiplier(monkeypatch) -> None:
    monkeypatch.setattr(
        serve.workflows,
        "_parse_clipboard_item",
        lambda _text: _parsed_payload(),
    )
    monkeypatch.setattr(
        serve,
        "_load_bundle_if_present",
        lambda **_kwargs: {
            "vectorizer": _DummyVectorizer(),
            "models": {
                "p10": _DummyRegressor(95.0),
                "p50": _DummyRegressor(120.0),
                "p90": _DummyRegressor(140.0),
            },
            "fallback_fast_sale_multiplier": "not-a-number",
            "metadata": {"row_count": 1200},
        },
    )

    payload = serve.predict_one_v3(
        _Client(),
        league="Mirage",
        clipboard_text="dummy",
        model_dir="/unused",
    )

    assert payload["prediction_source"] == "v3_model"
    assert payload["fast_sale_24h_price"] == 108.0


def test_predict_one_v3_runs_retrieval_search_and_attaches_diagnostics(
    monkeypatch,
) -> None:
    parsed_item = _parsed_payload()
    parsed_item["mod_features_json"] = (
        '{"explicit.crit_chance": 10, "explicit.life": 5}'
    )
    retrieval_calls: dict[str, object] = {}

    def _fake_parse(_text: str) -> dict[str, object]:
        return parsed_item

    monkeypatch.setattr(serve.workflows, "_parse_clipboard_item", _fake_parse)

    def _fake_run_search(
        *,
        parsed_item: dict[str, object],
        candidate_rows: list[dict[str, object]],
        ranked_affixes: list[dict[str, object]] | None,
        stage_support_targets=None,
        max_candidates: int,
    ) -> SearchResult:
        retrieval_calls["parsed_item"] = parsed_item
        retrieval_calls["candidate_rows"] = candidate_rows
        retrieval_calls["ranked_affixes"] = ranked_affixes
        retrieval_calls["max_candidates"] = max_candidates
        return SearchResult(
            stage=2,
            candidates=[
                {
                    "identity_key": "cmp-1",
                    "price": 99.0,
                    "score": 0.77,
                }
            ],
            dropped_affixes=["explicit.life"],
            effective_support=3,
            candidate_count=5,
            degradation_reason=None,
        )

    monkeypatch.setattr(serve.hybrid_search, "run_search", _fake_run_search)
    retrieval_query = {
        "built": False,
        "args": {},
    }

    def _fake_build_query(
        *, league: str, route: str, item_state_key: str, limit: int = 2000
    ) -> str:
        retrieval_query.update(
            {
                "built": True,
                "args": {
                    "league": league,
                    "route": route,
                    "item_state_key": item_state_key,
                    "limit": limit,
                },
            }
        )
        return "RETRIEVE"

    monkeypatch.setattr(serve.sql, "build_retrieval_candidate_query", _fake_build_query)

    def _fake_query_rows(_client, query: str):
        if query == "RETRIEVE":
            return [
                {
                    "identity_key": "id-1",
                    "base_type": "Hubris Circlet",
                    "rarity": "Rare",
                    "item_state_key": "rare|corrupted=0|fractured=0|synthesised=0",
                    "target_price_chaos": 100.0,
                    "target_fast_sale_24h_price": 95.0,
                    "target_sale_probability_24h": 0.62,
                    "support_count_recent": 5,
                    "mod_features_json": '{"explicit.crit_chance": 10}',
                    "as_of_ts": "2026-03-22T10:00:00",
                },
                {
                    "identity_key": "id-2",
                    "base_type": "Hubris Circlet",
                    "rarity": "Rare",
                    "item_state_key": "rare|corrupted=0|fractured=0|synthesised=0",
                    "target_price_chaos": 101.0,
                    "target_fast_sale_24h_price": 96.0,
                    "target_sale_probability_24h": 0.60,
                    "support_count_recent": 5,
                    "mod_features_json": '{"explicit.crit_chance": 10}',
                    "as_of_ts": "2026-03-22T09:00:00",
                },
            ]
        return []

    monkeypatch.setattr(serve, "_query_rows", _fake_query_rows)

    payload = serve.predict_one_v3(
        _Client(),
        league="Mirage",
        clipboard_text="dummy",
        model_dir="/does/not/exist",
    )

    assert retrieval_query["built"] is True
    assert retrieval_query["args"]["league"] == "Mirage"
    assert retrieval_query["args"]["route"] == "sparse_retrieval"
    assert (
        retrieval_query["args"]["item_state_key"]
        == "rare|corrupted=0|fractured=0|synthesised=0"
    )

    assert isinstance(retrieval_calls["parsed_item"], dict)
    assert len(retrieval_calls["candidate_rows"]) == 2
    assert retrieval_calls["ranked_affixes"]
    assert retrieval_calls["max_candidates"] == 64

    assert payload["retrieval_stage"] == 2
    assert payload["retrievalStage"] == 2
    assert payload["retrieval_candidate_count"] == 5
    assert payload["retrievalCandidateCount"] == 5
    assert payload["retrieval_effective_support"] == 3
    assert payload["retrieval_effectiveSupport"] == 3
    assert payload["retrieval_dropped_affixes"] == ["explicit.life"]
    assert payload["retrievalDroppedAffixes"] == ["explicit.life"]
    assert payload["retrieval_degradation_reason"] is None


def test_predict_one_v3_preserves_bundle_prediction_with_retrieval_context(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        serve.workflows,
        "_parse_clipboard_item",
        lambda _text: _parsed_payload(),
    )
    monkeypatch.setattr(
        serve,
        "_load_bundle_if_present",
        lambda **_kwargs: {
            "vectorizer": _DummyVectorizer(),
            "models": {
                "p10": _DummyRegressor(95.0),
                "p50": _DummyRegressor(120.0),
                "p90": _DummyRegressor(140.0),
                "fast_sale_24h": _DummyRegressor(109.0),
                "sale_probability": _DummyClassifier(),
            },
            "fallback_fast_sale_multiplier": 0.9,
            "metadata": {"row_count": 1200},
        },
    )
    monkeypatch.setattr(
        serve.sql,
        "build_retrieval_candidate_query",
        lambda **_kwargs: "RETRIEVE",
    )
    retrieval_called = {"run": 0}

    def _fake_run_search(
        *,
        parsed_item: dict[str, object],
        candidate_rows: list[dict[str, object]],
        ranked_affixes: list[dict[str, object]] | None,
        stage_support_targets=None,
        max_candidates: int,
    ) -> SearchResult:
        retrieval_called["run"] += 1
        return SearchResult(
            stage=4,
            candidates=[],
            dropped_affixes=[],
            effective_support=0,
            candidate_count=0,
            degradation_reason="no_relevant_comparables",
        )

    monkeypatch.setattr(serve.hybrid_search, "run_search", _fake_run_search)

    def _fake_query_rows(_client, query: str):
        if query == "RETRIEVE":
            return []
        return []

    monkeypatch.setattr(serve, "_query_rows", _fake_query_rows)

    payload = serve.predict_one_v3(
        _Client(),
        league="Mirage",
        clipboard_text="dummy",
        model_dir="/unused",
    )

    assert retrieval_called["run"] == 1
    assert payload["prediction_source"] == "v3_model"
    assert payload["fair_value_p50"] == 120.0
    assert payload["retrieval_stage"] == 4
    assert payload["retrieval_degradation_reason"] == "no_relevant_comparables"


def test_predict_one_v3_falls_back_when_core_predictor_raises(monkeypatch) -> None:
    monkeypatch.setattr(
        serve.workflows,
        "_parse_clipboard_item",
        lambda _text: _parsed_payload(),
    )
    monkeypatch.setattr(
        serve,
        "_load_bundle_if_present",
        lambda **_kwargs: {
            "vectorizer": _DummyVectorizer(),
            "models": {
                "p10": _DummyRegressor(95.0),
                "p50": _RaisingRegressor(),
                "p90": _DummyRegressor(140.0),
            },
            "fallback_fast_sale_multiplier": 0.9,
            "metadata": {"row_count": 1200},
        },
    )

    payload = serve.predict_one_v3(
        _Client(),
        league="Mirage",
        clipboard_text="dummy",
        model_dir="/unused",
    )

    assert payload["prediction_source"] == "v3_median_fallback"


def test_load_bundle_if_present_returns_none_on_corrupt_bundle(monkeypatch) -> None:
    monkeypatch.setattr(serve.Path, "exists", lambda _self: True)

    def _raise_load(_path):  # noqa: ANN001
        raise ValueError("corrupt")

    monkeypatch.setattr(serve.joblib, "load", _raise_load)

    payload = serve._load_bundle_if_present(
        model_dir="/unused",
        league="Mirage",
        route="sparse_retrieval",
    )

    assert payload is None


def test_predict_one_v3_returns_hybrid_prediction_source(monkeypatch) -> None:
    monkeypatch.setattr(
        serve.workflows,
        "_parse_clipboard_item",
        lambda _text: _parsed_payload(),
    )
    monkeypatch.setattr(
        serve,
        "_load_bundle_if_present",
        lambda **_kwargs: {
            "vectorizer": _DummyVectorizer(),
            "models": {
                "p10": _DummyRegressor(90.0),
                "p50": _DummyRegressor(110.0),
                "p90": _DummyRegressor(130.0),
                "fast_sale_24h": _DummyRegressor(102.0),
                "sale_probability": _DummyClassifier(),
            },
            "metadata": {"row_count": 100},
            "fair_value_residual_model": _DummyRegressor(4.0),
            "fast_sale_residual_model": _DummyRegressor(2.0),
        },
    )
    monkeypatch.setattr(
        serve.sql,
        "build_retrieval_candidate_query",
        lambda **_kwargs: "RETRIEVE",
    )
    monkeypatch.setattr(
        serve,
        "_query_rows",
        lambda _client, _query: [
            {
                "identity_key": "id-1",
                "base_type": "Hubris Circlet",
                "rarity": "Rare",
                "item_state_key": "rare|corrupted=0|fractured=0|synthesised=0",
                "target_price_chaos": 100.0,
                "target_fast_sale_24h_price": 95.0,
                "target_sale_probability_24h": 0.62,
                "support_count_recent": 5,
                "mod_features_json": "{}",
                "as_of_ts": "2026-03-22T10:00:00",
            }
        ],
    )
    monkeypatch.setattr(
        serve.hybrid_search,
        "run_search",
        lambda **_kwargs: SearchResult(
            stage=2,
            candidates=[{"identity_key": "id-1", "price": 100.0, "score": 0.9}],
            dropped_affixes=[],
            effective_support=1,
            candidate_count=1,
            degradation_reason=None,
        ),
    )

    payload = serve.predict_one_v3(
        _Client(),
        league="Mirage",
        clipboard_text="dummy",
        model_dir="/unused",
    )

    assert payload["prediction_source"] == "v3_hybrid"


def test_predict_one_v3_uses_stage_zero_prior_when_no_comparables(monkeypatch) -> None:
    monkeypatch.setattr(
        serve.workflows,
        "_parse_clipboard_item",
        lambda _text: _parsed_payload(),
    )
    monkeypatch.setattr(serve, "_load_bundle_if_present", lambda **_kwargs: None)
    monkeypatch.setattr(
        serve.sql,
        "build_retrieval_candidate_query",
        lambda **_kwargs: "RETRIEVE",
    )
    monkeypatch.setattr(serve, "_query_rows", lambda _client, _query: [])
    monkeypatch.setattr(
        serve.hybrid_search,
        "run_search",
        lambda **_kwargs: SearchResult(
            stage=0,
            candidates=[],
            dropped_affixes=[],
            effective_support=0,
            candidate_count=0,
            degradation_reason="no_relevant_comparables",
        ),
    )

    payload = serve.predict_one_v3(
        _Client(),
        league="Mirage",
        clipboard_text="dummy",
        model_dir="/unused",
    )

    assert payload["estimate_trust"] == "low"
    assert payload["searchDiagnostics"]["stage"] == 0


def test_predict_one_v3_does_not_apply_residual_on_stage_zero_prior(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        serve.workflows,
        "_parse_clipboard_item",
        lambda _text: _parsed_payload(),
    )
    monkeypatch.setattr(
        serve,
        "_load_bundle_if_present",
        lambda **_kwargs: {
            "vectorizer": _DummyVectorizer(),
            "models": {
                "p10": _DummyRegressor(90.0),
                "p50": _DummyRegressor(110.0),
                "p90": _DummyRegressor(130.0),
                "fast_sale_24h": _DummyRegressor(102.0),
            },
            "fair_value_residual_model": _DummyRegressor(20.0),
        },
    )
    monkeypatch.setattr(
        serve.sql,
        "build_retrieval_candidate_query",
        lambda **_kwargs: "RETRIEVE",
    )
    monkeypatch.setattr(serve, "_query_rows", lambda _client, _query: [])
    monkeypatch.setattr(
        serve.hybrid_search,
        "run_search",
        lambda **_kwargs: SearchResult(
            stage=0,
            candidates=[],
            dropped_affixes=[],
            effective_support=0,
            candidate_count=0,
            degradation_reason="no_relevant_comparables",
        ),
    )

    payload = serve.predict_one_v3(
        _Client(),
        league="Mirage",
        clipboard_text="dummy",
        model_dir="/unused",
    )

    assert payload["comparablesSummary"]["anchorPrice"] == payload["fair_value_p50"]
