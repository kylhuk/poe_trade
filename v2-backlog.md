# v2 Backlog (service:psapi only)

## Execution order (phase-first)
- Start with **Phase 1**, complete all acceptance criteria and evidence, then move to **Phase 2**, then **Phase 3**.
- Do not pull v3 work into any phase unless OAuth scope availability changes and triage is re-approved.
- Read this as the ground truth for v2 planning; every backlog item must stay within `service:psapi`, additive ClickHouse output, and the profitability targets (attention-minute, time-to-sell, sell-through, drawdown) outlined in `docs/v2-implementation-plan.md` and `poe1_league_currency_research_v3.md`.
- Refer to the referenced docs for evidence; every story cites the source (formatted as `filename:section`).

### Critical path and parallel lanes
- Critical path tasks are listed in phase execution waves; do not start non-critical tasks before prerequisite evidence is captured.
- Parallel work is allowed only when tasks do not modify the same ingestion worker, ClickHouse table/view, or UI surface.
- Any task that creates/changes a ClickHouse table/view gates downstream readers until evidence is recorded.
- Sequencing updates should modify story dependencies, not scope.

## Phase summary
| Phase | Duration | Outcomes | Gate | Source evidence |
|---|---|---|---|---|
| Phase 1 – Groundwork | Weeks 1–2 | Bronze `service:psapi` ingestion, Poe.ninja snapshots, ClickHouse checkpoints + ops monitor | Bronze tables ingest 90% of cursors for 10+ min + ops view reads checkpoints | `docs/v2-implementation-plan.md`:67-81; `06-db-etl-roadmap.md` (bronze emphasis) |
| Phase 2 – Strategy signals + UX | Weeks 3–4 | Liquidity heatmaps, async listing alerts, NiceGUI alert center stub, overlay prototype | Derived views surface `divines_per_attention_minute`, overlay emits snoozeable alerts, alert center shows severity cards | `docs/v2-implementation-plan.md`:72-76; `docs/v2-gap-matrix.md`:9-22 |
| Phase 3 – Reliability + Ops automation | Weeks 5–6 | Drift guard automation, rate-limit guard, SLO dashboard, fallback workflows | SLO dashboard ≥99%, drift guard self-heals, rate-limit halt on first 429 | `docs/v2-implementation-plan.md`:77-85; `docs/ops-runbook.md`:1-21 |

## Research checkpoints
- **PoE official docs & rate limits** – Gate: parse `X-Rate-Limit-*` headers on every psapi request and demonstrate retry behavior before enabling Bronze writer; Evidence: `curl -sS https://www.pathofexile.com/developer/docs | rg -n "X-Rate-Limit|Retry-After|User-Agent"` and captured integration test log proving throttler behavior (`docs/research/poe-data-sources.md`:18-28).
- **poe.ninja valuation safety** – Gate: define sample freshness TTL (<=3 min) and document Cloudflare pacing (<=1 rps). Evidence: `curl -sS 'https://poe.ninja/api/data/currencyoverview?league=Standard&type=Currency' | python -m json.tool | rg -n "lines|currencyDetails"` plus `SELECT now() - max(sample_time_utc) FROM bronze_poeninja_snapshot;` (`docs/research/poe-data-sources.md`:48-62).
- **PoEDB / Wiki enrichment posture** – Gate: treat PoEDB data as optional enrichment requiring fallback (mark `stale` on 404/429) and respect wiki licensing/attribution; Evidence: `curl -sS https://poedb.tw/us/General_disclaimer | rg -n "disclaimer|terms|copyright"` and `curl -sS https://www.poewiki.net/wiki/Currency_exchange_market | rg -n "CC BY-NC-SA|license"` (`docs/research/poe-data-sources.md`:63-120).
- **NiceGUI/overlay feasibility** – Gate: NiceGUI components must coexist with Streamlit fallback and overlay must support attention-minute focus guardrails. Evidence: `docs/ops-runtime-ui-upgrade-plan.md`:3-99 and `07-exilelens-overlay-plan.md`:1-59 describe migration steps and guardrails.

## Backlog execution model
### Task ID convention
`P<phase>-E<epic>-S<story>-T<task>`
Example: `P9-E9-S9.9-T9`
### Subtask ID convention
`P<phase>-E<epic>-S<story>-T<task>-ST<subtask>`
Example: `P1-E1-S1.1-T1-ST1`
**Epic template:** ID + name + profitability lens + dependencies + reference doc.
**Story template:**
  - Objective: measurable benefit (divines per attention-minute, time-to-sell, sell-through, drawdown, or attention-minute reduction).
  - Dependencies: data sources/scope (e.g., `service:psapi` public stash, ClickHouse views, ops runbook entry).
  - Acceptance Criteria: quantifiable outcome + gating criterion.
  - Evidence Required: precise commands/logs/screenshots with context (e.g., ClickHouse query, overlay animation capture).
