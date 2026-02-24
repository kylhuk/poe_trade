"""Private stash snapshot service logic."""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from ..config import constants

import uvicorn
from fastapi import FastAPI, Header, HTTPException, status

from ..db import ClickHouseClient
from .checkpoints import CheckpointStore
from .poe_client import PoeClient
from .rate_limit import RateLimitPolicy
from .status import StatusReporter

logger = logging.getLogger(__name__)


class OAuthToken:
    def __init__(self, access_token: str, expires_in: int) -> None:
        self.access_token = access_token
        self.refresh_token: str | None = None
        safety = max(expires_in - 30, 0)
        self.expires_at = datetime.now(timezone.utc) + timedelta(seconds=safety)

    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) >= self.expires_at


class OAuthClient:
    def __init__(
        self,
        client: PoeClient,
        client_id: str,
        client_secret: str,
        grant_type: str,
        scope: str,
    ) -> None:
        self._client = client
        self._client_id = client_id
        self._client_secret = client_secret
        self._grant_type = grant_type
        self._scope = scope

    def refresh(self) -> OAuthToken:
        payload: dict[str, str] = {
            "grant_type": self._grant_type,
            "client_id": self._client_id,
            "client_secret": self._client_secret,
        }
        payload["scope"] = self._scope
        response = self._client.request(
            "POST",
            "token",
            data=payload,
        )
        expires_value = response.get("expires_in")
        expires_seconds = 1800 if expires_value is None else int(expires_value)
        token = OAuthToken(
            access_token=response["access_token"],
            expires_in=expires_seconds,
        )
        token.refresh_token = response.get("refresh_token")
        return token


def oauth_client_factory(settings: Any) -> OAuthClient:
    if not (settings.oauth_client_id and settings.oauth_client_secret):
        raise ValueError("OAuth credentials are missing")
    grant_type = (settings.oauth_grant_type or "").strip()
    if grant_type != "client_credentials":
        raise ValueError("POE_OAUTH_GRANT_TYPE must be 'client_credentials'")
    scope = (settings.oauth_scope or "").strip()
    if "service:psapi" not in scope.split():
        raise ValueError("POE_OAUTH_SCOPE must include 'service:psapi'")
    policy = RateLimitPolicy(
        settings.rate_limit_max_retries,
        settings.rate_limit_backoff_base,
        settings.rate_limit_backoff_max,
        settings.rate_limit_jitter,
    )
    client = PoeClient(
        settings.poe_auth_base_url,
        policy,
        settings.poe_user_agent,
        settings.poe_request_timeout,
    )
    return OAuthClient(
        client,
        settings.oauth_client_id,
        settings.oauth_client_secret,
        grant_type,
        scope,
    )


