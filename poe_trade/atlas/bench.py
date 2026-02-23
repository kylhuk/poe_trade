from dataclasses import dataclass
from enum import Enum
from typing import Dict, Tuple
import hashlib
import random

from .models import Genome

class Scenario(Enum):
    MAP_CLEAR_BASELINE = "map_clear_baseline"
    PINNACLE_BOSS = "pinnacle_boss"
    DEFENSE_CHECK = "defense_check"
    BUDGET_MAPPING = "budget_mapping"


@dataclass
class BenchMetrics:
    dps: float
    survival: float
    mana_regen: float
    constraint_balance: float


def deterministic_rng(genome: Genome, scenario: Scenario) -> random.Random:
    scenario_hash = hashlib.sha256(scenario.value.encode("utf-8")).hexdigest()
    seed = int(genome.fingerprint()[:16], 16) ^ int(scenario_hash[:16], 16)
    return random.Random(seed)


def scenario_weights(scenario: Scenario) -> Dict[str, float]:
    base = {
        Scenario.MAP_CLEAR_BASELINE: {"dps": 1.0, "survival": 0.9, "mana": 0.8},
        Scenario.PINNACLE_BOSS: {"dps": 1.2, "survival": 1.2, "mana": 0.7},
        Scenario.DEFENSE_CHECK: {"dps": 0.8, "survival": 1.5, "mana": 0.9},
        Scenario.BUDGET_MAPPING: {"dps": 0.9, "survival": 0.95, "mana": 1.0},
    }
    return base[scenario]


@dataclass
class BenchResult:
    scenario: Scenario
    metrics: BenchMetrics
    viable: bool
    notes: Dict[str, str]


class BenchEvaluator:
    def evaluate(self, genome: Genome, scenario: Scenario) -> BenchResult:
        rng = deterministic_rng(genome, scenario)
        weights = scenario_weights(scenario)
        attr_total = sum(genome.attributes.values())
        resist_total = sum(genome.resists.values())
        base_dps = attr_total * weights["dps"]
        survival = (resist_total / 3.0) * weights["survival"]
        mana_regen = (genome.attributes["intelligence"] / 5.0) * weights["mana"]
        constraint_balance = 1.0 - min(0.5, abs(len(genome.auras) * 8 - genome.attributes["intelligence"]) / 100)
        cleanse = rng.random()
        viable = survive_viability(genome, scenario, survival, constraint_balance)
        metrics = BenchMetrics(
            dps=round(base_dps * (0.9 + cleanse * 0.2), 2),
            survival=round(survival * (0.95 + cleanse * 0.1), 2),
            mana_regen=round(mana_regen * (0.9 + (1 - cleanse) * 0.2), 2),
            constraint_balance=round(constraint_balance, 3),
        )
        notes = {
            "constraint": "reservation met" if constraint_balance > 0.5 else "tight reservation",
            "scenario_bonus": scenario.value,
        }
        return BenchResult(
            scenario=scenario,
            metrics=metrics,
            viable=viable,
            notes=notes,
        )


def survive_viability(genome: Genome, scenario: Scenario, survival: float, constraint_balance: float) -> bool:
    checkpoint = scenario is not Scenario.BUDGET_MAPPING
    return survival > 40 and constraint_balance > 0.4 and (checkpoint or genome.attributes["strength"] > 70)


class BenchCache:
    def __init__(self) -> None:
        self.storage: Dict[str, BenchResult] = {}

    def lookup(self, genome: Genome, scenario: Scenario, evaluator: BenchEvaluator) -> Tuple[BenchResult, bool]:
        key = f"{genome.fingerprint()}::{scenario.value}"
        if key in self.storage:
            return self.storage[key], True
        result = evaluator.evaluate(genome, scenario)
        self.storage[key] = result
        return result, False
