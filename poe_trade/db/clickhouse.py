"""Minimal ClickHouse HTTP wrapper."""

from __future__ import annotations

import logging
import os
import socket
import urllib.error
import urllib.parse
import urllib.request
import io
from collections.abc import Mapping
from dataclasses import dataclass

import pandas as pd

logger = logging.getLogger(__name__)


class ClickHouseClientError(RuntimeError):
    """Raised when ClickHouse requests fail."""

    def __init__(
        self,
        message: str,
        *,
        retryable: bool = False,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.retryable: bool = retryable
        self.status_code: int | None = status_code


def _is_retryable_http_status(status_code: int) -> bool:
    return status_code in {408, 425, 429, 500, 502, 503, 504}


@dataclass(frozen=True)
class ClickHouseClient:
    endpoint: str
    database: str | None = None
    user: str | None = None
    password: str | None = None
    timeout: float = 300.0

    @classmethod
    def from_env(cls, endpoint: str, database: str | None = None) -> "ClickHouseClient":
        resolved_database = (
            database or os.getenv("POE_CLICKHOUSE_DATABASE") or os.getenv("CH_DATABASE")
        )
        return cls(
            endpoint=endpoint,
            database=resolved_database,
            user=os.getenv("POE_CLICKHOUSE_USER") or os.getenv("CH_USER"),
            password=os.getenv("POE_CLICKHOUSE_PASSWORD") or os.getenv("CH_PASSWORD"),
            timeout=float(
                os.getenv("POE_CLICKHOUSE_TIMEOUT") or os.getenv("CH_TIMEOUT") or "300"
            ),
        )

    def execute(self, query: str, settings: Mapping[str, str] | None = None) -> str:
        payload = query.encode("utf-8")
        params: Mapping[str, str] = {}
        if self.user:
            params = {**params, "user": self.user}
        if self.password:
            params = {**params, "password": self.password}
        if self.database:
            params = {**params, "database": self.database}
        if settings:
            params = {**params, **settings}
        url = self._build_url(params)
        request = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "text/plain; charset=utf-8"},
            method="POST",
        )
        logger.debug("ClickHouse -> %s", url)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                response_body = response.read()
                text = (
                    response_body.decode("utf-8")
                    if isinstance(response_body, bytes)
                    else str(response_body)
                )
                logger.debug("ClickHouse response length=%d", len(text))
                return text
        except (
            urllib.error.HTTPError
        ) as exc:  # pragma: no cover - depends on ClickHouse
            msg = exc.read().decode("utf-8", errors="ignore")
            logger.error("ClickHouse HTTPError %s: %s", exc.code, msg)
            raise ClickHouseClientError(
                msg or f"HTTP {exc.code}",
                retryable=_is_retryable_http_status(exc.code),
                status_code=exc.code,
            ) from exc
        except urllib.error.URLError as exc:  # pragma: no cover - network
            logger.error("ClickHouse URLError: %s", exc)
            raise ClickHouseClientError(str(exc), retryable=True) from exc
        except (TimeoutError, socket.timeout) as exc:  # pragma: no cover - network
            logger.error("ClickHouse timeout: %s", exc)
            raise ClickHouseClientError(str(exc), retryable=True) from exc
        except OSError as exc:  # pragma: no cover - network
            logger.error("ClickHouse socket error: %s", exc)
            raise ClickHouseClientError(str(exc), retryable=True) from exc

    def query_df(
        self, query: str, settings: Mapping[str, str] | None = None
    ) -> pd.DataFrame:
        normalized = query.strip().rstrip(";")
        if " FORMAT " not in normalized.upper():
            normalized = f"{normalized} FORMAT JSONEachRow"
        payload = self.execute(normalized, settings=settings).strip()
        if not payload:
            return pd.DataFrame()
        return pd.read_json(io.StringIO(payload), lines=True)

    def _build_url(self, params: Mapping[str, str]) -> str:
        cleaned = self.endpoint.rstrip("/")
        if params:
            return f"{cleaned}/?{urllib.parse.urlencode(params)}"
        return f"{cleaned}/"
