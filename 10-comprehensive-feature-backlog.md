# Agent-ready Implementation Backlog

## 1 Objective & Usage Contract for Agents
- **Objective:** deliver a unified stack that highlights trade-ready stash data, routes questing with confidence, and rewrites item filters dynamically while staying within Path of Exile policy bounds.
- **Usage contract:** each task is atomic, evidence-backed, and runnable via explicit commands; agents must respect manual-trigger requirements, avoid automated input simulation, and surface telemetry events for every state transition.
- **Success:** overlay highlights + dim mask match stash payload footprints, quest companion recommends next steps with waypoint awareness, dynamic filters rebuild safely when build telemetry changes.

## 2 Global Constraints
1. **Policy & safety:** obey GGG rules—no automated input simulation, every filter reload requires user-initiated trigger, follow API rate-limit headers with backoff, and surface manual override when telemetry is missing 30+ seconds.
2. **Compatibility:** additive ClickHouse schema changes only; telemetry contracts must version per phase; NeverSink baselines stay intact and remain authoritative when market data ages beyond 15m.
3. **Operational guardrails:** log parser/ingestion health checks must detect schema drift, stash payload placements must be validated per league, and specialized tabs require explicit mapping before rendering.

## 3 Phase Roadmap (P0–P6)
- **P0 – Discovery & Validation:** validate payload positions, specialized tabs, quest reward normalization, log parser reliability, API limit behavior.
- **P1 – Contracts & Telemetry:** define schemas, ingestion, shared caches, and rate-limit-aware pipelines.
- **P2 – Overlay MVP:** full-footprint rendering, dim mask, selection caps, overflow UX.
- **P3 – Quest Companion Routing:** waypoint graph routing, confidence model, level/location tagging, reward recommendations.
- **P4 – Dynamic Filter Engine:** NeverSink deltas, market data freshness, validation/upload flow with rollback, policy compliance.
- **P5 – Integration:** shared telemetry, event linking across overlay, questing, filters; combined UX.
- **P6 – Hardening & Release:** performance tuning, smoke tests, docs, release artifacts.

## Artifact and mock registry
- **A1 – sample stash payload fixture:** `/artifacts/stash/sample_stash_payload.json` capturing `x/y/w/h`, `tab_type`, `tab_id`, and `league` so overlay tasks map grid positions to canvas coordinates.
- **A2 – sample Client.txt fixture:** `/artifacts/logs/Client.txt` with `entered area`, `Quest Completed`, and quest marker lines for parser drift detection and telemetry mapping.
- **A3 – quest_rewards normalized CSV:** `/artifacts/quest_rewards/normalized.csv` listing `quest_id,class,patch,confidence` with canonical IDs used by reward recommendations.
- **A4 – waypoint graph seed JSON:** `/artifacts/waypoints/seed_graph.json` describing waypoint nodes, acts, and adjacency weights for P3 routing probes.
- **A5 – market snapshot fixture:** `/artifacts/market/snapshot.json` mirroring ClickHouse columns plus `X-Rate-Limit-*` headers to test throttle responses and freshness switches.
- **A6 – telemetry contract JSON schemas:** `/artifacts/contracts/selection.json` plus policy metadata (manual trigger flag, rate-limit evidence, validation status) consumed by ingestion and overlay.
- **A7 – renderer harness stub:** `/artifacts/render/harness_stub.py` that consumes `A1`, exposes polygon verification, and logs render timing hooks for P2.
- **A8 – integration event mock stream:** `/artifacts/integration/mock_events.jsonl` with quest pins, overlay signals, and filter reload intents so integration tests replay known sequences without live services.

## Policy compliance audit checklist
- **Manual trigger requirement:** Run `python -m poe_trade.cli contract lint docs/contracts/selection.json` against `A6`; confirm output logs `manualTrigger` field exists and lint reports no missing policy flag.
- **No automated input simulation:** Replay `A8` via `python -m poe_trade.cli integration events --fixture artifacts/integration/mock_events.jsonl --assert trigger_source=manual`; the command must fail if any line omits `manual` and pass when all entries stay manual.
- **Rate-limit handling:** Feed `A5` into `python -m poe_trade.cli ingest --fixture artifacts/market/snapshot.json --rate-limit-check`; verify logs mention `Retry-After` headers and the command refuses extra calls until headers expire.
- **Filter validate-before-apply rule:** Use the renderer harness in `A7` to call `python -m poe_trade.cli filter reload --trigger manual --file artifacts/filters/sample.filter --dry-run`; ensure CLI emits `validation passed` before any apply log entry appears.

