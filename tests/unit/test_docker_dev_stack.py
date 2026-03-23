from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def repo_read(*parts: str) -> str:
    return (REPO_ROOT.joinpath(*parts)).read_text(encoding="utf-8")


def make_target_block(makefile: str, target: str) -> str:
    lines = makefile.splitlines()
    start = None
    for index, line in enumerate(lines):
        if line == f"{target}:":
            start = index
            break
    if start is None:
        raise AssertionError(f"missing make target: {target}")

    end = len(lines)
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if line and not line.startswith((" ", "\t")) and line.endswith(":"):
            end = index
            break

    return "\n".join(lines[start:end])


def test_makefile_up_uses_dev_overlay_without_build() -> None:
    makefile = repo_read("Makefile")
    up_block = make_target_block(makefile, "up")
    assert "docker-compose.dev.yml" in up_block
    assert "up --build" not in up_block


def test_dev_overlay_mounts_source_and_sets_pythonpath() -> None:
    dev_compose = repo_read("docker-compose.dev.yml")
    assert (
        "- .:/app" in dev_compose or "./:/app" in dev_compose or ".:/app" in dev_compose
    )
    assert "PYTHONPATH=/app" in dev_compose


def test_qa_up_stays_on_base_compose_files() -> None:
    makefile = repo_read("Makefile")
    qa_up_block = make_target_block(makefile, "qa-up")
    qa_compose_line = next(
        line for line in makefile.splitlines() if line.startswith("QA_COMPOSE :=")
    )
    assert "docker-compose.yml" in qa_compose_line
    assert "docker-compose.qa.yml" in qa_compose_line
    assert "docker-compose.dev.yml" not in qa_up_block


def test_dockerfile_uses_separate_runtime_dependency_manifest() -> None:
    dockerfile = repo_read("Dockerfile")
    assert "COPY README.md ./" in dockerfile
    assert "COPY requirements-runtime.txt ./" in dockerfile
    assert "pip install --no-cache-dir -r requirements-runtime.txt" in dockerfile
    assert dockerfile.index("COPY README.md ./") < dockerfile.index(
        "pip install --no-cache-dir --no-deps ."
    )
