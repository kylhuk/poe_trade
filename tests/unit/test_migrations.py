from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from poe_trade.db.migrations import (
    Migration,
    MigrationRunner,
    MigrationStatus,
    _resolve_migrations_dir,
)


class RecordingClient:
    def __init__(self, payload: str = "") -> None:
        self.payload = payload
        self.queries: list[str] = []

    def execute(self, query: str) -> str:
        self.queries.append(query)
        return self.payload


def test_source_checkout_resolves_repo_schema(tmp_path: Path) -> None:
    module_path = tmp_path / "repo" / "poe_trade" / "db" / "migrations.py"
    module_path.parent.mkdir(parents=True, exist_ok=True)
    repo_schema = tmp_path / "repo" / "schema" / "migrations"
    repo_schema.mkdir(parents=True, exist_ok=True)

    assert _resolve_migrations_dir(module_path) == repo_schema


def test_installed_package_uses_package_schema(tmp_path: Path) -> None:
    site_packages = tmp_path / "python" / "lib" / "python3.12" / "site-packages"
    module_path = site_packages / "poe_trade" / "db" / "migrations.py"
    module_path.parent.mkdir(parents=True, exist_ok=True)
    package_schema = site_packages / "poe_trade" / "schema" / "migrations"
    package_schema.mkdir(parents=True, exist_ok=True)

    assert _resolve_migrations_dir(module_path) == package_schema


def test_installed_package_falls_back_to_cwd_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    site_packages = tmp_path / "python" / "lib" / "python3.12" / "site-packages"
    module_path = site_packages / "poe_trade" / "db" / "migrations.py"
    module_path.parent.mkdir(parents=True, exist_ok=True)
    cwd_schema = tmp_path / "schema" / "migrations"
    cwd_schema.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(Path, "cwd", lambda: tmp_path)

    assert _resolve_migrations_dir(module_path) == cwd_schema


def test_installed_package_prefers_package_schema_when_both_exist(
    tmp_path: Path,
) -> None:
    site_packages = tmp_path / "python" / "lib" / "python3.12" / "site-packages"
    module_path = site_packages / "poe_trade" / "db" / "migrations.py"
    module_path.parent.mkdir(parents=True, exist_ok=True)
    package_schema = site_packages / "poe_trade" / "schema" / "migrations"
    package_schema.mkdir(parents=True, exist_ok=True)
    global_schema = site_packages / "schema" / "migrations"
    global_schema.mkdir(parents=True, exist_ok=True)

    assert _resolve_migrations_dir(module_path) == package_schema


def test_missing_paths_reports_attempted_candidates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module_path = tmp_path / "env" / "poe_trade" / "db" / "migrations.py"
    module_path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(Path, "cwd", lambda: tmp_path / "missing-cwd")

    with pytest.raises(RuntimeError) as excinfo:
        _resolve_migrations_dir(module_path)

    message = str(excinfo.value)
    assert "Migrations directory missing" in message
    assert "Checked:" in message


def test_split_sql_statements_skips_empty_chunks() -> None:
    sql = "CREATE DATABASE IF NOT EXISTS poe_trade;\n\nCREATE TABLE IF NOT EXISTS poe_trade.demo (id UInt8);\n"

    statements = MigrationRunner._split_sql_statements(sql)

    assert statements == [
        "CREATE DATABASE IF NOT EXISTS poe_trade",
        "CREATE TABLE IF NOT EXISTS poe_trade.demo (id UInt8)",
    ]


def test_apply_bootstraps_metadata_before_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = MigrationRunner(
        client=cast(Any, RecordingClient()),
        database="poe_trade",
        dry_run=False,
    )
    order: list[str] = []

    monkeypatch.setattr(
        runner, "_ensure_metadata_table", lambda: order.append("ensure")
    )

    def fake_status() -> list[MigrationStatus]:
        order.append("status")
        return []

    monkeypatch.setattr(runner, "status", fake_status)

    runner.apply()

    assert order == ["ensure", "status"]


def test_apply_executes_each_statement_and_records_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = RecordingClient()
    runner = MigrationRunner(
        client=cast(Any, client),
        database="poe_trade",
        dry_run=False,
    )
    migration = Migration(
        version="0001",
        description="meta",
        path=tmp_path / "0001_meta.sql",
        sql="CREATE DATABASE IF NOT EXISTS poe_trade;\nCREATE TABLE IF NOT EXISTS poe_trade.demo (id UInt8);",
        checksum="abc123",
    )
    recorded: list[str] = []

    monkeypatch.setattr(runner, "_ensure_metadata_table", lambda: None)
    monkeypatch.setattr(
        runner,
        "status",
        lambda: [
            MigrationStatus(migration=migration, applied=False, checksum_match=True)
        ],
    )
    monkeypatch.setattr(runner, "_record_applied", lambda m: recorded.append(m.version))

    runner.apply()

    assert client.queries == [
        "CREATE DATABASE IF NOT EXISTS poe_trade",
        "CREATE TABLE IF NOT EXISTS poe_trade.demo (id UInt8)",
    ]
    assert recorded == ["0001"]


def test_ensure_metadata_table_executes_create_database_and_table() -> None:
    client = RecordingClient()
    runner = MigrationRunner(
        client=cast(Any, client),
        database="poe_trade",
        dry_run=False,
    )

    runner._ensure_metadata_table()

    assert client.queries[0] == "CREATE DATABASE IF NOT EXISTS poe_trade"
    assert (
        "CREATE TABLE IF NOT EXISTS poe_trade.poe_schema_migrations"
        in client.queries[1]
    )
