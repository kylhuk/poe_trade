from pathlib import Path
import tomllib


REPO_ROOT = Path(__file__).resolve().parents[2]


def repo_read(*parts: str) -> str:
    return (REPO_ROOT.joinpath(*parts)).read_text(encoding="utf-8")


def repo_lines(*parts: str) -> list[str]:
    return repo_read(*parts).splitlines()


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
    app_services_line = next(
        line for line in makefile.splitlines() if line.startswith("APP_SERVICES :=")
    )
    assert "docker-compose.dev.yml" in up_block
    assert "up --build" not in up_block
    assert "account_stash_harvester" not in app_services_line
    assert "poeninja_snapshot" in app_services_line


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


def test_runtime_dependency_manifest_matches_pyproject() -> None:
    pyproject = tomllib.loads(repo_read("pyproject.toml"))
    project_dependencies = pyproject["project"]["dependencies"]
    runtime_requirements = [
        line
        for line in repo_lines("requirements-runtime.txt")
        if line and not line.lstrip().startswith("#")
    ]

    assert runtime_requirements == project_dependencies


def test_dockerignore_excludes_dev_noise() -> None:
    dockerignore = repo_read(".dockerignore")
    for entry in [
        ".venv",
        ".sisyphus/",
        "frontend/",
        "docs",
        "tests",
        "*.md",
        "!README.md",
    ]:
        assert entry in dockerignore
    for entry in ["frontend/node_modules", "frontend/dist", "frontend/.vite"]:
        assert entry not in dockerignore


def test_readme_documents_docker_dev_workflow() -> None:
    readme = repo_read("README.md")
    assert "`make up` = fast dev start for the core stack, no `--build`" in readme
    assert "`make build` = explicit image refresh for app services" in readme
    assert "`make rebuild` = refresh images, then restart the stack if needed" in readme
    assert (
        "repo-root edits under the mounted source tree no longer force Docker rebuilds"
        in readme
    )
    assert "poeninja_snapshot" in readme
    assert "account_stash_harvester" in readme
    assert (
        "ClickHouse, schema_migrator, market_harvester, scanner_worker, ml_trainer, poeninja_snapshot, and api"
        in readme
    )