## 4 LLM Agent Metadata Contract
Each task entry must include the following metadata fields so agents can execute autonomously:
- `id` – canonical task identifier (e.g., `P0-T01`).
- `phase` – the phase that task belongs to (P0..P6).
- `title` – human-friendly short title.
- `objective` – what success looks like for the task.
- `why_now` – urgency or gating rationale for immediate work.
- `task_type` – one of `discovery`, `implementation`, `integration`, `verification`, `release`.
- `recommended_agent_type` – pick from `docs`, `go-fast`, `go-tests`, `devops`, `proto-engineer`, `runner`, `review`.
- `inputs` – referenced artifacts or data sources (`A1`..`A8` or repo paths).
- `dependencies` – other task IDs or docs needed before starting.
- `outputs` – artifacts/files produced.
- `atomic_subtasks` – single-action steps described verbosely yet unambiguously.
- `verification_commands` – list of `command` + `pass_condition` pairs that prove completion.
- `policy_constraints` – include any relevant items from the compliance checklist.
- `blocking_conditions` – showstoppers that must be recorded and resolved.
- `completion_evidence` – what to submit to prove success.
- `handoff_on_success` – how to transfer ownership or notify teams.
- `handoff_on_failure` – what to document/notify when blocked.
- `definition_of_done` – final sign-off criteria.

## 5 Detailed Atomic Backlog by Phase

### P0 – Discovery & Validation Tasks

#### Stash schema and tab layout verification
Summary: Capture league-specific stash payload slices so overlay layout mappings are accurate.
```yaml
id: P0-T01
phase: P0
title: Stash schema and tab layout verification
objective: Verify stash payload fields (`x/y`, `w/h`, `tab_type`, `tab_id`) and tab layouts so overlay coordinates align with every supported league.
why_now: Overlay rendering cannot proceed until specialty tabs are mapped to grid coordinates.
task_type: discovery
recommended_agent_type: go-fast
inputs:
  - A1
dependencies:
  - 11-poe-domain-research-dossier.md
outputs:
  - docs/discovery/stash-schema.md
atomic_subtasks:
  - Call the public stash API for three leagues and capture payload samples.
  - Inspect each payload for `x`, `y`, `w`, `h`, `tab_type`, and `tab_id` fields.
  - Compare `tab_type` with `num_columns` to flag any non-12x12 layouts.
verification_commands:
  - command: python -m poe_trade.cli stash-schema --sample > /tmp/stash-fields.log && tail -n 20 /tmp/stash-fields.log
    pass_condition: log contains x, y, w, and h entries
policy_constraints:
  - Honor rate-limit headers and back off per Retry-After values.
blocking_conditions:
  - PoE stash API unreachable due to rate limiting or network failures.
completion_evidence: Updated doc with tab matrix and recorded any Retry-After headers encountered.
handoff_on_success: Notify overlay lead with doc link and discovery log entry.
handoff_on_failure: Log rate-limit incident in risk tracker and pause discovery work.
definition_of_done: Stash schema doc updated with tab matrix, acceptance criteria met, and no blocking rate limit issues.
```

#### Quest reward normalization verification
Summary: Deduplicate quest reward rows so recommendations stay consistent across classes.
```yaml
id: P0-T02
phase: P0
title: Quest reward normalization validation
objective: Normalize Cargo `quest_rewards` entries by resolution rules (patch preference, confidence tags) to serve canonical CSVs.
why_now: Reward recommendations downstream need deterministic identifiers before overlay integration.
task_type: discovery
recommended_agent_type: proto-engineer
inputs:
  - Cargo quest_rewards table
dependencies:
  - https://www.poewiki.net/w/api.php
outputs:
  - A3
  - docs/discovery/quest-rewards-normalization.md
atomic_subtasks:
  - Query `quest_rewards` rows and group by `quest_id`, `class`, and `patch` to highlight duplicates.
  - Define normalization rules that prioritize higher patch IDs and attach confidence levels.
  - Generate canonical CSV that matches the normalization spec without schema errors.
verification_commands:
  - command: python -m poe_trade.cli quest-rewards --cargo --validate
    pass_condition: normalized count equals expected deduped rows
policy_constraints:
  - Respect manual-trigger expectations when sampling production tables.
blocking_conditions:
  - Cargo API schema drift (missing columns) preventing normalization.
completion_evidence: Normalization spec plus canonical CSV imported without schema errors.
handoff_on_success: Share canonical CSV and spec with quest-reward consumers and log in discovery tracker.
handoff_on_failure: Document the schema drift in the discovery notes and notify data owner.
definition_of_done: Normalization spec and CSV reviewed, validation tool passes, dependencies noted.
```