- **Task template:** short actionable item (~1 day) tied to story; mention profitability metric impacted.
- **Subtask execution template:** action + evidence hook + stop condition + handoff note.
  - Action: define the specific code/work/change to complete before advancing.
  - Evidence hook: note the query/log/screenshot that proves the action satisfies acceptance.
  - Stop condition: describe the measurable checkpoint for pausing this work.
  - Handoff note: mention the next owner or consumer (e.g., ops, ClickHouse view users) and their dependency.
- **Definition of Done:** schema changes additive; ingestion respects rate limits; story metrics verified by ClickHouse queries (e.g., `SELECT count(*) FROM bronze_public_stash WHERE ingest_ts > now() - INTERVAL 10 MINUTE`) and documented evidences.

## Epic clarity & v2 scope checklist
- [ ] unique epic IDs per phase
- [ ] all phase outcomes mapped to epics
- [ ] each story owned by one epic
- [ ] v2 scope only `service:psapi`
- [ ] no `service:cxapi`/`service:leagues`/`account:*` in v2 stories
- [ ] additive ClickHouse only

## Execution sequencing checklist
- [ ] critical path guidance exists and references phase execution waves
- [ ] each phase has execution waves listing only existing task IDs
- [ ] subtask execution template exists under Backlog execution model
- [ ] wave dependencies are expressed with task IDs (no new scope)
- [ ] quick verification commands are present and current

### Quick verification commands
- `rg -n "Critical path and parallel lanes" v2-backlog.md`
- `rg -n "Phase 1 execution waves" v2-backlog.md`
- `rg -n "Phase 2 execution waves" v2-backlog.md`
- `rg -n "Phase 3 execution waves" v2-backlog.md`
- `rg -n "Subtask execution template" v2-backlog.md`

## Phase 1 backlog – Groundwork
- Scope gate for all stories in this phase: **v2-allowed** (`service:psapi` only).

### Phase 1 epics (ordered)
| Epic ID | Epic name | Order | Stories |
|---|---|---|---|
| P1-E1 | Bronze ingestion foundation | 1 | 1.1, 1.2 |
| P1-E2 | Trade metadata ingestion foundation | 2 | 1.4 |
| P1-E3 | Ops observability baseline | 3 | 1.3 |

#### Phase 1 execution waves
| Wave | Tasks (IDs) | Depends on | Parallel notes |
|---|---|---|---|
| P1-W1 | P1-E1-S1.1-T1, P1-E1-S1.1-T2, P1-E1-S1.2-T1, P1-E2-S1.4-T1 | Bronze worker readiness + checkpoint schema evidence | Parallel work limited to non-overlapping ingestion inputs; do not alter ClickHouse tables/views until evidence captured. |
| P1-W2 | P1-E1-S1.1-T3, P1-E1-S1.2-T2, P1-E1-S1.2-T3, P1-E2-S1.4-T2, P1-E2-S1.4-T3, P1-E3-S1.3-T1 | P1-W1 evidence + cursors/logs verified | Parallel lanes ok only for distinct jobs (e.g., logging vs cache) to avoid shared table contention. |
| P1-W3 | P1-E3-S1.3-T2, P1-E3-S1.3-T3 | P1-W2 ops observability view + runbook evidence | No parallel writes to the same view/UI until dependencies recorded.

### Epic P1-E1: Bronze ingestion foundation (`attention-minute` trust)
#### Story 1.1 – psapi public stash stream checker
- Objective: ensure `bronze_public_stash` captures ≥90% of psapi cursors to keep the attention-minute model fed with up-to-date supply data (`docs/v2-implementation-plan.md`:35-41). 
- Dependencies: `service:psapi` scope, ClickHouse bronze tables, checkpoint schema. 
- Acceptance Criteria: cursor metadata table tracks `cursor_hash`, `last_cursor_id`, `retrieved_at`; rolling progress query shows >=90% success across the latest 10 cursor transitions; retry_count p95 <= 1; table growth stays within planned bounds for 10-second polling. 
- Evidence Required: `SELECT quantileExact(0.95)(retry_count) FROM bronze_ingest_checkpoints WHERE service='psapi' AND retrieved_at > now() - INTERVAL 10 MINUTE;` plus `SELECT name,total_rows,total_bytes FROM system.tables WHERE database='poe_trade' AND name IN ('bronze_public_stash','bronze_ingest_checkpoints');` and `curl -H 'User-Agent: OAuth <client>/<version> (contact: <email>)' 'https://api.pathofexile.com/public-stash-tabs?id=<cursor>'` integration log snippet. 
Tasks:
  - [ ] P1-E1-S1.1-T1: Configure worker to persist `cursor_hash`+`retrieved_at` after each psapi page. Outcome: checkpoint table records every cursor page arrival so time-to-sell latency tracking covers 90% of cursors. Effort: 0.5 day.
    - [ ] P1-E1-S1.1-T1-ST1: Update worker code to write cursor_hash/retrieved_at before acknowledging each page.
    - [ ] P1-E1-S1.1-T1-ST2: Query bronze_ingest_checkpoints for recent cursor entries to prove timestamps persisted.
  - [ ] P1-E1-S1.1-T2: Add ClickHouse `bronze_ingest_checkpoints` insert-once job and table view with last 10 cursors. Outcome: ops view shows recent cursors for drawdown visibility. Effort: 0.5 day.
    - [ ] P1-E1-S1.1-T2-ST1: Schedule the ClickHouse insert job and view refresh covering the latest 10 cursors.
    - [ ] P1-E1-S1.1-T2-ST2: Validate that the ops view query returns the expected 10 cursor rows.
  - [ ] P1-E1-S1.1-T3: Instrument log that emits `divines_per_attention_minute_estimate` when ingestion checkpoint misses >20 seconds. Outcome: attention-minute risk flagging becomes observable in logs. Effort: 0.5 day.
    - [ ] P1-E1-S1.1-T3-ST1: Add a log hook emitting divines_per_attention_minute_estimate when checkpoint lag exceeds 20s.
    - [ ] P1-E1-S1.1-T3-ST2: Document a log snippet showing the risk flag after a simulated checkpoint miss.

