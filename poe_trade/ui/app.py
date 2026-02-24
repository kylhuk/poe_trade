"""Streamlit entrypoint with page router and helpers."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Callable

try:
    import streamlit as st
except ImportError:  # pragma: no cover - optional UI dependency
    st = None  # type: ignore[assignment]

try:
    from poe_trade.ui.client import LedgerApiClient
except ImportError:  # pragma: no cover - streamlit script run without package context
    from .client import LedgerApiClient

try:
    from poe_trade.ui.bridge_controls import render_bridge_controls
except ImportError:  # pragma: no cover - streamlit script run without package context
    from .bridge_controls import render_bridge_controls

try:
    from poe_trade.ui.ops_runtime import age_minutes, build_ops_summary, format_age
except ImportError:  # pragma: no cover - streamlit script run without package context
    from .ops_runtime import age_minutes, build_ops_summary, format_age

DESCRIPTION = "Wraeclast Ledger dashboard".strip()

GLOBAL_CSS = '''
<style>
:root {
  --ledger-bg: #f4f5f9;
  --ledger-panel: #ffffff;
  --ledger-border: #d7dee6;
  --ledger-accent: #1f7a8c;
  --ledger-shadow: 0 12px 32px rgba(15, 30, 45, 0.08);
  --ledger-muted: #5e6a7d;
  --ledger-heading: #0f172a;
  --ledger-gradient: linear-gradient(180deg, #eef2ff 0%, #f8fafc 100%);
}
body {
  background: var(--ledger-gradient);
  color: var(--ledger-heading);
}
.stApp {
  background: transparent;
}
main .block-container {
  padding: 0;
  background: transparent;
}
[data-testid='stSidebar'] {
  background: var(--ledger-panel);
  border-radius: 0 0 12px 12px;
  padding: 1rem 1rem 0.5rem;
  border: 1px solid var(--ledger-border);
}
.stSidebar .block-container {
  padding-top: 0.5rem;
}
.ledger-page-header {
  margin-bottom: 1.5rem;
  padding-bottom: 0.5rem;
  border-bottom: 1px solid rgba(15, 23, 42, 0.12);
}
.ledger-page-title {
  margin: 0;
  font-size: 1.9rem;
  font-weight: 600;
  color: var(--ledger-heading);
}
.ledger-page-context {
  margin: 0.25rem 0 0;
  font-size: 0.95rem;
  color: var(--ledger-muted);
}
.ledger-card {
  background: var(--ledger-panel);
  border: 1px solid var(--ledger-border);
  border-radius: 10px;
  padding: 1rem 1.2rem;
  box-shadow: var(--ledger-shadow);
  margin-bottom: 1rem;
}
.ledger-card__message {
  margin: 0;
  font-weight: 600;
  color: var(--ledger-heading);
}
.ledger-card__detail {
  margin: 0.35rem 0;
  color: var(--ledger-muted);
  line-height: 1.35;
}
.ledger-card__action {
  margin: 0;
  color: var(--ledger-accent);
  font-size: 0.9rem;
}
.ledger-card--error {
  border-color: #e02d3b;
}
@media (max-width: 768px) {
  [data-testid='stSidebar'] {
    padding: 0.75rem 0.75rem 0.35rem;
  }
  .ledger-page-header {
    margin-bottom: 1rem;
  }
  .ledger-card {
    padding: 0.9rem 1rem;
  }
}
</style>
'''

def _apply_streamlit_theme() -> None:
    if st is not None:
        st.markdown(GLOBAL_CSS, unsafe_allow_html=True)

def render_page_header(title: str, context: str) -> None:
    st.markdown(
        f'''
        <div class='ledger-page-header'>
            <h1 class='ledger-page-title'>{title}</h1>
            <p class='ledger-page-context'>{context}</p>
        </div>
        ''',
        unsafe_allow_html=True,
    )

def _card_html(
    variant: str,
    message: str,
    detail: str | None = None,
    action: str | None = None,
) -> str:
    detail_html = f"<p class='ledger-card__detail'>{detail}</p>" if detail else ''
    action_html = f"<p class='ledger-card__action'>{action}</p>" if action else ''
    return (
        f"<div class='ledger-card ledger-card--{variant}'>"
        f"<p class='ledger-card__message'>{message}</p>"
        f"{detail_html}{action_html}</div>"
    )

def render_empty_state(message: str, detail: str | None = None, action: str | None = None) -> None:
    st.markdown(_card_html('empty', message, detail, action), unsafe_allow_html=True)

def render_error_state(message: str, detail: str | None = None) -> None:
    st.markdown(_card_html('error', message, detail), unsafe_allow_html=True)

@dataclass(frozen=True)
class Page:
    label: str
    description: str
    render: Callable[[LedgerApiClient], None]

@dataclass(frozen=True)
class MenuItem:
    key: str
    label: str
    icon: str
    group: str

def format_stash_export(rows: list[dict[str, float | str]]) -> str:
    return "\n".join(
        f"{row['fp_loose']} x{row['count']} ({row['league']}) -> est {row['estimate']:.2f}c"
        for row in rows
    )


def _format_estimate_rows(snapshot) -> list[dict[str, float | str]]:
    return [
        {
            "Item": estimate.fp_loose,
            "League": estimate.league,
            "Est": round(estimate.price.est, 3),
            "Fast": round(estimate.price.list_fast, 3),
            "Patient": round(estimate.price.list_patient, 3),
        }
        for estimate in snapshot.estimates
    ]


def _export_rows(snapshot) -> list[dict[str, float | str]]:
    return [
        {
            "fp_loose": estimate.fp_loose,
            "league": estimate.league,
            "count": estimate.count,
            "estimate": round(estimate.price.est, 3),
        }
        for estimate in snapshot.estimates
    ]

def render_market_overview(client: LedgerApiClient) -> None:
    rows = client.market_overview()
    if rows:
        avg_confidence = sum(row["confidence"] for row in rows) / len(rows)
        st.metric("Confidence average", f"{avg_confidence:.2f}")
        st.table(rows)
    else:
        render_empty_state(
            "No price observations yet.",
            "Awaiting deterministic snapshots; check ingest services if this persists.",
        )


def render_stash_pricer(client: LedgerApiClient) -> None:
    snapshot = client.stash_pricing()
    rows = _format_estimate_rows(snapshot)
    export_rows = _export_rows(snapshot)
    if rows:
        st.table(rows)
        st.download_button(
            "Export price notes",
            format_stash_export(export_rows),
            file_name="stash-pricer.txt",
        )
    else:
        render_empty_state(
            "Stash pricer needs captured stashes.",
            "Capture a stash snapshot with the bridge to seed these estimates.",
        )


def render_flip_scanner(client: LedgerApiClient) -> None:
    data = client.flips()
    if not data.flips:
        render_empty_state(
            "Deterministic engine did not find flips.",
            "Wait for new captures or expand your tracked queries before rerunning.",
        )
        return
    rows = [
        {
            "Query": flip.query_key,
            "Profit": round(flip.expected_profit, 3),
            "Liquidity": round(flip.liquidity_score, 3),
            "Expiry": flip.expiry_ts.isoformat(),
        }
        for flip in data.flips
    ]
    st.table(rows)


def render_craft_advisor(client: LedgerApiClient) -> None:
    data = client.crafts()
    if not data.crafts:
        render_empty_state(
            "No crafts surfaced from the oracle yet.",
            "Refresh after new captures to populate craft plans.",
        )
        return
    rows = [
        {
            "Plan": craft.plan_id,
            "EV": round(craft.ev, 3),
            "Cost": round(craft.craft_cost, 3),
            "Details": craft.details,
        }
        for craft in data.crafts
    ]
    st.table(rows)


def render_farming_roi(client: LedgerApiClient) -> None:
    leaderboard = client.leaderboard()
    if not leaderboard.leaderboard:
        render_empty_state(
            "No farming sessions recorded yet.",
            "Run deterministic sessions or sync the ingestion pipeline.",
        )
        return
    rows = [
        {
            "Session": entry.session_id,
            "Profit/hr": round(entry.profit_per_hour, 2),
            "Duration (h)": round(entry.duration_s / 3600, 2),
        }
        for entry in leaderboard.leaderboard
    ]
    st.table(rows)


def render_build_atlas(client: LedgerApiClient) -> None:
    builds = client.atlas_builds()
    if builds:
        st.table(
            [
                {
                    "Build": build.name,
                    "Specialization": build.specialization,
                    "Nodes": build.node_count,
                }
                for build in builds
            ]
        )
        detail = client.atlas_build_detail(builds[0].build_id)
        if detail:
            st.markdown(f"**{detail.name}** ({detail.specialization})")
            st.write(f"Nodes: {', '.join(detail.nodes)}")
            st.write(detail.notes)
    else:
        render_empty_state(
            "No atlas builds available.",
            "Register builds via the deterministic planner to populate this view.",
        )


def render_daily_plan(client: LedgerApiClient) -> None:
    plan = client.advisor_daily_plan()
    if not plan.plan_items:
        render_empty_state(
            "No plan items in this deterministic seed.",
            "Ensure flips and crafts feed into the advisor before refreshing.",
        )
        return
    rows = [
        {
            "Action": item.action,
            "Summary": item.summary,
            "Priority": item.priority,
        }
        for item in plan.plan_items
    ]
    st.table(rows)

def render_ops_runtime(client: LedgerApiClient) -> None:
    mode_label = "Local (in-process service)" if client.local_mode else "Remote API"
    st.metric("API mode", mode_label)

    state = st.session_state
    refresh_controls = st.columns((1.2, 1.4, 1.2, 2.2))
    refresh_clicked = refresh_controls[0].button(
        "Refresh now", key="ops_refresh_now", use_container_width=True
    )
    auto_refresh = refresh_controls[1].toggle(
        "Auto-refresh", value=True, key="ops_auto_refresh"
    )
    refresh_interval = refresh_controls[2].selectbox(
        "Interval (sec)",
        options=[10, 30, 60, 120],
        key="ops_refresh_interval",
        disabled=not auto_refresh,
    )
    last_success_at = state.get("ops_last_success_at")
    if isinstance(last_success_at, datetime):
        refresh_controls[3].write(
            f"Last successful refresh: `{_display_timestamp(last_success_at)}`"
        )
        refresh_controls[3].write(
            f"Snapshot age: `{format_age(age_minutes(last_success_at))}`"
        )
    else:
        refresh_controls[3].write("Last successful refresh: `none`")

    if refresh_clicked and hasattr(st, "rerun"):
        st.rerun()

    run_every = (
        f"{refresh_interval}s" if auto_refresh and hasattr(st, "fragment") else None
    )
    if auto_refresh and not hasattr(st, "fragment"):
        st.info("Auto-refresh is unavailable in this Streamlit build; use Refresh now.")

    def _render_ops_snapshot() -> None:
        telemetry = None
        try:
            telemetry = client.ops_dashboard()
            state["ops_last_telemetry"] = telemetry
            state["ops_last_success_at"] = datetime.now(timezone.utc)
            state["ops_last_error"] = None
        except Exception as exc:  # pragma: no cover - runtime path
            telemetry = state.get("ops_last_telemetry")
            state["ops_last_error"] = str(exc)
            if telemetry is None:
                render_error_state(
                    "Unable to load operational telemetry.",
                    "Verify API/service reachability and credentials, then refresh again.",
                )
                st.code(str(exc))
                return
            st.error(
                "Live refresh failed; showing the last successful telemetry snapshot."
            )
            st.caption(f"Refresh error: {exc}")

        summary = build_ops_summary(telemetry)
        issue_count = len(summary.issues)
        banner = f"System status: {summary.severity.upper()}"
        detail = f"{summary.headline} (issues: {issue_count})"
        if summary.severity == "critical":
            st.error(f"{banner} - {detail}")
        elif summary.severity == "warning":
            st.warning(f"{banner} - {detail}")
        else:
            st.success(f"{banner} - {detail}")

        st.markdown("#### Action queue")
        if summary.issues:
            for issue in summary.issues:
                st.markdown(
                    f"- **[{issue.severity.upper()}] {issue.title}** - "
                    f"{issue.detail} Action: {issue.remediation}"
                )
        else:
            st.success("All clear: no active operational issues detected.")

        ingest = telemetry.ingest_rate
        public_age = age_minutes(ingest.public_stash_last_seen)
        currency_age = age_minutes(ingest.currency_last_seen)
        telemetry_age = age_minutes(telemetry.timestamp)
        freshness_col1, freshness_col2, freshness_col3 = st.columns(3)
        freshness_col1.metric(
            "Public stash rec/min",
            f"{ingest.public_stash_records_per_minute:.1f}",
            delta=f"last seen {format_age(public_age)} ago",
        )
        freshness_col2.metric(
            "Currency rec/min",
            f"{ingest.currency_records_per_minute:.1f}",
            delta=f"last seen {format_age(currency_age)} ago",
        )
        freshness_col3.metric(
            "Telemetry snapshot age",
            format_age(telemetry_age),
            delta=f"at {_display_timestamp(telemetry.timestamp)}",
        )

        request_rate = telemetry.request_rate
        req_col1, req_col2, req_col3 = st.columns(3)
        req_col1.metric("Requests/min", f"{request_rate.requests_per_minute:.1f}")
        req_col2.metric("Error rate (%)", f"{request_rate.error_rate_percent:.1f}")
        req_col3.metric("Throttled (%)", f"{request_rate.throttled_percent:.1f}")

        if telemetry.checkpoint_health:
            st.markdown("#### Checkpoint health")
            st.table(
                [
                    {
                        "Cursor": entry.cursor_name,
                        "Last checkpoint": _display_timestamp(entry.last_checkpoint),
                        "Expected interval (min)": entry.expected_interval_minutes,
                        "Drift (min)": round(entry.drift_minutes, 2),
                        "Status": "Alert" if entry.alert else "OK",
                    }
                    for entry in telemetry.checkpoint_health
                ]
            )
        else:
            render_empty_state(
                "No checkpoint health data yet.",
                "Checkpoint instrumentation has not reported entries yet.",
            )

        if telemetry.slo_status:
            st.markdown("#### SLO status")
            st.table(
                [
                    {
                        "Stream": status.stream_name,
                        "Target (min)": status.target_minutes,
                        "Observed (min)": round(status.observed_minutes, 2),
                        "Within SLO": status.within_slo,
                        "Note": status.note or "",
                    }
                    for status in telemetry.slo_status
                ]
            )
        else:
            render_empty_state(
                "No SLO entries reported yet.",
                "SLO data will appear once policies are published.",
            )

        if telemetry.rate_limit_alerts:
            st.markdown("#### Rate limit alerts")
            st.table(
                [
                    {
                        "Status code": alert.status_code,
                        "Occurrences": alert.occurrences,
                        "Window (min)": alert.window_minutes,
                        "Severity": alert.severity,
                        "Alert": alert.alert,
                    }
                    for alert in telemetry.rate_limit_alerts
                ]
            )
        else:
            st.success("No rate limit alerts currently active.")

        clipboard_command = "python -m poe_trade.services.exilelens --endpoint http://localhost/v1/item/analyze --mode clipboard"
        watch_command = "python -m poe_trade.services.exilelens --watch-clipboard --endpoint http://localhost/v1/item/analyze"
        clipboard_available = shutil.which("exilelens")
        with st.expander("Clipboard capture helper (local only)"):
            if clipboard_available:
                st.success(f"`exilelens` entry point found at {clipboard_available}")
            else:
                st.warning(
                    "`exilelens` is not on PATH; install the package or activate the console script on your workstation."
                )
            st.caption(
                "This helper must run on your local machine to access the Path of Exile clipboard data."
            )
            st.markdown("**One-shot capture:**")
            st.code(clipboard_command, language="bash")
            st.markdown("**Watch mode:**")
            st.code(watch_command, language="bash")
        with st.expander("Raw telemetry JSON"):
            st.code(
                json.dumps(telemetry.model_dump(), default=str, indent=2),
                language="json",
            )

    if hasattr(st, "fragment"):

        @st.fragment(run_every=run_every)
        def _ops_fragment() -> None:
            _render_ops_snapshot()

        _ops_fragment()
    else:  # pragma: no cover - fallback for older streamlit
        _render_ops_snapshot()

def _display_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")

PAGE_REGISTRY: dict[str, Page] = {
    "Market Overview": Page(
        label="Market Overview",
        description="Quick snapshot of deterministic markets.",
        render=render_market_overview,
    ),
    "Stash Pricer": Page(
        label="Stash Pricer",
        description="Value your planned stash exports.",
        render=render_stash_pricer,
    ),
    "Flip Scanner": Page(
        label="Flip Scanner",
        description="List deterministic flip opportunities.",
        render=render_flip_scanner,
    ),
    "Craft Advisor": Page(
        label="Craft Advisor",
        description="Curated craft plans for today.",
        render=render_craft_advisor,
    ),
    "Farming ROI": Page(
        label="Farming ROI",
        description="ROI leaderboard from seeded sessions.",
        render=render_farming_roi,
    ),
    "BuildAtlas": Page(
        label="BuildAtlas",
        description="Atlas build summaries and details.",
        render=render_build_atlas,
    ),
    "Daily Plan": Page(
        label="Daily Plan",
        description="Advisor daily plan generated from services.",
        render=render_daily_plan,
    ),
    "Ops & Runtime": Page(
        label="Ops & Runtime",
        description="Operational telemetry, rate limits, and clipboard guidance.",
        render=render_ops_runtime,
    ),
    "Bridge Controls": Page(
        label="Bridge Controls",
        description="Manual local bridge actions for capture, clipboard, overlay, and filters.",
        render=render_bridge_controls,
    ),
}

MENU_ITEMS: list[MenuItem] = [
    MenuItem("Market Overview", "Market Overview", "📈", "Markets"),
    MenuItem("Stash Pricer", "Stash Pricer", "💰", "Markets"),
    MenuItem("Flip Scanner", "Flip Scanner", "🧭", "Advisors"),
    MenuItem("Craft Advisor", "Craft Advisor", "🛠️", "Advisors"),
    MenuItem("Farming ROI", "Farming ROI", "🚜", "Advisors"),
    MenuItem("BuildAtlas", "BuildAtlas", "🗺️", "Atlas"),
    MenuItem("Daily Plan", "Daily Plan", "📋", "Advisors"),
    MenuItem("Ops & Runtime", "Ops & Runtime", "⚙️", "Operations"),
    MenuItem("Bridge Controls", "Bridge Controls", "🔗", "Controls"),
]

def _group_menu_items() -> dict[str, list[MenuItem]]:
    groups: dict[str, list[MenuItem]] = {}
    for item in MENU_ITEMS:
        groups.setdefault(item.group, []).append(item)
    return groups

def _render_sidebar_navigation() -> MenuItem:
    grouped = _group_menu_items()
    selected = st.sidebar.selectbox(
        "Focus area",
        MENU_ITEMS,
        format_func=lambda entry: f"{entry.icon} {entry.label}",
        key="ledger_nav",
    )
    st.sidebar.markdown("---")
    for group, entries in grouped.items():
        plural = "view" if len(entries) == 1 else "views"
        st.sidebar.markdown(f"**{group}** · {len(entries)} {plural}")
    return selected

def run() -> None:
    if st is None:
        print(
            "Streamlit is not installed. Install with `pip install streamlit` and retry."
        )
        return
    st.set_page_config(page_title=DESCRIPTION, layout="wide")
    _apply_streamlit_theme()
    client = LedgerApiClient()
    st.sidebar.title("Ledger UI")
    st.sidebar.caption("Deterministic render harness")
    st.sidebar.caption("Groupings highlight workflow focus")
    selected_menu = _render_sidebar_navigation()
    page = PAGE_REGISTRY[selected_menu.key]
    render_page_header(page.label, page.description)
    page.render(client)


if __name__ == "__main__":
    run()
