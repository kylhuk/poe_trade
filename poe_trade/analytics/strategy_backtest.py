from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Mapping, Sequence

from .session_ledger import SessionSnapshot

StrategyFunc = Callable[[SessionSnapshot, Mapping[str, float]], Mapping[str, object]]


@dataclass(frozen=True)
class StrategyKPITargets:
    profit_per_hour: str
    expected_value: str
    liquidity: str
    variance: str

    def to_row(self) -> dict[str, str]:
        return {
            "profit_per_hour": self.profit_per_hour,
            "expected_value": self.expected_value,
            "liquidity": self.liquidity,
            "variance": self.variance,
        }


@dataclass(frozen=True)
class StrategyDefinition:
    strategy_id: str
    title: str
    claim_summary: str
    tags: tuple[str, ...]
    sources: tuple[str, ...]
    required_inputs: tuple[str, ...]
    kpi_targets: StrategyKPITargets


@dataclass(frozen=True)
class StrategyKPISummary:
    profit_per_hour: float
    expected_value: float
    liquidity: float
    variance: float

    def to_row(self) -> dict[str, float]:
        return {
            "profit_per_hour": self.profit_per_hour,
            "expected_value": self.expected_value,
            "liquidity": self.liquidity,
            "variance": self.variance,
        }


@dataclass(frozen=True)
class StrategyBacktestResult:
    definition: StrategyDefinition
    success_rate: float
    triggers: int
    kpi_summary: StrategyKPISummary

    def to_row(self) -> dict[str, object]:
        return {
            "strategy_id": self.definition.strategy_id,
            "title": self.definition.title,
            "claim_summary": self.definition.claim_summary,
            "tags": self.definition.tags,
            "sources": self.definition.sources,
            "required_inputs": self.definition.required_inputs,
            "kpi_targets": self.definition.kpi_targets.to_row(),
            "success_rate": self.success_rate,
            "triggers": self.triggers,
            "kpi_summary": self.kpi_summary.to_row(),
        }


def _safe_non_negative(value: float | int | None) -> float:
    if value is None:
        return 0.0
    return float(value)


def _summarize_kpis(stats: Mapping[str, float]) -> StrategyKPISummary:
    listing_count = max(1, int(stats.get("listing_count", 1)))
    median = _safe_non_negative(stats.get("p50", 0.0))
    spread = _safe_non_negative(stats.get("spread", 0.0))
    volatility = _safe_non_negative(stats.get("volatility", 0.0))
    liquidity = _safe_non_negative(stats.get("liquidity_score", 0.0))
    return StrategyKPISummary(
        profit_per_hour=median / listing_count,
        expected_value=median + spread * 0.1,
        liquidity=liquidity,
        variance=volatility,
    )


def _make_delta_strategy(stat_key: str, multiplier: float) -> StrategyFunc:
    def _decision(snapshot: SessionSnapshot, stats: Mapping[str, float]) -> Mapping[str, object]:
        delta = snapshot.end_value - snapshot.start_value
        baseline = _safe_non_negative(stats.get(stat_key, 0.0))
        threshold = baseline * multiplier
        return {"expected_win": delta >= threshold}

    return _decision


