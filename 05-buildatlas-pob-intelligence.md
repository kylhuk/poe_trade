# BuildAtlas — Autonomous Build Discovery + Build Coach (PoB-powered)

## What BuildAtlas is
BuildAtlas is an autonomous build generator and optimizer that uses Path of Building as the source-of-truth calculator, and Wraeclast Ledger as the source-of-truth for item prices.

Two modes:
1) **AtlasForge (autonomous discovery)**: press one button, it generates and evaluates many *random but constrained* builds (skill tree + items + gems), then presents a sortable table (damage, survivability, cost, difficulty, etc.). From that table you can pick a build and export a PoB link/code.
2) **AtlasCoach (guided progression)**: import your current character (via PoE API or PoB) and get a prioritized roadmap (next passive points, gem upgrades, gear upgrades) with estimated price and expected power gain.

Key design goal: avoid “everyone plays the same build so items become overpriced” by:
- searching a large space (not just known builds),
- penalizing “meta-crowding risk” items (high price, high volatility, low supply),
- and promoting *diverse* solutions (novelty / diversity pressure).

## User experience

### A) One-button build discovery
Inputs (optional constraints; defaults provided):
- league/realm
- budget cap (chaos/divines)
- max difficulty (0–100)
- desired content profile (mapper / bosser / balanced)

Action:
- click **Generate builds** (or schedule a nightly run)

Output:
- a table you can filter/sort:
  - main skill, ascendancy
  - DPS (per scenario), EHP, max hit taken, recovery
  - resist status (caps), move speed proxy
  - **estimated total cost** (p50 + p10/p90)
  - difficulty score + reasons (e.g., “5 active skills”, “squishy”, “tight resists”)
  - “meta risk” (items likely to inflate)

### B) “Surprise me”
- click **Surprise Build**
- returns one build sampled from the “good + affordable + playable” set, weighted for novelty/fun

### C) Build coach for your current character
Inputs:
- your character snapshot from PoE API (items + tree) OR a PoB export

Outputs:
- next 10–30 passive points path (with per-point gains)
- gem upgrades (levels/quality, link changes) with cost and DPS delta
- gear upgrade shopping list ranked by “power gained per chaos”
- optional: alternative “pivot” targets (similar builds that become stronger/cheaper)

## Architecture (integrates into Wraeclast Ledger ecosystem)

### Services (docker-compose additions)
- `atlas_api` (FastAPI): triggers runs, serves build tables/details, exports PoB codes.
- `atlas_forge` (orchestrator): generates candidates, schedules evaluations, trains surrogate model (optional).
- `atlas_bench` (PoB worker pool): headless PoB eval workers in a locked-down container.
- `atlas_coach` (planner): computes upgrade steps for an imported character.
- (optional) `atlas_index` (vector/ANN): build embeddings for similarity + diversity (can be in-process FAISS; ClickHouse remains the only DB).

Dependencies:
- reads price stats and item templates from ClickHouse (Wraeclast Ledger)
- calls Ledger pricing endpoints for exact item price estimates when needed
- writes BuildAtlas tables into the same ClickHouse database (separate schema prefix recommended)

Security/hardening:
- PoB workers: no outbound network, non-root user, strict CPU/RAM limits, read-only FS.

## Core technical approach

Build discovery is a black-box, multi-objective optimization problem. PoB is the evaluator.

### 1) Reduce the search space (mandatory)
Do not attempt “full random across everything” (it will drown in invalid builds). Use *structured randomness*:

A. Choose an archetype seed:
- ascendancy (random, weighted)
- main skill gem (random, but compatible with ascendancy and weapon constraints)
- damage type intent (physical/fire/cold/lightning/chaos)
- delivery style (hit / DoT / minions / mines / totems / traps / brands)

B. Generate a “budget-valid baseline”:
- tree points at a target level (e.g., 92–95)
- gem links (1 main 6-link + auras + utility)
- gear: start with “generic life+res rares” + a small set of optional uniques

C. Then optimize locally (fast):
- improve tree allocation
- improve support gems
- improve gear under budget constraints
- enforce constraints (res caps, attribute requirements, reservation)

### 2) Build representation (the genome)
Represent a build as a JSON “genome” that is always convertible to PoB:
- class, ascendancy
- level target
- main skill + selected supports
- aura set
- passive nodes list (node IDs)
- gear spec per slot:
  - unique identifier OR “rare template id”
- config toggles per scenario (enemy/buffs)

Store genome + derived PoB XML (for reproducibility).

### 3) Evaluation (PoB as the oracle)
For each candidate genome, evaluate 2–4 standardized scenarios (same rules for all builds):
- MAP_CLEAR_BASELINE
- PINNACLE_BOSS
- DEFENSE_CHECK
- BUDGET_MAPPING (no “luxury flasks/toggles”)

Persist:
- DPS (and/or DoT), hit chance, ailment uptime if relevant
- EHP proxy, max hit taken, recovery/sec
- resist status (including chaos), suppression/block if relevant
- movement proxy and QoL flags (optional)
- validation flags (broken build, missing requirements, etc.)

