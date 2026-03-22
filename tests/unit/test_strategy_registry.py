from pathlib import Path
import tomllib

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
    assert all(pack.candidate_sql_path.name == "candidate.sql" for pack in packs)
    canonical_candidate_ids = {pack.strategy_id for pack in packs}
    discovered_candidate_ids = {
        pack.strategy_id for pack in packs if pack.candidate_sql_path.exists()
    }
    assert discovered_candidate_ids == canonical_candidate_ids
    bulk_essence = next(pack for pack in packs if pack.strategy_id == "bulk_essence")
    assert bulk_essence.min_expected_profit_chaos == 20.0
    assert bulk_essence.min_expected_roi == 0.2
    assert bulk_essence.min_confidence == 0.65
    assert bulk_essence.min_sample_count == 30
    assert bulk_essence.cooldown_minutes == 180
    assert bulk_essence.requires_journal is False


def test_list_strategy_packs_loads_safe_default_opportunity_gates() -> None:
    registry = importlib.import_module("poe_trade.strategy.registry")

    bulk_essence = next(
        pack
        for pack in registry.list_strategy_packs()
        if pack.strategy_id == "bulk_essence"
    )

    assert bulk_essence.max_staleness_minutes == 15
    assert bulk_essence.min_liquidity_score == 0.72
    assert bulk_essence.max_estimated_whispers == 6
    assert bulk_essence.max_estimated_operations == 3
    assert bulk_essence.advanced_override_profit_per_operation_chaos is None


def test_all_strategy_packs_define_opportunity_gate_params_in_metadata() -> None:
    registry = importlib.import_module("poe_trade.strategy.registry")
    required_params = (
        "max_staleness_minutes",
        "min_liquidity_score",
        "max_estimated_whispers",
        "max_estimated_operations",
        "advanced_override_profit_per_operation_chaos",
    )

    for pack in registry.list_strategy_packs():
        metadata = tomllib.loads(pack.metadata_path.read_text(encoding="utf-8"))
        params = metadata.get("params", {})
        assert isinstance(params, dict)
        for param in required_params:
            assert param in params


def test_list_strategy_packs_applies_override_and_clamp_rules(
    tmp_path, monkeypatch
) -> None:
    registry = importlib.import_module("poe_trade.strategy.registry")

    strategies_root = tmp_path / "strategies"
    sql_root = tmp_path / "sql"

    def write_strategy(name: str, params: str) -> None:
        strategy_dir = strategies_root / name
        strategy_dir.mkdir(parents=True)
        (strategy_dir / "strategy.toml").write_text(
            (
                f'id = "{name}"\n'
                f'name = "{name}"\n'
                "enabled = true\n"
                "\n[minima]\n"
                "expected_profit_chaos = 1\n"
                "\n[params]\n"
                f"{params}"
            ),
            encoding="utf-8",
        )
        (strategy_dir / "notes.md").write_text("notes\n", encoding="utf-8")
        sql_dir = sql_root / name
        sql_dir.mkdir(parents=True)
        (sql_dir / "discover.sql").write_text("SELECT 1\n", encoding="utf-8")
        (sql_dir / "backtest.sql").write_text("SELECT 1\n", encoding="utf-8")

    write_strategy(
        "explicit_override",
        "max_staleness_minutes = 42\n"
        "min_liquidity_score = 0.75\n"
        "max_estimated_whispers = 8\n"
        "max_estimated_operations = 5\n"
        "advanced_override_profit_per_operation_chaos = 18.5\n",
    )
    write_strategy(
        "clamped_invalid_override",
        "max_staleness_minutes = -7\n"
        'min_liquidity_score = "not-a-number"\n'
        "max_estimated_whispers = -3\n"
        "max_estimated_operations = -2\n"
        'advanced_override_profit_per_operation_chaos = "bad"\n',
    )
    write_strategy(
        "liquidity_cap_override",
        "min_liquidity_score = 1.5\n",
    )

    monkeypatch.setattr(registry, "STRATEGY_ROOT", strategies_root)
    monkeypatch.setattr(registry, "SQL_STRATEGY_ROOT", sql_root)

    packs = {pack.strategy_id: pack for pack in registry.list_strategy_packs()}

    explicit_override = packs["explicit_override"]
    assert explicit_override.max_staleness_minutes == 42
    assert explicit_override.min_liquidity_score == 0.75
    assert explicit_override.max_estimated_whispers == 8
    assert explicit_override.max_estimated_operations == 5
    assert explicit_override.advanced_override_profit_per_operation_chaos == 18.5

    clamped_invalid_override = packs["clamped_invalid_override"]
    assert clamped_invalid_override.max_staleness_minutes == 0
    assert clamped_invalid_override.min_liquidity_score == 0.5
    assert clamped_invalid_override.max_estimated_whispers == 0
    assert clamped_invalid_override.max_estimated_operations == 1
    assert clamped_invalid_override.advanced_override_profit_per_operation_chaos is None

    liquidity_cap_override = packs["liquidity_cap_override"]
    assert liquidity_cap_override.min_liquidity_score == 1.0


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
        min_expected_profit_chaos=10.0,
        min_expected_roi=0.1,
        min_confidence=0.5,
        min_sample_count=5,
        cooldown_minutes=60,
        requires_journal=False,
        max_staleness_minutes=15,
        min_liquidity_score=0.5,
        max_estimated_whispers=6,
        max_estimated_operations=3,
        advanced_override_profit_per_operation_chaos=None,
        metadata_path=metadata_path,
        notes_path=Path("notes.md"),
        discover_sql_path=Path("discover.sql"),
        backtest_sql_path=Path("backtest.sql"),
        candidate_sql_path=Path("candidate.sql"),
    )

    monkeypatch.setattr(registry, "list_strategy_packs", lambda: [pack])
    updated_path = registry.set_strategy_enabled("demo", False)

    assert updated_path == metadata_path
    assert "enabled = false" in metadata_path.read_text(encoding="utf-8")


