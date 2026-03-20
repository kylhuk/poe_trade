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
        self.settings: list[dict[str, str] | None] = []

    def execute(self, query: str, settings: dict[str, str] | None = None) -> str:
        self.queries.append(query)
        self.settings.append(settings)
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


def test_split_sql_statements_handles_line_comment_semicolons() -> None:
    sql = "SELECT 1; -- ignore ; inside comment\nSELECT 2;"

    statements = MigrationRunner._split_sql_statements(sql)

    assert statements == [
        "SELECT 1",
        "-- ignore ; inside comment\nSELECT 2",
    ]


def test_split_sql_statements_handles_block_comment_semicolons() -> None:
    sql = "SELECT 1 /* block ; comment */;\nSELECT 2;"

    statements = MigrationRunner._split_sql_statements(sql)

    assert statements == [
        "SELECT 1 /* block ; comment */",
        "SELECT 2",
    ]


def test_split_sql_statements_handles_quoted_semicolons() -> None:
    sql = "SELECT ';';\nSELECT \"semi;colon\";\nSELECT `ident;ifier`;"

    statements = MigrationRunner._split_sql_statements(sql)

    assert statements == [
        "SELECT ';'",
        'SELECT "semi;colon"',
        "SELECT `ident;ifier`",
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
    assert client.settings == [
        {"prefer_column_name_to_alias": "1"},
        {"prefer_column_name_to_alias": "1"},
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


def test_account_stash_account_scope_migration_is_additive() -> None:
    migration = (
        Path(__file__).resolve().parents[2]
        / "schema"
        / "migrations"
        / "0035_account_stash_account_scope.sql"
    )

    sql = migration.read_text(encoding="utf-8")

    assert "ALTER TABLE poe_trade.raw_account_stash_snapshot" in sql
    assert "ALTER TABLE poe_trade.silver_account_stash_items" in sql
    assert "ADD COLUMN IF NOT EXISTS account_name String DEFAULT ''" in sql


def test_mod_feature_stage_mv_migration_defines_materialized_view() -> None:
    migration = (
        Path(__file__).resolve().parents[2]
        / "schema"
        / "migrations"
        / "0047_poeninja_mod_feature_stage_mv_v1.sql"
    )

    sql = migration.read_text(encoding="utf-8")

    assert (
        "CREATE TABLE IF NOT EXISTS poe_trade.ml_item_mod_features_sql_stage_v1" in sql
    )
    assert (
        "CREATE MATERIALIZED VIEW IF NOT EXISTS "
        "poe_trade.mv_ml_item_mod_features_sql_stage_v1" in sql
    )


def test_incremental_v2_migration_defines_side_by_side_pipeline() -> None:
    migration = (
        Path(__file__).resolve().parents[2]
        / "schema"
        / "migrations"
        / "0048_ml_pricing_incremental_v2.sql"
    )

    sql = migration.read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS poe_trade.ml_fx_hour_v2" in sql
    assert (
        "CREATE MATERIALIZED VIEW IF NOT EXISTS "
        "poe_trade.mv_raw_poeninja_to_ml_fx_hour_v2" in sql
    )
    assert "CREATE TABLE IF NOT EXISTS poe_trade.ml_price_labels_v2" in sql
    assert (
        "CREATE MATERIALIZED VIEW IF NOT EXISTS "
        "poe_trade.mv_silver_ps_items_to_price_labels_v2" in sql
    )
    assert "CREATE TABLE IF NOT EXISTS poe_trade.ml_price_dataset_v2" in sql
    assert (
        "CREATE MATERIALIZED VIEW IF NOT EXISTS "
        "poe_trade.mv_price_labels_to_dataset_v2" in sql
    )


def test_incremental_v2_fx_currency_key_fix_migration_rebuilds_price_label_mv() -> None:
    migration = (
        Path(__file__).resolve().parents[2]
        / "schema"
        / "migrations"
        / "0049_ml_pricing_v2_fx_currency_key_fix.sql"
    )

    sql = migration.read_text(encoding="utf-8")

    assert "DROP TABLE IF EXISTS poe_trade.mv_silver_ps_items_to_price_labels_v2" in sql
    assert (
        "CREATE MATERIALIZED VIEW IF NOT EXISTS "
        "poe_trade.mv_silver_ps_items_to_price_labels_v2" in sql
    )
    assert "replaceRegexpAll(lowerUTF8(trimBoth(fx.currency))" in sql
    assert "IN ('div', 'divine', 'divines'), 'divine'" in sql


def test_incremental_v2_fx_alias_expansion_migration_maps_common_shorthand() -> None:
    migration = (
        Path(__file__).resolve().parents[2]
        / "schema"
        / "migrations"
        / "0050_ml_pricing_v2_fx_currency_alias_expansion.sql"
    )

    sql = migration.read_text(encoding="utf-8")

    assert "IN ('alch', 'alchemy'), 'orb of alchemy'" in sql
    assert (
        "IN ('gcp', 'gemcutter', 'gemcutters', 'gemcutter''s prism'), 'gemcutter''s prism'"
        in sql
    )
    assert "IN ('mirror',), 'mirror of kalandra'" in sql
    assert "IN ('exa', 'exalt', 'exalted', 'exalts'), 'exalted'" in sql


def test_v3_silver_observations_migration_creates_clickhouse_first_contract() -> None:
    migration = (
        Path(__file__).resolve().parents[2]
        / "schema"
        / "migrations"
        / "0051_ml_v3_silver_observations.sql"
    )

    sql = migration.read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS poe_trade.silver_v3_item_observations" in sql
    assert (
        "CREATE MATERIALIZED VIEW IF NOT EXISTS poe_trade.mv_raw_public_stash_to_silver_v3_item_observations"
        in sql
    )
    assert "FROM poe_trade.raw_public_stash_pages" in sql
    assert "CODEC(ZSTD(6))" in sql


def test_v3_events_and_sale_proxy_migration_creates_lifecycle_tables() -> None:
    migration = (
        Path(__file__).resolve().parents[2]
        / "schema"
        / "migrations"
        / "0052_ml_v3_events_and_sale_proxy_labels.sql"
    )

    sql = migration.read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS poe_trade.silver_v3_stash_snapshots" in sql
    assert "CREATE TABLE IF NOT EXISTS poe_trade.silver_v3_item_events" in sql
    assert "CREATE TABLE IF NOT EXISTS poe_trade.ml_v3_sale_proxy_labels" in sql
    assert (
        "CREATE MATERIALIZED VIEW IF NOT EXISTS poe_trade.mv_raw_public_stash_to_v3_stash_snapshots"
        in sql
    )


def test_v3_training_store_migration_creates_prediction_registry_tables() -> None:
    migration = (
        Path(__file__).resolve().parents[2]
        / "schema"
        / "migrations"
        / "0053_ml_v3_training_and_serving_store.sql"
    )

    sql = migration.read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS poe_trade.ml_v3_training_examples" in sql
    assert "CREATE TABLE IF NOT EXISTS poe_trade.ml_v3_retrieval_candidates" in sql
    assert "CREATE TABLE IF NOT EXISTS poe_trade.ml_v3_model_registry" in sql
    assert "CREATE TABLE IF NOT EXISTS poe_trade.ml_v3_price_predictions" in sql


def test_v3_eval_migration_creates_slice_gates_and_audit_tables() -> None:
    migration = (
        Path(__file__).resolve().parents[2]
        / "schema"
        / "migrations"
        / "0054_ml_v3_eval_and_promotion.sql"
    )

    sql = migration.read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS poe_trade.ml_v3_route_eval" in sql
    assert "CREATE TABLE IF NOT EXISTS poe_trade.ml_v3_eval_runs" in sql
    assert "CREATE TABLE IF NOT EXISTS poe_trade.ml_v3_promotion_audit" in sql


def test_v3_cleanup_migration_drops_legacy_derived_tables_not_raw() -> None:
    migration = (
        Path(__file__).resolve().parents[2]
        / "schema"
        / "migrations"
        / "0055_ml_v3_cleanup_legacy_derived.sql"
    )

    sql = migration.read_text(encoding="utf-8")

    assert "DROP TABLE IF EXISTS poe_trade.ml_price_dataset_v2" in sql
    assert "DROP TABLE IF EXISTS poe_trade.ml_model_registry_v1" in sql
    assert "DROP TABLE IF EXISTS poe_trade.silver_ps_items_raw" in sql
    assert "DROP TABLE IF EXISTS poe_trade.raw_public_stash_pages" not in sql
    assert "DROP TABLE IF EXISTS poe_trade.raw_account_stash_snapshot" not in sql
