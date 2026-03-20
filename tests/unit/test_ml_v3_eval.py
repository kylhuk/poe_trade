from __future__ import annotations

from poe_trade.ml.v3 import eval as v3_eval


def test_promotion_gate_passes_when_all_thresholds_met() -> None:
    gate = v3_eval.promotion_gate(
        global_fair_value_mdape=0.2,
        global_fast_sale_hit_rate=0.65,
        global_sale_probability_calibration_error=0.1,
        worst_slice_mdape=0.35,
    )

    assert gate["passed"] is True
    assert gate["reason"] == "pass"


def test_promotion_gate_reports_failure_reasons() -> None:
    gate = v3_eval.promotion_gate(
        global_fair_value_mdape=0.5,
        global_fast_sale_hit_rate=0.4,
        global_sale_probability_calibration_error=0.3,
        worst_slice_mdape=0.6,
    )

    assert gate["passed"] is False
    assert "global_mdape" in gate["reason"]
    assert "worst_slice" in gate["reason"]


def test_evaluate_run_records_route_and_summary_rows(monkeypatch) -> None:
    inserted: list[tuple[str, list[dict[str, object]]]] = []

    monkeypatch.setattr(
        v3_eval,
        "_query_rows",
        lambda *_args, **_kwargs: [
            {
                "route": "sparse_retrieval",
                "sample_count": 100,
                "fair_value_mdape": 0.25,
                "fair_value_wape": 0.3,
                "fast_sale_24h_hit_rate": 0.6,
                "sale_probability_calibration_error": 0.1,
                "confidence_calibration_error": 0.12,
            }
        ],
    )
    monkeypatch.setattr(
        v3_eval,
        "_insert_json_rows",
        lambda _client, table, rows: inserted.append((table, rows)),
    )

    payload = v3_eval.evaluate_run(
        object(),
        league="Mirage",
        run_id="run-123",
    )

    assert payload["summary"]["run_id"] == "run-123"
    assert payload["summary"]["gate_passed"] == 1
    assert inserted[0][0] == v3_eval.ROUTE_EVAL_TABLE
    assert inserted[1][0] == v3_eval.EVAL_RUNS_TABLE
