from __future__ import annotations

from pathlib import Path

import pytest

from poe_trade.db.migrations import _resolve_migrations_dir


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
