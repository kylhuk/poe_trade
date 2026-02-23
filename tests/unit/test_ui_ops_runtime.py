"""Tests for Ops runtime UI issue synthesis."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from poe_trade.api.schemas import (
    OpsCheckpointHealth,
    OpsDashboardResponse,
    OpsIngestRate,
    OpsRequestRate,
    OpsSLOStatus,
    RateLimitAlertSchema,
)
from poe_trade.ui.ops_runtime import (
    build_ops_summary,
    format_age,
    age_minutes,
    _rate_limit_issues,
)


def _ops_dashboard(
    *,
    timestamp: datetime,
    ingest: OpsIngestRate | None = None,
    request: OpsRequestRate | None = None,
    checkpoint: list[OpsCheckpointHealth] | None = None,
    slo: list[OpsSLOStatus] | None = None,
    rate_limit: list[RateLimitAlertSchema] | None = None,
) -> OpsDashboardResponse:
    base_ingest = OpsIngestRate(
        window_minutes=1,
        public_stash_records_per_minute=1.0,
        currency_records_per_minute=1.0,
        public_stash_last_seen=timestamp,
        currency_last_seen=timestamp,
    )
    base_request = OpsRequestRate(
        requests_per_minute=60.0,
        error_rate_percent=0.2,
        throttled_percent=0.1,
    )
    return OpsDashboardResponse(
        timestamp=timestamp,
        ingest_rate=ingest or base_ingest,
        checkpoint_health=checkpoint or [],
        request_rate=request or base_request,
        slo_status=slo or [],
        rate_limit_alerts=rate_limit or [],
    )


@pytest.fixture
def now() -> datetime:
    return datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def healthy_telemetry(now: datetime) -> OpsDashboardResponse:
    return _ops_dashboard(timestamp=now)


def test_build_ops_summary_healthy(healthy_telemetry: OpsDashboardResponse) -> None:
    summary = build_ops_summary(healthy_telemetry, now=healthy_telemetry.timestamp)
    assert summary.severity == "ok"
    assert summary.headline == "Operational telemetry looks healthy."
    assert summary.issues == []


def test_stale_ingest_generates_issues(now: datetime) -> None:
    public_age = now - timedelta(minutes=25)
    currency_age = now - timedelta(minutes=90)
    telemetry = _ops_dashboard(
        timestamp=now,
        ingest=OpsIngestRate(
            window_minutes=1,
            public_stash_records_per_minute=1.0,
            currency_records_per_minute=1.0,
            public_stash_last_seen=public_age,
            currency_last_seen=currency_age,
        ),
    )

    summary = build_ops_summary(telemetry, now=now)
    assert summary.severity == "critical"
    assert "critical" in summary.headline
    assert len(summary.issues) == 2

    public_issue, currency_issue = summary.issues
    assert public_issue.severity == "warning"
    assert "Public stash ingest" in public_issue.title
    assert "25.0m" in public_issue.detail
    assert "market_harvester logs" in public_issue.remediation

    assert currency_issue.severity == "critical"
    assert "Currency ingest" in currency_issue.title
    assert "90.0m" in currency_issue.detail
    assert "currency harvest pipeline" in currency_issue.remediation


def test_error_and_throttle_create_issues(now: datetime) -> None:
    telemetry = _ops_dashboard(
        timestamp=now,
        request=OpsRequestRate(
            requests_per_minute=120.0,
            error_rate_percent=3.2,
            throttled_percent=6.5,
        ),
    )

    summary = build_ops_summary(telemetry, now=now)
    assert summary.severity == "critical"
    assert len(summary.issues) == 2
    assert summary.issues[0].title == "Request error rate is elevated"
    assert "3.20%" in summary.issues[0].detail
    assert summary.issues[1].title == "Throttling pressure detected"
    assert "6.50%" in summary.issues[1].detail


def test_checkpoint_alert_and_slo_miss(now: datetime) -> None:
    checkpoint = OpsCheckpointHealth(
        cursor_name="main_stream",
        last_checkpoint=now - timedelta(minutes=5),
        expected_interval_minutes=5,
        drift_minutes=12,
        alert=True,
    )
    slo = OpsSLOStatus(
        stream_name="ingest_stream",
        target_minutes=5,
        observed_minutes=12,
        within_slo=False,
        note="queue backlog",
    )
    telemetry = _ops_dashboard(
        timestamp=now,
        checkpoint=[checkpoint],
        slo=[slo],
    )

    summary = build_ops_summary(telemetry, now=now)
    assert summary.severity == "critical"
    titles = {issue.title for issue in summary.issues}
    assert "Checkpoint drift on main_stream" in titles
    assert any(
        "SLO miss" in issue.title and issue.severity == "critical"
        for issue in summary.issues
    )
    slo_issue = next(issue for issue in summary.issues if "SLO miss" in issue.title)
    assert "queue backlog" in slo_issue.detail


def test_rate_limit_severity_mapping(now: datetime) -> None:
    alerts = [
        RateLimitAlertSchema(
            status_code=429,
            occurrences=2,
            window_minutes=5,
            severity="high",
            alert=True,
        ),
        RateLimitAlertSchema(
            status_code=503,
            occurrences=1,
            window_minutes=1,
            severity="info",
            alert=True,
        ),
    ]
    telemetry = _ops_dashboard(timestamp=now, rate_limit=alerts)
    issues = _rate_limit_issues(telemetry)
    assert len(issues) == 2
    assert issues[0].severity == "critical"
    assert "429" in issues[0].title
    assert issues[1].severity == "warning"
    assert "503" in issues[1].title


@pytest.mark.parametrize(
    ("input_minutes", "expected"),
    [
        (1.5, "1.5m"),
        (0.5, "30s"),
        (150.0, "2.5h"),
    ],
)
def test_age_and_format_helpers(input_minutes: float, expected: str) -> None:
    now = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    value = now - timedelta(minutes=input_minutes)
    assert age_minutes(value, now=now) == pytest.approx(input_minutes)
    assert format_age(input_minutes) == expected