#### Story 1.2 – poe.ninja snapshot pipeline
- Objective: add `bronze_poeninja_snapshot` to refresh valuations every minute so sell-through heuristics have reference prices fast (`docs/v2-implementation-plan.md`:35-41). 
- Dependencies: public poe.ninja endpoints, caching TTL (≤3 min), overlay schema to expose `sample_time_utc`. 
- Acceptance Criteria: snapshot job writes `detailsId`, `chaosEquivalent`, `listing_count`, `sparkline`, `sample_time_utc`; freshness query shows p95 recency <= 3 minutes over the last hour; fallback marks rows `stale=true` on source outage. 
- Evidence Required: `SELECT quantileExact(0.95)(dateDiff('second', sample_time_utc, now())) AS p95_age_sec FROM bronze_poeninja_snapshot WHERE sample_time_utc > now() - INTERVAL 1 HOUR;` plus `curl -sS 'https://poe.ninja/api/data/currencyoverview?league=Standard&type=Currency' | python -m json.tool | rg -n "lines|currencyDetails"`. 
Tasks:
  - [ ] P1-E1-S1.2-T1: Build scheduler hitting poe-ninja once per league per minute with backoff on 429/empty responses. Outcome: valuations refresh within 3-minute TTL while respecting Cloudflare pacing. Effort: 0.5 day.
    - [ ] P1-E1-S1.2-T1-ST1: Implement scheduler/backoff settings to hit poe.ninja per league once per minute.
    - [ ] P1-E1-S1.2-T1-ST2: Inspect schedule logs showing requests stay within TTL and backoff limits.
  - [ ] P1-E1-S1.2-T2: Cache JSON payload locally to prevent repeated Cloudflare hits and expose freshness tag. Outcome: stale data detection triggers without extra external requests. Effort: 0.5 day.
    - [ ] P1-E1-S1.2-T2-ST1: Add a local JSON cache layer and tag payloads with freshness metadata.
    - [ ] P1-E1-S1.2-T2-ST2: Run a query showing the stale flag flips without extra poe.ninja calls.
  - [ ] P1-E1-S1.2-T3: Document fallback for 404/429 (flag row as `stale` and emit ops alert referencing PoEDB risk posture). Outcome: ops runbook and alerts cover PoEDB/poe.ninja fallbacks. Effort: 0.5 day.
    - [ ] P1-E1-S1.2-T3-ST1: Write the fallback guidance referencing the PoEDB risk posture and ops alert mapping.
    - [ ] P1-E1-S1.2-T3-ST2: Point to the runbook or alert entry proving the fallback doc exists.