def _build_strategy_definitions() -> Sequence[StrategyDefinition]:
    return (
        StrategyDefinition(
            strategy_id="S01",
            title="Currency exchange market making (illiquid pairs)",
            claim_summary=(
                "Profit from stable spreads by placing buy/sell orders as a liquidity provider "
                "on illiquid currency pairs."
            ),
            tags=("currency", "market-making", "liquidity"),
            sources=(
                "https://www.reddit.com/r/pathofexile/comments/1e7rcvn/"
                "currency_trading_101_market_making_illiquid_pairs/",
            ),
            required_inputs=("listing_spreads", "fill_rates", "session_hold_time"),
            kpi_targets=StrategyKPITargets(
                profit_per_hour="Spread capture per hour versus resting order time",
                expected_value="Orderbook EV before matching fees",
                liquidity="Fill rate / resting depth on each side",
                variance="Holding-time drawdown windows",
            ),
        ),
        StrategyDefinition(
            strategy_id="S02",
            title="Bulk trading convenience premium",
            claim_summary=(
                "Bulk sells and buys trade faster and command a premium/discount in return for "
                "convenience."
            ),
            tags=("bulk", "pricing", "time-value"),
            sources=(
                "https://www.reddit.com/r/pathofexile/comments/uoo849/"
                "small_guide_for_bulk_trading_for_new_players/",
            ),
            required_inputs=("bulk_price_distribution", "time_to_sell", "inventory_depth"),
            kpi_targets=StrategyKPITargets(
                profit_per_hour="Delta between bulk and single-unit price per hour",
                expected_value="Opportunity cost of tied-up stock",
                liquidity="Units sold per chunk / time to clear",
                variance="Price swing between bulk/single orders",
            ),
        ),
        StrategyDefinition(
            strategy_id="S03",
            title="Expedition-focused mapping / logbooks",
            claim_summary=(
                "Expedition mapping delivers consistent profit via raw currency plus logbook rewards "
                "and scales with investment."
            ),
            tags=("expedition", "mapping", "logbook"),
            sources=("https://www.poe-vault.com/guides/guide-for-expedition-in-path-of-exile",),
            required_inputs=("session_tags", "logbook_values", "map_returns"),
            kpi_targets=StrategyKPITargets(
                profit_per_hour="Reward per hour with logbook bonus",
                expected_value="Expedition run EV from entry fees and loot",
                liquidity="Speed of logbook value realization",
                variance="Loot spread between runs",
            ),
        ),
        StrategyDefinition(
            strategy_id="S04",
            title="Expedition-only map routing",
            claim_summary=(
                "Rush to Expedition, complete it, and exit quickly while remaining profit-per-hour positive."
            ),
            tags=("expedition", "routing", "efficiency"),
            sources=(
                "https://www.reddit.com/r/pathofexile/comments/1697r86/"
                "what_are_some_currency_making_methods_other_than/",
            ),
            required_inputs=("session_tags", "map_costs", "scarab_values"),
            kpi_targets=StrategyKPITargets(
                profit_per_hour="Clean run profit divided by run time",
                expected_value="Net after map/scarab costs",
                liquidity="Speed of leaving post-run loot",
                variance="Deviation between full clear and rush runs",
            ),
        ),
        StrategyDefinition(
            strategy_id="S05",
            title="Delve fossils/resonators",
            claim_summary=(
                "Modern Delve fossil/resonator runs remain liquid and profitable on average."
            ),
            tags=("delve", "crafting", "currency"),
            sources=(
                "https://www.reddit.com/r/pathofexile/comments/1697r86/"
                "what_are_some_currency_making_methods_other_than/",
            ),
            required_inputs=("session_tags", "delve_loot", "fossil_prices"),
            kpi_targets=StrategyKPITargets(
                profit_per_hour="Fossil drop value per delve hour",
                expected_value="Resonator sell EV vs cost",
                liquidity="Time to flip fossils/resonators",
                variance="Tier dispersion in pack yields",
            ),
        ),
        StrategyDefinition(
            strategy_id="S06",
            title="Blighted maps for steady profit (low gear)",
            claim_summary=(
                "Blighted maps generate consistent profit even on modest builds when capturing key oils/cards."
            ),
            tags=("blight", "maps", "stability"),
            sources=(
                "https://www.reddit.com/r/pathofexile/comments/1697r86/"
                "what_are_some_currency_making_methods_other_than/",
            ),
            required_inputs=("session_tags", "oil_values", "blight_card_prices"),
            kpi_targets=StrategyKPITargets(
                profit_per_hour="Oil/card haul divided by clear time",
                expected_value="Average map drop EV",
                liquidity="Card sell-through vs map drop frequency",
                variance="Outcome spread per blighted map",
            ),
        ),
        StrategyDefinition(
            strategy_id="S07",
            title="Invitation farming",
            claim_summary=(
                "Invitations yield steady returns when runners tag sessions per invitation type."
            ),
            tags=("invitation", "farming", "tagging"),
            sources=(
                "https://www.reddit.com/r/pathofexile/comments/1697r86/"
                "what_are_some_currency_making_methods_other_than/",
            ),
            required_inputs=("session_tags", "invitation_rewards", "sell_vs_run"),
            kpi_targets=StrategyKPITargets(
                profit_per_hour="Reward per invitation run/hour",
                expected_value="Sell price EV minus entry fee",
                liquidity="How fast invitations flip",
                variance="Prize spread per invitation type",
            ),
        ),
        StrategyDefinition(
            strategy_id="S08",
            title="Essence farming (and Essence + Harvest)",
            claim_summary=(
                "Essence farming, including Harvest combinations, stays reliable early and scales in bulk."
            ),
            tags=("essence", "harvest", "farming"),
            sources=(
                "https://www.reddit.com/r/pathofexile/comments/1697r86/"
                "what_are_some_currency_making_methods_other_than/",
            ),
            required_inputs=("session_tags", "essence_tiers", "harvest_loot"),
            kpi_targets=StrategyKPITargets(
                profit_per_hour="Tier-weighted essence haul per hour",
                expected_value="Bulk EV per essence type",
                liquidity="Bulk premium vs single-piece sales",
                variance="Tier distribution volatility",
            ),
        ),
        StrategyDefinition(
            strategy_id="S09",
            title="Profit crafting: flasks via annul keep-good-mod",
            claim_summary=(
                "Buy two-mod flasks, annul to keep a strong modifier, then resell for profit."
            ),
            tags=("crafting", "flasks", "annul"),
            sources=(
                "https://www.reddit.com/r/pathofexile/comments/1otse86/"
                "i_know_its_kind_of_telling_on_your_secret_money/",
            ),
            required_inputs=("craft_actions", "flask_prices", "annul_rate"),
            kpi_targets=StrategyKPITargets(
                profit_per_hour="Net per-annul profit divided by craft time",
                expected_value="Post-craft EV vs input cost",
                liquidity="Flask sell-through compared to craft volume",
                variance="Annul outcome dispersion",
            ),
        ),
        StrategyDefinition(
            strategy_id="S10",
            title="Harvest reforge for saleable rares",
            claim_summary=(
                "Harvest reforges on targeted bases, such as rings, repeatedly produce saleable rares with positive EV."
            ),
            tags=("harvest", "crafting", "reforge"),
            sources=(
                "https://www.reddit.com/r/pathofexile/comments/1otse86/"
                "i_know_its_kind_of_telling_on_your_secret_money/",
            ),
            required_inputs=("craft_actions", "harvest_currency", "fp_loose_prices"),
            kpi_targets=StrategyKPITargets(
                profit_per_hour="Net reforge profit per hour",
                expected_value="Harverst EV vs base price",
                liquidity="Refined rare sell rate",
                variance="Reforge outcome spread",
            ),
        ),
        StrategyDefinition(
            strategy_id="S11",
            title="Targeted reforge spam on influenced bases",
            claim_summary=(
                "Reforge influenced bases (e.g., Shaper shields) until high-value mods appear, tracking saturation."
            ),
            tags=("crafting", "influence", "reforge"),
            sources=(
                "https://www.reddit.com/r/pathofexile/comments/1otse86/"
                "i_know_its_kind_of_telling_on_your_secret_money/",
            ),
            required_inputs=("listing_mods", "influenced_bases", "market_depth"),
            kpi_targets=StrategyKPITargets(
                profit_per_hour="Net reforge profit over time",
                expected_value="Chance-weighted sale EV",
                liquidity="Saturation-adjusted listing depth",
                variance="Mod spread between reforges",
            ),
        ),
        StrategyDefinition(
            strategy_id="S12",
            title="Systematic liquidation (everything sells if listed)",
            claim_summary=(
                "Consistently liquidate currencies/fragments/scarabs to accumulate small but reliable gains."
            ),
            tags=("liquidation", "currencies", "fragments"),
            sources=(
                "https://www.reddit.com/r/pathofexile/comments/1697r86/"
                "what_are_some_currency_making_methods_other_than/",
            ),
            required_inputs=("listing_depth", "weekly_profit", "currency_categories"),
            kpi_targets=StrategyKPITargets(
                profit_per_hour="Sell everything profit per hour",
                expected_value="Weekly liquidation EV per bucket",
                liquidity="Sale rate for small currencies",
                variance="Category spread across weeks",
            ),
        ),
    )


