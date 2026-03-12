import json
from types import SimpleNamespace

from poe_trade.ml import cli


def test_audit_data_writes_expected_keys(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(
        cli.settings,
        "get_settings",
        lambda: SimpleNamespace(clickhouse_url="http://clickhouse"),
    )

    class _Client:
        pass

    monkeypatch.setattr(
        cli.ClickHouseClient,
        "from_env",
        lambda _url: _Client(),
    )

    class _RuntimeProfile:
        machine = "linux-x86_64"
        cpu_cores = 12
        total_ram_gb = 16.0
        available_ram_gb = 8.0
        gpu_backend_available = False
        backend_availability = {"nvidia_smi": False, "rocm": False}
        chosen_backend = "cpu"
        default_workers = 6
        memory_budget_gb = 4.0

    monkeypatch.setattr(cli, "detect_runtime_profile", lambda: _RuntimeProfile())
    monkeypatch.setattr(cli, "persist_runtime_profile", lambda _profile: None)

    monkeypatch.setattr(
        cli,
        "build_audit_report",
        lambda _client, *, league, runtime_profile: {
            "league": league,
            "total_rows": 3,
            "priced_rows": 1,
            "clean_currency_rows": 1,
            "base_type_count": 1,
            "category_breakdown": [{"key": "essence", "value": 1}],
            "market_context_coverage": {
                "gold_currency_ref_hour_rows": 1,
                "gold_listing_ref_hour_rows": 1,
                "gold_liquidity_ref_hour_rows": 1,
            },
            "mod_storage_breakdown": {"explicit_mod_rows": 1},
            "poeninja_snapshot_rows": 0,
            "sale_proxy_rows": 0,
            "outlier_summary": {"trainable": 1},
            "hardware_profile": {
                "cpu_cores": runtime_profile.cpu_cores,
                "gpu_backend_available": runtime_profile.gpu_backend_available,
            },
            "chosen_backend": runtime_profile.chosen_backend,
            "default_workers": runtime_profile.default_workers,
            "memory_budget_gb": runtime_profile.memory_budget_gb,
            "target_contract": {
                "name": "execution-aware league price in chaos",
                "description": "desc",
                "recommendation_semantics": "semantics",
                "required_label_fields": [
                    "label_source",
                    "label_quality",
                    "as_of_ts",
                    "league",
                    "outlier_status",
                ],
            },
        },
    )

    output = tmp_path / "task-1-audit-data.json"
    result = cli.main(["audit-data", "--league", "Mirage", "--output", str(output)])

    assert result == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["priced_rows"] == 1
    assert payload["total_rows"] == 3
    assert payload["clean_currency_rows"] == 1
    assert payload["base_type_count"] == 1
    assert "category_breakdown" in payload
    assert "market_context_coverage" in payload
    assert "mod_storage_breakdown" in payload
    assert "poeninja_snapshot_rows" in payload
    assert "sale_proxy_rows" in payload
    assert "outlier_summary" in payload
    assert "hardware_profile" in payload
    assert payload["chosen_backend"] == "cpu"
    assert payload["default_workers"] == 6
    assert payload["memory_budget_gb"] == 4.0
    assert "target_contract" in payload
    assert json.loads(capsys.readouterr().out)["league"] == "Mirage"


def test_audit_data_rejects_unvalidated_league(monkeypatch, capsys):
    monkeypatch.setattr(
        cli.settings,
        "get_settings",
        lambda: SimpleNamespace(clickhouse_url="http://clickhouse"),
    )

    class _Client:
        pass

    monkeypatch.setattr(
        cli.ClickHouseClient,
        "from_env",
        lambda _url: _Client(),
    )

    class _RuntimeProfile:
        machine = "linux-x86_64"
        cpu_cores = 12
        total_ram_gb = 16.0
        available_ram_gb = 8.0
        gpu_backend_available = False
        backend_availability = {"nvidia_smi": False, "rocm": False}
        chosen_backend = "cpu"
        default_workers = 6
        memory_budget_gb = 4.0

    monkeypatch.setattr(cli, "detect_runtime_profile", lambda: _RuntimeProfile())
    monkeypatch.setattr(cli, "persist_runtime_profile", lambda _profile: None)

    result = cli.main(["audit-data", "--league", "Standard"])

    assert result == 2
    assert "not yet validated" in capsys.readouterr().err
