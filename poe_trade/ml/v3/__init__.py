"""ML v3 pipeline modules.

The v3 stack is ClickHouse-first and uses raw replay as the only persistent source
of truth for historical reconstruction.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .backfill import backfill_range, replay_day
    from .eval import evaluate_run, promotion_gate
    from .serve import predict_one_v3
    from .train import train_all_routes_v3, train_route_v3


_EXPORT_TO_MODULE = {
    "backfill_range": ".backfill",
    "replay_day": ".backfill",
    "evaluate_run": ".eval",
    "promotion_gate": ".eval",
    "predict_one_v3": ".serve",
    "train_all_routes_v3": ".train",
    "train_route_v3": ".train",
}


def __getattr__(name: str) -> Any:
    module_name = _EXPORT_TO_MODULE.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(module_name, package=__name__)
    value = getattr(module, name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))


__all__ = [
    "backfill_range",
    "replay_day",
    "evaluate_run",
    "promotion_gate",
    "predict_one_v3",
    "train_all_routes_v3",
    "train_route_v3",
]
