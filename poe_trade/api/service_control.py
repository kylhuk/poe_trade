from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from poe_trade.db import ClickHouseClient
from poe_trade.db.clickhouse import ClickHouseClientError

ServiceStatus = Literal["running", "stopped", "error", "starting", "stopping"]
ServiceAction = Literal["start", "stop", "restart"]

_ALLOWED_ACTIONS: tuple[ServiceAction, ...] = ("start", "stop", "restart")


@dataclass(frozen=True)
class ServiceDefinition:
    id: str
    name: str
    description: str
    type: str
    container: str
    controllable: bool
    actions: tuple[ServiceAction, ...]


@dataclass(frozen=True)
class ServiceSnapshot:
    id: str
    name: str
    description: str
    status: ServiceStatus
    uptime: int | None
    last_crawl: str | None
    rows_in_db: int | None
    container_info: str | None
    type: str
    allowed_actions: tuple[ServiceAction, ...]


def service_registry() -> tuple[ServiceDefinition, ...]:
    return (
        ServiceDefinition(
            id="clickhouse",
            name="ClickHouse",
            description="Primary analytical database",
            type="docker",
            container="clickhouse",
            controllable=False,
            actions=(),
        ),
        ServiceDefinition(
            id="schema_migrator",
            name="Schema Migrator",
            description="One-shot schema migration runner",
            type="worker",
            container="schema_migrator",
            controllable=False,
            actions=(),
        ),
        ServiceDefinition(
            id="market_harvester",
            name="Market Harvester",
            description="Public stash and exchange ingestion daemon",
            type="crawler",
            container="market_harvester",
            controllable=True,
            actions=_ALLOWED_ACTIONS,
        ),
        ServiceDefinition(
            id="account_stash_harvester",
            name="Account Stash Harvester",
            description="Private account stash snapshot daemon",
            type="crawler",
            container="account_stash_harvester",
            controllable=True,
            actions=_ALLOWED_ACTIONS,
        ),
        ServiceDefinition(
            id="api",
            name="API",
            description="Protected backend API service",
            type="analytics",
            container="api",
            controllable=False,
            actions=(),
        ),
    )


class ServiceControlError(RuntimeError):
    pass


class ServiceNotFoundError(ServiceControlError):
    pass


class ServiceActionInvalidError(ServiceControlError):
    pass


class ServiceActionForbiddenError(ServiceControlError):
    pass


def list_snapshots(client: ClickHouseClient) -> list[ServiceSnapshot]:
    snapshots: list[ServiceSnapshot] = []
    for service in service_registry():
        snapshots.append(_snapshot_for_service(client, service))
    return snapshots


def execute_service_action(
    client: ClickHouseClient,
    *,
    service_id: str,
    action: str,
) -> ServiceSnapshot:
    service = _service_by_id(service_id)
    if action not in _ALLOWED_ACTIONS:
        raise ServiceActionInvalidError("invalid service action")
    typed_action = action
    if typed_action not in service.actions or not service.controllable:
        raise ServiceActionForbiddenError("action is forbidden for this service")
    _run_compose_action(service, typed_action)
    return _snapshot_for_service(client, service)


def _service_by_id(service_id: str) -> ServiceDefinition:
    for service in service_registry():
        if service.id == service_id:
            return service
    raise ServiceNotFoundError("service not found")


def _snapshot_for_service(
    client: ClickHouseClient,
    service: ServiceDefinition,
) -> ServiceSnapshot:
    if service.id == "market_harvester":
        status = _ingest_status(client, queue_prefix="psapi:")
        return ServiceSnapshot(
            id=service.id,
            name=service.name,
            description=service.description,
            status=status,
            uptime=None,
            last_crawl=_latest_ingest_iso(client, queue_prefix="psapi:"),
            rows_in_db=_latest_row_count(client),
            container_info=service.container,
            type=service.type,
            allowed_actions=service.actions,
        )
    if service.id == "account_stash_harvester":
        status = _ingest_status(client, queue_prefix="account_stash:")
        return ServiceSnapshot(
            id=service.id,
            name=service.name,
            description=service.description,
            status=status,
            uptime=None,
            last_crawl=_latest_ingest_iso(client, queue_prefix="account_stash:"),
            rows_in_db=_latest_account_stash_row_count(client),
            container_info=service.container,
            type=service.type,
            allowed_actions=service.actions,
        )
    if service.id == "clickhouse":
        status = "running" if _clickhouse_ping_ok(client) else "error"
    elif service.id == "api":
        status = "running"
    else:
        status = "stopped"
    return ServiceSnapshot(
        id=service.id,
        name=service.name,
        description=service.description,
        status=status,
        uptime=None,
        last_crawl=None,
        rows_in_db=None,
        container_info=service.container,
        type=service.type,
        allowed_actions=service.actions,
    )


def _clickhouse_ping_ok(client: ClickHouseClient) -> bool:
    try:
        payload = client.execute("SELECT 1 FORMAT JSONEachRow").strip()
    except ClickHouseClientError:
        return False
    return payload == '{"1":1}'


def _latest_ingest_iso(client: ClickHouseClient, *, queue_prefix: str) -> str | None:
    query = (
        "SELECT max(last_ingest_at) AS ts "
        "FROM poe_trade.poe_ingest_status "
        f"WHERE startsWith(queue_key, '{queue_prefix}') "
        "FORMAT JSONEachRow"
    )
    try:
        payload = client.execute(query).strip()
    except ClickHouseClientError:
        return None
    if not payload:
        return None
    row = json.loads(payload.splitlines()[0])
    raw = row.get("ts")
    if raw is None:
        return None
    return str(raw).replace(" ", "T") + "Z"


def _latest_row_count(client: ClickHouseClient) -> int | None:
    query = (
        "SELECT count() AS rows FROM poe_trade.raw_public_stash_pages "
        "FORMAT JSONEachRow"
    )
    try:
        payload = client.execute(query).strip()
    except ClickHouseClientError:
        return None
    if not payload:
        return None
    row = json.loads(payload.splitlines()[0])
    value = row.get("rows")
    if value is None:
        return None
    return int(value)


def _ingest_status(client: ClickHouseClient, *, queue_prefix: str) -> ServiceStatus:
    latest = _latest_ingest_iso(client, queue_prefix=queue_prefix)
    if latest is None:
        return "stopped"
    try:
        last = datetime.fromisoformat(latest.replace("Z", "+00:00"))
    except ValueError:
        return "error"
    age_seconds = (datetime.now(timezone.utc) - last).total_seconds()
    if age_seconds <= 180:
        return "running"
    if age_seconds <= 900:
        return "stopping"
    return "stopped"


def _latest_account_stash_row_count(client: ClickHouseClient) -> int | None:
    query = (
        "SELECT count() AS rows FROM poe_trade.raw_account_stash_snapshot "
        "FORMAT JSONEachRow"
    )
    try:
        payload = client.execute(query).strip()
    except ClickHouseClientError:
        return None
    if not payload:
        return None
    row = json.loads(payload.splitlines()[0])
    value = row.get("rows")
    if value is None:
        return None
    return int(value)


def _run_compose_action(service: ServiceDefinition, action: ServiceAction) -> None:
    cmd = ["docker", "compose", action, service.container]
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
    except FileNotFoundError as exc:
        raise ServiceControlError("docker compose is unavailable") from exc
    except subprocess.CalledProcessError as exc:
        err = (exc.stderr or exc.stdout or "").strip()
        raise ServiceControlError(err or "service action failed") from exc