def test_candidate_sql_helper_prefers_canonical_path_when_present(tmp_path) -> None:
    registry = importlib.import_module("poe_trade.strategy.registry")
    canonical_sql = tmp_path / "candidate.sql"
    canonical_sql.write_text("SELECT 1 AS canonical", encoding="utf-8")
    backtest_sql = tmp_path / "backtest.sql"
    backtest_sql.write_text("SELECT 1 AS fallback", encoding="utf-8")

    pack = registry.StrategyPack(
        strategy_id="demo",
        name="Demo",
        enabled=True,
        priority=1,
        latency_class="delayed",
        execution_venue="manual_trade",
        capital_tier="bootstrap",
        min_expected_profit_chaos=10.0,
        min_expected_roi=0.1,
        min_confidence=0.5,
        min_sample_count=5,
        cooldown_minutes=60,
        requires_journal=False,
        max_staleness_minutes=15,
        min_liquidity_score=0.5,
        max_estimated_whispers=6,
        max_estimated_operations=3,
        advanced_override_profit_per_operation_chaos=None,
        metadata_path=tmp_path / "strategy.toml",
        notes_path=tmp_path / "notes.md",
        discover_sql_path=tmp_path / "discover.sql",
        backtest_sql_path=backtest_sql,
        candidate_sql_path=canonical_sql,
    )

    assert registry.get_candidate_sql_path(pack) == canonical_sql
    assert registry.load_candidate_sql(pack) == "SELECT 1 AS canonical"


def test_candidate_sql_helper_falls_back_to_backtest_path(tmp_path) -> None:
    registry = importlib.import_module("poe_trade.strategy.registry")
    backtest_sql = tmp_path / "backtest.sql"
    backtest_sql.write_text("SELECT 1 AS fallback", encoding="utf-8")

    pack = registry.StrategyPack(
        strategy_id="demo",
        name="Demo",
        enabled=True,
        priority=1,
        latency_class="delayed",
        execution_venue="manual_trade",
        capital_tier="bootstrap",
        min_expected_profit_chaos=10.0,
        min_expected_roi=0.1,
        min_confidence=0.5,
        min_sample_count=5,
        cooldown_minutes=60,
        requires_journal=False,
        max_staleness_minutes=15,
        min_liquidity_score=0.5,
        max_estimated_whispers=6,
        max_estimated_operations=3,
        advanced_override_profit_per_operation_chaos=None,
        metadata_path=tmp_path / "strategy.toml",
        notes_path=tmp_path / "notes.md",
        discover_sql_path=tmp_path / "discover.sql",
        backtest_sql_path=backtest_sql,
        candidate_sql_path=tmp_path / "candidate.sql",
    )

    assert registry.get_candidate_sql_path(pack) == backtest_sql
    assert registry.load_candidate_sql(pack) == "SELECT 1 AS fallback"


def test_all_backtest_sql_files_use_shared_contract_columns() -> None:
    registry = importlib.import_module("poe_trade.strategy.registry")
    required_columns = (
        "time_bucket",
        "league",
        "item_or_market_key",
        "semantic_key",
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


def test_candidate_sql_files_use_explicit_scanner_columns() -> None:
    registry = importlib.import_module("poe_trade.strategy.registry")
    required_aliases = (
        "AS TIME_BUCKET",
        "AS LEAGUE",
        "AS ITEM_OR_MARKET_KEY",
        "AS SEMANTIC_KEY",
        "AS EXPECTED_PROFIT_CHAOS",
        "AS EXPECTED_ROI",
        "AS CONFIDENCE",
        "AS SAMPLE_COUNT",
        "AS WHY_IT_FIRED",
        "AS BUY_PLAN",
        "AS EXIT_PLAN",
        "AS EXPECTED_HOLD_TIME",
    )
    sample_terms = (
        "bulk_listing_count",
        "listing_count",
        "small_listing_count",
        "observed_samples",
    )

    for pack in registry.list_strategy_packs():
        if not pack.candidate_sql_path.exists():
            continue
        sql = pack.candidate_sql_path.read_text(encoding="utf-8")
        upper_sql = sql.upper()
        assert "SELECT *" not in upper_sql
        for alias in required_aliases:
            assert alias in upper_sql
        assert any(term in sql for term in sample_terms)


def test_enabled_non_journal_discover_sql_contract() -> None:
    registry = importlib.import_module("poe_trade.strategy.registry")
    required_aliases = (
        "AS TIME_BUCKET",
        "AS LEAGUE",
        "AS ITEM_OR_MARKET_KEY",
        "AS EXPECTED_PROFIT_CHAOS",
        "AS EXPECTED_ROI",
        "AS CONFIDENCE",
        "AS SAMPLE_COUNT",
        "AS WHY_IT_FIRED",
        "AS BUY_PLAN",
        "AS EXIT_PLAN",
    )

    for pack in registry.list_strategy_packs():
        if not pack.enabled or pack.requires_journal:
            continue
        sql = pack.discover_sql_path.read_text(encoding="utf-8")
        upper_sql = sql.upper()
        assert "SELECT *" not in upper_sql
        for alias in required_aliases:
            assert alias in upper_sql
