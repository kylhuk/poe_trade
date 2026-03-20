from __future__ import annotations

from poe_trade.ml import workflows


def _base_comparison() -> dict[str, object]:
    return {
        "shadow_gate": {"pass": True, "reason_codes": []},
        "integrity_gate": {"pass": True, "reason_codes": []},
        "protected_cohort_regression": {"regression": False},
        "coverage_floor_ok": True,
        "serving_path_gate": {
            "pass": True,
            "overall_rae_improvement_relative": 0.06,
            "overall_extreme_miss_delta": -0.01,
            "sparse_extreme_miss_improvement_relative": 0.12,
            "ece_delta": 0.0,
            "max_required_cohort_rae_regression_relative": 0.0,
            "abstain_spike_justified": True,
            "required_dimensions_present": True,
            "protected_cohorts_present": True,
        },
    }


def test_promotion_requires_serving_path_rae_improvement() -> None:
    comparison = _base_comparison()
    comparison["serving_path_gate"]["overall_rae_improvement_relative"] = 0.01  # type: ignore[index]
    assert workflows._should_promote(comparison) is False


def test_promotion_blocks_on_calibration_regression() -> None:
    comparison = _base_comparison()
    comparison["serving_path_gate"]["ece_delta"] = 0.02  # type: ignore[index]
    assert workflows._should_promote(comparison) is False


def test_promotion_requires_all_required_cohort_dimensions_present() -> None:
    comparison = _base_comparison()
    comparison["serving_path_gate"]["required_dimensions_present"] = False  # type: ignore[index]
    assert workflows._should_promote(comparison) is False


def test_promotion_enforces_numeric_thresholds_exactly() -> None:
    comparison = _base_comparison()
    assert workflows._should_promote(comparison) is True
