from pathlib import Path

import importlib


def test_list_strategy_packs_discovers_initial_packs() -> None:
    registry = importlib.import_module("poe_trade.strategy.registry")
    packs = registry.list_strategy_packs()

    assert [pack.strategy_id for pack in packs] == [
        "advanced_rare_finish",
        "bulk_essence",
        "bulk_fossils",
        "cluster_basic",
        "corruption_ev",
        "cx_market_making",
        "dump_tab_reprice",
        "flask_basic",
        "fossil_scarcity",
        "fragment_sets",
        "high_dim_jewels",
        "map_logbook_packages",
        "rog_basic",
        "scarab_reroll",
    ]
    enabled_ids = {pack.strategy_id for pack in packs if pack.enabled}
    assert enabled_ids == {
        "bulk_essence",
        "bulk_fossils",
        "cluster_basic",
        "flask_basic",
        "fragment_sets",
        "map_logbook_packages",
    }
    assert all(pack.discover_sql_path.exists() for pack in packs)
    assert all(pack.backtest_sql_path.exists() for pack in packs)


def test_set_strategy_enabled_updates_metadata(tmp_path, monkeypatch) -> None:
    registry = importlib.import_module("poe_trade.strategy.registry")
    metadata_path = tmp_path / "strategy.toml"
    metadata_path.write_text(
        'id = "demo"\nname = "Demo"\nenabled = true\n',
        encoding="utf-8",
    )
    pack = registry.StrategyPack(
        strategy_id="demo",
        name="Demo",
        enabled=True,
        priority=1,
        latency_class="delayed",
        execution_venue="manual_trade",
        capital_tier="bootstrap",
        metadata_path=metadata_path,
        notes_path=Path("notes.md"),
        discover_sql_path=Path("discover.sql"),
        backtest_sql_path=Path("backtest.sql"),
    )

    monkeypatch.setattr(registry, "list_strategy_packs", lambda: [pack])
    updated_path = registry.set_strategy_enabled("demo", False)

    assert updated_path == metadata_path
    assert "enabled = false" in metadata_path.read_text(encoding="utf-8")


def test_all_backtest_sql_files_use_shared_contract_columns() -> None:
    registry = importlib.import_module("poe_trade.strategy.registry")
    required_columns = (
        "time_bucket",
        "league",
        "item_or_market_key",
        "expected_profit_chaos",
        "expected_roi",
        "confidence",
        "summary",
    )

    for pack in registry.list_strategy_packs():
        sql = pack.backtest_sql_path.read_text(encoding="utf-8")
        assert "SELECT *" not in sql
        for column in required_columns:
            assert column in sql
