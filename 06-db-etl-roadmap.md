# Database & ETL Roadmap

## Dependency map
- **MarketHarvester** (public stash + currency exchange) -> bronze raw tables in ClickHouse -> ETL service -> silver canonical schema -> ChaosScale and Ledger API/gold views.
- **StashScribe** (account stash snapshots + pricing) -> bronze stash snapshots -> ETL merges + `chaos` normalization -> silver price + valuation tables -> Ledger API exposures.
- **ChaosScale** (currency normalization, liquidity stats) -> reads silver exchange history + public stash anonymized prices -> writes liquidity metrics for Ledger API and downstream analytics (FlipFinder, ForgeOracle).
- **ETL** orchestrates transforms between bronze, silver, and gold layers, materializes truncation-safe aggregates, and drives `Ledger API` + auditing dashboards.
- **Ledger API** depends on silver/gold tables (ClickHouse) and feeds **Ledger UI**, **ExileLens**, and **BuildAtlas** clients; also exposes operational metadata for backfills.
- **Optional BuildAtlas** uses silver pricing + gold craft plans to rank builds; relies on stable ETL outputs.

### Source anchors for dependency map
- `00-ecosystem-overview.md` (component roles, API clients, ClickHouse as source of truth)
- `01-architecture.md` (service graph, bronze/silver/gold flow, table responsibilities)
- `02-implementation-tasklist.md` (epic ordering for collectors, ETL, pricing, API)
- `05-buildatlas-pob-intelligence.md` (BuildAtlas dependency on Ledger pricing outputs)

## Architecture and data model decisions
- **Bronze layer:** retains raw MarketHarvester + StashScribe events, partitioned by league/realm and ingestion date with short TTL (few days) so expensive storage is scoped; data stays in ClickHouse MergeTree engines tuned for append-only writes.
- **Silver layer:** owns canonical stashes, priced items, and exchange ticks; tables are partitioned by league and bucketed for joins, TTLs follow the audit retention policy in `01-architecture`, and idempotency relies on PoE cursors + `stash_id` dedupe logic before upgrading rows.
- **Gold layer:** exposes aggregations (currency stats, valuations, liquidity trends) and is rebuilt from deterministic ETL outputs; partitions align with API query granularity, TTLs mirror SLA-backed caches, and downstream services assume upstream transforms drop duplicates via `next_change_id` checkpoints.
- **Table families:** key families include `bronze_raw_stashes`, `bronze_exchange_events`, `silver_canonical_stashes`, `silver_currency_norm`, and `gold_currency_snapshot`/`gold_stash_summary`. Each family follows strict schema versions and exposes necessary metadata for ETL checkpoints and Ledger API contracts.
- **Idempotency posture:** ingestion jobs treat repeated reads from the same cursor as no-ops, deduplicate based on `(league, stash_id, change_id)`, and checkpoint commits before acknowledging success so ETL can resume without reprocessing or losing rows.

## PoE ingestion contract & rules
1. **Dynamic rate limits:** parse `X-Rate-Limit-Policy`, `X-Rate-Limit-Rules`, `X-Rate-Limit-<rule>`, `X-Rate-Limit-<rule>-State`, and `Retry-After` on every response; feed values into the global throttler and backoff logic.
2. **429 handling:** treat every HTTP 429 as a transient limit violation; stop issuing new requests, wait the longer of `Retry-After` or a jittered exponential backoff tied to the active rule window, and never resume until restriction state indicates requests are allowed.
3. **User-Agent:** every outbound PoE API request must carry the mandatory identifiable format (project name + environment + contact email) so the team can be contacted if the pattern is rejected.
4. **Checkpointing:** always persist `next_change_id` after consuming `/public-stash-tabs` or `/currency-exchange`; use the persisted cursor to resume instead of resetting to epoch if the process restarts or hits a failure.
5. **Empty stash detection:** `/public-stash-tabs` may return empty `stashes` when at the end of stream; continue polling the same `next_change_id` until stashes appear before advancing the cursor.
6. **Currency exchange cadence:** treat `/currency-exchange` as hourly historical data; `next_change_id` equals the unix hour and should be advanced sequentially, reconciling hourly gaps via ClickHouse ingestion timestamps.
7. **Known upstream delay:** public stash stream data is delayed by about 5 minutes; freshness SLOs must account for this and avoid false alarms.
8. **Invalid request budget:** avoid repeated invalid 4xx requests; classify permanent input/auth errors and stop retries early to prevent additional restrictions.

