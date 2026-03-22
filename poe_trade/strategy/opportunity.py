from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OpportunityScoreInput:
    expected_profit_chaos: float | None
    estimated_operations: int | None
    estimated_whispers: int | None = None
    expected_profit_per_operation_chaos: float | None = None


@dataclass(frozen=True)
class NormalizedOpportunityMetrics:
    estimated_operations: int | None
    estimated_whispers: int | None
    expected_profit_per_operation_chaos: float | None


def normalize_opportunity_metrics(
    snapshot: OpportunityScoreInput,
    *,
    default_estimated_operations: int | None = None,
    default_estimated_whispers: int | None = None,
    default_profit_per_operation_chaos: float | None = None,
) -> NormalizedOpportunityMetrics:
    estimated_operations = _positive_int_or_default(
        snapshot.estimated_operations,
        default=default_estimated_operations,
    )
    estimated_whispers = _non_negative_int_or_default(
        snapshot.estimated_whispers,
        default=default_estimated_whispers,
    )

    if snapshot.expected_profit_per_operation_chaos is not None:
        expected_profit_per_operation = snapshot.expected_profit_per_operation_chaos
    elif (
        snapshot.estimated_operations is not None and snapshot.estimated_operations > 0
    ):
        expected_profit_per_operation = expected_profit_per_operation_chaos(snapshot)
    elif default_profit_per_operation_chaos is not None:
        expected_profit_per_operation = default_profit_per_operation_chaos
    elif (
        snapshot.expected_profit_chaos is not None and estimated_operations is not None
    ):
        expected_profit_per_operation = snapshot.expected_profit_chaos / float(
            estimated_operations
        )
    else:
        expected_profit_per_operation = None

    return NormalizedOpportunityMetrics(
        estimated_operations=estimated_operations,
        estimated_whispers=estimated_whispers,
        expected_profit_per_operation_chaos=expected_profit_per_operation,
    )


def expected_profit_per_operation_chaos(
    snapshot: OpportunityScoreInput,
) -> float | None:
    if snapshot.expected_profit_chaos is None:
        return None
    if snapshot.estimated_operations is None or snapshot.estimated_operations <= 0:
        return None
    return snapshot.expected_profit_chaos / float(snapshot.estimated_operations)


def _positive_int_or_default(value: int | None, *, default: int | None) -> int | None:
    if value is not None and value > 0:
        return value
    if default is not None and default > 0:
        return default
    return None


def _non_negative_int_or_default(
    value: int | None, *, default: int | None
) -> int | None:
    if value is not None and value >= 0:
        return value
    if default is not None and default >= 0:
        return default
    return None
