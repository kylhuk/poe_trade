from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Sequence, List


@dataclass(frozen=True)
class BuildSnapshot:
    name: str
    power: float
    rank: int
    cost: float = 0.0
    meta_risk: float = 0.0


@dataclass(frozen=True)
class DeltaEntry:
    name: str
    rank_change: int
    delta_power: float
    delta_cost: float
    delta_meta_risk: float
    delta_score: float
    severity: str
    current_rank: int


SEVERITY_SCHEMA = (
    ("critical", {"rank_change": 3, "delta_score": 12.0}),
    ("major", {"rank_change": 1, "delta_score": 6.0}),
    ("minor", {"delta_score": 3.0}),
)


def _severity_priority(severity: str) -> int:
    mapping = {"critical": 0, "major": 1, "minor": 2, "stable": 3}
    return mapping.get(severity, 4)


def _determine_severity(rank_change: int, delta_score: float, had_previous: bool) -> str:
    if not had_previous:
        return "stable"
    for label, thresholds in SEVERITY_SCHEMA:
        rank_threshold = thresholds.get("rank_change")
        score_threshold = thresholds.get("delta_score")
        rank_ok = rank_threshold is not None and rank_change >= rank_threshold
        score_ok = score_threshold is not None and delta_score >= score_threshold
        if rank_ok or score_ok:
            return label
    return "stable"


def compute_patch_delta(
    previous: Sequence[BuildSnapshot], current: Sequence[BuildSnapshot]
) -> List[DeltaEntry]:
    previous_map: Dict[str, BuildSnapshot] = {entry.name: entry for entry in previous}
    deltas: List[DeltaEntry] = []
    for current_entry in current:
        prev_entry = previous_map.get(current_entry.name)
        had_previous = prev_entry is not None
        prior_power = prev_entry.power if prev_entry else 0.0
        prior_rank = prev_entry.rank if prev_entry else current_entry.rank
        prior_cost = prev_entry.cost if prev_entry else 0.0
        prior_meta = prev_entry.meta_risk if prev_entry else 0.0
        rank_change = prior_rank - current_entry.rank
        delta_power = round(current_entry.power - prior_power, 2)
        delta_cost = round(current_entry.cost - prior_cost, 2)
        delta_meta_risk = round(current_entry.meta_risk - prior_meta, 2)
        delta_score = round(
            rank_change * 2.5
            + delta_power * 0.35
            - max(delta_cost, 0.0) * 0.25
            - max(delta_meta_risk, 0.0) * 0.4,
            2,
        )
        severity = _determine_severity(rank_change, delta_score, had_previous)
        deltas.append(
            DeltaEntry(
                name=current_entry.name,
                rank_change=rank_change,
                delta_power=delta_power,
                delta_cost=delta_cost,
                delta_meta_risk=delta_meta_risk,
                delta_score=delta_score,
                severity=severity,
                current_rank=current_entry.rank,
            )
        )
    deltas.sort(
        key=lambda entry: (
            _severity_priority(entry.severity),
            -entry.delta_score,
            -entry.rank_change,
            entry.current_rank,
            entry.name,
        )
    )
    return deltas