### Epic P1-E2: Trade metadata ingestion foundation (`attention-minute` enrichment)
#### Story 1.4 – bronze trade metadata snapshots
- Objective: mirror `/api/trade/data/*` metadata into `bronze_trade_metadata` so liquidity heatmaps and overlays reference a consistent trade history without extra scope requests (`docs/v2-implementation-plan.md`:44-51).
- Dependencies: `service:psapi` trade metadata endpoints, ClickHouse bronze tables, dedup view.
- Acceptance Criteria: snapshot job writes `trade_id`, `item_id`, `listing_ts`, `delist_ts`, `trade_data_hash`, and freshness query shows p95 <= 5 minutes; dedup ensures only one row per `trade_id` per 24h and worker respects rate-limit guard (<=1 rps per cursor bucket).
- Evidence Required: `SELECT countDistinct(trade_id) FROM bronze_trade_metadata WHERE ts > now() - INTERVAL 1 HOUR;`, `SELECT quantileExact(0.95)(dateDiff('second', listing_ts, now())) FROM bronze_trade_metadata WHERE listing_ts > now() - INTERVAL 1 HOUR;`, and worker log showing `/api/trade/data/<cursor>` with `X-Rate-Limit-*` headers recorded.
Tasks:
  - [ ] P1-E2-S1.4-T1: Extend bronze ingestion worker to fetch `/api/trade/data/<cursor>` and persist metadata rows. Outcome: metadata table captures listing/delist signals keeping attention-minute accuracy intact. Effort: 0.75 day.
    - [ ] P1-E2-S1.4-T1-ST1: Extend the metadata worker to capture /api/trade/data/<cursor> results with rate-limit guard.
    - [ ] P1-E2-S1.4-T1-ST2: Query bronze_trade_metadata to show new rows and recorded rate-limit headers.
  - [ ] P1-E2-S1.4-T2: Build dedup + `trade_data_hash` logic so replays don’t duplicate listings and emit `price_change_flag`. Outcome: only unique trade_id rows exist and price shifts raise alerts for time-to-sell. Effort: 0.5 day.
    - [ ] P1-E2-S1.4-T2-ST1: Build dedup/hash logic and emit the price_change_flag for replays.
    - [ ] P1-E2-S1.4-T2-ST2: Verify the dedup view returns a single row per trade_id and that the price flag triggers.
  - [ ] P1-E2-S1.4-T3: Document fallback when metadata endpoint returns 429/444 and emit ops alert. Outcome: ops alert references fallback guidance reducing manual troubleshooting. Effort: 0.25 day.
    - [ ] P1-E2-S1.4-T3-ST1: Document fallback behavior for 429/444 responses and include the alert mapping.
    - [ ] P1-E2-S1.4-T3-ST2: Record an ops alert referencing the documented fallback steps.

### Epic P1-E3: Ops observability baseline (sell-through confidence)
#### Story 1.3 – checkpoint + drift view
- Objective: surface ops telemetry showing ingestion freshness so operators trust sell-through signals (`docs/v2-gap-matrix.md`:13-22). 
- Dependencies: ClickHouse views on `bronze_ingest_checkpoints`, `proc_logs`, ops dashboard (Streamlit/NiceGUI). 
- Acceptance Criteria: alert center reads `last_ingest_ts`; severity transitions to amber when staleness >20s and red when >60s; runbook section for automated and manual recovery is published.
- Evidence Required: screenshot/log of ops view showing severity card + query `SELECT now() - max(retrieved_at) FROM bronze_ingest_checkpoints;`. 
Tasks:
  - [ ] P1-E3-S1.3-T1: Add `v_ops_ingest_health` view for freshness + attention-meter; includes `divines_per_attention_minute` risk flag when stale. Outcome: view surfaces timely severity states to keep sell-through trust high. Effort: 0.5 day.
    - [ ] P1-E3-S1.3-T1-ST1: Define v_ops_ingest_health with freshness timestamps and the risk flag.
    - [ ] P1-E3-S1.3-T1-ST2: Share query output showing amber/red states reflected in the view.
  - [ ] P1-E3-S1.3-T2: Wire Streamlit hero badge to view and display amber/ red states. Outcome: ops dashboard immediately reflects attention-minute risk when thresholds breach. Effort: 0.5 day.
    - [ ] P1-E3-S1.3-T2-ST1: Connect the Streamlit hero badge to the view so severity badges update live.
    - [ ] P1-E3-S1.3-T2-ST2: Capture an ops dashboard screenshot showing the severity transition.
  - [ ] P1-E3-S1.3-T3: Draft ops runbook note referencing `docs/ops-runbook.md`:8-21 that documents restart steps when threshold breached. Outcome: operators follow documented recovery steps reducing manual drift. Effort: 0.5 day.
    - [ ] P1-E3-S1.3-T3-ST1: Draft a runbook note referencing recovery steps in docs/ops-runbook.md:8-21.
    - [ ] P1-E3-S1.3-T3-ST2: Link evidence that operators follow the documented steps when thresholds breach.

## Phase 2 backlog – Strategy signals + UX
- Scope gate for all stories in this phase: **v2-allowed** (`service:psapi` only).

### Phase 2 epics (ordered)
| Epic ID | Epic name | Order | Stories |
|---|---|---|---|
| P2-E1 | Liquidity heatmaps | 1 | 2.1 |
| P2-E2 | Alert delivery + overlay prototype | 2 | 2.2 |
| P2-E3 | UX migration + overlay polish | 3 | 2.3 |

