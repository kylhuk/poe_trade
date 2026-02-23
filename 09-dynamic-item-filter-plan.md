# Dynamic Item Filter Plan

1) Objective and player outcomes
- Deliver a runtime-driven filter rewriter that maps to build progression, hiding ground loot that cannot meaningfully support the current stage while surfacing relevant bases, colors, links, and implicit tiers.
- Outcomes: faster looting with fewer manual overrides, early visibility on critical upgrades (e.g., Level 13 needing R-B-B chest sockets), and alignment with both build needs and market reality.

2) Scope and non-goals
- Scope: player-facing filter generation for ground items (not stash or vendor windows), adapting to build state data from the client/session, with NeverSink-compatible output structure.
- Non-goals: modifying actual PoE client behavior beyond filter reload, rebalancing economy, or automating purchases. No attempt to mimic full vendor management.

3) Inputs and build-state model
- Input slices: character level, primary skill gems (socket colors), active ascendancy points, recently used skills, socketed item types, socket/link configurations, stash/search profiles.
- Model: build profile captures current gear priority (e.g., leveling, bossing, mapping) and maps to allowed socket colors/links. Example: level 13, swapping to a level 4 gem that needs R-B-B chest sockets triggers new delta rules so the delta highlights chest bases meeting the full `R-B-B` requirement.
- Derivable signals: socket meta (existing slots), gem colors (true color requirement vs. flexible), link needs, item base tiers (white/big base vs. unique) from NeverSink priority tags.
- Telemetry ingestion: client events (level-up, gem swap, socket/link/color adjustments) stream through an ingest queue/service (e.g., Kafka topic -> worker) where schema checks and event timestamps are validated before enqueuing; valid events map to the delta recompute trigger that replays the latest build state slice and issues a prioritized update.

4) NeverSink and market-data integration strategy
- Parse NeverSink filter sections (Rejoice, Recommended) and base-tier preferences to reuse naming conventions and warnings (e.g., `Show` with custom alerts for high-priority grounds).
- Merge league market signals (value per base/socket) from ClickHouse snapshots or API feeds, weighting bases that rose in price after league mechanics change (e.g., new league introduced socket re-rolls).
- Prioritize NeverSink `Priority` tiers when building baseline and overlay delta boosts when market data shows a base is both desirable and affordable.
- Market signal freshness: poll update feeds every 5 minutes, treat data older than 15 minutes as stale, and fall back to baseline-only weights while emitting a warning to telemetry/UX so the operator knows the signal is degraded.

5) Rule synthesis pipeline
- Baseline filter: use NeverSink defaults plus league defaults to cover permanent needs (leveling rings, rares, etc.), ensuring minimal false hides.
- Dynamic deltas: computed per build state—e.g., detect level 13 gem swap -> add rules: `Show` base Type `Chest` with socket colors matching R-B-B, bump priority for bases that can reach that socket configuration.
- Output: merge baseline + delta layers into a serialized filter (NeverSink-compatible naming) with metadata tags for current stage, allow preview diff.

6) Reload strategy and UX
- Generator writes to PoE filter path using temporary file -> atomic move to avoid corruption, then persist the final file in place instead of partial updates.
- Trigger PoE reload via user action or explicitly approved automation (e.g., UI autoloader hook) once the new file is in place; default flow never injects keystrokes automatically and no input simulation happens unless authorized.
- Provide rollback that keeps the previous filter backed up if user aborts reload; expose `dry-run` preview showing reduced ground density.

7) Safety guardrails
- False-hide prevention: enforce conservative tiers for any bases not explicitly whitelisted; default to `Show` for rares below required level.
- Conservative fallback: if build state data is missing or market feed laggy, revert to baseline filter only and log the missing signal.
- Validation: simulate R-B-B chest rule and confirm PoE filter parser accepts color/link expressions before committing.
- Safety smoke test: before atomic swap/reload, run a dry-run parse of the generated filter, surface diff assertions against current filter (delta limited to expected socket/color changes), ensure rare-visibility guard passes (no high-tier rares hidden), and keep rollback conditions documented so reload is aborted if validation or diff checks fail.

8) Performance and update cadence
- Update cadence set to build transitions (level up, gem swap) or manual refresh command; limit operations to once per 10 seconds to prevent I/O thrash.
- Keep synthesis light: only re-evaluate bases affected by the delta (e.g., socket colors changed) and cache NeverSink baseline until manual refresh.

9) Phased implementation plan
1. Data onboarding: parse NeverSink filter templates, store market signals, define build state telemetry schema.
2. Delta engine: implement rules that detect level/gem/socket shifts (use example: level 13 gem needing R-B-B chest) and compute priority deltas.
3. Writer + reload: atomic filter output, safe reload commands, preview diff view.
4. Guardrails + UX polish: add fallback modes, market weighting toggles, and developer telemetry ensuring safe hides.

10) Acceptance criteria
- Generator produces NeverSink-compatible filter files successfully reloaded in PoE.
- Build transitions (e.g., level 13 chest change) visibly shift shown items to R-B-B bases while retaining baseline coverage for other loot.
- Market signals used to bump relevant bases; regressions covered by safety rollbacks.

11) Evidence checklist (docs-only)
- [ ] NeverSink template parsing documented
- [ ] Market signal merge strategy outlined
- [ ] Example scenario (level 13 R-B-B chest) captured in plan
- [ ] Reload + safety guardrails described
