"""Operator-focused status synthesis for Ops & Runtime UI."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from poe_trade.api.schemas import OpsDashboardResponse

SEVERITY_ORDER = {"ok": 0, "warning": 1, "critical": 2}

PUBLIC_STALE_WARNING_MINUTES = 10.0
PUBLIC_STALE_CRITICAL_MINUTES = 30.0
CURRENCY_STALE_WARNING_MINUTES = 20.0
CURRENCY_STALE_CRITICAL_MINUTES = 60.0

ERROR_RATE_WARNING_PERCENT = 1.0
ERROR_RATE_CRITICAL_PERCENT = 3.0
THROTTLED_WARNING_PERCENT = 1.0
THROTTLED_CRITICAL_PERCENT = 5.0


@dataclass(frozen=True)
class OpsIssue:
    severity: str
    title: str
    detail: str
    remediation: str


@dataclass(frozen=True)
class OpsRuntimeSummary:
    severity: str
    headline: str
    issues: list[OpsIssue]


def age_minutes(value: datetime, *, now: datetime | None = None) -> float:
    """Return age in minutes from ``value`` to ``now`` (UTC)."""

    reference = now or datetime.now(timezone.utc)
    value_utc = _to_utc(value)
    reference_utc = _to_utc(reference)
    age = (reference_utc - value_utc).total_seconds() / 60.0
    return max(age, 0.0)


def format_age(minutes: float) -> str:
    """Render a compact age label for UI badges."""

    if minutes >= 120:
        return f"{minutes / 60.0:.1f}h"
    if minutes >= 1:
        return f"{minutes:.1f}m"
    return f"{minutes * 60.0:.0f}s"


def build_ops_summary(
    telemetry: OpsDashboardResponse,
    *,
    now: datetime | None = None,
) -> OpsRuntimeSummary:
    """Build severity rollup and actionable issue list."""

    issues = _ingest_issues(telemetry, now=now)
    issues.extend(_request_issues(telemetry))
    issues.extend(_checkpoint_issues(telemetry))
    issues.extend(_slo_issues(telemetry))
    issues.extend(_rate_limit_issues(telemetry))

    if not issues:
        return OpsRuntimeSummary(
            severity="ok",
            headline="Operational telemetry looks healthy.",
            issues=[],
        )

    severity = _max_severity(issue.severity for issue in issues)
    if severity == "critical":
        headline = f"{len(issues)} critical issue(s) require immediate action."
    else:
        headline = f"{len(issues)} warning issue(s) require operator review."
    return OpsRuntimeSummary(severity=severity, headline=headline, issues=issues)


def _ingest_issues(
    telemetry: OpsDashboardResponse,
    *,
    now: datetime | None,
) -> list[OpsIssue]:
    ingest = telemetry.ingest_rate
    public_age = age_minutes(ingest.public_stash_last_seen, now=now)
    currency_age = age_minutes(ingest.currency_last_seen, now=now)
    issues: list[OpsIssue] = []

    public_severity = _threshold_severity(
        public_age,
        warning=PUBLIC_STALE_WARNING_MINUTES,
        critical=PUBLIC_STALE_CRITICAL_MINUTES,
    )
    if public_severity != "ok":
        issues.append(
            OpsIssue(
                severity=public_severity,
                title="Public stash ingest is stale",
                detail=f"Latest event is {format_age(public_age)} old.",
                remediation=(
                    "Check market_harvester logs, validate OAuth token refresh, and "
                    "verify checkpoint progression for the active realm/league."
                ),
            )
        )

    currency_severity = _threshold_severity(
        currency_age,
        warning=CURRENCY_STALE_WARNING_MINUTES,
        critical=CURRENCY_STALE_CRITICAL_MINUTES,
    )
    if currency_severity != "ok":
        issues.append(
            OpsIssue(
                severity=currency_severity,
                title="Currency ingest is stale",
                detail=f"Latest event is {format_age(currency_age)} old.",
                remediation=(
                    "Inspect currency harvest pipeline, then confirm upstream API "
                    "responses and checkpoint file updates."
                ),
            )
        )
    return issues


def _request_issues(telemetry: OpsDashboardResponse) -> list[OpsIssue]:
    request_rate = telemetry.request_rate
    issues: list[OpsIssue] = []

    error_severity = _threshold_severity(
        request_rate.error_rate_percent,
        warning=ERROR_RATE_WARNING_PERCENT,
        critical=ERROR_RATE_CRITICAL_PERCENT,
    )
    if error_severity != "ok":
        issues.append(
            OpsIssue(
                severity=error_severity,
                title="Request error rate is elevated",
                detail=(
                    f"Error rate is {request_rate.error_rate_percent:.2f}% "
                    f"at {request_rate.requests_per_minute:.1f} req/min."
                ),
                remediation=(
                    "Review API/service logs for repeated failures and restart the "
                    "offending ingestion worker after resolving root cause."
                ),
            )
        )

    throttled_severity = _threshold_severity(
        request_rate.throttled_percent,
        warning=THROTTLED_WARNING_PERCENT,
        critical=THROTTLED_CRITICAL_PERCENT,
    )
    if throttled_severity != "ok":
        issues.append(
            OpsIssue(
                severity=throttled_severity,
                title="Throttling pressure detected",
                detail=(
                    f"Throttled responses are {request_rate.throttled_percent:.2f}% "
                    "of requests."
                ),
                remediation=(
                    "Increase polling interval, reduce concurrent workers, and verify "
                    "rate-limit headers from upstream services."
                ),
            )
        )
    return issues


def _checkpoint_issues(telemetry: OpsDashboardResponse) -> list[OpsIssue]:
    issues: list[OpsIssue] = []
    for entry in telemetry.checkpoint_health:
        severity = "critical" if entry.alert else "ok"
        if severity == "ok" and entry.expected_interval_minutes > 0:
            ratio = entry.drift_minutes / entry.expected_interval_minutes
            if ratio >= 2.0:
                severity = "warning"
        if severity == "ok":
            continue
        issues.append(
            OpsIssue(
                severity=severity,
                title=f"Checkpoint drift on {entry.cursor_name}",
                detail=(
                    f"Drift is {entry.drift_minutes:.1f} min "
                    f"(expected {entry.expected_interval_minutes:.1f} min)."
                ),
                remediation=(
                    "Confirm cursor is advancing, inspect checkpoint store integrity, "
                    "and restart the corresponding harvester if stalled."
                ),
            )
        )
    return issues


def _slo_issues(telemetry: OpsDashboardResponse) -> list[OpsIssue]:
    issues: list[OpsIssue] = []
    for status in telemetry.slo_status:
        if status.within_slo:
            continue
        severity = (
            "critical"
            if status.observed_minutes >= (status.target_minutes * 2)
            else "warning"
        )
        note = f" Note: {status.note}." if status.note else ""
        issues.append(
            OpsIssue(
                severity=severity,
                title=f"SLO miss on {status.stream_name}",
                detail=(
                    f"Observed {status.observed_minutes:.1f} min vs target "
                    f"{status.target_minutes:.1f} min.{note}"
                ),
                remediation=(
                    "Triage upstream delays for this stream and prioritize queue drain "
                    "until observed latency returns to target."
                ),
            )
        )
    return issues


def _rate_limit_issues(telemetry: OpsDashboardResponse) -> list[OpsIssue]:
    issues: list[OpsIssue] = []
    for alert in telemetry.rate_limit_alerts:
        if not alert.alert:
            continue
        severity = (
            "critical" if alert.severity.lower() in {"critical", "high"} else "warning"
        )
        issues.append(
            OpsIssue(
                severity=severity,
                title=f"Rate-limit alert ({alert.status_code})",
                detail=(
                    f"{alert.occurrences} events in {alert.window_minutes:.1f} min "
                    f"(severity: {alert.severity})."
                ),
                remediation=(
                    "Apply adaptive backoff, reduce poll cadence, and verify that "
                    "service credentials and headers are current."
                ),
            )
        )
    return issues


def _threshold_severity(value: float, *, warning: float, critical: float) -> str:
    if value >= critical:
        return "critical"
    if value >= warning:
        return "warning"
    return "ok"


def _max_severity(levels: list[str] | tuple[str, ...] | set[str] | iter) -> str:
    highest = "ok"
    for level in levels:
        if SEVERITY_ORDER[level] > SEVERITY_ORDER[highest]:
            highest = level
    return highest


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


__all__ = [
    "OpsIssue",
    "OpsRuntimeSummary",
    "age_minutes",
    "build_ops_summary",
    "format_age",
]