#### Log parser drift detection
Summary: Safeguard quest telemetry by testing parser resilience to `Client.txt` variations.
```yaml
id: P0-T03
phase: P0
title: Log parser drift detection
objective: Confirm `Client.txt` parser accuracy, capture schema drift, and map quest telemetry tokens.
why_now: Telemetry mapping needs reliable parser outputs before routing and reward components rely on quest events.
task_type: discovery
recommended_agent_type: go-fast
inputs:
  - A2
dependencies:
  - installer-detected log path guidance
outputs:
  - docs/discovery/log-parser-drift.md
  - test_corpus/log-parse-harness.json
atomic_subtasks:
  - Build a parser harness that reads the `A2` sample log and extracts zone/quest tokens with confidence scoring.
  - Edit the log to simulate drift and ensure the harness surfaces schema warnings.
  - Record quest-related telemetry events mapped to log markers.
verification_commands:
  - command: python -m poe_trade.cli log-parse --file /artifacts/logs/Client.txt --report
    pass_condition: prints parsed events and drift warnings when patterns fail
policy_constraints:
  - Avoid automated input simulation when replaying log samples.
blocking_conditions:
  - Sample log path missing from installer detection.
completion_evidence: Drift report, parser harness checked in, and confidence scores logged.
handoff_on_success: Publish report to telemetry team and reference in risk tracker.
handoff_on_failure: Note missing log artifact and escalate to discovery lead.
definition_of_done: Drift report finalized, harness checked in, parser warnings validated.
```

### P1 – Contracts & Telemetry

#### Telemetry and policy contract definition
Summary: Formalize telemetry schema and embed policy metadata before ingestion pipelines start.
```yaml
id: P1-T01
phase: P1
title: Telemetry and policy contract definition
objective: Document payload names, freshness constraints, and policy metadata for overlay selection, quest routing, and filter deltas.
why_now: Downstream ingestion and overlay components must rely on a stable contract before consuming data.
task_type: implementation
recommended_agent_type: docs
inputs:
  - A6
  - P0-T01
dependencies:
  - research dossier high/medium confidence tables
outputs:
  - docs/contracts/selection.json
  - docs/contracts/selection.md
atomic_subtasks:
  - Draft telemetry schema listing payloads, freshness windows, and consumer expectations.
  - Add policy fields (manualTrigger, rate-limit headers, validation status) to the schema.
  - Publish changelog entry documenting the schema version.
verification_commands:
  - command: python -m poe_trade.cli contract lint docs/contracts/selection.json
    pass_condition: schema validates and logs manualTrigger flag
policy_constraints:
  - Manual trigger flag must be present per compliance checklist.
blocking_conditions:
  - Contract missing policy fields or failing lint rules.
completion_evidence: Versioned contract document with changelog entry and lint pass evidence.
handoff_on_success: Notify ingestion and overlay owners that contract is merged.
handoff_on_failure: Iterate on missing fields and resend lint output to stakeholders.
definition_of_done: Contracts merged, version tagged, dependencies alerted.
```

#### Rate-limit aware ingestion pipeline
Summary: Build ingestion that honors PoE rate limits, freshness, and shared cache TTLs.
```yaml
id: P1-T02
phase: P1
title: Rate-limit aware ingestion pipeline
objective: Provision ingestion stages that respect headers, reject stale payloads, and emit TTL metrics for shared caches.
why_now: Fresh telemetry is essential before overlay or filter engine can rely on live reads.
task_type: implementation
recommended_agent_type: devops
inputs:
  - A5
  - A6
dependencies:
  - Redis/in-process cache availability
outputs:
  - services/ingest/README.md
  - dashboards/ingest-metrics.md
atomic_subtasks:
  - Implement rate-limit handling honoring `X-Rate-Limit-*` and backing off on 429 until `Retry-After` expires.
  - Validate JSON schema for incoming telemetry and reject overlay payloads older than 2s or filter data older than 15m.
  - Emit TTL bucket metrics for overlay (10s), quest (5m), and filter (15m) consumers and write them to shared cache.
verification_commands:
  - command: python -m poe_trade.cli ingest --test
    pass_condition: logs TTL metrics, rejects stale payloads, and shows rate-limit retries
policy_constraints:
  - Rate-limit handling per `A5` compliance checklist.
blocking_conditions:
  - Cache service unavailable.
completion_evidence: Ingestion service running in staging with observed TTL metrics.
handoff_on_success: Share staging logs and cache TTL verification with ops.
handoff_on_failure: Log cache outage and escalate to infrastructure team.
definition_of_done: Ingestion service runs in staging, metrics observed, cache TTLs verified.
```

