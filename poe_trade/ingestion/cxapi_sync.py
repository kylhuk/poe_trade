from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from ..config import constants
from ..db import ClickHouseClient
from .poe_client import PoeClient
from .rate_limit import glean_rate_limit, parse_retry_after
from .status import StatusReporter
from .sync_contract import queue_key
from .sync_state import SyncStateStore


def truncate_to_hour(value: datetime) -> datetime:
    utc = value.astimezone(timezone.utc)
    return utc.replace(minute=0, second=0, microsecond=0)


def last_completed_hour(now: datetime, *, offset_seconds: int = 15) -> datetime:
    guarded = now.astimezone(timezone.utc) - timedelta(seconds=max(0, offset_seconds))
    return truncate_to_hour(guarded) - timedelta(hours=1)


def cxapi_endpoint(realm: str, requested_hour: datetime) -> str:
    normalized_realm = realm.strip().lower()
    hour_id = int(truncate_to_hour(requested_hour).timestamp())
    if not normalized_realm or normalized_realm == "pc":
        return f"currency-exchange/{hour_id}"
    return f"currency-exchange/{normalized_realm}/{hour_id}"


def next_hour_cursor(requested_hour: datetime) -> datetime:
    return truncate_to_hour(requested_hour) + timedelta(hours=1)


@dataclass(frozen=True)
class CxCursorPlan:
    start_hour: datetime
    current_end_hour: datetime


def initial_backfill_window(
    now: datetime,
    *,
    backfill_hours: int,
    offset_seconds: int = 15,
) -> CxCursorPlan:
    current_end = last_completed_hour(now, offset_seconds=offset_seconds)
    start = current_end - timedelta(hours=max(0, backfill_hours - 1))
    return CxCursorPlan(start_hour=start, current_end_hour=current_end)