#### Phase 2 execution waves
| Wave | Tasks (IDs) | Depends on | Parallel notes |
|---|---|---|---|
| P2-W1 | P2-E1-S2.1-T1, P2-E1-S2.1-T2, P2-E1-S2.1-T3 | Phase 1 signal readiness + bronze/liquidity view evidence | Parallel lanes only across distinct aggregates and metadata pipelines. |
| P2-W2 | P2-E2-S2.2-T1, P2-E2-S2.2-T2, P2-E2-S2.2-T3 | P2-W1 liquidity metrics + alert design docs | Parallel work ok when UI wiring is separated from ClickHouse view changes. |
| P2-W3 | P2-E3-S2.3-T1, P2-E3-S2.3-T2, P2-E3-S2.3-T3 | P2-W2 alert view + overlay prototype evidence | Keep UI surfaces distinct (NiceGUI vs Streamlit) for parallel execution.

### Epic P2-E1: Liquidity heatmaps (`time-to-sell` focus)
#### Story 2.1 – silver canonical liquidity metrics
- Objective: derive `v_liquidity(item_id, league)` capturing median sell-through, delist rate, and time-to-sell so strategy signals understand liquidity before flashing alerts (`docs/v2-implementation-plan.md`:52-54; `docs/v2-gap-matrix.md`:17-21). 
- Dependencies: bronze tables, trade metadata, poe.ninja snapshots, ClickHouse additive view layer. 
- Acceptance Criteria: view exposes `sell_through_6hr`, `time_to_sell_median`, `drawdown_band`; values update within 10 min TTL; refresh queries stay within agreed compute budget for hourly operation. 
- Evidence Required: `SELECT * FROM v_liquidity WHERE league='Standard' LIMIT 5;` plus `SELECT query_duration_ms, read_rows FROM system.query_log WHERE query LIKE '%v_liquidity%' AND event_time > now() - INTERVAL 1 HOUR ORDER BY event_time DESC LIMIT 10;` and log showing `time_to_sell` change after a delist event. 
Tasks:
  - [ ] P2-E1-S2.1-T1: Join bronze public stash with canonical item metadata to compute `stack_size`, `listing_ts`, `delist_ts`. Outcome: liquidity view contains canonical timeline fields for every row. Effort: 0.75 day.
    - [ ] P2-E1-S2.1-T1-ST1: Join bronze public stash with item metadata so liquidity rows include timeline fields.
    - [ ] P2-E1-S2.1-T1-ST2: Inspect the view output to confirm stack_size, listing_ts, and delist_ts are present.
  - [ ] P2-E1-S2.1-T2: Build aggregate job computing median `time_to_sell` and sell-through percent over 6 hours. Outcome: drawdown modelling sees updated medians within the hourly TTL. Effort: 0.75 day.
    - [ ] P2-E1-S2.1-T2-ST1: Implement aggregates computing median time_to_sell and 6h sell-through.
    - [ ] P2-E1-S2.1-T2-ST2: Query the aggregates to confirm medians refresh within the hourly TTL.
  - [ ] P2-E1-S2.1-T3: Persist `divines_per_attention_minute_estimate` per row using logistic regression input. Outcome: profitability metric joins liquidity rows for downstream alerts. Effort: 0.5 day.
    - [ ] P2-E1-S2.1-T3-ST1: Persist divines_per_attention_minute_estimate on each liquidity row.
    - [ ] P2-E1-S2.1-T3-ST2: Run a query showing the profitability metric attached to the view rows.

### Epic P2-E2: Alert delivery + overlay prototype
#### Story 2.2 – async listing effectiveness alert
- Objective: alert when async listings yield net sell-through benefit after gold-tax friction, improving sell-through and attention-minute efficiency (`poe1_league_currency_research_v3.md`:231-270). 
- Dependencies: `service:psapi` listing metadata, gold tax model, overlay alert pipeline. 
- Acceptance Criteria: alert center surfaces severity card when `expected_delay_hours <= 6`, `sell_through_6hr >= 0.90`, and `divines_per_attention_minute_estimate >= 0.3`; overlay chime supports snooze and double-confirm guardrail for >5 divine actions.
- Evidence Required: ClickHouse log proving alert triggered (`SELECT * FROM v_async_alerts WHERE fired_at>now()-INTERVAL 1 DAY;`) and, once overlay prototype exists, `SELECT event_name,alert_id,attention_minute_delta,ack_state FROM overlay_event_log WHERE event_name IN ('alert_open','snooze','double_confirm') AND ts > now() - INTERVAL 1 DAY;` plus screenshot. 
Tasks:
  - [ ] P2-E2-S2.2-T1: Create `v_async_alerts` using public stash cadence + estimated gold tax to compute `expected_drawdown`. Outcome: alert view surfaces drawdown risk before overlay chimes. Effort: 1 day.
    - [ ] P2-E2-S2.2-T1-ST1: Create v_async_alerts combining stash cadence and gold-tax derived risk.
    - [ ] P2-E2-S2.2-T1-ST2: Query the view to confirm drawdown and severity fields are surfaced.
  - [ ] P2-E2-S2.2-T2: Hook NiceGUI alert center to this view, display severity and allow snooze/mute. Outcome: operators interact with severity cards and snooze without backlog noise. Effort: 1 day.
    - [ ] P2-E2-S2.2-T2-ST1: Wire the NiceGUI alert center to the view with snooze/mute controls.
    - [ ] P2-E2-S2.2-T2-ST2: Interact with the alert center and log a snooze event for evidence.
  - [ ] P2-E2-S2.2-T3: Extend overlay to pop alert, require double-confirm for >5 divines, and log attention-minute delta into `overlay_event_log`. Outcome: overlay records action metrics and enforces guardrails. Effort: 1 day.
    - [ ] P2-E2-S2.2-T3-ST1: Extend the overlay to require double-confirm for >5 divines and log attention-minute delta.
    - [ ] P2-E2-S2.2-T3-ST2: Capture overlay event log entries showing the delta and double-confirm events.