### Source anchors for PoE rules
- `https://www.pathofexile.com/developer/docs`
- `https://api.pathofexile.com/public-stash-tabs`
- `https://api.pathofexile.com/currency-exchange`

## Ingestion flow
- Request: MarketHarvester/StashScribe compose PoE calls (stashes/exchange) with compliant User-Agent and cursor inputs.
- Throttle: global throttler consumes `X-Rate-Limit-*` headers, enforces per-endpoint pacing, and feeds jittered backoff into runners.
- Ingest: successful responses land in bronze tables, applying league-aware partitioning and `stash_id` dedup before writes.
- Checkpoint: ingest jobs persist `next_change_id`/`Retry-After` after each batch and replay stored cursors on restart.
- ETL: silver canonical tables and gold aggregates materialize from bronze storage using deterministic transforms + checkpointed input to ensure resumability.
- API exposure: Ledger API and analytics services read silver/gold outputs for compliance with freshness/alerting contracts.

## Phased roadmap (DB + API ingestion + ETL first)
1. **Phase 0 – Baseline ClickHouse & ingestion plumbing (weeks 1–2)**
   - Deploy ClickHouse schema for bronze tables, indexes, and engine settings aligned with existing architecture docs.
   - Wire MarketHarvester + StashScribe so both push raw events into bronze tables (batch/fan-out adapters for PoE public stash + account APIs + exchange history).
   - Ensure global throttler service is in place to honor rate-limit headers, emit metrics, and surface logs for hitting 429s.
2. **Phase 1 – ETL stabilization and silver canonization (weeks 2–4)**
   - Build ETL pipelines that transform bronze material into silver canonical tables (stashes, priced items, exchange ticks, normalization factors) while enforcing schema contracts defined in `01-architecture`.
   - Connect checkpointed ingestion to ETL jobs; add resumability so failing runs restart from saved `next_change_id`.
   - Introduce gold output gating for Ledger API consumables (currency summary, price snapshots, stash valuations).
3. **Phase 2 – Operationalization & analytics prep (weeks 4–6)**
     - Harden ingestion for multi-league processing, add audit trails for missing hourly currency data, and publish runbooks for global throttler + checkpoint state.
     - Extend ETL to refresh gold-level aggregates (volatility, ROI windows, etc.) and feed analytics services (FlipFinder, ForgeOracle).
     - Document SLOs around freshness (public stash <=10m lag including upstream delay, currency data <=65m lag) and establish alerting on checkpoint regressions.
 4. **Phase 3 – Internal dashboard implementation (weeks 6–8)**
     - Implement the operational dashboard after core DB/ETL work so observability builds on stable data outputs; keep analytics-first priorities intact.
     - Reuse approved internal layouts and visuals, favor vanilla JavaScript with light Tailwind CSS, and wire data surfaces to the gold tables + SLO metrics.
     - Validate dashboard telemetry by surfacing ingest rate, checkpoint health, and route-specific latency snapshots expected by the Ops team.

## Milestone tasklists with acceptance criteria
1. **Milestone A – Raw ingestion established**
   - Scope / owner: ingestion team owns schema + connector rollout; ETL team prepares checkpoints for downstream use.
   - Tasks: define bronze schema, deploy MarketHarvester + StashScribe connectors, implement rate-limit parsing + throttler, store `next_change_id` and `Retry-After` logs.
   - Acceptance: bronze tables show >1 day of public stash + exchange rows; throttler logs include PoE headers; no ingestion runs exceed 1 req/sec average.
   - Evidence: ClickHouse query results (bronze tables) + throttler metric dashboard screenshots showing `rate_limit_remaining` tracked.
   - Verification steps: run ClickHouse queries to confirm bronze rows and inspect throttler metrics dashboard for header capture and sustained sub-1 req/sec pacing.
2. **Milestone B – ETL silver tables live**
   - Scope / owner: ETL squad owns silver pipeline hygiene and Ledger API prep work.
   - Tasks: write ETL transforms for normalized stashes/prices, stitch exchange history to chaos values, expose silver views for Ledger API.
   - Acceptance: silver tables contain joined data (item value + currency normalization) for at least three leagues; ETL job reruns resume from exact `next_change_id` on failure.
   - Evidence: ETL run logs showing successful checkpoint restore + query results demonstrating normalized pricing snapshots per league.
   - Verification steps: re-run ETL with a simulated failure, confirm logs show checkpoint resume, and query silver tables per league to ensure normalized pricing persisted.
