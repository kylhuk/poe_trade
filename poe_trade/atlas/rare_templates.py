from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Tuple
import hashlib


@dataclass(frozen=True)
class RareTemplate:
    id: str
    label: str
    vector: Tuple[float, ...]
    price_distribution: Dict[str, float]
    liquidity: Dict[str, float]


@dataclass(frozen=True)
class TemplateAllocation:
    selection: Dict[str, RareTemplate]
    total_cost: float
    unmet_constraints: Tuple[str, ...]


def _hash_template_key(label: str, vector: Tuple[float, ...], seed: int) -> str:
    fingerprint = f"{seed}:{label}:{','.join(str(v) for v in vector)}"
    return hashlib.sha256(fingerprint.encode()).hexdigest()[:12]


def build_template_from_vector(vector: Iterable[float], label: str, seed: int) -> RareTemplate:
    values = tuple(float(value) for value in vector)
    base_id = _hash_template_key(label, values, seed)
    low = round(min(values) * 10 + 5, 2)
    median = round((sum(values) / len(values)) * 2, 2)
    high = round(max(values) * 12 + 10, 2)
    velocity = round((median % 7) / 7 + 0.25, 3)
    liquidity = {"velocity": velocity, "stock": len(values) * 5}
    return RareTemplate(
        id=base_id,
        label=label,
        vector=values,
        price_distribution={"low": low, "median": median, "high": high},
        liquidity=liquidity,
    )


def deterministic_budget_selector(templates: Iterable[RareTemplate], chaos_budget: float) -> RareTemplate:
    ordered = sorted(
        templates,
        key=lambda template: (
            template.liquidity["velocity"],
            template.price_distribution["median"],
            template.id,
        ),
    )
    for template in ordered:
        if template.price_distribution["median"] <= chaos_budget:
            return template
    return min(ordered, key=lambda template: template.price_distribution["median"])


def _slot_score(template: RareTemplate, preference: float) -> float:
    liquidity_factor = template.liquidity.get("velocity", 0.0)
    return template.price_distribution["median"] - liquidity_factor * preference * 5.0


def _select_template_for_slot(
    templates: Iterable[RareTemplate], slot_budget: float, preference: float
) -> RareTemplate:
    weighted = sorted(
        templates,
        key=lambda template: (
            _slot_score(template, preference),
            template.price_distribution["median"],
            template.id,
        ),
    )
    for candidate in weighted:
        if candidate.price_distribution["median"] <= slot_budget:
            return candidate
    return min(weighted, key=lambda template: (template.price_distribution["median"], template.id))


def allocate_templates_by_slot(
    slot_templates: Dict[str, Iterable[RareTemplate]],
    total_budget: float,
    liquidity_preference: Mapping[str, float],
) -> TemplateAllocation:
    if not slot_templates:
        return TemplateAllocation(selection={}, total_cost=0.0, unmet_constraints=())

    preference_weights = [liquidity_preference.get(slot, 1.0) for slot in slot_templates]
    preference_sum = sum(preference_weights) if any(preference_weights) else float(len(slot_templates))
    selection: Dict[str, RareTemplate] = {}
    unmet: List[str] = []
    total_cost = 0.0

    for slot in sorted(slot_templates):
        templates = list(slot_templates[slot])
        if not templates:
            unmet.append(f"{slot} missing_templates")
            continue
        slot_pref = liquidity_preference.get(slot, 1.0)
        slot_budget = (
            total_budget * (slot_pref / preference_sum)
            if preference_sum
            else total_budget / max(1, len(slot_templates))
        )
        candidate = _select_template_for_slot(templates, slot_budget, slot_pref)
        cost = candidate.price_distribution["median"]
        total_cost += cost
        selection[slot] = candidate
        if cost > slot_budget:
            unmet.append(f"{slot} budget_exceeded median={cost:.2f} budget={slot_budget:.2f}")

    if total_cost > total_budget:
        unmet.append(
            f"total_budget_exceeded total_cost={total_cost:.2f} total_budget={total_budget:.2f}"
        )
    return TemplateAllocation(
        selection=selection,
        total_cost=round(total_cost, 2),
        unmet_constraints=tuple(unmet),
    )