### Epic P2-E3: UX migration + overlay polish
#### Story 2.3 – NiceGUI alert center stub
- Objective: migrate hero alert cards from Streamlit to NiceGUI while keeping both in sync so operators gain live severity cues without waiting on full replacement (`docs/ops-runtime-ui-upgrade-plan.md`:55-58). 
- Dependencies: shared ClickHouse views, `ops-runtime` Streamlit page, NiceGUI starter. 
- Acceptance Criteria: NiceGUI shows same alerts/card data, toggles severity, and writes ack logs back to ClickHouse; Streamlit continues read-only view. 
- Evidence Required: NiceGUI screenshot and `SELECT count(*) FROM ops_alert_log WHERE source='NiceGUI' AND ts > now() - INTERVAL 1 DAY;`.
Tasks:
  - [ ] P2-E3-S2.3-T1: Build NiceGUI page that reads `v_ops_alerts` and renders hero cards with severity badges + ack buttons. Outcome: NiceGUI surfaces ackable hero cards matching ops alerts. Effort: 0.75 day.
    - [ ] P2-E3-S2.3-T1-ST1: Implement NiceGUI hero cards that read v_ops_alerts with ack buttons.
    - [ ] P2-E3-S2.3-T1-ST2: Screenshot the NiceGUI view showing ack buttons plus severity badges.
  - [ ] P2-E3-S2.3-T2: Keep Streamlit page in read-only mode referencing the same view to avoid regression. Outcome: Streamlit remains synced as a fallback display. Effort: 0.25 day.
    - [ ] P2-E3-S2.3-T2-ST1: Keep the Streamlit page in read-only mode tied to the same view for fallback.
    - [ ] P2-E3-S2.3-T2-ST2: Confirm Streamlit still renders matching cards without ack capability.
  - [ ] P2-E3-S2.3-T3: Add event log entry when ack happens so overlay can mute future chimes. Outcome: overlay uses log to mute redundant alerts. Effort: 0.5 day.
    - [ ] P2-E3-S2.3-T3-ST1: Log ack actions to the event log so the overlay can mute future alerts.
    - [ ] P2-E3-S2.3-T3-ST2: Query the log to show ack entries linked to overlay mute requests.

## Phase 3 backlog – Reliability + Ops automation
- Scope gate for all stories in this phase: **v2-allowed** (`service:psapi` only).

### Phase 3 epics (ordered)
| Epic ID | Epic name | Order | Stories |
|---|---|---|---|
| P3-E1 | Drift guard automation | 1 | 3.1 |
| P3-E2 | Rate-limit safety & SLO dashboard | 2 | 3.2, 3.3 |
| P3-E3 | Fallback validation & runbook drills | 3 | 3.4 |

#### Phase 3 execution waves
| Wave | Tasks (IDs) | Depends on | Parallel notes |
|---|---|---|---|
| P3-W1 | P3-E1-S3.1-T1, P3-E1-S3.1-T2, P3-E2-S3.2-T1, P3-E2-S3.2-T2, P3-E2-S3.3-T1 | Phase 2 ops readiness + rate-limit instrumentation | Parallel only when automations hit different ClickHouse tables or UI tiles. |
| P3-W2 | P3-E2-S3.2-T3, P3-E2-S3.3-T2, P3-E2-S3.3-T3, P3-E1-S3.1-T3 | P3-W1 throttle/status views + dashboard tiles | Keep dashboard and drill docs separate before gating evidence. |
| P3-W3 | P3-E3-S3.4-T1, P3-E3-S3.4-T2, P3-E3-S3.4-T3 | P3-W2 SLO dashboard + alerts stability | Drill automation may run parallel to docs updates when no shared ClickHouse-writing occurs.