3. **Milestone C – Gold aggregates + API gating**
   - Scope / owner: analytics + API teams align on gating and alerting responsibilities.
   - Tasks: generate gold aggregates (currency stats, stash diffs), confirm Ledger API can answer price queries using silver/gold, publish SLO targets.
   - Acceptance: Ledger API responses match gold table data; monitoring alerts trigger on checkpoint drift >2 minutes.
   - Evidence: API response sample (with silver/gold reference), alert config snippet, SLO definition in docs.
   - Verification steps: compare API query outputs to gold aggregates via scripted spot checks and trigger the checkpoint drift alert rule in a test harness to confirm firing.
  4. **Milestone D – Internal dashboard surfaces**
   - Scope / owner: observability squad owns dashboard build, styling, and ops handoff.
   - Tasks: assemble approved layout components, wire vanilla JS + light Tailwind to gold tables/SLO metrics, document data bindings and refresh cadence.
   - Acceptance: dashboard reuses existing internal layout, shows ingest rate/checkpoint health, and serves measurable evidence of dashboard telemetry for the Ops team.
   - Evidence: deployed dashboard link (internal only) + screenshot showing required panels + README entry detailing approved visuals and stack choices.
   - Verification steps: load the internal dashboard in the approved layout, verify ingest/checkpoint panels update with live gold metrics, and confirm README notes stack choices.

## Operational plan (long-running backfill/sync, <1 req/sec average)
1. **Global throttler:** central service reads PoE `X-Rate-Limit-*` headers and `Retry-After`, updates a token bucket per endpoint, and exposes gRPC/api for ingestion jobs to request the next permitted timestamp.
2. **Checkpointing & resumability:** ingest loops persist `next_change_id` every successful batch; failures trigger restart logic that first replays stored cursor before issuing fresh requests, ensuring idempotent continues.
3. **Backfill strategy:** long-running catch-up jobs run with deliberate pacing (~0.8 req/sec) using the throttler; include progress markers per league/hour and log rate-limit headroom; if quota exhausts, the job sleeps using the max header value plus jitter.
4. **Evidence & telemetry:** log HTTP headers, checkpoint transitions, and ingested row counts; store these metrics in ClickHouse/system logs for dashboards proving compliance with SLOs (<1 req/sec, <=10m public-stash lag). Provide `poe_ingest_status` table summarizing last cursor, request rate, and error counts.
5. **SLOs & alerts:** freshness SLOs (public stash within 10m, currency data within 65m, ETL job success rate >99%) tied to alerting rules for stuck cursors and repeated 429/4xx violations.

## Critical path - ASAP DB + PoE sync (agent execution)
- **P0 (first 24h):**
  1. Task CP-01: Provision ClickHouse bronze schema + ingestion tables (depends on none)
  2. Task CP-02: Launch PoE ingestion runners (MarketHarvester/StashScribe) with mandatory User-Agent + cursor checkpointing (depends on CP-01)
  3. Task CP-03: Deploy global throttler + rate-limit observability (depends on CP-02)
- **P1 (24-72h):**
  1. Task CP-04: Wire ETL jobs to consume bronze -> silver canonical tables with checkpoint resumes (depends on CP-02)
  2. Task CP-05: Materialize silver views for currency/valuation and expose metrics for Ops (depends on CP-04)
  3. Task CP-06: Harden ingestion for league sharding + checkpoint audit logs (depends on CP-02)
- **P2 (week 1):**
  1. Task CP-07: Build gold aggregates + Ledger API gating tests (depends on CP-05)
  2. Task CP-08: Document SLOs + alerting for checkpoint drift and 429 storms (depends on CP-03 & CP-06)
  3. Task CP-09: Prep Ops handoff for dashboard-ready metrics so internal UI can wait until core sync is stable (depends on CP-07)
- **Dependency graph (ID: dependencies)**
  - CP-01: []
  - CP-02: [CP-01]
  - CP-03: [CP-02]
  - CP-04: [CP-02]
  - CP-05: [CP-04]
  - CP-06: [CP-02]
  - CP-07: [CP-05]
  - CP-08: [CP-03, CP-06]
  - CP-09: [CP-07]
- **Start syncing ASAP checklist**
  - confirm ClickHouse bronze tables exist with correct TTL/partitioning
  - verify PoE User-Agent & cursor persistence config before first request
  - launch throttler and confirm it captures `X-Rate-Limit-*` headers
  - ensure PoE runners persist `next_change_id` per league and log `Retry-After`
  - monitor ingestion logs for `429` spikes and hold new calls until backoff clears

