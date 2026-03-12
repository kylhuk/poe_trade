# Viable Trading Strategies (Mirage)

## 1) Fragment Spread Flipping (Currency Exchange)

Status: **GO-WITH-GUARDRAILS**

### Why this is currently viable
- Tradable market ids for set/fragment instruments are present in the official static trade data (for example: `sacrifice-set`, `mortal-set`, `shaper-set`, `the-mavens-writ`, `fragment-*`).
- Mirage CX snapshot shows positive executable spread on fragment markets with meaningful volume.
- This strategy maximizes profit per manual action better than bulk/low-margin methods in current data.

### Mirage backtest evidence (from current local data)
- Fragment/set chaos markets (`vol>=100`) with positive spread:
  - `reverent-fragment`: ask `60`, bid `28`, spread `32`, volume `803`
  - `devouring-fragment`: ask `105`, bid `82`, spread `23`, volume `2248`
  - `fragment-of-terror`: ask `54`, bid `41`, spread `13`, volume `609`
  - `reality-fragment`: ask `71`, bid `65`, spread `6`, volume `2444`
  - `lonely-fragment`: ask `13`, bid `8`, spread `5`, volume `519`
  - `synthesising-fragment`: ask `13`, bid `9`, spread `4`, volume `3418`
  - `awakening-fragment`: ask `11`, bid `7`, spread `4`, volume `2452`
- Aggregate across these 7 markets: average spread `12.43c`, total spread `87c`.
- Conservative execution model (1% hourly volume, capped at 10 flips per market):
  - total `729c` over `59` trade steps (`~12.4c/step`)
  - top two markets (`reverent-fragment` + `devouring-fragment`): `486c` over `18` steps (`27c/step`)

### Execution playbook (manual)
1. Prioritize `reverent-fragment` and `devouring-fragment`.
2. Enter only when live spread stays positive after refresh.
3. Size small first, then scale only if fills are consistent.
4. Ignore single-print outliers and stale quotes.

### Risk guardrails
- Treat `12-27c/step` as realistic band from current evidence; do not plan around higher implied numbers from sparse summary rows.
- Current Mirage coverage is thin (gold refs are a short window, CX is a single hour snapshot), so run this as a pilot strategy.
- Revalidate spread persistence before scaling.

## 2) High-Ticket CX Spread Sniping (Golden Oil + Tainted Divine Orb)

Status: **GO-WITH-GUARDRAILS (pilot)**

### Why this is currently viable
- External economy guidance also flags oils and tainted currency as high-value manual trading classes in Mirage.
- Mirage CX snapshot shows both instruments with high spread and strong volume.
- This pair currently beats fragment-only basket on profit per manual step in conservative sizing.

### Mirage backtest evidence (from current local data)
- `golden-oil`: ask `90`, bid `60`, spread `30`, volume `928`, conservative steps `9`, conservative profit `270c`
- `tainted-divine-orb`: ask `156`, bid `125`, spread `31`, volume `878`, conservative steps `8`, conservative profit `248c`
- Combined basket:
  - total conservative profit `518c`
  - total steps `17`
  - estimated profit per step `30.47c/step`

### Execution playbook (manual)
1. Keep buy and sell orders active only while spread stays >= `20c`.
2. Allocate most steps to `golden-oil` and `tainted-divine-orb` before lower-edge markets.
3. Reprice frequently to avoid stale spread decay.

### Risk guardrails
- This evidence is from a single Mirage CX hour; treat `30.47c/step` as a pilot upper-band, not stable expectation.
- Skip entries when spread compresses below `20c`.
- Maintain low capital per leg until repeated-hour persistence is observed.

## 3) Div Card CX Spread Pair (The Nurse + The Sephirot)

Status: **VIABLE (pilot)**

### Mirage backtest evidence (current local data)
- `the-nurse`: spread `30`, volume `461`, steps `4`, conservative profit `120c`
- `the-sephirot`: spread `17`, volume `791`, steps `7`, conservative profit `119c`
- Combined pair: total `239c` over `11` steps => `21.73c/step`

### Execution playbook (manual)
1. Run only the top two card markets above.
2. Enter when spread >= `12c` and volume remains >= `400`.
3. Exit or pause when spread compresses under `8c`.

### Risk guardrails
- Card spreads can collapse quickly around farming bursts.
- Keep this as secondary to strategy #1/#2 until persistence is confirmed.

## 4) Premium Scarab Spread Pair (Containment + Terrors)

Status: **VIABLE (pilot)**

### Mirage backtest evidence (current local data)
- `ambush-scarab-of-containment`: spread `22`, volume `3353`, steps `10`, conservative profit `220c`
- `domination-scarab-of-terrors`: spread `18`, volume `2912`, steps `10`, conservative profit `180c`
- Combined pair: total `400c` over `20` steps => `20.0c/step`