### 4) Cost estimation (from your market DB)
Compute build cost as a distribution (p10/p50/p90), not a single number.
- Uniques: direct pricing from listings
- Rares: price via your fp_loose/comps model (or via “rare templates”, see below)
- Gems: include awakened/enlighten-style costs when used

Add “meta-crowding risk”:
- penalize items with low liquidity + high volatility + fast price increase
- this pushes BuildAtlas away from “popular YouTube build items” early in a league

### 5) Difficulty scoring (explainable heuristics)
Difficulty = mechanics + survivability + gearing

Mechanics features:
- number of active buttons in the baseline rotation (proxy)
- reliance on conditional uptime (flasks, on-kill, temporary buffs)
- required positioning/aiming (proxy from skill behavior category)

Survivability features:
- EHP, max hit taken, recovery
- uncapped resists / weak chaos res
- “glass cannon penalty” if DPS is high but defenses fail thresholds

Gearing features:
- number of low-confidence rare items
- number of mandatory expensive uniques
- attribute/reservation tightness (fragile requirements)

Output:
- difficulty score 0–100
- reason codes (for UI)

### 6) The search algorithm (practical progression)
MVP: random + hill-climb
- generate many structured-random seeds
- locally improve each seed via greedy moves:
  - swap 1 support gem, accept if improves objective
  - add/remove small sets of passive nodes via PoB delta calls
  - swap one gear template for cheaper/stronger alternative
- keep top K per archetype and a global top set

Next: multi-objective evolutionary search (recommended)
- population = genomes
- mutation operators:
  - tree mutation (replace one cluster target, re-path)
  - support mutation (swap one support)
  - aura mutation (swap aura set within reservation)
  - gear mutation (swap template / add unique core)
- selection:
  - Pareto dominance (power vs cost vs difficulty)
  - novelty bonus (distance in embedding space)
- this avoids converging to “one build” and preserves diversity

Optional acceleration: surrogate model (ML)
- train a surrogate to predict PoB outputs from genome features
- use it to pre-rank 10k candidates cheaply
- only send the top N to PoB for confirmation (active learning loop)

## Rare item handling (so the gear dimension is tractable)

### Phase 1 (fast): “generic rare budgets”
- assume each rare slot is a generic life+res item with price from your market median
- enforce res/attribute caps approximately

This gets you early value quickly, but is coarse.

### Phase 2 (real): rare “templates” mined from your listing data
From ClickHouse market data:
- cluster rares by slot/base + mod families (life, resists, suppression, etc.)
- each cluster becomes a **template**:
  - expected stats vector (median rolls)
  - price distribution (p10/p50/p90) and liquidity
During build synthesis:
- choose one template per slot to satisfy constraints and optimize objective under budget

This turns “infinite rares” into a manageable catalog.

## AtlasCoach (upgrade path planner)
Given a character import:
1) Evaluate current state in PoB scenarios.
2) Identify bottlenecks:
   - missing caps, too low max hit, low DPS for content profile, etc.
3) Generate upgrade candidates:
   - passive point candidates (marginal gain per point)
   - gem upgrades (level/quality, alt supports)
   - item upgrades by querying your market templates + uniques
4) Score each upgrade by:
   - delta power / delta chaos
   - risk/confidence
5) Output a roadmap:
   - “cheap wins first”, then “medium”, then “stretch goals”
   - exportable shopping list

## Patch Radar (find “hidden power” after changes)
When PoB/game data updates:
- mark evaluations stale
- run targeted search:
  - prioritize skills/gems with the largest numeric changes
  - re-evaluate a wide random sample across archetypes
- produce “delta leaderboard”:
  - biggest DPS/EHP gains vs previous version
  - filtered by low cost + low meta risk

Goal: surface strong, cheap builds before they are widely copied.

## ClickHouse tables (BuildAtlas schema)
- atlas_build_genome(build_id, created_at, league, genome_json, pob_xml, tags[])
- atlas_build_eval(build_id, scenario_id, evaluated_at, metrics_map, valid, warnings[])
- atlas_build_cost(build_id, estimated_at, cost_p10, cost_p50, cost_p90, confidence, breakdown[])
- atlas_build_difficulty(build_id, scored_at, score, reason_codes[], details_map)
- atlas_build_rank(build_id, scenario_id, rank_ts, power_score, value_score, pareto_rank, meta_risk)
- atlas_coach_plan(character_id, created_at, target_profile, steps[], total_cost_est)

## Roadmap (recommended order)
1) PoB headless evaluation worker pool (`atlas_bench`)
2) Genome spec + “structured random” generator (`atlas_forge`)
3) Standard scenarios + persistence + table UI
4) Cost estimation integration (reusing Ledger)
5) Difficulty scoring + filter/sort UI
6) Evolutionary search + novelty
7) Rare templates catalog + budgeted gear synthesis
8) AtlasCoach upgrade planner
9) Patch Radar reruns + delta leaderboard
10) Surrogate model acceleration (optional)
