## 1) Objective and player outcomes
- Provide a single-pane questing companion that keeps players on the fastest route through PoE’s campaign while surfacing immediate tasks, reward trade-offs, and loot priorities.
- Outcome: player always knows the next zone/map, exact interaction (talk, kill, enter, use), relevant reward options, and any level/gem prep needed before proceeding.

## 2) Scope and non-goals
- Scope: acts 1-10 story quests across Harbingers/Expansions with deterministic steps; procedural map hints derived from heuristic replay data.
- Non-goals: crafting/trading workflows, third-party item management, and full map layout guidance beyond “usual location” cues.

## 3) Companion experience (user sees minute-to-minute)
- Side panel always visible in overlay/launcher: top strip states current act + level range.
- Primary card shows “Next Step”: zone or map name, action verb (enter, talk to, defeat), target details, and estimated time to completion.
- Secondary cues expose optional rewards, loot you should pick up, and gem setup reminders (e.g., “socket new Frostblink 4-link before Dried Lake”).
- Procedural zone hint area lists “usual locations” with confidence badge (high/medium/low) and timestamped source (run log, community tag).
- Reward pinboard shows quest reward options, default recommendation, and rationale (alignment with build, trade value, leveling utility).

## 4) Knowledge model (acts, zones, objectives, heuristics)
- Acts Model: finite state machine with each quest node (entry, completion, gating items) and linked zone metadata (level range, recommended cleared thresholds).
- Zone Metadata: canonical map name, vendor proximity, common mob density, and procedural map heuristics (spawn points, layout clusters).
- Objective Metadata: required action type, reward list, optional conditions (e.g., soak 3 shrines before crossing).
- Heuristics: “usual location” patterns stored as {zone,map}: {coords, confidence, source} derived from past runs and community logs; update weights per week.

## 5) Runtime state detection (location, level, quest state)
- Detect player position via overlay API or ingesting log lines (zone entry, waypoint, quest updates); fallback to manual entry UI for unsupported clients.
- Track level by parsing experience/level gain events; cross-check against zone’s expected range to avoid stale data.
- Quest state mirror: read questlog entries from client or rely on classic quest progression order; flag unknown states as “probable next” until concrete trigger hits.

## 6) Recommendation engines
- Next-step routing: solver uses current act, quest state, and location to propose shortest path (min swaps/backtrack) to reach objective; factors in travel sequences (waypoints, custom portals).
  - Acts 6-10 routing adds explicit speed knobs: waypoint ordering prioritizes adjacent gates, transition heuristics pick the act exit closest to the next quest node, detour policy limits optional clears unless they unlock a level gate, and level-gate checks delay transitions until the player has the intended range for the next act to avoid excess respecing or backtracking.
- Reward picks: rank quest rewards by build relevance (tags like “map clear”, “movement speed”), trade value (price API), and prep status (inventory space for new items).
- Loot priority hints: flag specific pickups (e.g., quest items, alt-quality gems) with labels; suppress warnings once picked.
- Gem setup: inspect socketed gems, compare to recommended progression (act-specific gems, support synergies), and prompt when swapping or buying new setups will unlock key mechanics.
  - Reminders only fire when the detected sockets/gems diverge from the current recommendation (compare socket colors, links, and gem levels) so alerts stay meaningful rather than repeating for already-matched setups.

## 7) UI plan
- Panel layout: top row (act, level), next-step card (zone + action + countdown), followed by horizontal tabs for Rewards, Loot, Gems, Usual Locations.
- Interaction: tap next-step to copy waypoint/map commands; reward row has radio/select to lock choice; loot pins link to journal entry; gem reminders open a quick view of recommended vendors.
- Confidence badges use color-coded chips (green/high, amber/med, gray/low) with tooltip explaining reliability.

## 8) Performance, reliability, and update cadence
- Lightweight runtime: data refresh triggered only on state change events and periodic heuristics sync (every 5 minutes).
- Reliability: fallbacks for missing telemetry (manual overrides). Cache heuristics with TTL so network hiccups degrade gracefully.
- Updates: weekly content sync (new league quests, map meta) and daily reward valuation pulls; document changes in changelog and overlay release notes.

## 9) Phased implementation plan with milestones
1. Data foundation: encode act/quest graph, zone metadata, and heuristic schema; stub APIs for reward info.
2. Runtime binding: implement location/level watcher plus quest state detections; surface minimal next-step card.
3. Recommendation engines: add reward selector, loot prioritizer, gem inspection logic into UI.
4. Heuristic hints & confidence: connect procedural location data to UI, support confidence badges.
5. Polishing & integrations: ExileLens overlay hooking, final performance tuning, release notes.

## 10) Acceptance criteria
- Side panel always shows non-null next step and correctly reflects quests progressed at least through Act 5 in tests.
- Reward recommendation must list at least two options and highlight the chosen one with rationale.
- “Usual location” hints change when heuristics update and clear when user provides manual confirmation.
- Gem setup reminders fire only when detected sockets/gems diverge from the recommendation for the next major fight so repeat alerts are suppressed.

## 11) Evidence checklist (docs-only)
- [ ] Knowledge model documented with act/zone/quest heuristics
- [ ] Runtime detection strategy noted
- [ ] Recommendation engines outlined with ranking factors
- [ ] UI plan lists interactions and badge semantics
