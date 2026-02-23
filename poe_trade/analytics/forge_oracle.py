from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import combinations
from typing import Iterable, Sequence


@dataclass(frozen=True)
class CraftAction:
    name: str
    cost: float
    value_gain: float


@dataclass(frozen=True)
class CraftPlan:
    steps: tuple[CraftAction, ...]
    expected_value: float


@dataclass(frozen=True)
class CraftOpportunity:
    detected_at: datetime
    league: str
    item_uid: str
    plan_id: str
    craft_cost: float
    est_after_price: float
    ev: float
    risk_score: float
    details: str

    def to_row(self) -> dict[str, object]:
        return {
            "detected_at": self.detected_at.isoformat(),
            "league": self.league,
            "item_uid": self.item_uid,
            "plan_id": self.plan_id,
            "craft_cost": self.craft_cost,
            "est_after_price": self.est_after_price,
            "ev": self.ev,
            "risk_score": self.risk_score,
            "details": self.details,
        }


class ForgeOracle:
    def __init__(self, actions: Iterable[CraftAction]):
        self.actions = tuple(actions)

    def enumerate_plans(self, depth: int = 1) -> Sequence[CraftPlan]:
        if depth <= 0:
            return ()
        plans: list[CraftPlan] = []
        for size in range(1, min(depth, len(self.actions)) + 1):
            for combo in combinations(self.actions, size):
                cost = sum(action.cost for action in combo)
                gain = sum(action.value_gain for action in combo)
                plans.append(CraftPlan(steps=combo, expected_value=gain - cost))
        return plans

    def best_plan(self, depth: int = 2) -> CraftPlan | None:
        plans = self.enumerate_plans(depth)
        if not plans:
            return None
        return max(plans, key=lambda plan: plan.expected_value)

    def compute_ev(self, plan: CraftPlan) -> float:
        return plan.expected_value

    def evaluate_plan(
        self,
        league: str,
        item_uid: str,
        current_price: float,
        plan: CraftPlan,
        detected_at: datetime | None = None,
    ) -> CraftOpportunity:
        now = detected_at or datetime.now(timezone.utc)
        plan_id = "+".join(action.name for action in plan.steps)
        craft_cost = sum(action.cost for action in plan.steps)
        value_gain = sum(action.value_gain for action in plan.steps)
        est_after = current_price + value_gain
        risk_score = round(0.05 * len(plan.steps), 3)
        ev = round(est_after - current_price - craft_cost - risk_score, 3)
        details = f"gain={value_gain:.2f}, cost={craft_cost:.2f}, risk={risk_score:.3f}"
        return CraftOpportunity(
            detected_at=now,
            league=league,
            item_uid=item_uid,
            plan_id=plan_id,
            craft_cost=craft_cost,
            est_after_price=est_after,
            ev=ev,
            risk_score=risk_score,
            details=details,
        )