### P2 – Overlay MVP

#### Full-footprint highlight rendering
Summary: Ensure overlays draw full stash footprints synchronized with stash data.
```yaml
id: P2-T01
phase: P2
title: Full-footprint highlight rendering
objective: Render single-item full-footprint highlight and sync overlay redraws to stash coordinates within 16ms.
why_now: The renderer cannot demonstrate overlays until full footprint polygons match grid data.
task_type: implementation
recommended_agent_type: go-fast
inputs:
  - A1
  - A6
  - A7
dependencies:
  - P0-T01 outputs
outputs:
  - modules/overlay/full-footprint.md
atomic_subtasks:
  - Map `(gridX, gridY)` plus `(width, height)` to canvas polygons covering each stash item.
  - Sync overlay redraws with stash scroll and zoom events, keeping per-render latency below 16ms.
  - Expose debug view showing calculated polygons for reviewer inspection.
verification_commands:
  - command: python -m poe_trade.cli overlay render --item-id 12345 --verify
    pass_condition: command returns success and sample coordinates match stash layout
policy_constraints:
  - Respect manual trigger rule for filter render reruns.
blocking_conditions:
  - Renderer harness stub missing or failing to launch.
completion_evidence: Renderer module committed with debug view and latency logs.
handoff_on_success: Share overlay module with visualization team and note readiness for P2-T02.
handoff_on_failure: Document harness issue and pause until stub is available.
definition_of_done: Renderer module committed, performance target met, overlay sample validated.
```

#### Dim mask layering
Summary: Add configurable dim masks that subtract highlights without artifacts.
```yaml
id: P2-T02
phase: P2
title: Dim mask layering around highlights
objective: Implement translucent dim mask layering around highlighted items with runtime intensity controls.
why_now: Dim masks provide focus before multi-selection UX ships.
task_type: implementation
recommended_agent_type: proto-engineer
inputs:
  - A1
  - A6
  - A7
dependencies:
  - P2-T01 completion
outputs:
  - modules/overlay/dim-mask.md
atomic_subtasks:
  - Paint a translucent dim mask and subtract highlighted polygons while preserving z-order.
  - Add a `setDimIntensity(float)` config, UI slider, and reset control.
  - Verify shader compilation succeeds on supported GPUs.
verification_commands:
  - command: python -m poe_trade.cli overlay dim-mask --intensity 0.65
    pass_condition: logs intensity update and mask shader compiles without errors
policy_constraints:
  - No automated input simulation in shader control flows.
blocking_conditions:
  - Shader compilation failures on target GPUs.
completion_evidence: Dim mask module merged with intensity logs and GPU notes.
handoff_on_success: Share module with UI team and confirm slider integration.
handoff_on_failure: Document GPU issues and notify rendering owner.
definition_of_done: Dim mask controls merged, intensity verified, GPU compatibility noted.
```

#### Multi-selection cap and recovery UX
Summary: Cap selections, show overflow hints, and fade overlay on feed drops.
```yaml
id: P2-T03
phase: P2
title: Multi-selection cap and recovery UX
objective: Enforce a 50-selection cap, log overflow, and recover gracefully when selection feeds stall.
why_now: Selection queue stability is required before quest routing highlights can rely on consistent overlays.
task_type: implementation
recommended_agent_type: go-fast
inputs:
  - A1
  - A8
dependencies:
  - Overlay highlight target ready
outputs:
  - modules/overlay/multi-selection.md
atomic_subtasks:
  - Ingest ExileLens trade-helper lists into the selection queue and validate their format.
  - Append raw selections while preserving arrival order and timestamps.
  - Log overflow and display “showing first 50 trade targets” when cap reached.
  - Detect ExileLens data loss, fade overlay within 500ms, and show a toast explaining the disconnect.
verification_commands:
  - command: python -m poe_trade.cli overlay multi-select --simulate 60
    pass_condition: logs cap hit and toast event appear
policy_constraints:
  - No automated input simulation when replaying `A8` fixtures.
blocking_conditions:
  - Missing toast handler or notification path.
completion_evidence: Queue logic merged with overflow logs and feed recovery test.
handoff_on_success: Notify overlay and QA teams that multi-selection UX is stable.
handoff_on_failure: Document missing toast handler and schedule stub implementation.
definition_of_done: Multi-selection queue and UX states validated end-to-end, feed recovery confirmed.
```

### P3 – Quest Companion Routing

