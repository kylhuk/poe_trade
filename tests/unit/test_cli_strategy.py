from poe_trade import cli


def test_strategy_list_outputs_discovered_packs(capsys):
    result = cli.main(["strategy", "list"])

    assert result == 0
    output = capsys.readouterr().out
    assert "bulk_essence\tBulk Essence Premium\t1\tmanual_trade\tdelayed" in output
    assert "fragment_sets\tFragment Set Assembly\t1\tmanual_trade\tdelayed" in output


def test_strategy_enable_command(monkeypatch, capsys):
    class _RegistryModule:
        @staticmethod
        def set_strategy_enabled(strategy_id, enabled):
            assert strategy_id == "bulk_essence"
            assert enabled is True
            return "/tmp/strategy.toml"

    monkeypatch.setattr(
        cli.importlib,
        "import_module",
        lambda name: _RegistryModule if name == "poe_trade.strategy.registry" else None,
    )

    result = cli.main(["strategy", "enable", "bulk_essence"])

    assert result == 0
    assert capsys.readouterr().out.strip() == "/tmp/strategy.toml"


def test_strategy_disable_command(monkeypatch, capsys):
    class _RegistryModule:
        @staticmethod
        def set_strategy_enabled(strategy_id, enabled):
            assert strategy_id == "bulk_essence"
            assert enabled is False
            return "/tmp/strategy.toml"

    monkeypatch.setattr(
        cli.importlib,
        "import_module",
        lambda name: _RegistryModule if name == "poe_trade.strategy.registry" else None,
    )

    result = cli.main(["strategy", "disable", "bulk_essence"])

    assert result == 0
    assert capsys.readouterr().out.strip() == "/tmp/strategy.toml"
