# Mirage ML Observability And Incumbent Tuning

## TL;DR
> **Summary**: Upgrade the offline `poe-ml` workflow so overnight runs explain themselves, compare each candidate against the promoted incumbent on a fixed Mirage evaluation contract, and stop tuning only when the candidate no longer improves safely.
> **Deliverables**:
> - machine-readable operator telemetry for every training/eval/promotion run
> - persisted candidate-vs-incumbent promotion audit with explicit verdicts and stop reasons
> - bounded tuning loop controls with real no-improvement/budget stopping
> - route-level diagnostics and hotspot reporting for Mirage
> - README/operator guidance for reading quality and tuning outputs
> **Effort**: Large
> **Parallel**: YES - 3 waves
> **Critical Path**: Task 1 -> Task 2 -> Task 4 -> Task 5 -> Task 6 -> Task 7 -> Task 8 -> Task 10

## Context
### Original Request
1) Make sure there is enough log/debug output so the user can see all the stats of the ML model to figure out what to tune.
2) Keep tuning all parameters needed until the ML algorithm trains properly and is able to predict accurately.

### Interview Summary
- User lacks actionable feedback after overnight training and cannot tell whether the loop trained, improved, regressed, or just spun.
- User selected **incumbent-beating** as the definition of `accurate enough` for Mirage v1 promotion/tuning.
- Default applied: tuning controls live in persisted config/status surfaces plus CLI overrides; no UI/dashboard work in this phase.

### Metis Review (gaps addressed)
- Lock one explicit evaluation contract and one explicit promotion contract before more tuning.
- Persist promotion verdicts, stop reasons, and candidate/incumbent deltas in machine-readable storage.
- Cap diagnostics to route/family/support-bucket hotspots; avoid unbounded cardinality.
- Make `--resume` honest: either real resumability or explicit non-support. No implied behavior.
- Use CLI/JSON/ClickHouse observability only; no dashboard expansion in this plan.

## Work Objectives
### Core Objective
Make `poe-ml` overnight tuning explainable and safely self-improving for Mirage by adding incumbent-aware evaluation, route-level diagnostics, bounded tuning controls, and explicit operator feedback.

### Deliverables
- additive ClickHouse storage for promotion audits, tuning rounds, tuning parameter lineage, and route hotspot summaries
- enriched `poe-ml status`, `poe-ml evaluate`, `poe-ml train-loop`, and `poe-ml report` outputs with candidate-vs-incumbent quality deltas and stop reasons
- fixed Mirage evaluation contract reused by manual `evaluate` and automatic `train-loop`
- bounded tuning loop with wall-clock/iteration/no-improvement stopping and persisted reasons
- honest `resume`/warm-start behavior and artifact lineage reporting
- operator docs in `README.md` for reading run quality and deciding whether to keep tuning

### Definition of Done (verifiable conditions with commands)
- `.venv/bin/poe-ml status --league Mirage --run latest` prints or returns `candidate_vs_incumbent`, `stop_reason`, `latest_avg_mdape`, `latest_avg_interval_coverage`, `route_hotspots`, and `active_model_version`.
- `.venv/bin/poe-ml evaluate --league Mirage --dataset-table poe_trade.ml_price_dataset_v1 --model-dir artifacts/ml/mirage_v1 --split rolling` writes evaluation rows and a promotion-comparison row against the promoted incumbent.
- `.venv/bin/poe-ml train-loop --league Mirage --dataset-table poe_trade.ml_price_dataset_v1 --model-dir artifacts/ml/mirage_v1 --max-iterations 2` exits with final status in `{completed,failed_gates,stopped_no_improvement,stopped_budget}` and persists the exact reason.
- `clickhouse-client --query "SELECT verdict FROM poe_trade.ml_promotion_audit_v1 WHERE league='Mirage' ORDER BY recorded_at DESC LIMIT 1"` returns exactly `promote` or `hold`.
- `clickhouse-client --query "SELECT count() FROM poe_trade.ml_route_hotspots_v1 WHERE league='Mirage' AND recorded_at > now() - INTERVAL 1 HOUR"` returns `> 0` after an evaluation run.
- `clickhouse-client --query "SELECT count() FROM poe_trade.ml_train_runs WHERE league='Mirage' AND status IN ('completed','failed_gates','stopped_no_improvement','stopped_budget')"` returns `> 0` after a loop run.