#### Runtime state detection and override
Summary: Surface telemetry confidence and manual override when data gaps exceed 30s.
```yaml
id: P3-T01
phase: P3
title: Runtime state detection and override
objective: Detect location/level telemetry confidence and surface manual override when telemetry lags.
why_now: Quest companion needs reliable state or manual override before routing decisions execute.
task_type: implementation
recommended_agent_type: go-fast
inputs:
  - A6
  - A2
dependencies:
  - Telemetry ingestion pipeline
outputs:
  - components/quest/state-detection.md
atomic_subtasks:
  - Consume location and level telemetry, compare against expected zone level ranges, and compute confidence tags.
  - Surface a manual override UI when telemetry is absent for more than 30 seconds.
  - Log telemetry gaps and user confirmations for traceability.
verification_commands:
  - command: python -m poe_trade.cli quest state-check --timeout 30
    pass_condition: prints confidence level or override prompt
policy_constraints:
  - Manual override UI must respect the manual trigger requirement.
blocking_conditions:
  - Telemetry source is missing or silent.
completion_evidence: State detection component with override UI and log traces.
handoff_on_success: Share telemetry gap log with quest team and document override behavior.
handoff_on_failure: Mark telemetry gap in risk tracker and pause further routing work.
definition_of_done: Override coverage documented, telemetry gap visibility validated.
```

#### Waypoint routing with confidence badges
Summary: Build routing engine that surfaces waypoint metadata and data confidence badges.
```yaml
id: P3-T02
phase: P3
title: Waypoint routing with confidence badges
objective: Construct waypoint routing that minimizes backtrack, attaches confidence badges, and surfaces location metadata.
why_now: Routing decisions must run before quest reward highlights appear.
task_type: implementation
recommended_agent_type: proto-engineer
inputs:
  - A4
dependencies:
  - Medium-confidence routing research
outputs:
  - components/quest/routing-card.md
atomic_subtasks:
  - Run shortest-path probe that minimizes waypoint backtracking.
  - Attach procedural hints with high/med/low confidence badges based on data stability.
  - Display nearest waypoint metadata (name, level, act) on the routing card.
verification_commands:
  - command: python -m poe_trade.cli quest route --from "Lioneye's Watch" --to "Dried Lake"
    pass_condition: returns planned steps with confidence per hop
policy_constraints:
  - Respect manual override gating when telemetry lags.
blocking_conditions:
  - Waypoint graph missing nodes needed for routes.
completion_evidence: Routing engine outputs paths with confidence and metadata card.
handoff_on_success: Share results with quest companion UI and confirm badge rendering.
handoff_on_failure: Flag missing nodes to discovery and pause routing rollout.
definition_of_done: Routing engine reviewed, confidence presentation tested, metadata verified.
```

#### Reward recommendation integration
Summary: Match normalized reward tables to overlay highlight events.
```yaml
id: P3-T03
phase: P3
title: Reward recommendation integration
objective: Recommend quest rewards and loot/gem hints, integrating events with the overlay for pre-highlighting.
why_now: Overlay needs reward signals before integration phase to pre-highlight candidate stash grids.
task_type: implementation
recommended_agent_type: go-fast
inputs:
  - A3
  - A8
  - Overlay telemetry feed
dependencies:
  - P0-T02 normalized table
  - Overlay highlight readiness
outputs:
  - services/rewards/recommendations.md
atomic_subtasks:
  - Match quest rewards to stash tabs/items using canonical IDs.
  - Recommend gems/loot and include reasoning tied to level/location.
  - Emit overlay events that pre-highlight candidate grids and reward items.
verification_commands:
  - command: python -m poe_trade.cli quest reward --quest "The Blood Altar" --class Duelist
    pass_condition: prints recommended loot and overlay signal log
policy_constraints:
  - Emit mock overlay events via `A8` with manual trigger annotations.
blocking_conditions:
  - Normalized reward table missing or incomplete.
completion_evidence: Reward service logs overlay signals and reasoning statements.
handoff_on_success: Share overlay event log and reasoning with integration owner.
handoff_on_failure: Escalate normalized table absence in discovery notes.
definition_of_done: Reward service integrated with overlay, telemetry logged, policy noted.
```

### P4 – Dynamic Filter Engine