### Epic P3-E1: Drift guard automation (`drawdown` protection)
#### Story 3.1 – self-heal drift responder
- Objective: restart bronze worker + mute alerts whenever `last_ingest_ts` lag >20s to prevent drawdowns caused by stale data (`docs/v2-implementation-plan.md`:61-65). 
- Dependencies: checkpoint table, automation job, ops log. 
- Acceptance Criteria: guard triggers restart within 1 round trip, writes `ops_drift_log` with reason, overlays extend drawdown protection flag (e.g., freeze signals) for 5 min, and simulated 429 bursts trigger the same mute/flag workflow deterministically. 
- Evidence Required: `SELECT * FROM ops_drift_log ORDER BY triggered_at DESC LIMIT 3;`, restart command output, and `SELECT ts,signal_class,mute_reason,auto_resume_at FROM ops_signal_mute_log WHERE ts > now() - INTERVAL 1 DAY;` after a simulated 429 test run. 
Tasks:
  - [ ] P3-E1-S3.1-T1: Implement watchdog job that queries `bronze_ingest_checkpoints` and issues restart via existing runner API. Outcome: drift guard restarts worker within one round trip when lag exceeds 20s. Effort: 0.75 day.
    - [ ] P3-E1-S3.1-T1-ST1: Create a watchdog job that checks bronze_ingest_checkpoints and calls the runner API.
    - [ ] P3-E1-S3.1-T1-ST2: Show the log of a restart triggered promptly after a simulated 20s lag.
  - [ ] P3-E1-S3.1-T2: Emit overlay flag `stale_data=true` and mute async alerts until guard clears. Outcome: overlay and alerts remain muted while stale_data flag persists. Effort: 0.5 day.
    - [ ] P3-E1-S3.1-T2-ST1: Emit overlay flag stale_data=true and mute async alerts until the guard clears.
    - [ ] P3-E1-S3.1-T2-ST2: Evidence the overlay flag/mute state while the guard is active.
  - [ ] P3-E1-S3.1-T3: Add and document test script (e.g., `python -m poe_trade.tools.simulate_rate_limit --status 429 --count 3`) to verify guard mute/flag + auto-resume behavior. Outcome: automation recreates guard workflow and documents recovery. Effort: 0.5 day.
    - [ ] P3-E1-S3.1-T3-ST1: Add and document a script simulating 429 bursts for guard validation.
    - [ ] P3-E1-S3.1-T3-ST2: Capture the script output showing the mute/auto-resume sequence.

### Epic P3-E2: Rate-limit safety & SLO dashboard
#### Story 3.2 – rate-limit throttler + alerts
- Objective: parse `X-Rate-Limit-*` headers, back off on 429/Retry-After, and surface throttle events on ops dashboard to protect attention-minute/time-to-sell continuity (`docs/research/poe-data-sources.md`:18-40). 
- Dependencies: HTTP client, ClickHouse `bronze_requests` table, ops view. 
- Acceptance Criteria: throttle counter increments on every 429, ingestion pauses for mandated window, dashboard shows `rate_limit_status` per source. 
- Evidence Required: `SELECT count(*) FROM bronze_requests WHERE status=429 AND league='Standard';` plus HTTP response snippet with headers. 
Tasks:
  - [ ] P3-E2-S3.2-T1: Extend HTTP client to capture `X-Rate-Limit-Client`/`Retry-After` and insert into `bronze_requests`. Outcome: rate-limit metadata is stored for every 429 response. Effort: 0.5 day.
    - [ ] P3-E2-S3.2-T1-ST1: Extend the HTTP client to record rate-limit headers into bronze_requests.
    - [ ] P3-E2-S3.2-T1-ST2: Query bronze_requests to show rows containing the stored header values.
  - [ ] P3-E2-S3.2-T2: Implement backoff state machine that halts psapi polling and resumes after header-derived window. Outcome: client pauses/resumes based on header windows protecting attention-minute continuity. Effort: 0.75 day.
    - [ ] P3-E2-S3.2-T2-ST1: Implement the backoff state machine honoring the Retry-After windows.
    - [ ] P3-E2-S3.2-T2-ST2: Demonstrate pause/resume logs matching those header windows.
  - [ ] P3-E2-S3.2-T3: Surface throttle status on SLO dashboard with `attention_minute_penalty` column referencing paused windows. Outcome: dashboard flags throttle penalties so operators see time-to-sell impact. Effort: 0.5 day.
    - [ ] P3-E2-S3.2-T3-ST1: Add the throttle penalty column to the SLO dashboard source view.
    - [ ] P3-E2-S3.2-T3-ST2: Capture a dashboard screenshot showing the penalty column flagged during throttle.