class StashScribe:
    def __init__(
        self,
        api_client: PoeClient,
        auth_client: OAuthClient,
        ck_client: ClickHouseClient,
        checkpoint_store: CheckpointStore,
        status_reporter: StatusReporter,
        league: str,
        realm: str,
        stash_api_path: str = constants.DEFAULT_POE_STASH_API_PATH,
        account: str | None = None,
    ) -> None:
        self._api_client = api_client
        self._auth_client = auth_client
        self._clickhouse = ck_client
        self._checkpoints = checkpoint_store
        self._status = status_reporter
        self._league = league
        self._realm = realm
        self._stash_api_path = stash_api_path
        self._account = account or "stash"
        self._token: OAuthToken | None = None
        self._error_count = 0
        self._stalled_since: datetime | None = None
        self._lock = threading.Lock()
        self._capture_lock = threading.Lock()

    def run(self, interval: float, dry_run: bool, once: bool) -> None:
        logger.info(
            "StashScribe starting league=%s realm=%s dry_run=%s",
            self._league,
            self._realm,
            dry_run,
        )
        stop_event = threading.Event()
        try:
            while not stop_event.is_set():
                self.capture_snapshot(dry_run=dry_run)
                if once:
                    return
                stop_event.wait(interval)
        except KeyboardInterrupt:
            logger.info("StashScribe interrupted")

    def capture_snapshot(self, dry_run: bool) -> None:
        with self._capture_lock:
            self._perform_capture(dry_run)

    def _perform_capture(self, dry_run: bool) -> None:
        key = f"{self._realm}:{self._league}"
        start = time.monotonic()
        cursor = self._checkpoints.read(key)
        next_change_id: str | None = None
        status_text = "success"
        error_message: str | None = None
        now = datetime.now(timezone.utc)
        try:
            self._ensure_token()
            params: dict[str, str] = {"league": self._league}
            if self._realm:
                params["realm"] = self._realm
            if cursor:
                params["id"] = cursor
            payload = self._api_client.request(
                "GET", self._stash_api_path, params=params
            )
            if isinstance(payload, dict):
                next_change_id = payload.get("next_change_id")
                rows = self._rows(payload, now)
                if rows and not dry_run:
                    self._write(rows)
                if next_change_id and not dry_run:
                    self._checkpoints.write(key, next_change_id)
                with self._lock:
                    self._error_count = 0
                    self._stalled_since = None
            else:
                status_text = "unexpected payload"
                logger.warning("Unexpected stash payload: %s", payload)
        except Exception as exc:  # pragma: no cover - best effort
            error_message = str(exc)
            status_text = "error"
            with self._lock:
                if self._error_count == 0:
                    self._stalled_since = now
                self._error_count += 1
            logger.exception("StashScribe failed to capture snapshot")
        finally:
            duration = time.monotonic() - start
            rate = 1.0 / max(duration, 1e-3)
            self._status.report(
                league=self._league,
                realm=self._realm,
                cursor=cursor,
                next_change_id=next_change_id,
                last_ingest_at=now,
                request_rate=rate,
                status=status_text,
                error=error_message,
                error_count=self._error_count,
                stalled_since=self._stalled_since,
            )

    def _ensure_token(self) -> None:
        if self._token is None or self._token.is_expired():
            self._token = self._auth_client.refresh()
            self._api_client.set_bearer_token(self._token.access_token)

    def _rows(self, payload: dict[str, Any], now: datetime) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        captured = now.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        next_change_id = payload.get("next_change_id")
        entries = payload.get("tabs")
        if not entries:
            entries = payload.get("stashes") or []
        for entry in entries:
            tab_id = str(
                entry.get("id")
                or entry.get("tab_id")
                or entry.get("stash_id")
                or ""
            )
            rows.append(
                {
                    "snapshot_id": f"{self._account}:{tab_id}:{captured}",
                    "captured_at": captured,
                    "realm": self._realm,
                    "league": self._league,
                    "tab_id": tab_id,
                    "next_change_id": next_change_id or "",
                    "payload_json": json.dumps(entry, ensure_ascii=False),
                }
            )
        return rows

    def _write(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        payload = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)
        query = (
            "INSERT INTO poe_trade.raw_account_stash_snapshot "
            "(snapshot_id, captured_at, realm, league, tab_id, next_change_id, payload_json)\n"
            "FORMAT JSONEachRow\n"
            f"{payload}"
        )
        self._clickhouse.execute(query)

    def start_trigger_server(
        self, port: int, trigger_token: str | None
    ) -> tuple[uvicorn.Server, threading.Thread]:
        app = create_trigger_app(self, trigger_token)
        config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
        server = uvicorn.Server(config)
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        logger.info("StashScribe trigger server running on port %s", port)
        return server, thread


def create_trigger_app(service: StashScribe, trigger_token: str | None) -> FastAPI:
    app = FastAPI(title="PoE Stash Trigger")

    @app.post("/trigger")
    def trigger(x_trigger_token: str | None = Header(None)) -> dict[str, str]:
        if not trigger_token:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Trigger endpoint disabled without a token",
            )
        if x_trigger_token != trigger_token:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                detail="Unauthorized trigger token",
            )
        service.capture_snapshot(dry_run=False)
        return {"status": "completed"}

    return app
