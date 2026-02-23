"""BuildAtlas autonomous forge (optional)."""

from __future__ import annotations

import argparse
import logging
from random import Random
from typing import Sequence

from ..atlas import GenomeGenerator, evolve
from ..config import settings as config_settings
from ._runner import run_idle_service

logger = logging.getLogger(__name__)

SERVICE_NAME = "atlas_forge"


def _configure_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=SERVICE_NAME)
    parser.add_argument("--dry-run", action="store_true", help="Generate builds and exit")
    parser.add_argument("--count", type=int, default=3, help="How many genomes to seed")
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
    generator = GenomeGenerator(seed=2026)
    population = [generator.generate() for _ in range(args.count)]
    rng = Random(2026 + args.count)
    offspring = evolve(population, rng, target_size=args.count + 1)
    fingerprints = ",".join(genome.fingerprint()[:6] for genome in population)
    logger.info("Generated %s builds; fingerprints=%s", len(population), fingerprints)
    if offspring:
        evolved_ids = ",".join(genome.fingerprint()[:6] for genome in offspring[:2])
        logger.info("Evolved %s builds; sample=%s", len(offspring), evolved_ids)
    if args.dry_run:
        return
    run_idle_service(SERVICE_NAME)

if __name__ == "__main__":
    main()
