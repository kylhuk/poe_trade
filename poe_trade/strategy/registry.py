from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import tomllib


STRATEGY_ROOT = Path(__file__).resolve().parents[2] / "strategies"
SQL_STRATEGY_ROOT = Path(__file__).resolve().parents[1] / "sql" / "strategy"

DEFAULT_MAX_STALENESS_MINUTES = 15
DEFAULT_MIN_LIQUIDITY_SCORE = 0.5
DEFAULT_MAX_ESTIMATED_WHISPERS = 6
DEFAULT_MAX_ESTIMATED_OPERATIONS = 3


@dataclass(frozen=True)
class StrategyPack:
    strategy_id: str
    name: str
    enabled: bool
    priority: int
    latency_class: str
    execution_venue: str
    capital_tier: str
    min_expected_profit_chaos: float | None
    min_expected_roi: float | None
    min_confidence: float | None
    min_sample_count: int | None
    cooldown_minutes: int
    requires_journal: bool
    max_staleness_minutes: int
    min_liquidity_score: float
    max_estimated_whispers: int
    max_estimated_operations: int
    advanced_override_profit_per_operation_chaos: float | None
    metadata_path: Path
    notes_path: Path
    discover_sql_path: Path
    backtest_sql_path: Path
    candidate_sql_path: Path


def list_strategy_packs() -> list[StrategyPack]:
    if not STRATEGY_ROOT.exists():
        return []
    packs: list[StrategyPack] = []
    for strategy_dir in sorted(
        path for path in STRATEGY_ROOT.iterdir() if path.is_dir()
    ):
        metadata_path = strategy_dir / "strategy.toml"
        notes_path = strategy_dir / "notes.md"
        sql_dir = SQL_STRATEGY_ROOT / strategy_dir.name
        discover_sql_path = sql_dir / "discover.sql"
        backtest_sql_path = sql_dir / "backtest.sql"
        candidate_sql_path = sql_dir / "candidate.sql"
        if not metadata_path.exists() or not notes_path.exists():
            continue
        if not discover_sql_path.exists() or not backtest_sql_path.exists():
            continue
        metadata = tomllib.loads(metadata_path.read_text(encoding="utf-8"))
        minima = metadata.get("minima", {})
        params = metadata.get("params", {})
        if not isinstance(minima, dict):
            minima = {}
        if not isinstance(params, dict):
            params = {}
        packs.append(
            StrategyPack(
                strategy_id=str(metadata["id"]),
                name=str(metadata["name"]),
                enabled=bool(metadata.get("enabled", False)),
                priority=int(metadata.get("priority", 0)),
                latency_class=str(metadata.get("latency_class", "delayed")),
                execution_venue=str(metadata.get("execution_venue", "manual_trade")),
                capital_tier=str(metadata.get("capital_tier", "bootstrap")),
                min_expected_profit_chaos=_as_optional_float(
                    minima.get("expected_profit_chaos")
                ),
                min_expected_roi=_as_optional_float(minima.get("roi")),
                min_confidence=_as_optional_float(minima.get("confidence")),
                min_sample_count=_as_optional_int(params.get("min_sample_count")),
                cooldown_minutes=max(
                    0, _as_int(params.get("cooldown_minutes"), default=0)
                ),
                requires_journal=bool(params.get("requires_journal", False)),
                max_staleness_minutes=max(
                    0,
                    _as_int(
                        params.get("max_staleness_minutes"),
                        default=DEFAULT_MAX_STALENESS_MINUTES,
                    ),
                ),
                min_liquidity_score=max(
                    0.0,
                    min(
                        1.0,
                        _as_float(
                            params.get("min_liquidity_score"),
                            default=DEFAULT_MIN_LIQUIDITY_SCORE,
                        ),
                    ),
                ),
                max_estimated_whispers=max(
                    0,
                    _as_int(
                        params.get("max_estimated_whispers"),
                        default=DEFAULT_MAX_ESTIMATED_WHISPERS,
                    ),
                ),
                max_estimated_operations=max(
                    1,
                    _as_int(
                        params.get("max_estimated_operations"),
                        default=DEFAULT_MAX_ESTIMATED_OPERATIONS,
                    ),
                ),
                advanced_override_profit_per_operation_chaos=_as_optional_float(
                    params.get("advanced_override_profit_per_operation_chaos")
                ),
                metadata_path=metadata_path,
                notes_path=notes_path,
                discover_sql_path=discover_sql_path,
                backtest_sql_path=backtest_sql_path,
                candidate_sql_path=candidate_sql_path,
            )
        )
    return packs


def get_candidate_sql_path(pack: StrategyPack) -> Path:
    if pack.candidate_sql_path.exists():
        return pack.candidate_sql_path
    if pack.discover_sql_path.exists():
        return pack.discover_sql_path
    return pack.backtest_sql_path


def load_candidate_sql(pack: StrategyPack) -> str:
    return get_candidate_sql_path(pack).read_text(encoding="utf-8")


def _as_optional_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _as_optional_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip():
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _as_int(value: object, *, default: int) -> int:
    parsed = _as_optional_int(value)
    return parsed if parsed is not None else default


def _as_float(value: object, *, default: float) -> float:
    parsed = _as_optional_float(value)
    return parsed if parsed is not None else default


def set_strategy_enabled(strategy_id: str, enabled: bool) -> Path:
    pack = next(
        (pack for pack in list_strategy_packs() if pack.strategy_id == strategy_id),
        None,
    )
    if pack is None:
        raise ValueError(f"Unknown strategy pack: {strategy_id}")
    original = pack.metadata_path.read_text(encoding="utf-8")
    metadata = tomllib.loads(original)
    current_enabled = bool(metadata.get("enabled", False))
    if current_enabled == enabled:
        return pack.metadata_path
    updated = re.sub(
        r"^enabled\s*=\s*(true|false)\s*$",
        f"enabled = {'true' if enabled else 'false'}",
        original,
        count=1,
        flags=re.MULTILINE,
    )
    if updated == original:
        raise ValueError(f"Strategy pack missing enabled flag: {strategy_id}")
    _ = pack.metadata_path.write_text(updated, encoding="utf-8")
    return pack.metadata_path
