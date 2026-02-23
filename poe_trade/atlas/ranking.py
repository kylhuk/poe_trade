from dataclasses import dataclass
from typing import Dict, List

from .models import Genome
from .bench import BenchResult

@dataclass
class CostDistribution:
    p10: float
    p50: float
    p90: float


def compute_cost_distribution(genome: Genome) -> CostDistribution:
    base = len(genome.supports) * 15 + sum(genome.attributes.values()) * 0.3
    return CostDistribution(
        p10=round(base * 0.6, 1),
        p50=round(base, 1),
        p90=round(base * 1.4, 1),
    )


@dataclass
class DifficultyScore:
    score: float
    reasons: List[str]


def compute_difficulty(result: BenchResult) -> DifficultyScore:
    base = result.metrics.survival * 0.4 + result.metrics.dps * 0.1
    reason = []
    if result.metrics.constraint_balance < 0.6:
        reason.append("reservation tight")
    if not result.viable:
        reason.append("fails viability")
    return DifficultyScore(score=round(base, 2), reasons=reason or ["stable"])


@dataclass
class PowerScore:
    power: float
    value: float


def compute_power_scores(result: BenchResult) -> PowerScore:
    power = result.metrics.dps * 0.5 + result.metrics.survival * 0.2
    value = len(result.notes.get("scenario_bonus", "")) + result.metrics.constraint_balance
    return PowerScore(power=round(power, 2), value=round(value, 2))


@dataclass
class MetaRiskScore:
    overcap_risk: float
    reservation_risk: float


def compute_meta_risk(genome: Genome) -> MetaRiskScore:
    overcap = max(0.0, (sum(genome.resists.values()) / 3.0 - 70) / 30.0)
    reservation = max(0.0, (len(genome.auras) * 8 - genome.attributes["intelligence"]) / 80.0)
    return MetaRiskScore(overcap_risk=round(overcap, 3), reservation_risk=round(reservation, 3))


class AtlasRowSerializer:
    @staticmethod
    def genome_row(genome: Genome) -> Dict[str, object]:
        fingerprint = genome.fingerprint()
        return {
            "build_id": fingerprint,
            "created_at": "2026-02-23T00:00:00Z",
            "league": "Standard",
            "genome_json": genome.to_json(),
            "pob_xml": f"<build id='{fingerprint}'/>",
            "tags": genome.supports,
            "creator": "buildatlas",
            "status": "draft",
        }

    @staticmethod
    def eval_row(genome: Genome, result: BenchResult) -> Dict[str, object]:
        metrics = {
            "dps": result.metrics.dps,
            "survival": result.metrics.survival,
            "mana_regen": result.metrics.mana_regen,
            "constraint_balance": result.metrics.constraint_balance,
        }
        warning = result.notes.get("constraint") if result.notes else None
        warnings = [warning] if warning else []
        return {
            "build_id": genome.fingerprint(),
            "scenario_id": result.scenario.value,
            "evaluated_at": "2026-02-23T00:00:00Z",
            "metrics_map": metrics,
            "valid": int(result.viable),
            "warnings": warnings,
        }

    @staticmethod
    def cost_row(genome: Genome, distribution: CostDistribution) -> Dict[str, object]:
        return {
            "build_id": genome.fingerprint(),
            "estimated_at": "2026-02-23T00:00:00Z",
            "cost_p10": distribution.p10,
            "cost_p50": distribution.p50,
            "cost_p90": distribution.p90,
            "confidence": 0.95,
            "breakdown": [
                f"supports:{len(genome.supports)}",
                f"attribute_points:{sum(genome.attributes.values())}",
            ],
        }

    @staticmethod
    def difficulty_row(genome: Genome, result: BenchResult, difficulty: DifficultyScore) -> Dict[str, object]:
        return {
            "build_id": genome.fingerprint(),
            "scored_at": "2026-02-23T00:00:00Z",
            "score": difficulty.score,
            "reason_codes": difficulty.reasons,
            "details_map": {
                "viable": "true" if result.viable else "false",
                "constraint_balance": f"{result.metrics.constraint_balance:.3f}",
            },
        }

    @staticmethod
    def rank_row(genome: Genome, result: BenchResult, power: PowerScore, meta: MetaRiskScore) -> Dict[str, object]:
        combined_meta_risk = round(max(meta.overcap_risk, meta.reservation_risk), 3)
        return {
            "build_id": genome.fingerprint(),
            "scenario_id": result.scenario.value,
            "rank_ts": "2026-02-23T00:00:00Z",
            "power_score": power.power,
            "value_score": power.value,
            "pareto_rank": 1,
            "meta_risk": combined_meta_risk,
        }