#### Story 3.3 – SLO dashboard + fallback note
- Objective: display 95% bronze ingestion latency <60s and 99% alert freshness <30s, plus link to runbook steps to reverse drift (improves drawdown and trust). 
- Dependencies: drift guard logs, rate-limit stats, ops runbook doc. 
- Acceptance Criteria: dashboard renders both metrics, highlights red state when violated, and links to `docs/ops-runbook.md`:1-21. 
- Evidence Required: dashboard screenshot + `SELECT quantileExact(0.95)(ingest_latency_seconds) AS p95_ingest, quantileExact(0.99)(alert_latency_seconds) AS p99_alert FROM v_slo_metrics WHERE ts > now() - INTERVAL 1 DAY;`.
Tasks:
  - [ ] P3-E2-S3.3-T1: Create ClickHouse view `v_slo_metrics` aggregating ingestion latency & alert lag. Outcome: dashboard queries pull latency quantiles for SLO validation. Effort: 0.5 day.
    - [ ] P3-E2-S3.3-T1-ST1: Build v_slo_metrics aggregating ingest latency and alert lag quantiles.
    - [ ] P3-E2-S3.3-T1-ST2: Query the view returning p95 ingest and p99 alert values.
  - [ ] P3-E2-S3.3-T2: Build NiceGUI dashboard tile showing metrics + link to runbook instructions. Outcome: tile highlights red states and links to recovery steps. Effort: 0.5 day.
    - [ ] P3-E2-S3.3-T2-ST1: Add the NiceGUI tile showing metrics and the runbook link.
    - [ ] P3-E2-S3.3-T2-ST2: Capture a screenshot of the tile displaying metric values and link.
  - [ ] P3-E2-S3.3-T3: Document manual fallback steps that complement autop-runbook. Outcome: documentation ties manual steps to telemetry metrics. Effort: 0.25 day.
    - [ ] P3-E2-S3.3-T3-ST1: Document the manual fallback steps tied to the telemetry metrics.
    - [ ] P3-E2-S3.3-T3-ST2: Publish the doc referencing those metrics and expected resolution.

### Epic P3-E3: Fallback validation & runbook drills
#### Story 3.4 – fallback drills & runbook validation
- Objective: validate fallback procedures (drift guard mute, rate-limit handoff, overlay mute) through scripted drills and ensure runbook triggers measurable SLO recovery within acceptable windows (`docs/ops-runbook.md`:1-21).
- Dependencies: drift guard logs, rate-limit metrics, ops runbook doc, drill automation script.
- Acceptance Criteria: drill run records time to restore Bronze ingest (<90s), overlay flags reset, and SLO dashboard metric recovers; drill result document references specific view (`v_slo_metrics`) and states `divines_per_attention_minute` penalty <= 0.1 during drill.
- Evidence Required: drill log `fallback_drill_log` row with durations, `SELECT recovery_time FROM fallback_drill_log ORDER BY ts DESC LIMIT 1;`, and annotated runbook update linking to drill outcome.
Tasks:
  - [ ] P3-E3-S3.4-T1: Create drill automation that simulates 429 bursts and documents guard response. Outcome: drill logs capture restart timelines and mute behavior. Effort: 1 day.
    - [ ] P3-E3-S3.4-T1-ST1: Create drill automation capturing restart timelines and mute behavior.
    - [ ] P3-E3-S3.4-T1-ST2: Log a fallback_drill_log row showing the recorded durations.
  - [ ] P3-E3-S3.4-T2: Update runbook with drill checklist, required notifications, and `fallback_drill_log` schema. Outcome: runbook embeds drill checklist plus schema notes for the log. Effort: 0.5 day.
    - [ ] P3-E3-S3.4-T2-ST1: Update the runbook with the drill checklist, notifications, and schema details.
    - [ ] P3-E3-S3.4-T2-ST2: Point to the runbook entry showing the new checklist in docs.
  - [ ] P3-E3-S3.4-T3: Capture drill evidence (dashboard screenshot, log snippet showing recovery_time) and file under docs runbook section. Outcome: evidence package lives under runbook docs for audit. Effort: 0.25 day.
    - [ ] P3-E3-S3.4-T3-ST1: Store drill evidence (dashboard screenshot, recovery log snippet) under docs.
    - [ ] P3-E3-S3.4-T3-ST2: Reference the evidence package in the runbook docs for audit.

## V3 parking lot (scope-gated & deferred)
- **Scope gates:** `service:cxapi` (currency exchange simulator/backtests), `service:leagues` (phase priors), `account:*` (stash snapshots) stay deferred until tokens include those scopes per `artifacts/planning/v2-scope-availability.txt`:7-15 and triage list (`docs/v2-v3-feature-triage.md`:21-50). Keep notes on modeling inputs so v3 can pick up without rework. 
- **Non-scope deferrals:** non-additive ClickHouse rewrites, PoEDB-heavy enrichments outside optional fallback (per `docs/v2-v3-feature-triage.md`:44-51). 

## Risks & assumptions
- Risk: PoEDB/Wiki enrichment endpoints may 404/429; assumption: base ingestion relies on `service:psapi` + poe.ninja only, enrichment toggled off until stable per `docs/research/poe-data-sources.md`:63-120. 
- Assumption: `service:psapi` availability persists; we verify weekly via `ops_scope_audit` entries and log `invalid_scope` responses as per `artifacts/planning/v2-scope-availability.txt`:3-15. 
- Risk: ClickHouse schema must stay additive; we never drop columns or rewrite tables, aligning with `docs/v2-gap-matrix.md`:1-23.
