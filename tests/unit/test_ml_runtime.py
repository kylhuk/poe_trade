import json

from poe_trade.ml import runtime


def test_detect_runtime_profile_cpu_safe_defaults():
    profile = runtime.detect_runtime_profile()

    assert profile.chosen_backend == "cpu"
    assert profile.cpu_cores >= 1
    assert 1 <= profile.default_workers <= 6
    assert profile.memory_budget_gb >= 1.0


def test_persist_runtime_profile_writes_json(tmp_path):
    profile = runtime.detect_runtime_profile()
    target = tmp_path / "runtime-profile.json"

    written = runtime.persist_runtime_profile(profile, path=target)

    assert written == target
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["chosen_backend"] == "cpu"
    assert payload["default_workers"] >= 1