class CxapiSync:
    def __init__(
        self,
        client: PoeClient,
        ck_client: ClickHouseClient,
        sync_state: SyncStateStore,
        status_reporter: StatusReporter,
        auth_client: Any | None = None,
        *,
        service_name: str = "market_harvester",
    ) -> None:
        self._client = client
        self._clickhouse = ck_client
        self._sync_state = sync_state
        self._status = status_reporter
        self._auth_client = auth_client
        self._token: Any | None = None
        self._service_name = service_name

    def sync_hour(
        self, realm: str, requested_hour: datetime, *, dry_run: bool = False
    ) -> dict[str, object]:
        hour_ts = truncate_to_hour(requested_hour)
        endpoint = cxapi_endpoint(realm, hour_ts)
        queue = queue_key(constants.FEED_KIND_CXAPI, realm)
        now = datetime.now(timezone.utc)
        self._ensure_token()
        response = self._client.request_with_metadata("GET", endpoint)
        payload = response.payload
        if not isinstance(payload, dict):
            raise ValueError(f"Unexpected CX payload: {payload}")
        next_change_id = int(payload.get("next_change_id") or int(hour_ts.timestamp()))
        status_text = (
            "idle" if next_change_id == int(hour_ts.timestamp()) else "success"
        )
        if not dry_run:
            self._write_raw_hour(realm, hour_ts, next_change_id, payload, now)
            self._write_request_entry(queue, realm, endpoint, now, response)
            self._write_checkpoint_entry(
                queue,
                realm,
                endpoint,
                str(int(hour_ts.timestamp())),
                str(next_change_id),
                now,
                response,
                status_text,
            )
        self._status.report(
            queue_key=queue,
            feed_kind=constants.FEED_KIND_CXAPI,
            contract_version=constants.INGEST_CONTRACT_VERSION,
            league=None,
            realm=realm,
            cursor=str(int(hour_ts.timestamp())),
            next_change_id=str(next_change_id),
            last_ingest_at=now,
            request_rate=1.0,
            status=status_text,
            error=None,
            error_count=0,
            stalled_since=None,
        )
        return {
            "queue_key": queue,
            "requested_hour": hour_ts,
            "next_change_id": next_change_id,
            "status": status_text,
        }

    def _ensure_token(self) -> None:
        if self._auth_client is None:
            return
        if self._token is None or bool(getattr(self._token, "is_expired")()):
            self._token = self._auth_client.refresh()
            self._client.set_bearer_token(getattr(self._token, "access_token"))

    def _write_raw_hour(
        self,
        realm: str,
        requested_hour: datetime,
        next_change_id: int,
        payload: Mapping[str, object],
        recorded_at: datetime,
    ) -> None:
        row = {
            "recorded_at": self._format_ts(recorded_at),
            "realm": realm,
            "requested_hour": truncate_to_hour(requested_hour).strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            "next_change_id": next_change_id,
            "payload_json": json.dumps(payload, ensure_ascii=False),
        }
        query = (
            "INSERT INTO poe_trade.raw_currency_exchange_hour "
            "(recorded_at, realm, requested_hour, next_change_id, payload_json)\n"
            "FORMAT JSONEachRow\n"
            f"{json.dumps(row, ensure_ascii=False)}"
        )
        self._clickhouse.execute(query)

    def _write_request_entry(
        self,
        queue: str,
        realm: str,
        endpoint: str,
        requested_at: datetime,
        response: object,
    ) -> None:
        headers = getattr(response, "headers")
        row = {
            "requested_at": self._format_ts(requested_at),
            "service": self._service_name,
            "queue_key": queue,
            "feed_kind": constants.FEED_KIND_CXAPI,
            "contract_version": constants.INGEST_CONTRACT_VERSION,
            "realm": realm,
            "league": None,
            "endpoint": endpoint,
            "http_method": "GET",
            "status": int(getattr(response, "status_code")),
            "attempts": int(getattr(response, "attempts")),
            "response_ms": int(getattr(response, "duration_ms")),
            "rate_limit_raw": json.dumps(
                dict(headers), ensure_ascii=False, sort_keys=True
            ),
            "rate_limit_parsed": json.dumps(
                glean_rate_limit(headers), ensure_ascii=False, sort_keys=True
            ),
            "retry_after_seconds": parse_retry_after(headers),
            "error": "",
        }
        query = (
            "INSERT INTO poe_trade.bronze_requests "
            "(requested_at, service, queue_key, feed_kind, contract_version, realm, league, endpoint, http_method, status, attempts, response_ms, rate_limit_raw, rate_limit_parsed, retry_after_seconds, error)\n"
            "FORMAT JSONEachRow\n"
            f"{json.dumps(row, ensure_ascii=False)}"
        )
        self._clickhouse.execute(query)

    def _write_checkpoint_entry(
        self,
        queue: str,
        realm: str,
        endpoint: str,
        last_cursor: str,
        next_cursor: str,
        retrieved_at: datetime,
        response: object,
        status_text: str,
    ) -> None:
        row = {
            "service": self._service_name,
            "queue_key": queue,
            "feed_kind": constants.FEED_KIND_CXAPI,
            "contract_version": constants.INGEST_CONTRACT_VERSION,
            "realm": realm,
            "league": None,
            "endpoint": endpoint,
            "last_cursor_id": last_cursor,
            "next_cursor_id": next_cursor,
            "cursor_hash": next_cursor,
            "retrieved_at": self._format_ts(retrieved_at),
            "retry_count": max(0, int(getattr(response, "attempts")) - 1),
            "status": status_text,
            "error": "",
            "http_status": int(getattr(response, "status_code")),
            "response_ms": int(getattr(response, "duration_ms")),
        }
        query = (
            "INSERT INTO poe_trade.bronze_ingest_checkpoints "
            "(service, queue_key, feed_kind, contract_version, realm, league, endpoint, last_cursor_id, next_cursor_id, cursor_hash, retrieved_at, retry_count, status, error, http_status, response_ms)\n"
            "FORMAT JSONEachRow\n"
            f"{json.dumps(row, ensure_ascii=False)}"
        )
        self._clickhouse.execute(query)

    @staticmethod
    def _format_ts(value: datetime) -> str:
        return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


__all__ = [
    "CxCursorPlan",
    "CxapiSync",
    "cxapi_endpoint",
    "initial_backfill_window",
    "last_completed_hour",
    "next_hour_cursor",
    "truncate_to_hour",
]
