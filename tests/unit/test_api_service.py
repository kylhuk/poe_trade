from __future__ import annotations

from types import SimpleNamespace

import pytest

from poe_trade import cli
from poe_trade.services import api as service_api


def test_cli_can_dispatch_api_service(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[list[str]] = []

    def _fake_main(argv):
        called.append(list(argv))
        return 0

    monkeypatch.setattr(cli, "_ensure_settings", lambda: None)
    monkeypatch.setattr(cli, "_load_service_main", lambda name: _fake_main)
    result = cli.main(
        ["service", "--name", "api", "--", "--host", "127.0.0.1", "--port", "8080"]
    )
    assert result == 0
    assert called == [["--host", "127.0.0.1", "--port", "8080"]]


def test_service_help_renders() -> None:
    with pytest.raises(SystemExit) as exc:
        service_api.main(["--help"])
    assert exc.value.code == 0


def test_unknown_service_still_errors() -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["service", "--name", "not-a-real-service"])
    assert exc.value.code == 2


def test_service_main_delegates_to_app_layer(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = SimpleNamespace(api_bind_host="127.0.0.1", api_bind_port=8080)
    seen: dict[str, object] = {}
    monkeypatch.setattr(service_api.config_settings, "get_settings", lambda: cfg)
    monkeypatch.setattr(service_api, "_configure_logging", lambda: None)
    monkeypatch.setattr(
        service_api,
        "create_app",
        lambda settings: seen.setdefault("app_settings", settings) or object(),
    )

    def _stop(app, *, host, port):
        seen["app"] = app
        seen["host"] = host
        seen["port"] = port
        raise RuntimeError("stop")

    monkeypatch.setattr(service_api, "serve", _stop)
    with pytest.raises(RuntimeError, match="stop"):
        service_api.main(["--host", "127.0.0.1", "--port", "9090"])
    assert seen["app_settings"] is cfg
    assert seen["host"] == "127.0.0.1"
    assert seen["port"] == 9090