### Must Have
- one frozen Mirage evaluation contract reused by both manual and automatic evaluation
- candidate-vs-incumbent comparison on the same frozen eval slice before any promotion decision
- route-level and family-level hotspot diagnostics with support-bucket context, limited to top-N outputs
- machine-readable stop reasons for every training loop termination
- tuning parameter lineage persisted per run so operators know what changed
- honest warm-start/resume reporting; if resumability is partial, the status surface must say so explicitly
- CLI-first feedback only; no dashboard dependency

### Must NOT Have (guardrails, AI slop patterns, scope boundaries)
- no web UI or dashboard implementation
- no promotion based only on absolute thresholds without incumbent comparison
- no vague status strings like `running fine` or `improving`; every verdict must be backed by numeric deltas
- no unbounded diagnostic dimensions that explode storage cardinality
- no manual-only verification steps in acceptance criteria
- no silent fallback where `resume` claims continuity but restarts cold

## Verification Strategy
> ZERO HUMAN INTERVENTION — all verification is agent-executed.
- Test decision: `tests-after` using `pytest`, CLI command checks, and ClickHouse row assertions
- QA policy: Every task includes agent-executed happy-path and failure-path scenarios
- Evidence: `.sisyphus/evidence/task-{N}-{slug}.{ext}`

## Execution Strategy
### Parallel Execution Waves
> Target: 5-8 tasks per wave. <3 per wave (except final) = under-splitting.
> Extract shared dependencies as Wave-1 tasks for max parallelism.

Wave 1: evaluation contract + additive storage + run telemetry foundation (`deep`, `protocol-compat`)
Wave 2: incumbent comparison + bounded tuning controls + route diagnostics (`deep`, `unspecified-high`)
Wave 3: operator-facing status/report/docs polish + end-to-end verification (`writing`, `quick`, `deep`)

### Dependency Matrix (full, all tasks)
- `1` blocks `2,3,4,5,6,7,8,9,10`
- `2` blocks `4,5,6,7,8,10`
- `3` blocks `5,6,7,8,9,10`
- `4` blocks `5,6,7,8,10`
- `5` blocks `7,8,10`
- `6` blocks `7,8,9,10`
- `7` blocks `8,9,10`
- `8` blocks `9,10`
- `9` blocks `10`

### Agent Dispatch Summary (wave -> task count -> categories)
- Wave 1 -> 3 tasks -> `deep`
- Wave 2 -> 4 tasks -> `deep`, `unspecified-high`
- Wave 3 -> 3 tasks -> `writing`, `quick`, `deep`

## TODOs
> Implementation + Test = ONE task. Never separate.
> EVERY task MUST have: Agent Profile + Parallelization + QA Scenarios.

