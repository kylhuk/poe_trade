Objective and user outcomes
- Describe how an ExileLens overlay can highlight multiple stash items as part of PoE trade workflows.
- Users see selected items’ full footprint highlighted and other items dimmed when their stash is open, reducing misclicks during trading.
- Highlighting supports pricing thresholds (>=10 chaos) and trade-target lists so buyers and sellers stay aligned on value.

Scope and non-goals
- In scope: overlay interaction with the PoE client while a stash tab is open, tracking selection state, and rendering on top of the stash grid.
- Out of scope: any modifications to the Path of Exile client itself or automations that move items between tabs; we only read selection/footprint data and paint overlays.

System architecture
- Data ingestion layer observes ExileLens events describing the open stash tab, selected item IDs, and their footprint coordinates (row/column + height + width).
- Overlay service hosts a renderer that mirrors the stash grid and exposes APIs for selection updates (add/remove items, apply price filters).
- Coordinate the overlay with ExileLens so both are aware of the current stash zone; the overlay subscribes to the stash tab lifecycle events and redraws as the user switches tabs.

Data model and APIs
- Selection payload: list of item handles containing stash tab identifier, grid X/Y, width, height, and optional metadata (chaos value, trade tag).
- Public API calls:
  * `updateSelection(List<Selection>)` – full-replacement updates; expected after tab switch or new focus.
  * `clearSelection()` – resets overlay state when stash closes.
  * `setDimIntensity(float)` – optional tuning for dimming effect.
- Store per-item selection metadata in a lightweight cache keyed by ExileLens item ID to avoid recomputing footprints for repeated renders.

Overlay rendering strategy (grid mapping, full-footprint polygons, dim mask)
- Map stash grid cells to overlay coordinates using the stash tab’s grid dimensions and the renderer canvas size.
- For each selected item, draw a filled polygon that covers every cell of its footprint by calculating the rectangle that spans `(gridX, gridY)` through `(gridX+width-1, gridY+height-1)`.
- Render a translucent dim mask over the entire stash grid before drawing selections; then clear the mask on selected footprints to keep them fully bright while non-selected items stay visible but subdued.
- Ensure the dim mask and highlights share the same z-order and respond to stash scrolling so their positions stay aligned.

Selection scenarios (pricing threshold + trade-helper)
- Pricing threshold: derive selected set from metadata where `chaosValue >= 10`. The overlay automatically updates when pricing metadata refreshes (e.g., periodic ExileLens scans) so qualifying items glow.
- Trade helper: accept buyer-provided lists of item IDs or coordinates to highlight multiple pieces simultaneously. Support both single-item focus and bulk requests (up to the practical upper bound documented below).

Performance and latency budget
- Practical upper bound: render up to ~50 selections per stash grid update; batching beyond that adds complexity and minimal benefit, so fall back to a grouped highlight (e.g., by tab regions).
- Maintain <16ms render latency per frame to stay within 60fps feel; only recompute polygons when selection list or stash scroll/zoom events change.
- Keep selection cache small (map size matching typical stash size) and avoid re-rendering entire canvas when only one item’s highlight changes.

Failure modes and fallback UX
- If ExileLens stops reporting selections, overlay should fade out gracefully and notify the user via a lightweight toast that selection data is unavailable.
- If excessive selections arrive (>50), only highlight the first 50 and log a warning; provide a UI hint (e.g., “displaying first 50 trade targets”) to explain the partial view.
- On stash resize/zoom, delay redraw by <100ms to prevent flicker; if mapping information is missing, fall back to a subtle border highlight without dimming.

Phased implementation plan with milestones
Phase 1
- Hook into ExileLens selection events, recreate stash grid mapping, and render a single selection highlight (full footprint).
Phase 2
- Add dim mask layer, support multiple selections, and expose `setDimIntensity` for configuration.
Phase 3
- Introduce pricing threshold logic, trade helper lists, and impose the 50-selection cap with informative messaging.

Acceptance criteria
- Opening a stash tab and selecting an item results in a full-footprint highlight overlayed on the grid.
- Non-selected items remain visible but dimmed while the mask respects dynamic stash scrolling/zoom.
- Pricing and trade helper flows can pass lists of items and see them highlighted; system logs when selection limits are reached.

Evidence checklist (docs-only, tests/lint N/A unless explicitly added)
- `07-exilelens-overlay-plan.md`
- Tests: not run / N/A
- Lint: not run / N/A
