from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Mapping, Sequence

from ..etl.models import CurrencySnapshot
from ..etl.pipeline import run_etl_pipeline
from .chaos_scale import ChaosScaleEngine
from .flip_finder import FlipOpportunity, find_flip_opportunities
from .forge_oracle import CraftAction, CraftOpportunity, ForgeOracle
from .price_stats import PriceStatsRow, compute_price_stats
from .session_ledger import FarmingSessionRow, SessionSnapshot, summarize_session
from .strategy_backtest import StrategyRegistry
from .stash_pricer import StashPriceSuggestion, StashPricer


@dataclass
class AnalyticsPipelineResult:
    listings: Sequence[Mapping[str, object]]
    price_stats: Mapping[str, object]
    stash_suggestions: Sequence[Mapping[str, object]]
    flip_opportunities: Sequence[Mapping[str, object]]
    craft_opportunities: Sequence[Mapping[str, object]]
    farming_sessions: Sequence[Mapping[str, object]]
    strategy_results: Sequence[Mapping[str, object]]


def orchestrate_analytics(
    rows: Iterable[Mapping[str, object]],
    currency_snapshots: Iterable[CurrencySnapshot],
    sessions: Iterable[SessionSnapshot],
) -> AnalyticsPipelineResult:
    etl_result = run_etl_pipeline(rows)
    chaos = ChaosScaleEngine.from_snapshots(currency_snapshots)
    normalized_values = {
        listing.listing_uid: chaos.normalize_listing(listing.price_amount, listing.price_currency)
        for listing in etl_result.listings
    }
    price_stats = compute_price_stats(normalized_values.values())
    price_bucket = datetime.now(timezone.utc)
    price_stats_row = PriceStatsRow.from_prices(
        "global",
        "global",
        price_bucket,
        normalized_values.values(),
        metadata={"source": "analytics_pipeline"},
    )
    stash_snapshot_id = f"snapshot-{etl_result.metrics.get('total_rows', 0)}"
    stash_suggestions = StashPricer.suggest_prices(
        stash_snapshot_id,
        etl_result.listings,
        price_stats,
    )
    flips = find_flip_opportunities(
        etl_result.listings,
        price_stats,
        price_overrides=normalized_values,
    )
    oracle = ForgeOracle(
        (
            CraftAction(name="add_expl", cost=2, value_gain=4),
            CraftAction(name="reroll", cost=5, value_gain=8),
        )
    )
    craft_opportunities: list[CraftOpportunity]
    craft_opportunities = []
    base_price = price_stats.get("p50", 0.0)
    for item in etl_result.items:
        plan = oracle.best_plan(depth=2)
        if not plan:
            continue
        craft_opportunities.append(
            oracle.evaluate_plan(
                league=item.league,
                item_uid=item.item_uid,
                current_price=base_price,
                plan=plan,
            )
        )
        break
    session_rows = [summarize_session(session) for session in sessions]
    strategy_registry = StrategyRegistry.with_builtin_strategies()
    strategy_results = strategy_registry.backtest(sessions, price_stats)
    listing_dicts = [
        {
            "listing_id": listing.listing_uid,
            "listing_uid": listing.listing_uid,
            "price_amount": listing.price_amount,
            "currency": listing.price_currency,
            "price_chaos": normalized_values.get(listing.listing_uid, listing.price_amount),
        }
        for listing in etl_result.listings
    ]
    flip_records = [flip.to_row() for flip in flips]
    craft_records = [opportunity.to_row() for opportunity in craft_opportunities]
    return AnalyticsPipelineResult(
        listings=listing_dicts,
        price_stats=price_stats_row.to_row(),
        stash_suggestions=[suggestion.to_row() for suggestion in stash_suggestions],
        flip_opportunities=flip_records,
        craft_opportunities=craft_records,
        farming_sessions=[session.to_row() for session in session_rows],
        strategy_results=[result.to_row() for result in strategy_results],
    )
