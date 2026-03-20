import json
from types import SimpleNamespace
from typing import cast

from poe_trade.ml import cli
from poe_trade.ml import workflows


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


def test_train_loop_forwards_bounded_controls(monkeypatch, capsys):
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

    seen: dict[str, object] = {}

    def _fake_train_loop(
        _client,
        *,
        league,
        dataset_table,
        model_dir,
        max_iterations,
        max_wall_clock_seconds,
        no_improvement_patience,
        min_mdape_improvement,
        resume,
    ):
        seen.update(
            {
                "league": league,
                "dataset_table": dataset_table,
                "model_dir": model_dir,
                "max_iterations": max_iterations,
                "max_wall_clock_seconds": max_wall_clock_seconds,
                "no_improvement_patience": no_improvement_patience,
                "min_mdape_improvement": min_mdape_improvement,
                "resume": resume,
            }
        )
        return {"status": "stopped_budget", "stop_reason": "iteration_budget_exhausted"}

    monkeypatch.setattr(cli, "train_loop", _fake_train_loop)

    result = cli.main(
        [
            "train-loop",
            "--league",
            "Mirage",
            "--dataset-table",
            "poe_trade.ml_price_dataset_v2",
            "--model-dir",
            "artifacts/ml/mirage_v2",
            "--max-iterations",
            "2",
            "--max-wall-clock-seconds",
            "1800",
            "--no-improvement-patience",
            "2",
            "--min-mdape-improvement",
            "0.005",
            "--resume",
        ]
    )

    assert result == 0
    assert seen["max_iterations"] == 2
    assert seen["max_wall_clock_seconds"] == 1800
    assert seen["no_improvement_patience"] == 2
    assert seen["min_mdape_improvement"] == 0.005
    assert seen["resume"] is True
    assert "iteration_budget_exhausted" in capsys.readouterr().out


def test_train_loop_rejects_legacy_v1_dataset(monkeypatch, capsys):
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
    monkeypatch.setattr(
        cli, "detect_runtime_profile", lambda: cast(object, SimpleNamespace())
    )
    monkeypatch.setattr(cli, "persist_runtime_profile", lambda _profile: None)

    result = cli.main(
        [
            "train-loop",
            "--league",
            "Mirage",
            "--dataset-table",
            "poe_trade.ml_price_dataset_v1",
            "--model-dir",
            "artifacts/ml/mirage_v2",
        ]
    )

    assert result == 2
    assert "v2 dataset table" in capsys.readouterr().err


