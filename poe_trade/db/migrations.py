"""Migration tooling for ClickHouse schema baseline."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .clickhouse import ClickHouseClient, ClickHouseClientError
from ..config import settings as config_settings


def _resolve_migrations_dir(module_path: Path | None = None) -> Path:
    resolved = module_path or Path(__file__).resolve()
    candidates = (
        resolved.parents[1] / "schema" / "migrations",
        resolved.parents[2] / "schema" / "migrations",
        Path.cwd() / "schema" / "migrations",
    )
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    attempted = ", ".join(str(path) for path in candidates)
    raise RuntimeError(f"Migrations directory missing. Checked: {attempted}")


MIGRATIONS_DIR = _resolve_migrations_dir()
METADATA_TABLE = "poe_schema_migrations"
LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class Migration:
    version: str
    description: str
    path: Path
    sql: str
    checksum: str


@dataclass(frozen=True)
class MigrationStatus:
    migration: Migration
    applied: bool
    checksum_match: bool


class MigrationRunner:
    def __init__(self, client: ClickHouseClient, database: str, dry_run: bool) -> None:
        self.client = client
        self.database = database
        self.dry_run = dry_run
        self.migrations = self._load_migrations()

    def _load_migrations(self) -> list[Migration]:
        if not MIGRATIONS_DIR.exists():
            raise RuntimeError(f"Migrations directory missing: {MIGRATIONS_DIR}")
        migrations: list[Migration] = []
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            stem = path.stem
            if not stem:
                continue
            if "_" not in stem:
                continue
            version, _, label = stem.partition("_")
            description = label.replace("_", " ")
            sql = path.read_text()
            checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()
            migrations.append(
                Migration(
                    version=version,
                    description=description,
                    path=path,
                    sql=sql,
                    checksum=checksum,
                )
            )
        return migrations

    def status(self) -> list[MigrationStatus]:
        applied = self._fetch_applied()
        results: list[MigrationStatus] = []
        for migration in self.migrations:
            stored_checksum = applied.get(migration.version)
            applied_flag = stored_checksum is not None
            checksum_match = (
                stored_checksum == migration.checksum if applied_flag else True
            )
            results.append(
                MigrationStatus(
                    migration=migration,
                    applied=applied_flag,
                    checksum_match=checksum_match,
                )
            )
        return results

    def log_status(self) -> None:
        statuses = self.status()
        for status in statuses:
            state = "applied" if status.applied else "pending"
            checksum_note = "" if status.checksum_match else " (checksum mismatch)"
            LOGGER.info("%s %s%s", status.migration.version, state, checksum_note)
        pending = [st for st in statuses if not st.applied]
        if pending:
            LOGGER.info(
                "pending migrations: %s", [m.migration.version for m in pending]
            )
        else:
            LOGGER.info("all migrations applied")

    def apply(self) -> None:
        if not self.dry_run:
            self._ensure_metadata_table()
        statuses = self.status()
        pending = [st.migration for st in statuses if not st.applied]
        if not pending:
            LOGGER.info("nothing to apply")
            return
        for migration in pending:
            LOGGER.info("applying %s (%s)", migration.version, migration.description)
            if self.dry_run:
                LOGGER.info(
                    "dry-run enabled: skipping execution of %s", migration.path.name
                )
                continue
            for statement in self._split_sql_statements(migration.sql):
                self.client.execute(statement)
            self._record_applied(migration)
        LOGGER.info("migration run complete")

    def _ensure_metadata_table(self) -> None:
        self.client.execute(f"CREATE DATABASE IF NOT EXISTS {self.database}")
        table = f"{self.database}.{METADATA_TABLE}"
        create_table_sql = f"""CREATE TABLE IF NOT EXISTS {table} (
    version String,
    description String,
    checksum String,
    applied_at DateTime64(3, 'UTC') DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree()
ORDER BY (version)
SETTINGS index_granularity = 8192"""
        self.client.execute(create_table_sql)

    @staticmethod
    def _split_sql_statements(sql: str) -> list[str]:
        # ClickHouse HTTP endpoint rejects multi-statement payloads.
        return [statement.strip() for statement in sql.split(";") if statement.strip()]

    def _fetch_applied(self) -> dict[str, str]:
        table = f"{self.database}.{METADATA_TABLE}"
        query = (
            f"SELECT version, checksum FROM {table} ORDER BY version FORMAT JSONEachRow"
        )
        try:
            payload = self.client.execute(query)
        except ClickHouseClientError as exc:
            LOGGER.debug("failed to query migration table: %s", exc)
            return {}
        cleaned = payload.strip()
        if not cleaned:
            return {}
        versions: dict[str, str] = {}
        for line in cleaned.splitlines():
            try:
                record = json.loads(line)
            except (
                json.JSONDecodeError
            ):  # pragma: no cover - depends on ClickHouse format
                continue
            version = record.get("version")
            checksum = record.get("checksum")
            if isinstance(version, str) and isinstance(checksum, str):
                versions[version] = checksum
        return versions

    def _record_applied(self, migration: Migration) -> None:
        table = f"{self.database}.{METADATA_TABLE}"
        desc = self._escape(migration.description)
        insert_sql = """INSERT INTO %s (version, description, checksum)
VALUES ('%s', '%s', '%s')""" % (
            table,
            migration.version,
            desc,
            migration.checksum,
        )
        self.client.execute(insert_sql)
        LOGGER.debug("recorded migration %s", migration.version)

    @staticmethod
    def _escape(value: str) -> str:
        return value.replace("'", "''")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="poe-migrate")
    parser.add_argument("--status", action="store_true", help="Show migration status")
    parser.add_argument("--apply", action="store_true", help="Apply pending migrations")
    parser.add_argument(
        "--dry-run", action="store_true", help="Do not execute SQL statements"
    )
    parser.add_argument(
        "--database",
        default=os.getenv("POE_CLICKHOUSE_DATABASE", "poe_trade"),
        help="ClickHouse database to target",
    )
    args = parser.parse_args(argv)
    if not args.status and not args.apply:
        parser.error("at least one of --status or --apply is required")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    cfg = config_settings.get_settings()
    client = ClickHouseClient.from_env(cfg.clickhouse_url, database=args.database)
    runner = MigrationRunner(
        client=client, database=args.database, dry_run=args.dry_run
    )
    if args.status:
        runner.log_status()
    if args.apply:
        runner.apply()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