#### NeverSink delta recompute
Summary: Recompute filter deltas with telemetry, market weight, and fallback freshness logic.
```yaml
id: P4-T01
phase: P4
title: NeverSink delta recompute
objective: Merge NeverSink baseline with build telemetry and ClickHouse market weights, degrading gracefully if data ages past 15m.
why_now: Filter deltas must react to runtime states before validation/upload flows are wired.
task_type: implementation
recommended_agent_type: go-fast
inputs:
  - A5
  - A6
dependencies:
  - Build telemetry ingestion
outputs:
  - services/filter/delta-compute.md
atomic_subtasks:
  - Detect level/gem/socket changes and trigger delta recompute when telemetry changes.
  - Merge NeverSink baseline with market-weighted deltas, falling back to baseline if data older than 15 minutes.
  - Emit telemetry describing inputs, freshness, and output priority ordering.
verification_commands:
  - command: python -m poe_trade.cli filter delta --build-state sample.json
    pass_condition: outputs diff summary with freshness flag
policy_constraints:
  - Freshness threshold enforcement per `A5` market snapshot guidance.
blocking_conditions:
  - ClickHouse price feed missing; fallback path needed.
completion_evidence: Delta module committed with telemetry logs and fallback confirmation.
handoff_on_success: Notify filter team that delta recompute is ready for validation.
handoff_on_failure: Log missing feed and proceed with baseline fallback while alerting data owners.
definition_of_done: Delta module shipped with telemetry and verified fallback path.
```

#### Filter validation and rollback flow
Summary: Validate filter changes, emit smoke tests, and keep rollback ready.
```yaml
id: P4-T02
phase: P4
title: Filter validation and rollback flow
objective: Provide a validation/upload flow with dry-run, diff, and rollback while enforcing manual triggers.
why_now: Safe filter reloads must exist before marketplace guardrails apply deltas.
task_type: implementation
recommended_agent_type: go-fast
inputs:
  - Filter text fixture
  - A6
  - A5
dependencies:
  - Manual trigger policy
outputs:
  - services/filter/reload-flow.md
atomic_subtasks:
  - Write the filter to a temporary file and run the dry-run parser for syntax, color, and link errors.
  - Compare the diff against the current filter and abort if risky changes hide high-tier rares.
  - Backup the previous filter and document the rollback command while requiring a manual trigger for reload.
verification_commands:
  - command: python -m poe_trade.cli filter reload --trigger manual --file new.filter
    pass_condition: validation passes, smoke tests report, and rollback command registered
policy_constraints:
  - Manual trigger requirement for filter reloads.
blocking_conditions:
  - Validation fails and requires manual review.
completion_evidence: Reload pipeline documentation, smoke-test telemetry, and rollback plan.
handoff_on_success: Publish reload playbook and inform release owner.
handoff_on_failure: Capture validation errors and request manual review.
definition_of_done: Reload pipeline vetted, rollback plan documented, policy trigger enforced.
```

#### Market guardrails and throttling
Summary: Safeguard uploads with freshness warnings and rate-limit retries.
```yaml
id: P4-T03
phase: P4
title: Market guardrails and throttling
objective: Enforce market freshness guardrails, throttle uploads per headers, and surface dashboard metrics.
why_now: Guardrails must run before filters are reloaded in production.
task_type: implementation
recommended_agent_type: devops
inputs:
  - A5
dependencies:
  - ClickHouse snapshot availability
outputs:
  - dashboards/market-freshness.md
atomic_subtasks:
  - Flag price data older than 15 minutes, switch to baseline, and emit telemetry/UI warning banner.
  - Ensure upload flow respects rate limits, retries per `Retry-After`, and logs each 429 as blocking until duration ends.
  - Add smoke-test reporting to rollout dashboard showing market freshness state.
verification_commands:
  - command: python -m poe_trade.cli filter market-check --age 900
    pass_condition: warns about stale data and confirms fallback use
policy_constraints:
  - Rate-limit compliance and manual trigger for uploads.
blocking_conditions:
  - API forces rate limit without headers.
completion_evidence: Guardrails enforced, dashboard updated, and stale data flow documented.
handoff_on_success: Share dashboard updates with release and ops teams.
handoff_on_failure: Escalate missing headers and log issue.
definition_of_done: Guardrails enforced, dashboard updated, stale data flow documented.
```

### P5 – Integration

#### Overlay and quest companion sync
Summary: Connect quest reward pins to overlay highlights and metadata tooltips.
```yaml
id: P5-T01
phase: P5
title: Overlay and quest companion sync
objective: When quest pins reward, signal overlay to highlight candidate grids while showing quest metadata tooltips.
why_now: Integration must precede shared telemetry to show reward context on overlays.
task_type: integration
recommended_agent_type: go-fast
inputs:
  - A6
  - A8
dependencies:
  - P3 reward recommendations
outputs:
  - integration/overlay-quest-sync.md
atomic_subtasks:
  - Signal overlay to highlight candidate stash rectangles when quest pins reward, retaining full footprint highlight.
  - Surface quest level/location metadata on overlay tooltip with collapsible summary.
verification_commands:
  - command: python -m poe_trade.cli integration overlay-quest --pin "The Blood Altar"
    pass_condition: overlay highlights and tooltip shows location data
policy_constraints:
  - Manual trigger requirement for quest pin events in `A8` fixture.
blocking_conditions:
  - Missing quest pin events in the integration stream.
completion_evidence: Integration log capturing highlight events and tooltip metadata.
handoff_on_success: Confirm with overlay and quest teams that sync is functional.
handoff_on_failure: Note missing pin events and expand discovery entry.
definition_of_done: Overlay/quest sync confirmed, metadata tooltip tested, dim mask preserved.
```

