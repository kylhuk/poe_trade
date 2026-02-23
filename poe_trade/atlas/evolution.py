from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence, Tuple
import random
import copy

from .models import Genome


@dataclass(frozen=True)
class EvolutionMetrics:
    power: float
    survivability: float


@dataclass(frozen=True)
class EvolutionConfig:
    objective_weights: Tuple[float, float] = (0.6, 0.4)
    novelty_weight: float = 0.05


@dataclass
class RankedGenome:
    genome: Genome
    metrics: EvolutionMetrics
    novelty: float
    power_component: float
    survivability_component: float
    novelty_bonus: float
    objective_score: float


def compute_metrics(genome: Genome) -> EvolutionMetrics:
    attr_score = sum(genome.attributes.values())
    resist_score = sum(genome.resists.values())
    survivability = (resist_score / 3) + (genome.attributes.get("strength", 0) * 0.5)
    power = attr_score * 0.6 + resist_score * 0.4
    return EvolutionMetrics(power=power, survivability=survivability)


def compute_objective_components(metrics: EvolutionMetrics, weights: Tuple[float, float]) -> Tuple[float, float]:
    power_weight, survivability_weight = weights
    power_component = metrics.power * power_weight
    survivability_component = metrics.survivability * survivability_weight
    return power_component, survivability_component


def compute_novelty(genome: Genome, population: Sequence[Genome]) -> float:
    if not population:
        return 0.0
    diffs: List[float] = []
    for other in population:
        if other is genome:
            continue
        set_difference = set(genome.passives) ^ set(other.passives)
        attr_distance = sum(
            abs(genome.attributes[k] - other.attributes.get(k, 0)) for k in genome.attributes
        )
        diffs.append(len(set_difference) + attr_distance * 0.01)
    return sum(diffs) / len(diffs) if diffs else 0.0


def mutate_genome(genome: Genome, rng: random.Random) -> Genome:
    mutated = copy.deepcopy(genome)
    attr_keys = sorted(mutated.attributes)
    if attr_keys:
        key = attr_keys[rng.randrange(len(attr_keys))]
        delta = rng.choice([-3, -2, -1, 1, 2, 3])
        mutated.attributes[key] = max(10, mutated.attributes[key] + delta)

    resist_keys = sorted(mutated.resists)
    if resist_keys:
        key = resist_keys[rng.randrange(len(resist_keys))]
        delta = rng.choice([-5, -3, -1, 1, 3, 5])
        mutated.resists[key] = max(0, min(100, mutated.resists[key] + delta))

    if mutated.supports:
        idx = rng.randrange(len(mutated.supports))
        base_support = mutated.supports[idx]
        mutated.supports[idx] = base_support if base_support.endswith("+") else f"{base_support}+"

    toggles = list(mutated.toggles.keys())
    if toggles:
        toggle_key = toggles[rng.randrange(len(toggles))]
        mutated.toggles[toggle_key] = not mutated.toggles[toggle_key]

    return mutated


def crossover_genomes(a: Genome, b: Genome, rng: random.Random) -> Genome:
    merged = copy.deepcopy(a)
    merged.main_skill = a.main_skill if rng.random() < 0.5 else b.main_skill
    merged.supports = ([a.supports[0]] if a.supports else []) + ([b.supports[-1]] if b.supports else [])
    if a.auras and b.auras:
        merged.auras = [b.auras[0], a.auras[-1]]
    merged.passives = sorted(set(a.passives + b.passives))[:3]
    merged.attributes = {
        key: (a.attributes.get(key, 0) + b.attributes.get(key, 0)) // 2
        for key in sorted(set(a.attributes) | set(b.attributes))
    }
    merged.resists = {
        key: min(100, (a.resists.get(key, 0) + b.resists.get(key, 0)) // 2)
        for key in sorted(set(a.resists) | set(b.resists))
    }
    return merged


def rank_population(
    population: Iterable[Genome],
    rng: random.Random,
    elite: int = 2,
    config: EvolutionConfig = EvolutionConfig(),
) -> List[RankedGenome]:
    genomes = list(population)
    ranked: List[RankedGenome] = []
    for genome in genomes:
        metrics = compute_metrics(genome)
        power_component, survivability_component = compute_objective_components(
            metrics, config.objective_weights
        )
        novelty = compute_novelty(genome, genomes)
        novelty_bonus = config.novelty_weight * novelty
        objective_score = power_component + survivability_component + novelty_bonus
        ranked.append(
            RankedGenome(
                genome,
                metrics,
                novelty,
                power_component,
                survivability_component,
                novelty_bonus,
                objective_score,
            )
        )

    ranked.sort(
        key=lambda entry: (
            -entry.objective_score,
            -entry.novelty,
            -entry.power_component,
            entry.genome.fingerprint(),
        )
    )

    return ranked[:elite]


def evolve(
    population: Iterable[Genome],
    rng: random.Random,
    target_size: int,
    config: EvolutionConfig = EvolutionConfig(),
) -> List[Genome]:
    survivors = rank_population(
        population, rng, elite=max(1, target_size // 2), config=config
    )
    if not survivors:
        return []
    next_gen: List[Genome] = [entry.genome for entry in survivors]
    fingerprints: Dict[str, Genome] = {entry.genome.fingerprint(): entry.genome for entry in survivors}
    attempts = 0
    while len(next_gen) < target_size:
        if attempts > target_size * 10:
            break
        parents = rng.sample(survivors, k=2) if len(survivors) > 1 else (survivors[0], survivors[0])
        offspring = crossover_genomes(parents[0].genome, parents[1].genome, rng)
        candidate = mutate_genome(offspring, rng)
        fingerprint = candidate.fingerprint()
        if fingerprint in fingerprints:
            attempts += 1
            continue
        fingerprints[fingerprint] = candidate
        next_gen.append(candidate)
        attempts = 0
    return next_gen[:target_size]
