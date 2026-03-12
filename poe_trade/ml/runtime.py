from __future__ import annotations

import json
import os
import platform
import shutil
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path


DEFAULT_RUNTIME_PROFILE_PATH = (
    Path(os.getenv("POE_ML_RUNTIME_PROFILE_PATH", "")).expanduser()
    if os.getenv("POE_ML_RUNTIME_PROFILE_PATH")
    else Path.home() / ".cache" / "poe_trade" / "poe_ml_runtime_profile.json"
)


@dataclass(frozen=True)
class RuntimeProfile:
    machine: str
    cpu_cores: int
    total_ram_gb: float
    available_ram_gb: float
    gpu_backend_available: bool
    backend_availability: dict[str, bool]
    chosen_backend: str
    default_workers: int
    memory_budget_gb: float
    detected_at: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def detect_runtime_profile(default_memory_budget_gb: float = 4.0) -> RuntimeProfile:
    cpu_cores = max(1, int(os.cpu_count() or 1))
    total_ram_gb, available_ram_gb = _read_ram_metrics()
    backend_availability = {
        "nvidia_smi": shutil.which("nvidia-smi") is not None,
        "rocm": shutil.which("rocminfo") is not None,
    }
    gpu_backend_available = any(backend_availability.values())

    chosen_backend = "cpu"
    default_workers = max(1, min(6, cpu_cores))

    if available_ram_gb > 0:
        dynamic_budget = max(1.0, min(default_memory_budget_gb, available_ram_gb * 0.5))
    else:
        dynamic_budget = max(1.0, default_memory_budget_gb)

    return RuntimeProfile(
        machine=f"{platform.system()}-{platform.machine()}",
        cpu_cores=cpu_cores,
        total_ram_gb=round(total_ram_gb, 2),
        available_ram_gb=round(available_ram_gb, 2),
        gpu_backend_available=gpu_backend_available,
        backend_availability=backend_availability,
        chosen_backend=chosen_backend,
        default_workers=default_workers,
        memory_budget_gb=round(dynamic_budget, 2),
        detected_at=datetime.now(UTC).replace(microsecond=0).isoformat(),
    )


def persist_runtime_profile(
    profile: RuntimeProfile, path: Path = DEFAULT_RUNTIME_PROFILE_PATH
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(json.dumps(profile.to_dict(), sort_keys=True, indent=2) + "\n")
    return path


def _read_ram_metrics() -> tuple[float, float]:
    mem_total_kb = 0
    mem_available_kb = 0
    meminfo_path = Path("/proc/meminfo")
    if meminfo_path.exists():
        for line in meminfo_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("MemTotal:"):
                mem_total_kb = _parse_kb_value(line)
            elif line.startswith("MemAvailable:"):
                mem_available_kb = _parse_kb_value(line)
    if mem_total_kb <= 0:
        total_bytes = _safe_sysconf("SC_PAGE_SIZE") * _safe_sysconf("SC_PHYS_PAGES")
        mem_total_kb = int(total_bytes / 1024) if total_bytes > 0 else 0
    if mem_available_kb <= 0:
        mem_available_kb = mem_total_kb
    return mem_total_kb / (1024 * 1024), mem_available_kb / (1024 * 1024)


def _safe_sysconf(name: str) -> int:
    try:
        return int(os.sysconf(name))
    except (AttributeError, ValueError, OSError):
        return 0


def _parse_kb_value(line: str) -> int:
    parts = line.split()
    if len(parts) < 2:
        return 0
    try:
        return int(parts[1])
    except ValueError:
        return 0
