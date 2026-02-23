from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from random import Random
from typing import Dict, List, Optional

from ..atlas import (
    AtlasCoach,
    BenchEvaluator,
    BenchResult,
    BuildMetric,
    BuildSnapshot,
    CharacterState,
    CostDistribution,
    DeltaEntry,
    DifficultyScore,
    Genome,
    GenomeGenerator,
    MetaRiskScore,
    PowerScore,
    Scenario,
    TemplateAllocation,
    UpgradeStep,
    allocate_templates_by_slot,
    build_template_from_vector,
    compute_cost_distribution,
    compute_difficulty,
    compute_meta_risk,
    compute_power_scores,
    compute_patch_delta,
    evolve,
)
from .atlas_types import AtlasBuildRecord, AtlasRunRecord

ATLAS_BUILD_COUNT = 3
ATLAS_INITIAL_SEED = 2026
ATLAS_TEMPLATE_SEED = 4242
ATLAS_TEMPLATE_BUDGET = 130.0


@dataclass(frozen=True)
class AtlasBuildState:
    record: AtlasBuildRecord
    genome: Genome
    bench_results: Dict[Scenario, BenchResult]
    cost: CostDistribution
    difficulty: DifficultyScore
    power: PowerScore
    meta_risk: MetaRiskScore


class AtlasOrchestrator:
    def __init__(self, anchor: datetime) -> None:
        self._anchor = anchor
        self._generator = GenomeGenerator(seed=ATLAS_INITIAL_SEED)
        self._bench = BenchEvaluator()
        self._coach = AtlasCoach()
        self._scenarios: List[Scenario] = [
            Scenario.MAP_CLEAR_BASELINE,
            Scenario.PINNACLE_BOSS,
            Scenario.DEFENSE_CHECK,
            Scenario.BUDGET_MAPPING,
        ]
        self._build_states: Dict[str, AtlasBuildState] = self._seed_builds()
        self._patch_snapshots: List[BuildSnapshot] = self._compute_patch_snapshots()
        self._last_patch_delta: List[DeltaEntry] = []
        self._last_template_allocation: Optional[TemplateAllocation] = None
        self._runs: List[AtlasRunRecord] = []
        self._run_counter = 0

    def build_states(self) -> List[AtlasBuildState]:
        return list(self._build_states.values())

    def build_state(self, build_id: str) -> AtlasBuildState | None:
        return self._build_states.get(build_id)

    def export_payload(self, build_id: str) -> Dict[str, str] | None:
        state = self.build_state(build_id)
        if state is None:
            return None
        return {
            "build": state.record.name,
            "specialization": state.record.specialization,
            "notes": state.record.notes,
            "power": f"{state.power.power:.1f}",
            "cost_p50": f"{state.cost.p50:.1f}",
        }

    def run_build(self, build_id: str, focus: str | None) -> AtlasRunRecord | None:
        state = self.build_state(build_id)
        if state is None:
            return None
        scenario = self._resolve_scenario(focus)
        self._run_counter += 1
        run = AtlasRunRecord(
            run_id=f"run-{self._run_counter:03d}",
            build_id=build_id,
            generated_at=datetime.now(timezone.utc),
            node_count=state.record.node_count,
            status="completed",
            scenario=scenario.value,
            cost=state.cost.p50,
            power=state.power.power,
            meta_risk=max(state.meta_risk.overcap_risk, state.meta_risk.reservation_risk),
        )
        self._runs.append(run)
        self._last_template_allocation = self._allocate_templates_for_run(state)
        previous_snapshots = self._patch_snapshots
        self._refresh_population()
        current_snapshots = self._compute_patch_snapshots()
        self._last_patch_delta = compute_patch_delta(previous_snapshots, current_snapshots)
        self._patch_snapshots = current_snapshots
        return run

    def last_run(self) -> AtlasRunRecord | None:
        if not self._runs:
            return None
        return self._runs[-1]

    def surprise_message(self) -> str:
        if not self._runs:
            return "Atlas is waiting for the first run."
        if not self._last_patch_delta:
            return f"Atlas run completed; {self._template_summary()}"
        entry = self._last_patch_delta[0]
        return (
            f"Patch {entry.severity}: {entry.name} -> rank {entry.current_rank} "
            f"(Δ{entry.delta_score:+.2f}); {self._template_summary()}"
        )

    def coach_steps(self) -> List[UpgradeStep]:
        candidates = self._build_metric_candidates()
        if not candidates:
            return []
        state = self._build_character_state()
        return self._coach.plan(state, candidates)

    def _seed_builds(self) -> Dict[str, AtlasBuildState]:
        states: Dict[str, AtlasBuildState] = {}
        for index in range(ATLAS_BUILD_COUNT):
            genome = self._generator.generate()
            metadata = self._build_state_from_genome(genome, index)
            states[metadata.record.build_id] = metadata
        return states

    def _build_state_from_genome(self, genome: Genome, index: int) -> AtlasBuildState:
        nodes = self._build_nodes(genome)
        updated_at = self._anchor + timedelta(hours=index * 6)
        bench_results = {
            scenario: self._bench.evaluate(genome, scenario) for scenario in self._scenarios
        }
        primary_result = bench_results[self._scenarios[0]]
        cost = compute_cost_distribution(genome)
        power = compute_power_scores(primary_result)
        difficulty = compute_difficulty(primary_result)
        meta_risk = compute_meta_risk(genome)
        record = AtlasBuildRecord(
            build_id=genome.fingerprint(),
            name=f"{genome.ascendancy or genome.class_name} {genome.main_skill}",
            specialization=genome.ascendancy or genome.class_name,
            node_count=len(nodes),
            updated_at=updated_at,
            nodes=nodes,
            notes=f"{self._scenarios[0].value} focus; power={power.power:.1f}",
        )
        return AtlasBuildState(
            record=record,
            genome=genome,
            bench_results=bench_results,
            cost=cost,
            difficulty=difficulty,
            power=power,
            meta_risk=meta_risk,
        )

    def _build_nodes(self, genome: Genome) -> List[str]:
        candidates = genome.passives[:3] + genome.supports[:2] + genome.auras[:2]
        nodes = list(dict.fromkeys(candidates))
        if not nodes:
            nodes = [genome.main_skill]
        return nodes

    def _resolve_scenario(self, focus: str | None) -> Scenario:
        if focus:
            key = focus.lower()
            mapping = {
                "map": Scenario.MAP_CLEAR_BASELINE,
                "clear": Scenario.MAP_CLEAR_BASELINE,
                "boss": Scenario.PINNACLE_BOSS,
                "pinnacle": Scenario.PINNACLE_BOSS,
                "defense": Scenario.DEFENSE_CHECK,
                "budget": Scenario.BUDGET_MAPPING,
            }
            for term, scenario in mapping.items():
                if term in key:
                    return scenario
        return self._scenarios[0]

    def _allocate_templates_for_run(self, state: AtlasBuildState) -> TemplateAllocation:
        base_vector = (
            state.power.power / 20.0,
            state.cost.p50 / 40.0,
            (state.meta_risk.overcap_risk + state.meta_risk.reservation_risk) * 5.0,
        )
        slot_templates: Dict[str, List[object]] = {
            "weapon": [
                build_template_from_vector(
                    tuple(value + 0.1 for value in base_vector),
                    "weapon",
                    ATLAS_TEMPLATE_SEED,
                )
            ],
            "body": [
                build_template_from_vector(
                    tuple(value + 0.2 for value in base_vector),
                    "body",
                    ATLAS_TEMPLATE_SEED + 1,
                )
            ],
            "jewelry": [
                build_template_from_vector(
                    tuple(value + 0.3 for value in base_vector),
                    "jewelry",
                    ATLAS_TEMPLATE_SEED + 2,
                )
            ],
        }
        preferences = {"weapon": 1.2, "body": 1.0, "jewelry": 0.8}
        return allocate_templates_by_slot(slot_templates, ATLAS_TEMPLATE_BUDGET, preferences)

    def _template_summary(self) -> str:
        allocation = self._last_template_allocation
        if not allocation or not allocation.selection:
            return "templates pending"
        ids = ",".join(sorted(template.id[:6] for template in allocation.selection.values()))
        return f"templates {ids}"

    def _build_metric_candidates(self) -> List[BuildMetric]:
        snapshots = self._patch_snapshots
        name_map = {state.record.name: state for state in self._build_states.values()}
        metrics: List[BuildMetric] = []
        for snapshot in snapshots:
            state = name_map.get(snapshot.name)
            if state is None:
                continue
            metrics.append(
                BuildMetric(
                    name=snapshot.name,
                    potential_gain=max(1.0, snapshot.power * 0.1),
                    required_chaos=snapshot.cost,
                    rank=snapshot.rank,
                )
            )
        return metrics

    def _build_character_state(self) -> CharacterState:
        chaos = self._last_template_allocation.total_cost if self._last_template_allocation else 60.0
        current_power = max((snapshot.power for snapshot in self._patch_snapshots), default=90.0)
        return CharacterState(
            chaos=max(1.0, chaos),
            current_power=current_power,
            map_completion=0.6,
        )

    def _refresh_population(self) -> None:
        genomes = [state.genome for state in self._build_states.values()]
        rng = Random(ATLAS_INITIAL_SEED + self._run_counter)
        offspring = evolve(genomes, rng, target_size=len(genomes))
        if not offspring:
            return
        new_states: Dict[str, AtlasBuildState] = {}
        for index, genome in enumerate(offspring):
            state = self._build_state_from_genome(genome, index)
            new_states[state.record.build_id] = state
        self._build_states = new_states

    def _compute_patch_snapshots(self) -> List[BuildSnapshot]:
        snapshots: List[BuildSnapshot] = []
        ordered = sorted(
            self._build_states.values(),
            key=lambda state: (-state.power.power, state.record.name),
        )
        for idx, state in enumerate(ordered, start=1):
            snapshots.append(
                BuildSnapshot(
                    name=state.record.name,
                    power=state.power.power,
                    rank=idx,
                    cost=state.cost.p50,
                    meta_risk=max(state.meta_risk.overcap_risk, state.meta_risk.reservation_risk),
                )
            )
        return snapshots
