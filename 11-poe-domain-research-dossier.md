Scope and assumptions
- Focus is Path of Exile 1 campaign + stash workflows (Acts 1-10) for three systems: stash overlay, questing companion, and dynamic filter rewrite.
- This document is implementation input, not gameplay advice; each fact maps to an engineering decision.
- Official sources are used for API contracts and policy constraints. Community sources are used for domain data and heuristics with explicit confidence labels.

Source quality policy
- High confidence: official GGG docs (`pathofexile.com/developer/docs*`, `pathofexile.com/item-filter/about`).
- Medium confidence: curated community sources (PoE Wiki, Maxroll, FilterBlade, established tooling docs).
- Low confidence: forum anecdotes and unverified posts; allowed only as follow-up leads, not build-time truth.

High-confidence official findings

| Finding | Source URL | Confidence | Implementation impact |
|---|---|---|---|
| Filter DSL is block-based with `Show`/`Hide`/`Minimal`; matching is first-hit unless `Continue` is used. Relevant conditions include `Sockets`, `SocketGroup`, `LinkedSockets`, `Width`, and `Height`. | https://www.pathofexile.com/item-filter/about | High | Dynamic filter engine must parse and emit these primitives exactly, and keep ordering semantics intact. |
| Developer policy allows local log-file reading when user is aware, but forbids automation patterns (timers, automatic triggers, multi-action macros). Manual invocation and one game action per invocation are required. | https://www.pathofexile.com/developer/docs | High | Default design must avoid simulated input. Any action with game interaction requires explicit user trigger. |
| API rate limits are dynamic and exposed through `X-Rate-Limit-*` and `Retry-After`; clients must handle 429/4xx responses. | https://www.pathofexile.com/developer/docs | High | Add rate-limit aware retry/backoff and hard rollback behavior for filter update flows. |
| Item filter management API supports create/update/get and `validate=true` for server-side validation against current game version. Update endpoints may return `202 Accepted`. | https://www.pathofexile.com/developer/docs/reference | High | Always validate candidate filter text before activating it; support async acceptance/polling states. |
| Stash/public stash item payloads expose dimensions and placement needed for footprint rendering (`w`, `h`, and position data), plus socket arrays and item metadata. | https://www.pathofexile.com/developer/docs/reference | High | Overlay can mark full item rectangles without image recognition when data source is stash API/public stash payloads. |
| Public stash stream is intentionally delayed (5-minute delay), with pagination via `next_change_id`. | https://www.pathofexile.com/developer/docs/reference | High | Use public stash only for broad market signals, not low-latency user-facing stash overlays. |

Medium-confidence community findings

| Finding | Source URL | Confidence | Implementation impact |
|---|---|---|---|
| Standard stash tabs are 12x12 and quad tabs are 24x24. | https://www.poewiki.net/wiki/Stash | Medium | Grid renderer needs tab-shape metadata and specialized-tab fallbacks. |
| Socket/link constraints: item type limits (e.g., body armor/two-hand up to 6) and practical ilvl gates (4/5/6 sockets around 25/35/50). | https://www.poewiki.net/wiki/Socket | Medium | Filter/overlay must block impossible socket targets and explain why. |
| Areas are procedurally generated from layouts with recurring tendencies; objective placement is probabilistic, not deterministic. | https://www.poewiki.net/wiki/Area | Medium | Quest hints must use confidence scores, not exact coordinates. |
| Waypoint list by act is stable enough for route-graph scaffolding; recent behavior includes waypoint auto-activation by proximity. | https://www.poewiki.net/wiki/Waypoint | Medium | Build route planner as graph over unlocked waypoints and zone transitions. |
| Act pages (1,2,5,10 sampled) expose hub-and-spoke progression and optional detours suitable for route heuristics. | https://www.poewiki.net/wiki/Act_1 ; https://www.poewiki.net/wiki/Act_2 ; https://www.poewiki.net/wiki/Act_5 ; https://www.poewiki.net/wiki/Act_10 | Medium | Seed campaign FSM with required vs optional branches and level ranges. |
| PoE Wiki Cargo supports structured extraction (`cargoquery`) and has relevant tables (`areas`, `quest_rewards`). | https://www.poewiki.net/w/api.php?action=help&modules=cargoquery&format=json ; https://www.poewiki.net/wiki/Special:CargoTables/areas ; https://www.poewiki.net/wiki/Special:CargoTables/quest_rewards | Medium | Prefer structured ingestion pipelines over free-text scraping for quest/routing data. |
| Quest reward data is class-sensitive and patch-sensitive in practice; normalization is required before runtime use. | https://www.poewiki.net/wiki/Special:CargoTables/quest_rewards | Medium | Build `quest x class x patch` canonical tables with version tags and confidence flags. |
| Campaign speed guides provide practical heuristics for acts, but are not authoritative game contracts. | https://maxroll.gg/poe/getting-started/campaign-guide | Medium | Treat as heuristic inputs with source tags and easy override in UI. |
| Local tooling commonly reads `Client.txt`; known install-specific log paths are documented by community references. | https://www.poecommunity.help/information/log-file | Medium | Ship setup checker for log path detection and parser health diagnostics. |
| FilterBlade is fan-made (not GGG-affiliated) and should be treated as a high-value but non-authoritative integration source. | https://www.filterblade.xyz/ | Medium | Keep official filter syntax validation as final gate before deployment. |

Data-model implications by feature

- Stash overlay
  - Primary model fields: `item_id`, `tab_id`, `x`, `y`, `w`, `h`, `sockets[]`, `ilvl`, `rarity`, `baseType`, `note`, `chaos_estimate`.
  - Renderer contract: full-footprint rectangle per selected item, plus dim-mask excluding selected bounds.
  - Tab handling: regular/quad dimensions and specialized-tab exclusion behavior.

- Questing companion
  - Core graph: `zone_node`, `act`, `area_level`, `waypoint_present`, `neighbors`, `objective_type`.
  - Runtime state: `current_zone`, `current_level`, `quest_flags`, `last_waypoint`, `confidence`.
  - Reward model: normalized `quest_reward` rows keyed by `quest_id + class + patch` with reasoned recommendations.

- Dynamic item filter
  - Rule model: AST nodes for `Show/Hide/Continue` blocks and conditions (`Sockets`, `SocketGroup`, `LinkedSockets`, etc.).
  - Safety model: `last_validated_filter`, `validation_time`, `market_data_age`, `fallback_reason`.
  - Freshness policy: if market signal age exceeds threshold, degrade to conservative baseline and warn user.

Open questions and validation backlog

- Confirm exact stash payload path for placement fields (`x/y` in root vs nested structures) across endpoints and leagues.
- Verify specialized stash tab behavior for overlay mapping (currency/map/fragment tabs are not simple rectangular inventories).
- Build Cargo ingestion POC for `areas` and `quest_rewards`, including pagination and schema-drift detection.
- Validate quest-reward normalization for class-specific rows and duplicate rewards across patches.
- Benchmark filter validation/upload cadence under real API limits and define safe throttle defaults.
- Build parser test corpus for `Client.txt` event extraction (`entered area`, whispers, quest transitions) with confidence scoring.