## Agent task cards (ready to assign)
- Task ID / Title: ATC-01 / Provision bronze ClickHouse schema
  - Suggested agent type: go-fast
  - Scope: define bronze tables, engines, TTLs, and partitions for MarketHarvester/StashScribe
  - Commands to run: `clickhouse-client --multiquery < schema/bronze.sql`
  - Acceptance criteria: bronze tables writable with league/date partitions and TTLs; schema version pinned
  - Evidence required: schema DDL diff + sample insert showing successful write
  - Dependencies: none
- Task ID / Title: ATC-02 / Launch PoE runners with compliant User-Agent
  - Suggested agent type: runner
  - Scope: configure MarketHarvester + StashScribe to send `Project/Env <email>` UA and checkpoint `next_change_id`
  - Commands to run: `./bin/market-harvester --user-agent "PoETrade/sync staging <ops@example.com>"` (stashes) and similar for exchange
  - Acceptance criteria: first run logs UA header, saves cursor per league/hour, and writes rows to bronze
  - Evidence required: ingestion logs + ClickHouse row counts by league
  - Dependencies: ATC-01
- Task ID / Title: ATC-03 / Deploy global throttler + observability
  - Suggested agent type: devops
  - Scope: deploy service reading PoE `X-Rate-Limit-*`, expose API for ingestion gating, and ship metrics
  - Commands to run: `docker-compose up throttler` or k8s helm upgrade
  - Acceptance criteria: throttler API returns next-permitted timestamp and metrics emit `rate_limit_remaining`
  - Evidence required: API curl response + monitoring screenshot showing header capture
  - Dependencies: ATC-02
- Task ID / Title: ATC-04 / Wire ETL bronze->silver checkpointed pipeline
  - Suggested agent type: go-fast
  - Scope: implement deterministic transforms, dedupe logic, and checkpoint resume hooks for silver stashes/prices
  - Commands to run: `./etl run --config etl/silver.json --cursor-path /var/lib/poe/cursors`
  - Acceptance criteria: ETL rerun after failure resumes from stored `next_change_id`; silver tables contain normalized rows
  - Evidence required: ETL logs showing checkpoint restore + silver table query output
  - Dependencies: ATC-02
- Task ID / Title: ATC-05 / Materialize silver views + metrics for Ops
  - Suggested agent type: go-fast
  - Scope: expose silver views (normalize price/exchange) and surface metrics (ingest rate, checkpoint age)
  - Commands to run: `clickhouse-client --query "SELECT ..."` for validation
  - Acceptance criteria: silver view refresh succeeds, metrics table/tracking updated real-time
  - Evidence required: view definition, validation query output, metrics dashboard snippet
  - Dependencies: ATC-04
- Task ID / Title: ATC-06 / Harden ingestion sharding & checkpoint logging
  - Suggested agent type: devops
  - Scope: add multi-league queueing, log checkpoint transitions, and backfill awareness for `next_change_id`
  - Commands to run: `./ingest supervise --leagues=all --checkpoint-log` and verify logs
  - Acceptance criteria: each league reports cursor progress + throttle metrics, logs include Retry-After values
  - Evidence required: league progress log snippets + alerting config for stalls
  - Dependencies: ATC-02
- Task ID / Title: ATC-07 / Generate gold aggregates + Ledger API gating
  - Suggested agent type: go-fast
  - Scope: build gold-level currency snapshots and ensure Ledger API reads them with gating
  - Commands to run: `./gold-aggregator run` + `./ledger-api validate`
  - Acceptance criteria: Ledger API responses match gold table data and gating config rejects stale rows
  - Evidence required: sample API response + query diff
  - Dependencies: ATC-05
- Task ID / Title: ATC-08 / Publish SLO + alert documentation for sync health
  - Suggested agent type: docs
  - Scope: document SLOs, checkpoint drift alerts, rate-limit handling, and ops transitions for 429 storms
  - Commands to run: none (doc updates)
  - Acceptance criteria: README section covers SLO numbers, checkpoint benchmarks, and alert playbooks
  - Evidence required: doc link + snippet showing new SLOs
  - Dependencies: ATC-03 & ATC-06