- [ ] 1. Freeze the Mirage evaluation and promotion contract

  **What to do**: Define one shared Mirage evaluation contract module reused by `evaluate`, `train-loop`, and `status`. It must specify the fixed eval slice/window, primary metric (`mdape`), guardrail coverage floor, incumbent-comparison semantics, top-N hotspot dimensions, and final verdict enums. Replace any ad hoc per-command interpretation with this contract.
  **Must NOT do**: Do not leave promotion or tuning semantics duplicated across CLI/workflow functions. Do not keep `accurate enough` as an informal README concept.

  **Recommended Agent Profile**:
  - Category: `deep` — Reason: this is the canonical contract all downstream logic must follow.
  - Skills: [] — why needed: bounded repo analysis is enough.
  - Omitted: [`frontend-ui-ux`] — why not needed: no UI scope.

  **Parallelization**: Can Parallel: NO | Wave 1 | Blocks: `2,3,4,5,6,7,8,9,10` | Blocked By: none

  **References**:
  - Pattern: `poe_trade/ml/workflows.py:794` — existing `evaluate_stack` entry point to unify under one contract.
  - Pattern: `poe_trade/ml/workflows.py:876` — `train_loop` currently consumes eval output and promotion gate.
  - Pattern: `poe_trade/ml/workflows.py:980` — `status` surface already returns latest eval feedback; extend from contract.
  - Pattern: `poe_trade/ml/workflows.py:1689` — current promotion gate is absolute-threshold-only and must be replaced by incumbent-aware logic.
  - Pattern: `poe_trade/ml/contract.py:17` — existing target contract pattern to mirror for evaluation contract reuse.
  - External: `https://catboost.ai/docs/en/concepts/output-data_training-log` — logging/metric contract inspiration.

  **Acceptance Criteria**:
  - [ ] One shared Python surface defines verdict enums and comparison rules used by `evaluate`, `train-loop`, and `status`.
  - [ ] `poe-ml status --league Mirage --run latest` returns the same verdict vocabulary used by stored promotion audits.
  - [ ] The planned eval window/slice is machine-readable and queryable from run metadata.

  **QA Scenarios**:
  ```
  Scenario: Shared contract drives status and evaluation
    Tool: Bash
    Steps: Run `.venv/bin/poe-ml evaluate --league Mirage --dataset-table poe_trade.ml_price_dataset_v1 --model-dir artifacts/ml/mirage_v1 --split rolling`, then `.venv/bin/poe-ml status --league Mirage --run latest`.
    Expected: Both outputs use the same verdict enum set and expose candidate/incumbent comparison keys.
    Evidence: .sisyphus/evidence/task-1-eval-contract.txt

  Scenario: Unsupported split is rejected consistently
    Tool: Bash
    Steps: Run `.venv/bin/poe-ml evaluate --league Mirage --dataset-table poe_trade.ml_price_dataset_v1 --model-dir artifacts/ml/mirage_v1 --split random`.
    Expected: Command exits non-zero with a clear contract error; no silent fallback to rolling.
    Evidence: .sisyphus/evidence/task-1-eval-contract-error.txt
  ```

  **Commit**: YES | Message: `feat(ml): freeze mirage eval contract` | Files: `poe_trade/ml/*`, `tests/unit/*`

- [ ] 2. Add additive promotion-audit and tuning-lineage storage

  **What to do**: Create additive tables for `ml_promotion_audit_v1` and `ml_tuning_rounds_v1`. Persist candidate artifact id, incumbent artifact id, fit round, warm-start source, tuning parameters, verdict, gate inputs, stop reason, and recorded timestamps. Keep row schemas narrow and machine-readable.
  **Must NOT do**: Do not overload `ml_train_runs` or `ml_eval_runs` with opaque JSON blobs when first-class columns are needed for operator queries.

  **Recommended Agent Profile**:
  - Category: `deep` — Reason: additive schema/data-contract work must stay queryable and stable.
  - Skills: [`protocol-compat`] — why needed: ClickHouse evolution must stay additive and safe.
  - Omitted: [`docs-specialist`] — why not needed: storage design first.

  **Parallelization**: Can Parallel: NO | Wave 1 | Blocks: `4,5,6,7,8,10` | Blocked By: `1`

  **References**:
  - Pattern: `schema/migrations/0032_ml_pricing_v1.sql` — existing ML table naming/storage style.
  - Pattern: `poe_trade/ml/workflows.py:1499` — current `ml_eval_runs` schema helper style.
  - Pattern: `poe_trade/ml/workflows.py:1505` — current `ml_train_runs` schema helper style.
  - Pattern: `poe_trade/ml/workflows.py:1636` — current model registry promotion write path to complement.

  **Acceptance Criteria**:
  - [ ] `poe-migrate --status --dry-run` shows new additive migration(s) cleanly.
  - [ ] `clickhouse-client --query "DESCRIBE TABLE poe_trade.ml_promotion_audit_v1"` includes `candidate_model_version`, `incumbent_model_version`, `verdict`, `avg_mdape_candidate`, `avg_mdape_incumbent`, `coverage_candidate`, `coverage_incumbent`, `stop_reason`, and `recorded_at`.
  - [ ] `clickhouse-client --query "DESCRIBE TABLE poe_trade.ml_tuning_rounds_v1"` includes `fit_round`, `warm_start_from`, `tuning_config_id`, `iteration_budget`, and `recorded_at`.

  **QA Scenarios**:
  ```
  Scenario: Promotion audit rows persist after evaluation
    Tool: Bash
    Steps: Run one `poe-ml evaluate ...` command and query the latest `poe_trade.ml_promotion_audit_v1` row for Mirage.
    Expected: Exactly one row exists with explicit verdict and candidate/incumbent metric columns populated.
    Evidence: .sisyphus/evidence/task-2-promotion-audit.txt

  Scenario: Failed-gate run still records verdict and reason
    Tool: Bash
    Steps: Force a gate hold via a strict config/test fixture, then query `poe_trade.ml_promotion_audit_v1`.
    Expected: Verdict is `hold`, stop reason is non-empty, and no promoted row is written for that attempt.
    Evidence: .sisyphus/evidence/task-2-promotion-hold.txt
  ```

  **Commit**: YES | Message: `feat(ml): add promotion audit storage` | Files: `schema/migrations/*`, `poe_trade/ml/*`, `tests/unit/*`

