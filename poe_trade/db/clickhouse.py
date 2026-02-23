"""Minimal ClickHouse HTTP wrapper."""

from __future__ import annotations

import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Mapping

logger = logging.getLogger(__name__)


class ClickHouseClientError(RuntimeError):
    """Raised when ClickHouse requests fail."""


@dataclass(frozen=True)
class ClickHouseClient:
    endpoint: str
    database: str | None = None
    user: str | None = None
    password: str | None = None
    timeout: float = 30.0

    @classmethod
    def from_env(cls, endpoint: str, database: str | None = None) -> "ClickHouseClient":
        resolved_database = (
            database
            or os.getenv("POE_CLICKHOUSE_DATABASE")
            or os.getenv("CH_DATABASE")
        )
        return cls(
            endpoint=endpoint,
            database=resolved_database,
            user=os.getenv("POE_CLICKHOUSE_USER") or os.getenv("CH_USER"),
            password=os.getenv("POE_CLICKHOUSE_PASSWORD") or os.getenv("CH_PASSWORD"),
            timeout=float(
                os.getenv("POE_CLICKHOUSE_TIMEOUT")
                or os.getenv("CH_TIMEOUT")
                or "30"
            ),
        )

    def execute(self, query: str) -> str:
        payload = query.encode("utf-8")
        params: Mapping[str, str] = {}
        if self.user:
            params = {**params, "user": self.user}
        if self.password:
            params = {**params, "password": self.password}
        if self.database:
            params = {**params, "database": self.database}
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
                text = response.read().decode("utf-8")
                logger.debug("ClickHouse response length=%d", len(text))
                return text
        except urllib.error.HTTPError as exc:  # pragma: no cover - depends on ClickHouse
            msg = exc.read().decode("utf-8", errors="ignore")
            logger.error("ClickHouse HTTPError %s: %s", exc.code, msg)
            raise ClickHouseClientError(msg) from exc
        except urllib.error.URLError as exc:  # pragma: no cover - network
            logger.error("ClickHouse URLError: %s", exc)
            raise ClickHouseClientError(str(exc)) from exc

    def _build_url(self, params: Mapping[str, str]) -> str:
        cleaned = self.endpoint.rstrip("/")
        if params:
            return f"{cleaned}/?{urllib.parse.urlencode(params)}"
        return f"{cleaned}/"
