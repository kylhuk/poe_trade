# Non-Flipping Crafting Methods (Mirage)

Snapshot scope:
- League: `Mirage`
- Source: `poe_trade.v_ps_items_enriched`
- Price currency: `chaos`
- Goal: deterministic transformation steps (not passive buy/relist)

## Method 1: Quicksilver Trigger Craft (Charge Recovery + Ele Res)

### Buy filter
- Base: `Quicksilver Flask`
- Explicit mods must include both:
  - `#% increased Charge Recovery`
  - `#% additional Elemental Resistances during Effect`
- Do not buy if it already has target trigger enchant.
- Max buy: `<= 2 chaos` (best at `1 chaos`).

### Craft step
- Bench enchant: `Used at the end of this Flask's effect`
- Deterministic cost: `5 Instilling Orbs`

### Exit plan
- Relist band: `30-40 chaos`
- Fast exit: list near low end (`30-33c`)
- Margin exit: list near high end (`36-40c`)

### Why this works
- Historical pair spread in the dataset showed strong uplift for the same explicit pair when the target trigger is present.

## Method 2: Quicksilver Mapping QoL Craft (Duration + Move Speed)

### Buy filter
- Base: `Quicksilver Flask`
- Explicit mods must include both:
  - `#% increased Duration`
  - `#% increased Movement Speed during Effect`
- Do not buy if already trigger-automated.
- Max buy: `<= 8 chaos`.

### Craft step
- Bench enchant: `Used at the end of this Flask's effect`
- Deterministic cost: `5 Instilling Orbs`

### Exit plan
- Relist band: `22-30 chaos`
- Fast exit: `22-25c`
- Margin exit: `27-30c`

### Why this works
- Mapping-quality utility flasks with automation trigger consistently clear a convenience premium vs untriggered equivalents.

## Method 3: Granite Defensive Automation Craft (Dual Block During Effect)

### Buy filter
- Base: `Granite Flask`
- Explicit mods must include both:
  - `+#% Chance to Block Attack Damage during Effect`
  - `+#% Chance to Block Spell Damage during Effect`
- Do not buy if already trigger-automated.
- Max buy: `<= 10 chaos`.

### Craft step
- Bench enchant: `Used at the end of this Flask's effect`
- Deterministic cost: `5 Instilling Orbs`

### Exit plan
- Relist band: `40-50 chaos`
- Fast exit: `40-44c`
- Margin exit: `47-50c`

### Why this works
- Niche defensive utility flasks gain strong convenience value once automated, while the craft step is deterministic and cheap.

## Shared Execution SOP

1. Search with exact base + exact explicit pair + no target trigger.
2. Buy only at/under max buy threshold.
3. Bench craft the trigger (`Used at the end of this Flask's effect`).
4. Relist immediately in the target band.
5. Reprice every `8-12h`; if stale, cut by `1-2c`.

## Risk Controls

- Skip listings with off-meta corrupted/enkindled states that reduce uptime use cases.
- Do not overpay above max-buy thresholds; edge collapses quickly.
- Keep inventory rotation fast; these are throughput crafts, not long holds.