- [ ] 3. Make runtime/tuning controls explicit and bounded

  **What to do**: Define the v1 tuning-control contract: iteration budget, wall-clock budget, patience/no-improvement budget, warm-start enabled flag, true/false resume support, and metric logging cadence. Expose safe defaults via settings plus CLI overrides for experiments, and persist the effective values per run.
  **Must NOT do**: Do not leave budget/stop policy hidden in loop internals. Do not claim `resume` works if it is still a no-op.

  **Recommended Agent Profile**:
  - Category: `deep` — Reason: shared settings/runtime/CLI contract spans multiple surfaces.
  - Skills: [] — why needed: existing settings pattern is enough.
  - Omitted: [`protocol-compat`] — why not needed: primarily Python/config work.

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: `5,6,7,8,9,10` | Blocked By: `1`

  **References**:
  - Pattern: `poe_trade/ml/runtime.py:36` — current runtime defaults and budget derivation.
  - Pattern: `poe_trade/config/settings.py` — existing env parsing/merge pattern.
  - Pattern: `poe_trade/ml/cli.py:152` — current `train-loop` CLI surface to extend.
  - External: `https://catboost.ai/docs/en/features/snapshots` — snapshot/warm-start guardrails.

  **Acceptance Criteria**:
  - [ ] Effective tuning controls appear in persisted run metadata and `poe-ml status`.
  - [ ] `--resume` either resumes from a documented persisted checkpoint or returns a clear non-support error.
  - [ ] `train-loop` can terminate with `stopped_no_improvement` and `stopped_budget` without ambiguity.

  **QA Scenarios**:
  ```
  Scenario: Loop stops on no-improvement policy
    Tool: Bash
    Steps: Run `poe-ml train-loop --league Mirage ... --max-iterations 5` with a no-improvement patience small enough to trigger.
    Expected: Final status is `stopped_no_improvement`; status output shows the exact patience setting used.
    Evidence: .sisyphus/evidence/task-3-stop-no-improvement.txt

  Scenario: Unsupported resume is honest
    Tool: Bash
    Steps: Run `poe-ml train-loop --league Mirage ... --resume` against a scenario with no valid checkpoint.
    Expected: Either a true resume occurs from persisted state, or the command exits with an explicit resume-not-available reason.
    Evidence: .sisyphus/evidence/task-3-resume-honesty.txt
  ```

  **Commit**: YES | Message: `feat(ml): add bounded tuning controls` | Files: `poe_trade/config/*`, `poe_trade/ml/*`, `tests/unit/*`

