"""Deterministic SLO helpers for monitoring dashboards."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping, Sequence


@dataclass(frozen=True)
class FreshnessSLOStatus:
    stream_name: str
    target_minutes: int
    observed_minutes: float
    within_slo: bool
    note: str | None = None


@dataclass(frozen=True)
class CheckpointDriftAlert:
    cursor_name: str
    last_checkpoint: datetime
    expected_interval_minutes: int
    drift_minutes: float
    alert: bool


@dataclass(frozen=True)
class RateLimitAlert:
    status_code: int
    occurrences: int
    window_minutes: int
    severity: str
    alert: bool


def evaluate_ingest_freshness(
    public_last: datetime,
    currency_last: datetime,
    reference: datetime,
) -> Sequence[FreshnessSLOStatus]:
    """Score the public stash and currency streams against their freshness targets."""

    def _build(stream_name: str, target: int, observed: datetime) -> FreshnessSLOStatus:
        observed_minutes = max(0.0, (reference - observed).total_seconds() / 60)
        within_slo = observed_minutes <= target
        note = None
        if not within_slo:
            note = f"lag {observed_minutes:.1f}m exceeds {target}m"
        return FreshnessSLOStatus(
            stream_name=stream_name,
            target_minutes=target,
            observed_minutes=round(observed_minutes, 1),
            within_slo=within_slo,
            note=note,
        )

    return (
        _build("public_stash", 10, public_last),
        _build("currency_snapshot", 65, currency_last),
    )


def detect_checkpoint_drift(
    cursor_name: str,
    last_checkpoint: datetime,
    reference: datetime,
    expected_interval_minutes: int,
) -> CheckpointDriftAlert:
    """Raise an alert when a checkpoint cursor drifts beyond its cadence."""

    drift_minutes = max(0.0, (reference - last_checkpoint).total_seconds() / 60)
    alert = drift_minutes >= expected_interval_minutes * 2
    return CheckpointDriftAlert(
        cursor_name=cursor_name,
        last_checkpoint=last_checkpoint,
        expected_interval_minutes=expected_interval_minutes,
        drift_minutes=round(drift_minutes, 1),
        alert=alert,
    )


def detect_repeated_rate_errors(
    error_counts: Mapping[int, int], window_minutes: int, threshold: int = 5
) -> Sequence[RateLimitAlert]:
    """Detect repeating 4xx/429 sprees that merit operator attention."""

    alerts: list[RateLimitAlert] = []
    for status_code, occurrences in sorted(error_counts.items()):
        alert = occurrences >= threshold
        severity = "critical" if status_code == 429 else "warning"
        alerts.append(
            RateLimitAlert(
                status_code=status_code,
                occurrences=occurrences,
                window_minutes=window_minutes,
                severity=severity,
                alert=alert,
            )
        )
    return tuple(alerts)