def test_report_includes_manifest_and_baseline_benchmark_metadata(
    monkeypatch, tmp_path
):
    baseline_path = tmp_path / "task-1-baseline.json"
    baseline_path.write_text(
        json.dumps(
            {
                "latency_ms": {"p50": 12.5, "p95": 48.8},
                "corpus_hash": "corpus-abc123",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("POE_ML_BASELINE_BENCHMARK_PATH", str(baseline_path))

    def _fake_query(_client, query: str):
        if "FROM poe_trade.ml_eval_runs" in query and "GROUP BY run_id" in query:
            return [{"run_id": "eval-2", "recorded_at": "2026-03-15 12:00:00"}]
        if "FROM poe_trade.ml_eval_runs" in query and "GROUP BY route" in query:
            return [
                {
                    "route": "structured_boosted",
                    "mdape": 0.11,
                    "wape": 0.2,
                    "rmsle": 0.3,
                    "abstain_rate": 0.05,
                }
            ]
        if "SELECT dataset_snapshot_id, eval_slice_id, source_watermarks_json" in query:
            return [
                {
                    "dataset_snapshot_id": "dataset-2",
                    "eval_slice_id": "eval-slice-2",
                    "source_watermarks_json": '{"dataset_max_as_of_ts":"2026-03-15 12:00:00"}',
                }
            ]
        if "FROM poe_trade.ml_route_eval_v1" in query and "GROUP BY family" in query:
            return []
        if "FROM poe_trade.ml_price_predictions_v1" in query:
            return []
        if "FROM poe_trade.ml_price_labels_v2" in query:
            return []
        return []

    monkeypatch.setattr(workflows, "_ensure_supported_league", lambda _league: None)
    monkeypatch.setattr(workflows, "_query_rows", _fake_query)
    monkeypatch.setattr(
        workflows,
        "_eval_feedback_for_run",
        lambda *_args, **_kwargs: {
            "candidate_vs_incumbent": {},
            "latest_avg_mdape": 0.11,
            "latest_avg_interval_coverage": 0.8,
            "promotion_policy": {},
        },
    )
    monkeypatch.setattr(
        workflows,
        "_latest_route_hotspots",
        lambda *_args, **_kwargs: {"top_improving": [], "top_regressing": []},
    )
    monkeypatch.setattr(
        workflows,
        "_promotion_verdict_for_run",
        lambda *_args, **_kwargs: "hold",
    )

    report_path = tmp_path / "report.json"
    payload = workflows.report(
        cast(workflows.ClickHouseClient, cast(object, SimpleNamespace())),
        league="Mirage",
        model_dir="artifacts/ml/mirage_v1",
        output=str(report_path),
    )

    assert payload["dataset_snapshot_id"] == "dataset-2"
    assert payload["eval_slice_id"] == "eval-slice-2"
    assert payload["source_watermarks"]["dataset_max_as_of_ts"] == "2026-03-15 12:00:00"
    assert payload["baseline_benchmark_evidence_path"] == str(baseline_path)
    assert payload["baseline_benchmark"]["p50_ms"] == 12.5
    assert payload["baseline_benchmark"]["p95_ms"] == 48.8
    assert payload["baseline_benchmark"]["corpus_hash"] == "corpus-abc123"


def test_report_handles_malformed_baseline_benchmark_metadata(monkeypatch, tmp_path):
    baseline_path = tmp_path / "task-1-baseline.json"
    baseline_path.write_text("not-json", encoding="utf-8")
    monkeypatch.setenv("POE_ML_BASELINE_BENCHMARK_PATH", str(baseline_path))

    def _fake_query(_client, query: str):
        if "FROM poe_trade.ml_eval_runs" in query and "GROUP BY run_id" in query:
            return [{"run_id": "eval-2", "recorded_at": "2026-03-15 12:00:00"}]
        if "FROM poe_trade.ml_eval_runs" in query and "GROUP BY route" in query:
            return [
                {
                    "route": "structured_boosted",
                    "mdape": 0.11,
                    "wape": 0.2,
                    "rmsle": 0.3,
                    "abstain_rate": 0.05,
                }
            ]
        if "SELECT dataset_snapshot_id, eval_slice_id, source_watermarks_json" in query:
            return [
                {
                    "dataset_snapshot_id": "dataset-2",
                    "eval_slice_id": "eval-slice-2",
                    "source_watermarks_json": '{"dataset_max_as_of_ts":"2026-03-15 12:00:00"}',
                }
            ]
        if "FROM poe_trade.ml_route_eval_v1" in query and "GROUP BY family" in query:
            return []
        if "FROM poe_trade.ml_price_predictions_v1" in query:
            return []
        if "FROM poe_trade.ml_price_labels_v2" in query:
            return []
        return []

    monkeypatch.setattr(workflows, "_ensure_supported_league", lambda _league: None)
    monkeypatch.setattr(workflows, "_query_rows", _fake_query)
    monkeypatch.setattr(
        workflows,
        "_eval_feedback_for_run",
        lambda *_args, **_kwargs: {
            "candidate_vs_incumbent": {},
            "latest_avg_mdape": 0.11,
            "latest_avg_interval_coverage": 0.8,
            "promotion_policy": {},
        },
    )
    monkeypatch.setattr(
        workflows,
        "_latest_route_hotspots",
        lambda *_args, **_kwargs: {"top_improving": [], "top_regressing": []},
    )
    monkeypatch.setattr(
        workflows,
        "_promotion_verdict_for_run",
        lambda *_args, **_kwargs: "hold",
    )

    report_path = tmp_path / "report.json"
    payload = workflows.report(
        cast(workflows.ClickHouseClient, cast(object, SimpleNamespace())),
        league="Mirage",
        model_dir="artifacts/ml/mirage_v1",
        output=str(report_path),
    )

    assert payload["baseline_benchmark_evidence_path"] == str(baseline_path)
    assert payload["baseline_benchmark"] == {}


def test_report_handles_missing_manifest_row(monkeypatch, tmp_path):
    baseline_path = tmp_path / "task-1-baseline.json"
    baseline_path.write_text(
        json.dumps(
            {
                "latency_ms": {"p50": 10.0, "p95": 35.0},
                "corpus_hash": "corpus-missing-manifest",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("POE_ML_BASELINE_BENCHMARK_PATH", str(baseline_path))

    def _fake_query(_client, query: str):
        if "FROM poe_trade.ml_eval_runs" in query and "GROUP BY run_id" in query:
            return [{"run_id": "eval-2", "recorded_at": "2026-03-15 12:00:00"}]
        if "FROM poe_trade.ml_eval_runs" in query and "GROUP BY route" in query:
            return [
                {
                    "route": "structured_boosted",
                    "mdape": 0.11,
                    "wape": 0.2,
                    "rmsle": 0.3,
                    "abstain_rate": 0.05,
                }
            ]
        if "SELECT dataset_snapshot_id, eval_slice_id, source_watermarks_json" in query:
            return []
        if "FROM poe_trade.ml_route_eval_v1" in query and "GROUP BY family" in query:
            return []
        if "FROM poe_trade.ml_price_predictions_v1" in query:
            return []
        if "FROM poe_trade.ml_price_labels_v2" in query:
            return []
        return []

    monkeypatch.setattr(workflows, "_ensure_supported_league", lambda _league: None)
    monkeypatch.setattr(workflows, "_query_rows", _fake_query)
    monkeypatch.setattr(
        workflows,
        "_eval_feedback_for_run",
        lambda *_args, **_kwargs: {
            "candidate_vs_incumbent": {},
            "latest_avg_mdape": 0.11,
            "latest_avg_interval_coverage": 0.8,
            "promotion_policy": {},
        },
    )
    monkeypatch.setattr(
        workflows,
        "_latest_route_hotspots",
        lambda *_args, **_kwargs: {"top_improving": [], "top_regressing": []},
    )
    monkeypatch.setattr(
        workflows,
        "_promotion_verdict_for_run",
        lambda *_args, **_kwargs: "hold",
    )

    report_path = tmp_path / "report.json"
    payload = workflows.report(
        cast(workflows.ClickHouseClient, cast(object, SimpleNamespace())),
        league="Mirage",
        model_dir="artifacts/ml/mirage_v1",
        output=str(report_path),
    )

    assert payload["dataset_snapshot_id"] == ""
    assert payload["eval_slice_id"] == ""
    assert payload["source_watermarks_json"] == "{}"
    assert payload["source_watermarks"] == {}
    assert payload["baseline_benchmark_evidence_path"] == str(baseline_path)
    assert payload["baseline_benchmark"]["p50_ms"] == 10.0
    assert payload["baseline_benchmark"]["p95_ms"] == 35.0
    assert payload["baseline_benchmark"]["corpus_hash"] == "corpus-missing-manifest"


def test_report_surfaces_integrity_hold_reason_fixtures(monkeypatch, tmp_path):
    baseline_path = tmp_path / "task-3-baseline.json"
    baseline_path.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("POE_ML_BASELINE_BENCHMARK_PATH", str(baseline_path))

    def _fake_query(_client, query: str):
        if "FROM poe_trade.ml_eval_runs" in query and "GROUP BY run_id" in query:
            return [{"run_id": "eval-2", "recorded_at": "2026-03-15 12:00:00"}]
        if "FROM poe_trade.ml_eval_runs" in query and "GROUP BY route" in query:
            return [
                {
                    "route": "structured_boosted",
                    "mdape": 0.11,
                    "wape": 0.2,
                    "rmsle": 0.3,
                    "abstain_rate": 0.05,
                }
            ]
        if "SELECT dataset_snapshot_id, eval_slice_id, source_watermarks_json" in query:
            return [
                {
                    "dataset_snapshot_id": "dataset-2",
                    "eval_slice_id": "eval-slice-2",
                    "source_watermarks_json": '{"dataset_max_as_of_ts":"2026-03-15 12:00:00"}',
                }
            ]
        if "FROM poe_trade.ml_route_eval_v1" in query and "GROUP BY family" in query:
            return []
        if "FROM poe_trade.ml_price_predictions_v1" in query:
            return []
        if "FROM poe_trade.ml_price_labels_v2" in query:
            return []
        return []

    monkeypatch.setattr(workflows, "_ensure_supported_league", lambda _league: None)
    monkeypatch.setattr(workflows, "_query_rows", _fake_query)
    monkeypatch.setattr(
        workflows,
        "_eval_feedback_for_run",
        lambda *_args, **_kwargs: {
            "candidate_vs_incumbent": {
                "hold_reason_codes": [
                    workflows.PROMOTION_LEAKAGE_REASON_CODE,
                    workflows.PROMOTION_FRESHNESS_REASON_CODE,
                ],
                "integrity_gate": {
                    "pass": False,
                    "reason_codes": [
                        workflows.PROMOTION_LEAKAGE_REASON_CODE,
                        workflows.PROMOTION_FRESHNESS_REASON_CODE,
                    ],
                },
                "protected_cohort_regression": {"regression": False},
            },
            "latest_avg_mdape": 0.11,
            "latest_avg_interval_coverage": 0.8,
            "promotion_policy": {
                "protected_cohort": {},
                "integrity": {
                    "freshness_max_lag_minutes": workflows.PROMOTION_FRESHNESS_MAX_LAG_MINUTES
                },
            },
        },
    )
    monkeypatch.setattr(
        workflows,
        "_latest_route_hotspots",
        lambda *_args, **_kwargs: {"top_improving": [], "top_regressing": []},
    )
    monkeypatch.setattr(
        workflows,
        "_promotion_verdict_for_run",
        lambda *_args, **_kwargs: "hold",
    )

    report_path = tmp_path / "report-task-3-fail.json"
    payload = workflows.report(
        cast(workflows.ClickHouseClient, cast(object, SimpleNamespace())),
        league="Mirage",
        model_dir="artifacts/ml/mirage_v1",
        output=str(report_path),
    )

    assert payload["promotion_verdict"] == "hold"
    assert payload["candidate_vs_incumbent"]["hold_reason_codes"] == [
        workflows.PROMOTION_LEAKAGE_REASON_CODE,
        workflows.PROMOTION_FRESHNESS_REASON_CODE,
    ]
    assert (
        payload["promotion_policy"]["integrity"]["freshness_max_lag_minutes"] == 180.0
    )


def test_report_surfaces_integrity_pass_fixture(monkeypatch, tmp_path):
    baseline_path = tmp_path / "task-3-baseline-pass.json"
    baseline_path.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("POE_ML_BASELINE_BENCHMARK_PATH", str(baseline_path))

    def _fake_query(_client, query: str):
        if "FROM poe_trade.ml_eval_runs" in query and "GROUP BY run_id" in query:
            return [{"run_id": "eval-2", "recorded_at": "2026-03-15 12:00:00"}]
        if "FROM poe_trade.ml_eval_runs" in query and "GROUP BY route" in query:
            return [
                {
                    "route": "structured_boosted",
                    "mdape": 0.09,
                    "wape": 0.18,
                    "rmsle": 0.25,
                    "abstain_rate": 0.04,
                }
            ]
        if "SELECT dataset_snapshot_id, eval_slice_id, source_watermarks_json" in query:
            return [
                {
                    "dataset_snapshot_id": "dataset-2",
                    "eval_slice_id": "eval-slice-2",
                    "source_watermarks_json": '{"dataset_max_as_of_ts":"2026-03-15 12:00:00"}',
                }
            ]
        if "FROM poe_trade.ml_route_eval_v1" in query and "GROUP BY family" in query:
            return []
        if "FROM poe_trade.ml_price_predictions_v1" in query:
            return []
        if "FROM poe_trade.ml_price_labels_v2" in query:
            return []
        return []

    monkeypatch.setattr(workflows, "_ensure_supported_league", lambda _league: None)
    monkeypatch.setattr(workflows, "_query_rows", _fake_query)
    monkeypatch.setattr(
        workflows,
        "_eval_feedback_for_run",
        lambda *_args, **_kwargs: {
            "candidate_vs_incumbent": {
                "hold_reason_codes": [],
                "integrity_gate": {
                    "pass": True,
                    "reason_codes": [],
                },
                "protected_cohort_regression": {"regression": False},
            },
            "latest_avg_mdape": 0.09,
            "latest_avg_interval_coverage": 0.83,
            "promotion_policy": {
                "protected_cohort": {},
                "integrity": {
                    "freshness_max_lag_minutes": workflows.PROMOTION_FRESHNESS_MAX_LAG_MINUTES
                },
            },
        },
    )
    monkeypatch.setattr(
        workflows,
        "_latest_route_hotspots",
        lambda *_args, **_kwargs: {"top_improving": [], "top_regressing": []},
    )
    monkeypatch.setattr(
        workflows,
        "_promotion_verdict_for_run",
        lambda *_args, **_kwargs: "promote",
    )

    report_path = tmp_path / "report-task-3-pass.json"
    payload = workflows.report(
        cast(workflows.ClickHouseClient, cast(object, SimpleNamespace())),
        league="Mirage",
        model_dir="artifacts/ml/mirage_v1",
        output=str(report_path),
    )

    assert payload["promotion_verdict"] == "promote"
    assert payload["candidate_vs_incumbent"]["hold_reason_codes"] == []
    assert payload["candidate_vs_incumbent"]["integrity_gate"]["pass"] is True


def _report_fixture_query_for_shadow_gates(_client, query: str):
    if "FROM poe_trade.ml_eval_runs" in query and "GROUP BY run_id" in query:
        return [{"run_id": "eval-shadow", "recorded_at": "2026-03-15 12:00:00"}]
    if "FROM poe_trade.ml_eval_runs" in query and "GROUP BY route" in query:
        return [
            {
                "route": "structured_boosted",
                "mdape": 0.09,
                "wape": 0.18,
                "rmsle": 0.25,
                "abstain_rate": 0.04,
            }
        ]
    if "SELECT dataset_snapshot_id, eval_slice_id, source_watermarks_json" in query:
        return [
            {
                "dataset_snapshot_id": "dataset-shadow",
                "eval_slice_id": "eval-slice-shadow",
                "source_watermarks_json": '{"dataset_max_as_of_ts":"2026-03-15 12:00:00"}',
            }
        ]
    if "FROM poe_trade.ml_route_eval_v1" in query and "GROUP BY family" in query:
        return []
    if "FROM poe_trade.ml_price_predictions_v1" in query:
        return []
    if "FROM poe_trade.ml_price_labels_v2" in query:
        return []
    return []


def test_report_surfaces_shadow_gate_pass_fixture(monkeypatch, tmp_path):
    baseline_path = tmp_path / "task-10-baseline-pass.json"
    baseline_path.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("POE_ML_BASELINE_BENCHMARK_PATH", str(baseline_path))

    monkeypatch.setattr(workflows, "_ensure_supported_league", lambda _league: None)
    monkeypatch.setattr(
        workflows, "_query_rows", _report_fixture_query_for_shadow_gates
    )
    monkeypatch.setattr(
        workflows,
        "_eval_feedback_for_run",
        lambda *_args, **_kwargs: {
            "candidate_vs_incumbent": {
                "hold_reason_codes": [],
                "shadow_gate": {
                    "pass": True,
                    "same_eval_slice": True,
                    "reason_codes": [],
                    "mdape_relative_improvement": 0.25,
                    "min_relative_mdape_improvement": 0.2,
                },
                "integrity_gate": {"pass": True, "reason_codes": []},
                "protected_cohort_regression": {"regression": False},
            },
            "latest_avg_mdape": 0.09,
            "latest_avg_interval_coverage": 0.83,
            "promotion_policy": {
                "shadow": {
                    "min_relative_mdape_improvement": 0.2,
                    "require_same_eval_slice": True,
                },
                "protected_cohort": {"max_mdape_regression": 0.0},
                "integrity": {
                    "freshness_max_lag_minutes": workflows.PROMOTION_FRESHNESS_MAX_LAG_MINUTES
                },
            },
        },
    )
    monkeypatch.setattr(
        workflows,
        "_latest_route_hotspots",
        lambda *_args, **_kwargs: {"top_improving": [], "top_regressing": []},
    )
    monkeypatch.setattr(
        workflows,
        "_promotion_verdict_for_run",
        lambda *_args, **_kwargs: "promote",
    )

    payload = workflows.report(
        cast(workflows.ClickHouseClient, cast(object, SimpleNamespace())),
        league="Mirage",
        model_dir="artifacts/ml/mirage_v1",
        output=str(tmp_path / "report-task-10-pass.json"),
    )

    assert payload["promotion_verdict"] == "promote"
    assert payload["candidate_vs_incumbent"]["hold_reason_codes"] == []
    assert payload["candidate_vs_incumbent"]["shadow_gate"]["pass"] is True
    assert (
        payload["promotion_policy"]["shadow"]["min_relative_mdape_improvement"] == 0.2
    )


def test_report_surfaces_shadow_gate_failure_matrix(monkeypatch, tmp_path):
    baseline_path = tmp_path / "task-10-baseline-failures.json"
    baseline_path.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("POE_ML_BASELINE_BENCHMARK_PATH", str(baseline_path))

    fixtures = [
        [workflows.PROMOTION_SHADOW_MDAPE_REASON_CODE],
        ["hold_protected_cohort_regression"],
        [workflows.PROMOTION_LEAKAGE_REASON_CODE],
        [workflows.PROMOTION_FRESHNESS_REASON_CODE],
    ]
    for reason_codes in fixtures:
        monkeypatch.setattr(workflows, "_ensure_supported_league", lambda _league: None)
        monkeypatch.setattr(
            workflows,
            "_query_rows",
            _report_fixture_query_for_shadow_gates,
        )
        monkeypatch.setattr(
            workflows,
            "_eval_feedback_for_run",
            lambda *_args, _reason_codes=reason_codes, **_kwargs: {
                "candidate_vs_incumbent": {
                    "hold_reason_codes": list(_reason_codes),
                    "shadow_gate": {
                        "pass": _reason_codes
                        != [workflows.PROMOTION_SHADOW_MDAPE_REASON_CODE],
                        "same_eval_slice": True,
                        "reason_codes": list(_reason_codes)
                        if _reason_codes
                        == [workflows.PROMOTION_SHADOW_MDAPE_REASON_CODE]
                        else [],
                    },
                    "integrity_gate": {
                        "pass": not any(
                            code in _reason_codes
                            for code in (
                                workflows.PROMOTION_LEAKAGE_REASON_CODE,
                                workflows.PROMOTION_FRESHNESS_REASON_CODE,
                            )
                        ),
                        "reason_codes": [
                            code
                            for code in _reason_codes
                            if code
                            in (
                                workflows.PROMOTION_LEAKAGE_REASON_CODE,
                                workflows.PROMOTION_FRESHNESS_REASON_CODE,
                            )
                        ],
                    },
                    "protected_cohort_regression": {
                        "regression": _reason_codes
                        == ["hold_protected_cohort_regression"],
                        "reason_code": "hold_protected_cohort_regression"
                        if _reason_codes == ["hold_protected_cohort_regression"]
                        else None,
                    },
                },
                "latest_avg_mdape": 0.11,
                "latest_avg_interval_coverage": 0.8,
                "promotion_policy": {
                    "shadow": {
                        "min_relative_mdape_improvement": 0.2,
                        "require_same_eval_slice": True,
                    },
                    "protected_cohort": {"max_mdape_regression": 0.0},
                    "integrity": {
                        "freshness_max_lag_minutes": workflows.PROMOTION_FRESHNESS_MAX_LAG_MINUTES
                    },
                },
            },
        )
        monkeypatch.setattr(
            workflows,
            "_latest_route_hotspots",
            lambda *_args, **_kwargs: {"top_improving": [], "top_regressing": []},
        )
        monkeypatch.setattr(
            workflows,
            "_promotion_verdict_for_run",
            lambda *_args, **_kwargs: "hold",
        )

        payload = workflows.report(
            cast(workflows.ClickHouseClient, cast(object, SimpleNamespace())),
            league="Mirage",
            model_dir="artifacts/ml/mirage_v1",
            output=str(tmp_path / f"report-task-10-failure-{reason_codes[0]}.json"),
        )

        assert payload["promotion_verdict"] == "hold"
        assert payload["candidate_vs_incumbent"]["hold_reason_codes"] == reason_codes


def test_v3_backfill_command_dispatches(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli.settings,
        "get_settings",
        lambda: SimpleNamespace(clickhouse_url="http://clickhouse"),
    )
    monkeypatch.setattr(cli.ClickHouseClient, "from_env", lambda _url: object())
    monkeypatch.setattr(
        cli, "detect_runtime_profile", lambda: cast(object, SimpleNamespace())
    )
    monkeypatch.setattr(cli, "persist_runtime_profile", lambda _profile: None)
    monkeypatch.setattr(
        cli.v3_backfill,
        "backfill_range",
        lambda *_args, **_kwargs: {"days_processed": 2, "league": "Mirage"},
    )

    result = cli.main(
        [
            "v3-backfill",
            "--league",
            "Mirage",
            "--start-day",
            "2026-03-20",
            "--end-day",
            "2026-03-21",
        ]
    )

    assert result == 0
    assert "days_processed" in capsys.readouterr().out


def test_v3_predict_one_requires_one_input_source(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli.settings,
        "get_settings",
        lambda: SimpleNamespace(clickhouse_url="http://clickhouse"),
    )
    monkeypatch.setattr(cli.ClickHouseClient, "from_env", lambda _url: object())
    monkeypatch.setattr(
        cli, "detect_runtime_profile", lambda: cast(object, SimpleNamespace())
    )
    monkeypatch.setattr(cli, "persist_runtime_profile", lambda _profile: None)

    result = cli.main(["v3-predict-one", "--league", "Mirage"])

    assert result == 2
    assert "v3-predict-one requires one of" in capsys.readouterr().err
