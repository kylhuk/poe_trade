from __future__ import annotations

from pathlib import Path

from ..db import ClickHouseClient


SQL_ROOT = Path(__file__).resolve().parents[1] / "sql"


def resolve_refresh_files(layer: str, group: str | None = None) -> list[Path]:
    layer_name = layer.strip().lower()
    if layer_name == "gold":
        if group not in (None, "refs"):
            raise ValueError(f"Unsupported gold refresh group: {group}")
        search_root = SQL_ROOT / "gold"
    elif layer_name == "silver":
        search_root = SQL_ROOT / "silver"
    else:
        raise ValueError(f"Unsupported refresh layer: {layer}")
    if not search_root.exists():
        return []
    return sorted(path for path in search_root.glob("*.sql") if path.is_file())


def execute_refresh_group(
    client: ClickHouseClient,
    *,
    layer: str,
    group: str | None = None,
    dry_run: bool = False,
) -> list[Path]:
    sql_files = resolve_refresh_files(layer, group)
    if dry_run:
        return sql_files
    for sql_file in sql_files:
        client.execute(sql_file.read_text(encoding="utf-8"))
    return sql_files