### Execution playbook (manual)
1. Keep both orders live only while spread >= `15c`.
2. Favor faster turnover over wider inventory hold.
3. Re-quote frequently due to active competition.

### Risk guardrails
- Scarab books are liquid but highly competitive; stale orders lose edge fast.
- Treat as medium-profit fallback when oil/tainted or fragment spreads are not available.

## 5) Niche Micro-Market Basket (Mirage Utility Currencies) — Too Good To Be True Candidate

Status: **GO-WITH-GUARDRAILS (strict probe only)**

### Thesis
Under-the-radar Mirage utility currencies show unusually wide CX spreads with moderate/high volume. This looks abnormally strong and may be a real niche edge, but current evidence is still one-hour-only.

### Mirage backtest evidence (current local data)
- Core basket:
  - `coin-of-knowledge`: ask `65`, bid `42`, spread `23`, vol `1719`, steps `10`, conservative profit `230c`
  - `cluster-fog` (Refracting Fog): ask `75`, bid `54`, spread `21`, vol `1029`, steps `10`, conservative profit `210c`
  - `echo-of-reverence`: ask `130`, bid `97`, spread `33`, vol `532`, steps `5`, conservative profit `165c`
  - `tailoring-orb`: ask `65`, bid `50`, spread `15`, vol `759`, steps `7`, conservative profit `105c`
  - `mavens-chisel-of-proliferation`: ask `13`, bid `1`, spread `12`, vol `1493`, steps `10`, conservative profit `120c`
- Basket total: `830c / 42 steps = 19.76c per step`.

### Extra niche confirmation (same snapshot)
- Additional Maven chisel spreads:
  - `mavens-chisel-of-divination`: ask `10`, bid `5`, spread `5`, vol `1348`
  - `mavens-chisel-of-procurement`: ask `5`, bid `1`, spread `4`, vol `1853`
- This suggests a family-level pattern, not only one isolated market id.

### Tradability confirmation
- All relevant ids exist in official trade static data categories:
  - `coin-of-knowledge` (DjinnCoins)
  - `mavens-chisel-of-proliferation` (Currency)
  - `cluster-fog` (Currency)
  - `echo-of-reverence` (Fragments)
  - `tailoring-orb` (Currency)

### Oracle stress-test verdict
- Decision: **GO-WITH-GUARDRAILS**
- Realistic range under current evidence: `0 to 19.76c/step`.
- Meaning: treat quoted edge as an upper bound until recurrence and realized round-trip fills are proven.

### Kill-switch conditions
1. Positive spread disappears on follow-up snapshot.
2. Probe trade cannot complete both sides near quoted spread.
3. Realized probe PnL is `<= 0c/step`.
4. Edge depends mostly on one outlier (`mavens-chisel-of-proliferation` 13/1).
5. No independent recurrence beyond single-hour snapshot.

### Probe deployment plan
1. Do not deploy full basket at once; treat each market as separate hypothesis.
2. Start with less discontinuous markets (`coin-of-knowledge`, `cluster-fog`) before extreme outliers.
3. Use tiny size only; require completed round-trip to count edge.
4. Re-check recurrence on additional snapshots before any scaling.
5. Scale only markets with positive realized probes; stop immediately on first failed probe.

## 6) 100c+ Jackpot Snipes (Ultra-Illiquid CX Outliers)

Status: **GO-WITH-GUARDRAILS (sniper only, not scalable)**

### Why this exists
This is the only currently observed Mirage class that satisfies a hard `>=100c per step` threshold directly from quoted spread.

### Mirage evidence (current local data, chaos-quoted)
- `the-immortal`: ask `1150`, bid `852`, spread `298`, vol `11`
- `the-shieldbearer`: ask `690`, bid `466`, spread `224`, vol `25`
- `runegraft-of-the-fortress`: ask `635`, bid `518`, spread `117`, vol `46`
- `runegraft-of-the-warp`: ask `900`, bid `800`, spread `100`, vol `3`

### Feasibility filter (strict)
- `vol < 20`: reject (`the-immortal`, `runegraft-of-the-warp`) due to fragility.
- `vol 20-39`: conditional watchlist (`the-shieldbearer`).
- `vol >= 40`: primary deployable (`runegraft-of-the-fortress`).

### Oracle verdict
- Decision: **GO-WITH-GUARDRAILS**
- Interpretation: valid for `100c+` per-step snipes, but throughput is very low and non-scalable in current snapshot.

### Execution model
1. Treat as opportunistic sniper mode only.
2. Deploy only when spread remains >= `100c` after refresh.
3. Prioritize `runegraft-of-the-fortress`; then `the-shieldbearer`.
4. Use tiny size and require completed round-trip before counting edge.
5. Abort immediately if realized step PnL drops <= `0c`.
