# Wraeclast Ledger — Strategy Registry (Community-Sourced) to Test

Purpose: register “known player strategies” as testable hypotheses and validate them using your own data (prices + sessions).

## How to use this file
1) Add each strategy as a `strategy_id` with:
- Required inputs (market tables, session tags, craft actions)
- KPI definitions (profit/hour, EV, liquidity, variance)
- Detector query (how to surface opportunities)
2) Run it in two modes:
- Backtest (historical, if you keep enough listings)
- Live test (SessionLedger: start/end sessions + tag)

## Strategies (initial set)

### S01 — Currency exchange market making (illiquid pairs)
Claim (players): profit from stable spreads by placing buy/sell orders as liquidity provider.
Test:
- Identify pairs with high spread and acceptable fill rate.
- Measure inventory holding time and drawdowns.

Sources (examples):
- https://www.reddit.com/r/pathofexile/comments/1e7rcvn/currency_trading_101_market_making_illiquid_pairs/

### S02 — Bulk trading convenience premium
Claim (players): bulk sells faster and can command a premium; bulk buys can get discounts.
Test:
- Compare bulk vs single-unit price distributions.
- Include time-to-sell and opportunity cost.

Sources:
- https://www.reddit.com/r/pathofexile/comments/uoo849/small_guide_for_bulk_trading_for_new_players/

### S03 — Expedition-focused mapping / logbooks
Claim (guides/players): Expedition is consistently profitable (raw currency + logbooks) and scales with investment.
Test:
- Tag sessions “Expedition”.
- Track logbook value distribution and liquidity.

Sources:
- https://www.poe-vault.com/guides/guide-for-expedition-in-path-of-exile

### S04 — “Expedition-only” map routing
Claim (players): rush to Expedition in a map, do it, leave, still profit/hour-positive.
Test:
- Compare profit/hour for “full clear” vs “expedition-only” sessions.
- Include map + scarab/compass costs.

Sources:
- https://www.reddit.com/r/pathofexile/comments/1697r86/what_are_some_currency_making_methods_other_than/

### S05 — Delve fossils/resonators
Claim (players): fossils/resonators are liquid and profitable.
Test:
- Tag sessions “Delve”.
- Track which fossils have best profit/hour and sell-through.

Sources:
- https://www.reddit.com/r/pathofexile/comments/1697r86/what_are_some_currency_making_methods_other_than/

### S06 — Blighted maps for steady profit (low gear)
Claim (players): blighted maps are strong profit even on modest builds.
Test:
- Tag sessions “Blight”.
- Track variance and which oils/cards drive value.

Sources:
- https://www.reddit.com/r/pathofexile/comments/1697r86/what_are_some_currency_making_methods_other_than/

### S07 — Invitation farming
Claim (players): invitations are consistent money with the right setup.
Test:
- Tag sessions per invitation type.
- Compare “sell invitation” vs “run invitation” outcomes.

Sources:
- https://www.reddit.com/r/pathofexile/comments/1697r86/what_are_some_currency_making_methods_other_than/

### S08 — Essence farming (and Essence + Harvest)
Claim (players): essences are reliable early and remain good in bulk; combine with other mechanics.
Test:
- Tag sessions “Essence”, “Essence+Harvest”.
- Track bulk premium and per-tier EV.

Sources:
- https://www.reddit.com/r/pathofexile/comments/1697r86/what_are_some_currency_making_methods_other_than/

### S09 — Profit crafting: flasks via annul “keep good mod”
Claim (players): buy 2-mod flasks, annul for ~50% chance to keep good mod, resell.
Test:
- Model craft action: “annul one mod”.
- EV using observed post-craft sell prices.

Sources:
- https://www.reddit.com/r/pathofexile/comments/1otse86/i_know_its_kind_of_telling_on_your_secret_money/

### S10 — Harvest reforge for saleable rares (e.g., chaos reforge rings)
Claim (players): certain reforges on specific bases produce sellable outcomes with positive EV.
Test:
- Model the craft action cost (Harvest currency valued via ChaosScale).
- Outcome valuation via your fp_loose comps and price distributions.

Sources:
- https://www.reddit.com/r/pathofexile/comments/1otse86/i_know_its_kind_of_telling_on_your_secret_money/

### S11 — Targeted reforge spam on influenced bases (example: Shaper shields)
Claim (players): repeatedly reforge influenced bases aiming for high-value mods.
Test:
- Requires mod-tag metadata and enough listings for outcome valuation.
- Track market saturation and liquidity.

Sources:
- https://www.reddit.com/r/pathofexile/comments/1otse86/i_know_its_kind_of_telling_on_your_secret_money/

### S12 — Systematic liquidation (“everything sells if you list it”)
Claim (players): consistent selling of small currencies/fragments/scarabs adds up.
Test:
- Compare weekly profit from “sell everything” vs “selective selling”.
- Identify best categories by profit/time.

Sources:
- https://www.reddit.com/r/pathofexile/comments/1697r86/what_are_some_currency_making_methods_other_than/

## Add new strategies safely
- Only add strategies you can cite to a public guide/post/thread.
- Treat each as a hypothesis; validate with SessionLedger and market stats before scaling.
