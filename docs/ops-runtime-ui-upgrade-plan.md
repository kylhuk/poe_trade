## Ops & Runtime UX Upgrade Plan

### Problem statement

- The current `poe_trade/ui/app.py` Streamlit page surfaces raw alert data with limited hierarchy, making critical operator decisions hard to prioritize during peak league events.
- Filtering is manual, context is fragmented, and refresh controls are either missing or opaque; stale data often leads operators to refresh repeatedly, adding cognitive load.
- Health states blend together and lack an escalation path, so a single outage can mask cascading severity and slow remediation.

### Design principles for an operator-focused page

1. **Signal clarity** – present alerts grouped by health hierarchy and allow one-click escalation context while keeping the hands on the keyboard minimal.
1. **Context-rich affordances** – surface league/item metadata, snapshot age, and upstream dependency status alongside alerts so the next action is obvious.
1. **Controlled automation** – auto-refresh, throttling, and pause controls exist but never surprise operators; guardrails prevent resource spikes during large leagues.
1. **Resilience visible** – never leave the operator guessing about system availability; empty, offline, or degraded modes must explain the state and next steps.

### Future information architecture/layout

- **Hero summary band**: league snapshot timestamp, dominant health status (with severity rollup), active auto-refresh state, and quick jump links to critical sections.
- **Health dashboard**: multi-state gauges or cards (green/yellow/red/black) showing component counts, hit rates, and performance metrics per subsystem.
- **Alert feed**: grouped by severity + subsystem with inline remediation hints and expandable detail (clickable leak-down per ClickHouse table or league shard).
- **Operations timeline**: append-only log of actions taken + auto-refresh events to audit operator interventions.
- **Controls rail**: filtering toggles, severity presets, auto-refresh controls, and export buttons for diagnostics.

### Health status model

- **States**: Healthy, Degraded, Critical, Unknown/Offline; each rollup aggregates alerts by severity scores (Critical=4, High=3, Medium=2, Low=1).
- **Severity rollup**: highest accompanying state drives page banner (Critical if any critical alerts exist; otherwise Degraded if medium count exceeds tolerance). Include component-level state so operators can drill into failing services.
- **Operators can pin** a subsystem to override default rollup for quick monitoring.

### Actionable remediation framework

- **Alert type → recommended action → escalation trigger**
  - Stream ingestion lag → verify ClickHouse queue/backfill, restart ingestion worker → escalate at 2 consecutive lag spikes (>30s). Prevents schedule drift.
  - ClickHouse error burst → follow query diagnostics cookbook, throttle OLAP queries → escalate if KV store health dips below 95% success for 5 min.
  - Snapshot freshness gap → rerun scraper, inspect league metadata → escalate if freshness gap exceeds configured SLA (e.g., 5m) for >2 intervals.
  - Ops agent offline → confirm process, collect logs, restart → escalate to devops lead when offline persists >10m.

### Auto-refresh strategy

- **Default interval**: 30s with jitter to avoid burstiness; configurable per operator profile.
- **Controls**: explicit Pause/Resume toggle, slider for interval, and quick buttons for 15s/60s for ad-hoc tuning.
- **Pause state**: timestamped banner + manual Resume; automatically resume after safety window if not manually unpaused and health remains stable.
- **Staleness indicators**: badges on components showing “data age” with coloring (≤30s green, ≤2m amber, >2m red); linked to stale-data remediation suggestions.
- **Load guardrails**: disable auto-refresh when streaming backlog > threshold or when browser tab loses focus; notify operator via subtle toast.

### Empty/error/offline states and resilience

- **Empty state**: show template workflow (import league snapshot, enable alerts) with a CTA to “Load last known data.” Display next scheduled data pull.
- **Error state**: surface brief error summary, retry button, and direct link to diagnostics logs; keep existing alert list but mark as outdated until refresh succeeds.
- **Offline state**: if backend unreachable, highlight last successful snapshot and provide fallback info (cached alerts) plus guidance for reestablishing connection.
- **Resilience behavior**: maintain incremental caching of the last successful health rollup; if new data load fails, keep this cache visible and log the failure in the timeline.

### Implementation roadmap

1. **Phase 1 – Health surfacing and controls**
   - Scope: add hero summary band, health model cards, auto-refresh controls (default interval+pause), severity rollup logic, staleness badges.
   - Dependencies: current Streamlit layout, health metrics exposed via `poe_trade/ui/app.py`, team alignment on severity weights.
   - Out of scope: alert remediation workflow and timeline logging (for Phase 2).
   - Success metrics/acceptance: health banner shows aggregated state, controls wired to refresh logic, staleness badges update after refresh.
1. **Phase 2 – Remediation context and resilience**
   - Scope: actionable remediation framework card, alert feed grouping by severity, offline/error empty states, cached resilience fallback, and initial ops timeline events.
   - Dependencies: alert metadata (type, dependencies), caching layer for fallback data, log access for timeline.
   - Out of scope: detailed escalation automation and metric dashboards (Phase 3).
   - Success metrics: every alert card shows recommended action, offline banner surfaces cached data, timeline records refresh/resume events.
1. **Phase 3 – Automation, verification, and metrics**
   - Scope: escalation triggers wiring, health/performance dashboards, logging integrations (export, timeline persistence), success metrics reporting.
   - Dependencies: monitoring hooks, alert router instrumentation, historical health data for metrics.
   - Out of scope: rewriting backend data ingestion for new alerts (stick to UI changes).
   - Success metrics: alerts can escalate via defined triggers, dashboard charts show historical severity counts, verified logging commands available.

### Non-goals

- Reworking backend data ingestion pipelines or ClickHouse schema.
- Adding unrelated Streamlit pages beyond Ops & Runtime.
- Automating remediation actions without explicit operator consent.

### Success metrics and acceptance per phase

- Phase 1: measurable decrease in stale data refresh warnings, auto-refresh toggle works, severity rollup matches backend status.
- Phase 2: every alert surfaces remediation guidance, offline/error states display cached info with retry options, timeline logs actions for at least 24h.
- Phase 3: escalation triggers send notifications (via existing channels), dashboards expose severity trend lines, operator satisfaction survey target met.

### Verification plan (planning)

- `python -m poe_trade.cli --help` (once CLI exists) to ensure tooling responds to new UI flags.
- `streamlit run poe_trade/ui/app.py` + manual walkthrough verifying hero band, badges, and remediation cards.
- Automated reload test (not yet implemented) to confirm guardrails trigger under artificial lag.

### Risks and mitigations

- Risk: Streamlit refresh/backpressure causes resource spikes when multiple operators tune intervals. *Mitigation*: guardrails disable auto-refresh when backlog high and add toastr warnings.
- Risk: severity rollup conflicts with multiple component states. *Mitigation*: allow pinning per subsystem and document override behavior in hero band.
- Risk: cached health data being stale during outages. *Mitigation*: mark caches explicitly with timestamps and fast retry CTA.

### Actionable follow-up

1. Wire Streamlit controls to actual auto-refresh backend signals and document any new CLI flags.
1. Draft alert remediation content for each upstream service (ClickHouse, ingestion, snapshotting) and link them in UI.