#### Quest-driven filter confirmation
Summary: Flow quest stage constraints into filter deltas and explain reload status.
```yaml
id: P5-T02
phase: P5
title: Quest-driven filter confirmation
objective: Convey quest stage constraints into filter delta priorities and expose UI confirmations for reloads.
why_now: Filter engine must understand quest context before rollout metrics can tie to stages.
task_type: integration
recommended_agent_type: go-fast
inputs:
  - A5
  - A6
dependencies:
  - P4 delta pipeline
outputs:
  - integration/quest-filter-confirmation.md
atomic_subtasks:
  - Push quest-stage constraints (e.g., require R-B-B chest) into filter delta priority lists.
  - Display quest UI confirmation when filter reload is queued/completed, referencing reason and telemetry.
verification_commands:
  - command: python -m poe_trade.cli integration quest-filter --stage "Act 1"
    pass_condition: delta requests queue and UI log message appear
policy_constraints:
  - Manual trigger enforcement for filter reload confirmations.
blocking_conditions:
  - Quest telemetry missing stage ID.
completion_evidence: Logs showing quest constraints and confirmation messages.
handoff_on_success: Share confirmation flow with UI owners and telemetry team.
handoff_on_failure: Document missing stage ID and request telemetry fix.
definition_of_done: Quest-filter linkage documented, UI confirmation flow reviewed.
```

#### Shared telemetry for overlay and filters
Summary: Tie overlay selection events to filter boosts and rollout metrics.
```yaml
id: P5-T03
phase: P5
title: Shared telemetry for overlay and filters
objective: Emit shared telemetry linking selection events to filter rebuilds and capture rollout metrics.
why_now: Shared metrics are required before release-level dashboards can signal health.
task_type: integration
recommended_agent_type: devops
inputs:
  - A5
  - A6
dependencies:
  - P1 ingestion
  - P4 delta engine
outputs:
  - dashboards/overlay-filter-telemetry.md
atomic_subtasks:
  - Emit telemetry linking selection IDs to filter boost decisions along with policy flags.
  - Record metrics for selection accuracy, reload rate, and manual overrides per rollout stage.
verification_commands:
  - command: python -m poe_trade.cli telemetry self-check --metrics overlay,filter
    pass_condition: writes metrics and reports no missing fields
policy_constraints:
  - Ensure telemetry records include policy context from `A6`.
blocking_conditions:
  - Telemetry sink unreachable.
completion_evidence: Shared telemetry table populated and dashboard queries validated.
handoff_on_success: Provide dashboard updates to release analytics.
handoff_on_failure: Log sink outage and pause dashboard publishing.
definition_of_done: Shared telemetry pipeline documented, dashboard queries validated.
```

### P6 – Hardening & Release

#### Overlay performance tuning and caching
Summary: Keep overlay render latency under 16ms while caching heuristics/deltas.
```yaml
id: P6-T01
phase: P6
title: Overlay performance tuning and caching
objective: Profile overlay rendering for <16ms latency with 50 highlights and cache quest heuristics/filter deltas.
why_now: Performance targets must be met before smoke tests and release approvals.
task_type: verification
recommended_agent_type: go-tests
inputs:
  - Runtime metrics
  - Cache store
dependencies:
  - P2 overlay
  - P3/P4 heuristics
outputs:
  - reports/overlay-performance.md
atomic_subtasks:
  - Profile overlay render path with 50 highlights to ensure latency stays under 16ms.
  - Cache quest heuristics and filter deltas when inputs remain unchanged.
  - Log cache hit/miss telemetry per component.
verification_commands:
  - command: python -m poe_trade.cli perf overlay --max-highlights 50
    pass_condition: latency log remains below 16ms
policy_constraints:
  - Document telemetry guardrails for caching per AGENTS instructions.
blocking_conditions:
  - Profiler lacks representative sample data.
completion_evidence: Tuning report with before/after stats and cache telemetry.
handoff_on_success: Share report with release owner and QA.
handoff_on_failure: Note missing data and coordinate new profiling runs.
definition_of_done: Tuning report approved and cache strategy verified.
```

