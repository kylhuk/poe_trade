"""PoB bench worker pool (optional)."""

from __future__ import annotations

import argparse
import logging
from typing import Sequence

from ..atlas import BenchCache, BenchEvaluator, GenomeGenerator, Scenario
from ..config import settings as config_settings
from ._runner import run_idle_service

logger = logging.getLogger(__name__)

SERVICE_NAME = "atlas_bench"


def _configure_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=SERVICE_NAME)
    parser.add_argument("--dry-run", action="store_true", help="Run evaluation cycle once")
    parser.add_argument("--samples", type=int, default=2, help="Number of genomes to evaluate")
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
    generator = GenomeGenerator(seed=199)
    evaluator = BenchEvaluator()
    cache = BenchCache()
    scenarios = [Scenario.MAP_CLEAR_BASELINE, Scenario.PINNACLE_BOSS]
    for index in range(args.samples):
        genome = generator.generate()
        for scenario in scenarios:
            result, cached = cache.lookup(genome, scenario, evaluator)
            logger.info(
                "Bench %s scenario=%s cached=%s dps=%.2f surv=%.2f",
                genome.fingerprint()[:6],
                scenario.value,
                cached,
                result.metrics.dps,
                result.metrics.survival,
            )
    if args.dry_run:
        return
    run_idle_service(SERVICE_NAME)

if __name__ == "__main__":
    main()