- [ ] 4. Replace absolute-threshold-only promotion with candidate-vs-incumbent comparison

  **What to do**: Rework promotion logic so each candidate is evaluated against the currently promoted incumbent on the exact same frozen eval slice. Promotion rules must include: candidate primary metric improvement, coverage non-regression floor, and protected route/family no-regression checks for top-volume Mirage cohorts.
  **Must NOT do**: Do not compare the candidate only to the previous run. Do not promote on aggregate improvement if a protected cohort regresses beyond the allowed threshold.

  **Recommended Agent Profile**:
  - Category: `deep` — Reason: this is the critical behavior change that prevents blind self-promotion.
  - Skills: [] — why needed: conventional evaluation logic.
  - Omitted: [`artistry`] — why not needed: no unconventional pattern needed.

  **Parallelization**: Can Parallel: NO | Wave 2 | Blocks: `5,6,7,8,10` | Blocked By: `1,2`

  **References**:
  - Pattern: `poe_trade/ml/workflows.py:921` — current evaluate-then-promote flow to replace.
  - Pattern: `poe_trade/ml/workflows.py:1022` — current latest-vs-previous trend helper; candidate-vs-incumbent must be distinct.
  - Pattern: `poe_trade/ml/workflows.py:1636` — current model registry write path.
  - External: `https://catboost.ai/docs/en/concepts/output-data_training-log` — metric logging cadence ideas.

  **Acceptance Criteria**:
  - [ ] `poe-ml status --league Mirage --run latest` returns a `candidate_vs_incumbent` object with verdict, metric deltas, and cohort-regression summary.
  - [ ] A run that beats incumbent overall but regresses a protected cohort beyond threshold yields `hold`.
  - [ ] A successful promotion writes both registry rows and a promotion-audit verdict row referencing incumbent + candidate ids.

  **QA Scenarios**:
  ```
  Scenario: Candidate beats incumbent and promotes
    Tool: Bash
    Steps: Run `poe-ml train-loop --league Mirage ... --max-iterations 1` in a fixture/config where candidate metrics safely beat incumbent.
    Expected: Final status is `completed`; latest promotion audit verdict is `promote`; active model version changes.
    Evidence: .sisyphus/evidence/task-4-promote-incumbent.txt

  Scenario: Candidate improves globally but is held for protected cohort regression
    Tool: Bash
    Steps: Run evaluation on a fixture/config producing one regressing protected cohort.
    Expected: Verdict is `hold` with explicit protected-cohort reason in both status and promotion audit.
    Evidence: .sisyphus/evidence/task-4-protected-hold.txt
  ```

  **Commit**: YES | Message: `feat(ml): compare candidates against incumbent` | Files: `poe_trade/ml/*`, `tests/unit/*`

