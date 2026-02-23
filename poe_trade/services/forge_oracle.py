"""Forge evaluation engine"""

from __future__ import annotations

import argparse
import logging
from typing import Sequence

from ..analytics.forge_oracle import CraftAction, ForgeOracle
from ._runner import run_idle_service

logger = logging.getLogger(__name__)

SERVICE_NAME = "forge_oracle"


def _default_actions() -> Sequence[CraftAction]:
    return [
        CraftAction(name="AddPrefix", cost=3.0, value_gain=6.0),
        CraftAction(name="AddSuffix", cost=4.5, value_gain=7.5),
        CraftAction(name="Reroll", cost=5.0, value_gain=12.0),
    ]


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the forge oracle service")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    engine = ForgeOracle(_default_actions())
    plan = engine.best_plan(depth=2)
    if plan:
        logger.info("Best plan ev=%.2f steps=%s", plan.expected_value, [action.name for action in plan.steps])
    else:
        logger.info("No plan found")

    if args.dry_run:
        return

    run_idle_service(SERVICE_NAME)