BUILTIN_STRATEGY_DEFINITIONS: dict[str, StrategyDefinition] = {
    definition.strategy_id: definition
    for definition in _build_strategy_definitions()
}


_STRATEGY_DECISION_CONFIGS: dict[str, tuple[str, float]] = {
    "S01": ("spread", 0.2),
    "S02": ("liquidity_score", 0.1),
    "S03": ("p50", 0.05),
    "S04": ("volatility", 0.3),
    "S05": ("p75", 0.1),
    "S06": ("p25", 0.15),
    "S07": ("listing_count", 0.05),
    "S08": ("p90", 0.05),
    "S09": ("spread", 0.4),
    "S10": ("volatility", 0.25),
    "S11": ("liquidity_score", 0.2),
    "S12": ("listing_count", 0.1),
}


_BUILTIN_STRATEGY_DETECTORS: dict[str, StrategyFunc] = {
    strategy_id: _make_delta_strategy(stat_key, multiplier)
    for strategy_id, (stat_key, multiplier) in _STRATEGY_DECISION_CONFIGS.items()
}


class StrategyRegistry:
    def __init__(self) -> None:
        self._strategies: dict[str, tuple[StrategyDefinition, StrategyFunc]] = {}

    def register(self, definition: StrategyDefinition, func: StrategyFunc) -> None:
        self._strategies[definition.strategy_id] = (definition, func)

    def backtest(
        self,
        sessions: Iterable[SessionSnapshot],
        stats: Mapping[str, float],
    ) -> Sequence[StrategyBacktestResult]:
        results: list[StrategyBacktestResult] = []
        for definition, strategy in self._strategies.values():
            triggers = 0
            successes = 0
            for session in sessions:
                decision = strategy(session, stats)
                if not decision:
                    continue
                triggers += 1
                if decision.get("expected_win", False):
                    successes += 1
            rate = successes / triggers if triggers else 0.0
            results.append(
                StrategyBacktestResult(
                    definition=definition,
                    success_rate=rate,
                    triggers=triggers,
                    kpi_summary=_summarize_kpis(stats),
                )
            )
        return results

    @classmethod
    def with_builtin_strategies(cls) -> "StrategyRegistry":
        registry = cls()
        for strategy_id, definition in BUILTIN_STRATEGY_DEFINITIONS.items():
            detector = _BUILTIN_STRATEGY_DETECTORS.get(strategy_id)
            if detector:
                registry.register(definition, detector)
        return registry

    @classmethod
    def builtin_definitions(cls) -> dict[str, StrategyDefinition]:
        return dict(BUILTIN_STRATEGY_DEFINITIONS)
