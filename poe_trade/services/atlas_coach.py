"""BuildAtlas coach (optional)."""

from __future__ import annotations

import argparse
import logging
from typing import Sequence

from ..atlas import (
    AtlasCoach,
    BuildMetric,
    CharacterState,
    GenomeGenerator,
    Scenario,
    BenchEvaluator,
    compute_power_scores,
)
from ..config import settings as config_settings
from ._runner import run_idle_service

logger = logging.getLogger(__name__)

SERVICE_NAME = "atlas_coach"


def _configure_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=SERVICE_NAME)
    parser.add_argument("--dry-run", action="store_true", help="Plan upgrades and exit")
    parser.add_argument("--budget", type=float, default=75.0, help="Chaos budget for coach summaries")
    parser.add_argument("--count", type=int, default=3, help="Number of candidate builds")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    cfg = config_settings.get_settings()
    parser = _configure_parser()
    args = parser.parse_args(argv)
    port = cfg.service_ports.get(SERVICE_NAME, None)
    logger.info(
        "%s starting on port %s (clickhouse=%s) realms=%s leagues=%s",
        SERVICE_NAME,
        port,
        cfg.clickhouse_url,
        cfg.realms,
        cfg.leagues,
    )
    generator = GenomeGenerator(seed=303)
    evaluator = BenchEvaluator()
    scenario = Scenario.MAP_CLEAR_BASELINE
    metrics: list[BuildMetric] = []
    for index in range(args.count):
        genome = generator.generate()
        result = evaluator.evaluate(genome, scenario)
        score = compute_power_scores(result)
        metrics.append(
            BuildMetric(
                name=f"{genome.main_skill} {index+1}",
                potential_gain=round(score.power * 0.3 + 5.0, 2),
                required_chaos=round(score.power / 5.0 + 10.0, 2),
                rank=index + 1,
            )
        )
    coach = AtlasCoach()
    state = CharacterState(
        chaos=max(1.0, args.budget),
        current_power=max((metric.potential_gain for metric in metrics), default=80.0),
        map_completion=0.65,
    )
    steps = coach.plan(state, metrics)
    for step in steps:
        logger.info(
            "Coach step=%s priority=%.3f cost=%.2f rationale=%s",
            step.name,
            step.priority,
            step.cost,
            step.rationale,
        )
    if not steps:
        logger.info("Coach found no upgrades; increase budget or run atlas_builds first")
    if args.dry_run:
        return
    run_idle_service(SERVICE_NAME)

if __name__ == "__main__":
    main()
