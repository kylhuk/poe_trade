from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List


@dataclass(frozen=True)
class CharacterState:
    chaos: float
    current_power: float
    map_completion: float


@dataclass(frozen=True)
class BuildMetric:
    name: str
    potential_gain: float
    required_chaos: float
    rank: int

    def gain_per_chaos(self) -> float:
        return self.potential_gain / max(1.0, self.required_chaos)


@dataclass(frozen=True)
class UpgradeStep:
    name: str
    description: str
    priority: float
    cost: float
    phase: str
    rationale: str


class AtlasCoach:
    PHASE_ORDER = {"cheap": 0, "medium": 1, "stretch": 2}
    LOW_CONFIDENCE_THRESHOLD = 0.5

    def plan(self, state: CharacterState, candidates: Iterable[BuildMetric]) -> List[UpgradeStep]:
        steps: List[UpgradeStep] = []
        available_chaos = max(1.0, state.chaos)
        for metric in candidates:
            gain_per_chaos = metric.gain_per_chaos()
            phase = self._determine_phase(metric.required_chaos, available_chaos)
            conflict_reasons: List[str] = []
            if metric.required_chaos > state.chaos:
                conflict_reasons.append("budget exceeded")
            if gain_per_chaos < self.LOW_CONFIDENCE_THRESHOLD:
                conflict_reasons.append("low confidence")
            priority = round(
                gain_per_chaos - metric.rank * 0.01 - len(conflict_reasons) * 0.05,
                4,
            )
            description = (
                f"Upgrade {metric.name}: gain_per_chaos={gain_per_chaos:.3f},"
                f" target_power={state.current_power + metric.potential_gain:.1f}"
            )
            rationale = (
                f"phase={phase}; cost={metric.required_chaos:.1f}; "
                + ("; ".join(conflict_reasons) if conflict_reasons else "confidence ok")
            )
            steps.append(
                UpgradeStep(
                    name=metric.name,
                    description=description,
                    priority=priority,
                    cost=metric.required_chaos,
                    phase=phase,
                    rationale=rationale,
                )
            )
        steps.sort(
            key=lambda step: (
                -step.priority,
                self.PHASE_ORDER.get(step.phase, 3),
                step.cost,
                step.name,
            )
        )
        return steps

    def _determine_phase(self, cost: float, available: float) -> str:
        if cost <= available * 0.35:
            return "cheap"
        if cost <= available * 0.75:
            return "medium"
        return "stretch"
