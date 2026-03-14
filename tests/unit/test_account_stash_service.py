from __future__ import annotations

from types import SimpleNamespace

from poe_trade.services import account_stash_harvester as service


def test_service_exits_when_disabled(monkeypatch) -> None:
    monkeypatch.setattr(
        service.config_settings,
        "get_settings",
        lambda: SimpleNamespace(enable_account_stash=False),
    )
    assert service.main([]) == 0


def test_service_requires_access_token(monkeypatch) -> None:
    monkeypatch.setattr(
        service.config_settings,
        "get_settings",
        lambda: SimpleNamespace(
            enable_account_stash=True,
            account_stash_access_token="",
        ),
    )
    assert service.main([]) == 1
