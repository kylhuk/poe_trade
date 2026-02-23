"""Streamlit entrypoint with page router and helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

try:
    import streamlit as st
except ImportError:  # pragma: no cover - optional UI dependency
    st = None  # type: ignore[assignment]

from .client import LedgerApiClient

DESCRIPTION = "Wraeclast Ledger dashboard".strip()


@dataclass(frozen=True)
class Page:
    label: str
    description: str
    render: Callable[[LedgerApiClient], None]


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
    st.subheader("Market Overview")
    st.caption("Curated snapshots for deterministic currency lanes.")
    if rows:
        avg_confidence = sum(row["confidence"] for row in rows) / len(rows)
        st.metric("Confidence average", f"{avg_confidence:.2f}")
        st.table(rows)
    else:
        st.info("No price observations yet.")


def render_stash_pricer(client: LedgerApiClient) -> None:
    snapshot = client.stash_pricing()
    st.subheader("Stash Pricer")
    st.caption("Estimate worth of curated stash contents.")
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
        st.info("There are no stash entries yet.")


def render_flip_scanner(client: LedgerApiClient) -> None:
    data = client.flips()
    st.subheader("Flip Scanner")
    st.caption("Highlights deterministic flip opportunities.")
    if not data.flips:
        st.info("Deterministic engine did not find flips.")
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
    st.subheader("Craft Advisor")
    st.caption("Proposed crafts with deterministic EV.")
    if not data.crafts:
        st.info("No crafts surfaced from the oracle yet.")
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
    st.subheader("Farming ROI")
    st.caption("Session ROI leaderboard from deterministic data.")
    if not leaderboard.leaderboard:
        st.info("No farming sessions recorded yet.")
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
    st.subheader("BuildAtlas")
    st.caption("Summary of deterministic atlas builds.")
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
        st.info("No atlas builds available.")


def render_daily_plan(client: LedgerApiClient) -> None:
    plan = client.advisor_daily_plan()
    st.subheader("Daily Plan")
    st.caption("Priority actions generated from flips and crafts.")
    if not plan.plan_items:
        st.info("No plan items in this deterministic seed.")
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
}


def run() -> None:
    if st is None:
        print(
            "Streamlit is not installed. Install with `pip install streamlit` and retry."
        )
        return
    client = LedgerApiClient()
    st.set_page_config(page_title=DESCRIPTION)
    st.sidebar.title("Ledger UI")
    st.sidebar.caption("Deterministic render harness")
    choice = st.sidebar.radio("Navigate", list(PAGE_REGISTRY.keys()))
    page = PAGE_REGISTRY[choice]
    st.header(page.label)
    st.write(page.description)
    page.render(client)


if __name__ == "__main__":
    run()