#### Smoke tests and rollback playbook
Summary: Automate smoke suite, record rollback steps, and highlight policy guardrails.
```yaml
id: P6-T02
phase: P6
title: Smoke tests and rollback playbook
objective: Run smoke tests for overlay, quest routing, and filter reload + rollback while documenting rollback plans.
why_now: Release gating requires smoke coverage and rollback readiness before publishing.
task_type: verification
recommended_agent_type: runner
inputs:
  - Test harnesses
  - Rollout flag controls
dependencies:
  - P5 integration
outputs:
  - playbooks/smoke-tests.md
atomic_subtasks:
  - Automate smoke tests covering overlay highlight, quest companion card, and filter reload with rollback verification.
  - Document rollback/playback plan with feature flag disable steps for overlay, quest, and filter components.
  - Reference manual trigger policy guardrails for smoke and rollback paths.
verification_commands:
  - command: python -m poe_trade.cli smoke run
    pass_condition: all checks green and rollback stub executed
policy_constraints:
  - Manual trigger requirement for smoke-triggered reloads.
blocking_conditions:
  - Smoke automation flagged by policy; manual intervention required.
completion_evidence: Smoke suite logs and published rollback playbook.
handoff_on_success: Notify release owner that smoke tests and rollback plan are complete.
handoff_on_failure: Record policy flag and queue manual execution.
definition_of_done: Smoke tests green, rollback plan published, policy reminders noted.
```

#### Release documentation and readiness signal
Summary: Publish release notes, update AGENTS, and signal readiness.
```yaml
id: P6-T03
phase: P6
title: Release documentation and readiness signal
objective: Publish release notes covering overlay, questing, filter updates, refresh `AGENTS.md`, and document readiness signals.
why_now: Documentation closes the release loop and keeps operators aware of telemetry policies.
task_type: release
recommended_agent_type: docs
inputs:
  - Change log from previous phases
  - AGENTS instructions
dependencies:
  - Release docs
outputs:
  - docs/release-notes.md
  - AGENTS.md
atomic_subtasks:
  - Draft release notes summarizing overlay, questing, and filter changes plus policy guardrails.
  - Update `AGENTS.md` with new telemetry guardrails, release policy references, and CLI shortcuts.
  - Signal release readiness with changelog entries and PR links.
verification_commands:
  - command: python -m poe_trade.cli docs check --focus release-notes
    pass_condition: references overlay, quest, and filter features without missing fields
policy_constraints:
  - Cite policy guardrails and manual trigger reminders in documentation.
blocking_conditions:
  - Release owner review pending or blocked.
completion_evidence: Published release notes, updated AGENTS, and readiness signal recorded.
handoff_on_success: Notify release owner and stakeholders about documentation publication.
handoff_on_failure: Hold on publication until release owner review completes.
definition_of_done: Documentation published, AGENTS synced, release readiness communicated.
```

## 6 Risk/Unknown Tracker & Discovery Tasks
- **R1:** Rate-limit drift when hitting PoE API; mitigation P1-T02.1 + P4-T03.2 with `Retry-After` handling.
- **R2:** Specialized stash tabs (currency/map) lacking rectangular grid; discovery P0-T01.2 ensures layout map before overlay rendering.
- **R3:** Quest reward table schema drift; managed by P0-T02 normalization + P3-T03 integration.
- **R4:** Log parser schema drift; P0-T03 includes detection tests and confidence scoring.
- **R5:** Market data aging / stale signals; P4-T03 enforces freshness gate + telemetry banner.
- **Discovery tasks:** P0 tasks above create documented signals for unknowns; each adds backlog entry if new constraint emerges.

## 7 Milestone Sequencing
1. **M1 – Foundation Gate (P0+P1):** verify discovery items, finalize contracts, telemetry ingestion, shared cache.
2. **M2 – Overlay Launch (P2):** full-footprint highlight, dim mask, multi-selection UX validated.
3. **M3 – Quest Companion (P3):** routing + reward cards online with confidence badges.
4. **M4 – Filter Engine Activation (P4):** NeverSink deltas, validation/upload safety, market guardrails in place.
5. **M5 – Integrated Stack (P5):** shared telemetry/events linking overlay, questing, filters with confirmable rollout metrics.
6. **M6 – Release Harden (P6):** performance targets met, smoke tests pass, documentation/release artifacts complete.

Ensure each milestone is gated by its phase exit criteria (e.g., telemetry passes, contracts approved, smoke tests clean) before progressing. Include MVP definitions per milestone and mention any remaining discovery items when gating.