- Task ID / Title: ATC-09 / Dashboard readiness prep (post core sync)
  - Suggested agent type: review
  - Scope: capture metrics owners/license for internal dashboard once core sync outputs stable
  - Commands to run: `none`
  - Acceptance criteria: checklist of data bindings + approval from Ops lead noting core pipeline settled
  - Evidence required: reviewed checklist + sign-off note
  - Dependencies: ATC-07

## First deployment runbook (to start sync now)
- **Prerequisites & env vars**
  - ClickHouse credentials + endpoint (`CH_HOST`, `CH_USER`, `CH_PASSWORD`, `CH_DATABASE`)
  - PoE User-Agent format: `PoETrade/<env> <team-email>` (e.g., `PoETrade/staging ops@example.com`)
  - Cursor store path (`POE_CURSOR_DIR`) + encryption keys if needed
  - Throttler endpoint (`POE_THROTTLER_URL`) and monitoring token (`THROTTLER_API_KEY`)
  - Alerting hook definition for 429 storms/checkpoint stalls
- **Launch sequence**
  1. Apply ClickHouse schema migrations for bronze tables.
  2. Start global throttler service and verify `Rate-Limit` header capture via curl.
  3. Start MarketHarvester + StashScribe with correct User-Agent/cursor env vars.
  4. Monitor initial write into bronze tables (per league row counts) and confirm throttler does not drop requests.
  5. Kick off ETL silver pipeline pointing to cursor store with `--resume`.
- **Smoke checks**
  - Bronze ClickHouse query returns recent `ingested_at` per league within last 5 minutes.
  - ETL logs show checkpoint restore and writes to silver tables.
  - Throttler metrics record requests served and `rate_limit_remaining` values >0.
- **Monitoring checks**
  - Rate-limit/backoff: dashboards/metrics show `X-Rate-Limit-<rule>` consumption, `Retry-After`, and active backoff durations.
  - Checkpoint progress: `poe_ingest_status` (or equivalent) shows `next_change_id` advancing for each league/hour.
  - Progress markers: log derived `last_ingest_time`, `avg_req_per_sec`, and `stalled_since` for alerting.
- **Failure recovery practices**
  - 429 storms: pause new requests until `Retry-After` expires, log the rule backing the storm, and notify Ops via alert hook.
  - Checkpoint stalls: if `next_change_id` stops advancing for >10m, restart runner with `--dry-run` to verify cursor logic before resuming.
  - Invalid-request spikes: classify repeated 4xx as config/auth issues, disable offending league/endpoint, correct input, and restart to avoid ban.

## Dashboard implementation constraints (internal only)
- Layout reuse policy: fully copying a pre-approved layout/visual set is acceptable because the dashboard stays internal; document any deviations and sign-off required by the observability lead.
- Allowed stack: prefer vanilla JavaScript for DOM/data binding plus light Tailwind CSS for utility styling to keep the frontend lean; avoid adding new component frameworks or heavy theming libraries.
- Data scope: show ingest rate, checkpoint health, and gold-table metrics defined earlier, keeping the dashboard an operational window into DB/ETL outputs rather than a bespoke analytics surface.
- Non-goals: no new design system, no public-facing restyling, and no custom visualization library beyond the approved palette/chart set.
- Evidence of compliance: README fragment should cite the reused layout source, note that styling adheres to the vanilla JS + Tailwind stack, and mention that matching visuals were acceptable for this internal surface.

## Open questions & risks
- Risk: PoE rate limits tighten unexpectedly; mitigations include global backoff, layered caching, and queueing longer backfills overnight when quota relaxes. Source: `https://www.pathofexile.com/developer/docs` (dynamic rate limits + restrictions).
- Question: should MarketHarvester use multiple realm/league workers or one long-lived cursor per realm? Need to balance parallelism with global rate budgets. Source: `https://api.pathofexile.com/public-stash-tabs` (realm-aware cursor stream semantics).
- Risk: `next_change_id` handling changes or cursor regressions cause duplicate/missed ingest windows; monitor for regressions and add guardrails (reject older IDs, alert on rewind). Source: `https://api.pathofexile.com/public-stash-tabs` and `https://api.pathofexile.com/currency-exchange` (cursor-based progression).
- Question: what level of historical retention do we keep in bronze vs. silver tables for compliance with TTL requirements described in project architecture docs? Source: `00-ecosystem-overview.md` and `01-architecture.md` (raw TTL guidance, layered storage).
- Question: who governs the approved dashboard layouts/visuals referenced by the internal template, and how do we record changes to that source so reuse stays aligned with Ops expectations? Source: platform observability charter (internal reference).