- [ ] 5. Persist route and hotspot diagnostics fit for operator use

  **What to do**: Add a capped `ml_route_hotspots_v1` surface summarizing top improving/regressing route/family/support-bucket cohorts per eval run. Include sample count, candidate metric, incumbent metric, delta, abstain-rate delta, and support bucket. Wire it into `status` and `report` as concise top-N sections.
  **Must NOT do**: Do not emit unbounded base-type-level detail by default. Do not make operators query raw eval tables just to see regressions.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` — Reason: storage + ranking logic is bounded but important.
  - Skills: [`protocol-compat`] — why needed: new additive route hotspot surface.
  - Omitted: [`docs-specialist`] — why not needed: storage and CLI first.

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: `7,8,10` | Blocked By: `3,4`

  **References**:
  - Pattern: `poe_trade/ml/workflows.py:1293` — current report aggregation to extend.
  - Pattern: `poe_trade/ml/workflows.py:1557` — route-eval storage pattern to mirror.
  - Pattern: `poe_trade/ml/workflows.py:1334` — confidence-bucket reporting style.

  **Acceptance Criteria**:
  - [ ] `clickhouse-client --query "SELECT count() FROM poe_trade.ml_route_hotspots_v1 WHERE league='Mirage' ORDER BY recorded_at DESC LIMIT 1"` returns `> 0` after evaluation.
  - [ ] `poe-ml status --league Mirage --run latest` includes top regressions and top improvements with sample counts.
  - [ ] `poe-ml report --league Mirage ...` includes hotspot sections without requiring manual joins.

  **QA Scenarios**:
  ```
  Scenario: Status shows route hotspots
    Tool: Bash
    Steps: Run one eval, then `poe-ml status --league Mirage --run latest`.
    Expected: Output contains top improving and regressing route/family/support-bucket entries with numeric deltas.
    Evidence: .sisyphus/evidence/task-5-route-hotspots-status.txt

  Scenario: Hotspot table is capped and queryable
    Tool: Bash
    Steps: Query `poe_trade.ml_route_hotspots_v1` for the latest eval run.
    Expected: Row count stays within the configured top-N cap and includes required columns.
    Evidence: .sisyphus/evidence/task-5-route-hotspots-table.txt
  ```

  **Commit**: YES | Message: `feat(ml): add route hotspot diagnostics` | Files: `schema/migrations/*`, `poe_trade/ml/*`, `tests/unit/*`

- [ ] 6. Make tuning progress and convergence visible per round

  **What to do**: For each training round, record data range, train/eval row counts, per-route support counts, chosen tuning config id, fit round, warm-start actual usage, elapsed time, and metric deltas. Surface this in `status` and a dedicated training-round query path so users can tell whether a long loop is learning or wasting time.
  **Must NOT do**: Do not reduce overnight visibility to only final status. Do not claim warm-start was used unless the training path actually consumed incumbent/previous artifacts.

  **Recommended Agent Profile**:
  - Category: `deep` — Reason: round-level lineage must stay consistent across status/report/storage.
  - Skills: [] — why needed: no extra specialization required.
  - Omitted: [`frontend-ui-ux`] — why not needed: CLI only.

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: `7,8,10` | Blocked By: `3,4`

  **References**:
  - Pattern: `poe_trade/ml/workflows.py:1588` — current train-run persistence helper.
  - Pattern: `poe_trade/ml/workflows.py:980` — current status output shape to extend.
  - Pattern: `poe_trade/ml/workflows.py:558` — train-route artifact generation with `fit_round`/`warm_start_from`.
  - External: `https://catboost.ai/docs/en/features/snapshots` — snapshot/warm-start semantics.

  **Acceptance Criteria**:
  - [ ] `poe-ml status --league Mirage --run latest` includes current or latest round number, effective tuning config id, elapsed time, and actual warm-start usage.
  - [ ] Round-level telemetry is persisted per run and queryable without reading artifacts directly.
  - [ ] Two sequential one-iteration runs show incremented round lineage and distinguish fresh vs resumed/warm-started behavior.

  **QA Scenarios**:
  ```
  Scenario: Sequential runs show convergence lineage
    Tool: Bash
    Steps: Run two consecutive one-iteration loops and inspect latest round telemetry.
    Expected: Second run references prior artifact/round lineage and exposes updated round metadata.
    Evidence: .sisyphus/evidence/task-6-round-lineage.txt

  Scenario: Cold-start round is labeled honestly
    Tool: Bash
    Steps: Remove or isolate prior artifact context and run one iteration.
    Expected: Status/round telemetry clearly reports cold-start behavior instead of claiming warm-start.
    Evidence: .sisyphus/evidence/task-6-cold-start.txt
  ```

  **Commit**: YES | Message: `feat(ml): expose tuning round telemetry` | Files: `poe_trade/ml/*`, `tests/unit/*`

- [ ] 7. Add bounded tuning loop stop criteria and verdicts

  **What to do**: Implement no-improvement stopping, budget stopping, and exhausted-search stopping for the overnight loop. Use incumbent-aware deltas and fixed Mirage eval windows to determine whether more iterations are justified. Persist exact stop criteria inputs and final stop reason in both storage and CLI output.
  **Must NOT do**: Do not let `train-loop` run indefinitely without explicit budgets. Do not use a stop rule that ignores candidate-vs-incumbent quality.

  **Recommended Agent Profile**:
  - Category: `deep` — Reason: loop-control logic affects all overnight behavior.
  - Skills: [] — why needed: repo logic is sufficient.
  - Omitted: [`ultrabrain`] — why not needed: conventional bounded-loop control.

  **Parallelization**: Can Parallel: NO | Wave 2 | Blocks: `8,10` | Blocked By: `4,5,6`

  **References**:
  - Pattern: `poe_trade/ml/workflows.py:876` — current unbounded/iteration-driven loop.
  - Pattern: `poe_trade/ml/workflows.py:1022` — current delta feedback logic to reuse for no-improvement rules.
  - External: `https://catboost.ai/docs/en/concepts/overfitting-detector` — stop-policy inspiration.

  **Acceptance Criteria**:
  - [ ] `train-loop` can finish with statuses `completed`, `failed_gates`, `stopped_no_improvement`, or `stopped_budget` only.
  - [ ] `status` reports the exact stop reason and the thresholds that caused it.
  - [ ] Loop behavior is deterministic under a fixed config and dataset snapshot.

  **QA Scenarios**:
  ```
  Scenario: Budget stop triggers cleanly
    Tool: Bash
    Steps: Run `poe-ml train-loop --league Mirage ...` with a deliberately small iteration or wall-clock budget.
    Expected: Final status is `stopped_budget`; stop reason includes the exhausted budget dimension.
    Evidence: .sisyphus/evidence/task-7-stopped-budget.txt

  Scenario: Flat-quality loop stops for no improvement
    Tool: Bash
    Steps: Run a loop configuration where candidate-vs-incumbent deltas remain below the minimum improvement threshold for the patience window.
    Expected: Final status is `stopped_no_improvement`; no extra iterations continue past patience.
    Evidence: .sisyphus/evidence/task-7-stopped-no-improvement.txt
  ```

  **Commit**: YES | Message: `feat(ml): bound overnight tuning loops` | Files: `poe_trade/ml/*`, `tests/unit/*`

- [ ] 8. Upgrade operator-facing status and report surfaces

  **What to do**: Expand `poe-ml status` and `poe-ml report` so an operator can answer, from one command: did training run, did the candidate beat the incumbent, which routes improved/regressed, what is the current best model, why did the loop stop, and what tuning config ran. Keep output concise but complete, and preserve JSON-first machine readability.
  **Must NOT do**: Do not require manual SQL just to understand whether overnight training helped. Do not hide critical fields only in artifact files.

  **Recommended Agent Profile**:
  - Category: `writing` — Reason: output contract clarity matters as much as raw logic here.
  - Skills: [] — why needed: CLI/report wording only.
  - Omitted: [`docs-specialist`] — why not needed: CLI/report surface first.

  **Parallelization**: Can Parallel: YES | Wave 3 | Blocks: `9,10` | Blocked By: `5,6,7`

  **References**:
  - Pattern: `poe_trade/ml/cli.py:363` — current status CLI path.
  - Pattern: `poe_trade/ml/workflows.py:980` — current status payload shape.
  - Pattern: `poe_trade/ml/workflows.py:1293` — current report payload shape.
  - Pattern: `README.md:22` — existing quick-start commands to keep aligned.

  **Acceptance Criteria**:
  - [ ] `poe-ml status --league Mirage --run latest` returns a self-sufficient summary with candidate/incumbent verdict, deltas, stop reason, and hotspots.
  - [ ] `poe-ml report --league Mirage ...` contains route metrics, hotspot summaries, outlier cleaning summary, and low-confidence reasons tied to current incumbent/candidate context.
  - [ ] Both surfaces remain parseable JSON without requiring human-oriented scraping.

  **QA Scenarios**:
  ```
  Scenario: Status explains overnight run in one command
    Tool: Bash
    Steps: Run `poe-ml status --league Mirage --run latest` after at least one overnight-style loop.
    Expected: Output answers whether the run trained, whether it improved, why it stopped, and what model is active.
    Evidence: .sisyphus/evidence/task-8-status-explains-run.txt

  Scenario: Report summarizes quality without raw-table digging
    Tool: Bash
    Steps: Run `poe-ml report --league Mirage --model-dir artifacts/ml/mirage_v1 --output .sisyphus/evidence/task-8-report.json`.
    Expected: JSON includes route metrics, hotspot summaries, candidate/incumbent context, and low-confidence reasons.
    Evidence: .sisyphus/evidence/task-8-report.json
  ```

  **Commit**: YES | Message: `feat(ml): improve operator quality readouts` | Files: `poe_trade/ml/*`, `tests/unit/*`

- [ ] 9. Document the tuning workflow and operator readout

  **What to do**: Update `README.md` so the ML quick start includes: how to run one bounded overnight loop, how to read `status`, what `promote` vs `hold` means, and how to interpret route hotspots and stop reasons. Keep it terse and CLI-first.
  **Must NOT do**: Do not document UI/dashboard flows or pretend the system self-improves without operator-visible evidence.

  **Recommended Agent Profile**:
  - Category: `writing` — Reason: this is docs polish anchored to final command outputs.
  - Skills: [`docs-specialist`] — why needed: concise, evidence-backed README diff.
  - Omitted: [`protocol-compat`] — why not needed: docs only.

  **Parallelization**: Can Parallel: YES | Wave 3 | Blocks: `10` | Blocked By: `8`

  **References**:
  - Pattern: `README.md:22` — current ML quick start section.
  - Pattern: `README.md:37` — current CLI bullet list for ML commands.

  **Acceptance Criteria**:
  - [ ] README includes a minimal `train-loop -> status -> report -> predict-one` operator flow.
  - [ ] README defines the meaning of `promote`, `hold`, `stopped_no_improvement`, and `stopped_budget`.
  - [ ] Documented commands exactly match current CLI surface.

  **QA Scenarios**:
  ```
  Scenario: README commands run as documented
    Tool: Bash
    Steps: Execute each documented ML quick-start command in order.
    Expected: Commands exist, run, and produce fields described in README.
    Evidence: .sisyphus/evidence/task-9-readme-commands.txt

  Scenario: README does not overclaim self-improvement
    Tool: Bash
    Steps: Grep README for ML status/verdict/stop-reason wording.
    Expected: Wording matches actual CLI outputs and avoids unsupported claims.
    Evidence: .sisyphus/evidence/task-9-readme-claims.txt
  ```

  **Commit**: YES | Message: `docs(ml): explain overnight tuning workflow` | Files: `README.md`

- [ ] 10. Add automated verification for the observability+tuning contract

  **What to do**: Add focused tests and command checks covering evaluation contract reuse, promotion audit writes, stop reasons, hotspot tables, incumbent-vs-candidate comparison, and status/report payload keys. Keep tests deterministic and avoid needing long overnight wall-clock waits.
  **Must NOT do**: Do not rely on manual log inspection. Do not leave critical verdict or stop-reason behavior untested.

  **Recommended Agent Profile**:
  - Category: `deep` — Reason: this is the final lock on correctness and operator trust.
  - Skills: [] — why needed: repo-native tests suffice.
  - Omitted: [`playwright`] — why not needed: CLI only.

  **Parallelization**: Can Parallel: NO | Wave 3 | Blocks: none | Blocked By: `2,3,4,5,6,7,8,9`

  **References**:
  - Test: `tests/unit/test_ml_cli.py` — current ML CLI testing pattern.
  - Test: `tests/unit/test_ml_runtime.py` — current runtime testing pattern.
  - Pattern: `poe_trade/ml/cli.py:341` — `evaluate` command path to validate.
  - Pattern: `poe_trade/ml/cli.py:352` — `train-loop` command path to validate.
  - Pattern: `poe_trade/ml/cli.py:363` — `status` command path to validate.

  **Acceptance Criteria**:
  - [ ] `pytest` covers status/report/promotion-verdict payload keys and stop reasons.
  - [ ] One scripted verification bundle proves route hotspots and promotion audit rows are written after evaluation.
  - [ ] Zero new diagnostics/errors appear in modified ML files.

  **QA Scenarios**:
  ```
  Scenario: Contract tests pass for observability+tuning surfaces
    Tool: Bash
    Steps: Run `.venv/bin/pytest tests/unit/test_ml_cli.py tests/unit/test_ml_runtime.py tests/unit/test_ml_tuning.py`.
    Expected: All targeted tests pass and cover verdicts, stop reasons, and hotspot/report payloads.
    Evidence: .sisyphus/evidence/task-10-pytest.txt

  Scenario: CLI/status/report contract is verifiable end-to-end
    Tool: Bash
    Steps: Run one bounded loop, then `status`, `evaluate`, `report`, and ClickHouse queries for promotion/hotspot rows.
    Expected: Every required machine-readable surface is populated and consistent.
    Evidence: .sisyphus/evidence/task-10-end-to-end.txt
  ```

  **Commit**: YES | Message: `test(ml): verify tuning observability contract` | Files: `tests/unit/*`, `poe_trade/ml/*`

## Final Verification Wave (4 parallel agents, ALL must APPROVE)
- [ ] F1. Plan Compliance Audit — oracle
- [ ] F2. Code Quality Review — unspecified-high
- [ ] F3. Real Manual QA — unspecified-high
- [ ] F4. Scope Fidelity Check — deep

## Commit Strategy
- Commit 1: shared evaluation contract + additive storage foundations
- Commit 2: candidate-vs-incumbent promotion logic + bounded tuning controls
- Commit 3: status/report/readme/operator guidance
- Commit 4: verification/tests/evidence bundle

## Success Criteria
- Overnight loops no longer leave the operator blind: one `status` command explains run state, improvement, stop reason, and active model.
- Promotions are incumbent-aware and auditable, not absolute-threshold-only.
- Route-level regressions are visible and queryable, not hidden in a flat global MDAPE.
- Tuning loops stop for explicit reasons instead of spinning indefinitely.
- Mirage tuning can be judged on a fixed evaluation contract and repeated safely over multiple nights.
