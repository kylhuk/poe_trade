# Path of Exile Data Source Research

This research captures feasibility, cadence, and compliance for the most actionable Path of Exile data surfaces we can tap for continuous "bronze" ingestion (market snapshots, metadata, heuristics).

## Executive summary table

| Source | Key data domains | Access pattern | Rate-limit / cadence note | Bronze ingestion fit |
| --- | --- | --- | --- | --- |
| Official PoE Developer/API docs | Account profiles, leagues, ladders, trade metadata, errors, OAuth policies | RESTful `api.pathofexile.com` endpoints | Dynamic limits signalled by `X-Rate-Limit-*` headers (`client: 10:5:10` sample) | Governance layer + league/ladder references required before pulling other feeds |
| PoE trade data (`/api/trade/data/*`) | League-specific categories, base types, item/unique lists, fragments, etc. | JSON `GET https://www.pathofexile.com/api/trade/data/<resource>` | Subject to official API limits; avoid invalid requests | Schema seeds for category metadata (e.g., `trade_category`, `item_type`, `variation`) |
| poe.ninja | Live chaos/$ valuation, sparklines, listing counts for currencies, uniques, oils, etc. | REST `/poe1/api/economy/stash/current/<domain>/overview` with `league` & `type` | Undocumented; obey conservative pacing (1/s); data records include `sample_time_utc` for freshness | Price signals + listing density per league for heuristics |
| poedb.tw | Community-updated mods, crafting bench options, hideouts, recipes | JSON endpoints such as `https://poedb.tw/us/json.php/<table>` (undocumented) | Unknown; endpoints sometimes 404, no public rate docs | Supplement mod/craft metadata, hideout names and OR filters for richer schema |
| Path of Exile Wiki Cargo API | Items, mods, skills, versions via MediaWiki cargo tables | `GET https://pathofexile.fandom.com/api.php?action=cargoquery&...` | MediaWiki limits apply; chunk via `limit`/`offset`, avoid high-frequency polls | Canonical mod/item metadata and versioned release history |
| Path of Building (PoB) community data repo | Static game data (tree nodes, mods, skill gems, item bases) in Lua tables | Download raw files from GitHub (`raw.githubusercontent.com/.../dev/src/Modules/Data.lua`) | GitHub raw limit (~60 req/hr unauthenticated); repo updated each patch | Reference baseline for mods, nodes, and base items with MIT license |

## Detailed per-source notes

### Official Path of Exile Developer/API docs
- **Primary URL:** https://www.pathofexile.com/developer/docs
- **Data domains:** Account profiles, filters, leagues, ladder/pvp metadata, item filters, and the rate-limit | error contract that governs all `api.pathofexile.com` surfaces.
- **Profitability relevance:** Authoritative contract for every upstream feed; ensures bronze ingestion obeys OAuth/user-agent/rate-limit guardrails before touching gold data.
- **Access pattern:** REST calls (GET/POST) at `https://api.pathofexile.com`; private scopes require OAuth 2.1; every app must set `User-Agent: OAuth {clientId}/{version} (contact: {contact})`.
- **Auth requirements:** OAuth 2.1 for sensitive endpoints; public metadata can be read with app credentials only. The docs mandate per-app registration via `oauth@grindinggear.com`.
- **Expected cadence/refresh:** Data delivered in real time but may be cached; docs note headers can change without notice, so ingestors must parse `X-Rate-Limit` values on every response.
- **Rate-limit guidance:** Headers describe `X-Rate-Limit-Policy`, `X-Rate-Limit-Rules` (e.g., `client`), and `X-Rate-Limit-Client: 10:5:10`, plus `Retry-After` when returning 429. Invalid request bursts trigger automatic restrictions.
- **License/TOS constraints:** Terms of Use clause 7 (scraping/extraction prohibited without prior written approval) and clause 6/7 require licensed, non-commercial usage of data; violation can terminate access and trigger indemnity.
- **Reliability/operational risk:** Hosted by GGG; uptime generally high but subject to league launches. Invalid requests (4xx) count toward abuse thresholds, so bronze ingestion needs sane validation prior to submission.
- **Bronze ingestion fit + recommended raw schema topics:** Use this doc as grounding metadata (leagues, ladder rules, trade categories) and as a compliance checklist; raw schema fields include `league`, `realm`, `rule`, `ladder_entries`, `trade_category`.
- **Evidence links/commands used:**
  - `curl -s https://www.pathofexile.com/developer/docs` (Rate-limit, OAuth expectations).
  - `curl -s https://www.pathofexile.com/legal/terms-of-use-and-privacy-policy` (clause 7 prohibits scraping).

### PoE trade data (`/api/trade/data/*`)
- **Primary URL:** Example `https://www.pathofexile.com/api/trade/data/items` (basis for all trade metadata feeds).
- **Data domains:** League-specific bucket lists (Accessories, Maps, etc.), listing templates for classification, link/socket limits, base types, fragments, and their localized IDs.
- **Profitability relevance:** Provides exhaustive lookup tables required before calling the actual trade search API (e.g., to translate `type`/`id` in `trade/search` responses to meaningful categories).
- **Access pattern:** Simple `GET` returning JSON with `result` array; no body required beyond optional `realm`. The response enumerates each `entries` list for the requested trade domain.
- **Auth requirements:** Does not require OAuth but inherits the global user-agent/rate-limit expectations from the official docs.
- **Expected cadence/refresh:** Updated when trade infrastructure syncs with league data; can change per patch but is nearly constant within a league (static lists with periodic adjustments from GGG).
- **Rate-limit guidance:** Same `X-Rate-Limit` headers described in the developer docs; stash-specific endpoints should be paced at <=1 rps, other trade data <=4 rps.
- **License/TOS constraints:** Covered by the same Terms of Use cited above; extraction only through authorized API.
- **Reliability/operational risk:** Official but throttled; invalid HTTP parameters (wrong `type` etc.) count as invalid requests. The feed is high priority for bronze ingestion because it unlocks valid search payload construction.
- **Bronze ingestion fit + recommended raw schema topics:** Capture feeds such as `trade_category`, `item_type`, `variation_id`, `listing_class`; store as reference tables to normalize downstream crawl data (IDs, icons, sockets).
- **Evidence links/commands used:**
  - `curl -s https://www.pathofexile.com/api/trade/data/items` (raw JSON list of trade categories).
  - `curl -s https://www.pathofexile.com/developer/docs` (rate-limit contract reuse).

### poe.ninja
- **Primary URL:** `https://poe.ninja/api/data/...` and its redirected path (e.g., `https://poe.ninja/poe1/api/economy/stash/current/currency/overview?league=Standard&type=Currency`).
- **Data domains:** Chaos/exalted equivalents, `pay`/`receive` snapshots, sparkline data, `listing_count`, and `detailsId` per currency/type; other endpoints cover uniques, maps, oils, fossils, etc.
- **Profitability relevance:** Valuable for generating price signals and measuring listing density that feeds profitability heuristics (especially for bronze-tier valuations).
- **Access pattern:** REST GET with required `league` and `type` query parameters; returns `lines` array with `pay`, `receive`, and sparkline fields; also exposes `sample_time_utc` per record for freshness checks.
- **Auth requirements:** Public; no credentials necessary. User agents and polite timing are still important to avoid Cloudflare blocking.
- **Expected cadence/refresh:** Each record exposes `sample_time_utc` (e.g., `2026-02-24T12:23:25.0630522Z`) and the site advertises rapid updates after stash refreshes; assume high cadence (seconds to minutes) but treat as best-effort.
- **Rate-limit guidance:** Unpublished; endpoints redirect and serve data via Cloudflare. No headers indicate formal limits, so throttle to ~1 rps to avoid IP bans (observed `curl -i` shows 301/302 redirects but no `Retry-After`).
- **License/TOS constraints:** Site stresses it is unaffiliated with GGG; reuse should respect their advert/Discord/FAQ pages. No formal redistribution license is published, so treat data as proprietary and honor their privacy/FAQ guidance before sharing.
- **Reliability/operational risk:** Single-maintainer service with no SLA; endpoints or URL patterns can change at any time. Cloudflare front also introduces additional latency/resets.
- **Bronze ingestion fit + recommended raw schema topics:** Snapshot valuations (fields like `detailsId`, `chaosEquivalent`, `listing_count`, `pay.value`, `receive.value`, `sparkline.data`, `sample_time_utc`) aggregated per league and type provide must-have insights for early heuristic iterations.
- **Evidence links/commands used:**
  - `curl -i https://poe.ninja` (homepage metadata including "not affiliated with GGG").
  - `curl -s 'https://poe.ninja/poe1/api/economy/stash/current/currency/overview?league=Standard&type=Currency'` (currency valuation JSON with `sample_time_utc`).

### poedb.tw
- **Primary URL:** https://poedb.tw (landing) and https://poedb.tw/us/General_disclaimer; JSON endpoints such as `https://poedb.tw/us/json.php/Hideouts/Hideouts` are hinted at by community code but not formally documented.
- **Data domains:** Wide array of community-curated information (mods, crafting bench options, hideout assets, unique/rarity data) assembled into a browsable wiki.
- **Profitability relevance:** Useful for enriching mod descriptions, crafting constraints, and hideout metadata that is otherwise absent from official APIs.
- **Access pattern:** Historically available through `json.php/<table>` downloads; e.g., the `parse-poedb-hideout-api` repo points to `https://poedb.tw/us/json.php/Hideouts/Hideouts`. Attempted `curl -i https://poedb.tw/us/json.php/Mods/Gen?cn=Bow` returned 404 during this research, so plan for brittle access.
- **Auth requirements:** None documented.
- **Expected cadence/refresh:** Community-updated alongside the wiki; major updates happen per league, but specific `json.php` exports may lag or go offline since they are not part of the main UI.
- **Rate-limit guidance:** Unknown; no headers or docs disclose limits. The fact that many endpoints return 404 suggests tooling may rely on internal exports rather than formal APIs.
- **License/TOS constraints:** General disclaimer cites GGG IP rights and notes the reused Fandom/PoE Wiki content is under CC BY-NC-SA 3.0, so any reuse must comply with that license (non-commercial, attribution, share-alike).
- **Reliability/operational risk:** Community-run with frequent downtime; JSON exports can disappear (404) or change paths without notice; use only for enrichment, not core ingestion.
- **Bronze ingestion fit + recommended raw schema topics:** Snapshot mod definitions (`mods` table), crafting bench options, and hideout templates can join trade data for context; schema fields include `mod_id`, `mod_description`, `craft_bench_name`, `hideout_name`, and associated locale keys.
- **Evidence links/commands used:**
  - `curl -s https://poedb.tw/us/General_disclaimer` (license references CC BY-NC-SA and GGG IP).
  - `curl -s https://raw.githubusercontent.com/explooosion/parse-poedb-hideout-api/master/README.md` (shows `json.php/Hideouts/Hideouts` endpoint).
  - `curl -i 'https://poedb.tw/us/json.php/Mods/Gen?cn=Bow'` (returned 404, demonstrating instability).

### Path of Exile Wiki Data Query API (Fandom)
- **Primary URL:** https://pathofexile.fandom.com/wiki/Path_of_Exile_Wiki:Data_query_API
- **Data domains:** Cargo tables for items, mods, skills, versions, bestiary recipes, and more, all queryable through MediaWiki cargo queries.
- **Profitability relevance:** Authoritative descriptions of modifiers, release timelines, and template data that help translate raw trade IDs into readable traits.
- **Access pattern:** `GET https://pathofexile.fandom.com/api.php?action=cargoquery&tables=items&fields=name&limit=5...`; queries support `where`, `group_by`, `offset`, and `format=auto` for JSON output.
- **Auth requirements:** None for read-only queries, although editing requires signing in.
- **Expected cadence/refresh:** Updated as the community maintains the wiki; modifications can be frequent around patch notes and league launches.
- **Rate-limit guidance:** MediaWiki enforces throttles; use small `limit` (e.g., 5-500) and respect the `maxlag` parameter to avoid slowing the shared wiki. Chunk queries with `offset` and extend `limit` cautiously.
- **License/TOS constraints:** Content is licensed CC BY-NC-SA (per page footer) so any redistributions must credit the wiki, stay non-commercial, and share alike.
- **Reliability/operational risk:** Hosted by Fandom; general web reliability is good but subject to community edits and rate-limiting. Heavy queries risk hitting `maxlag` or per-IP throttle.
- **Bronze ingestion fit + recommended raw schema topics:** Use cargo query results for `items`, `mods`, `skill_levels`, `version` history as a canonical metadata layer for heuristics and to label trade data.
- **Evidence links/commands used:**
  - `webfetch` on https://pathofexile.fandom.com/wiki/Path_of_Exile_Wiki:Data_query_API (cargo query instructions, sample responses, CC BY-NC-SA footnote).

### Path of Building Community data repo
- **Primary URL:** https://github.com/PathOfBuildingCommunity/PathOfBuilding with raw data served via `https://raw.githubusercontent.com/PathOfBuildingCommunity/PathOfBuilding/dev/src/Modules/Data.lua`.
- **Data domains:** Static game schema (node/talent tree, mod definitions, item manifests, gem data) encoded in Lua tables that Path of Building ingests to power its calculator.
- **Profitability relevance:** Provides curated modifiers and base item sets, which can be cross-referenced to ensure bronze ingestion interprets trade IDs consistently with community tooling.
- **Access pattern:** Download raw Lua files from GitHub (e.g., `curl https://raw.githubusercontent.com/.../Modules/Data.lua`); repo publishes MIT license and is updated around each PoE patch.
- **Auth requirements:** None; GitHub raw downloads subject to general API rate limits (60 requests/hour unauthenticated).
- **Expected cadence/refresh:** Repo is actively maintained; latest commit touching `src/Modules/Data.lua` was `2026-01-28T14:09:09Z`, showing patch follow-through.
- **Rate-limit guidance:** GitHub raw content is rate-limited (60 requests per hour without auth, higher with token). Cache clones locally to avoid hitting the cap.
- **License/TOS constraints:** MIT license (README) so data can be reused commercially with attribution to the author.
- **Reliability/operational risk:** Third-party repo but on GitHub, so availability is good; however, updates may lag official patches slightly and Lua format requires parsing pipeline.
- **Bronze ingestion fit + recommended raw schema topics:** Use `data.node`, `data.mods`, `data.itemBases` as canonical definitions to enrich trade data; storing `mod_id`, `weight`, `stat`, and `value_range` fields aids consistent valuations.
- **Evidence links/commands used:**
  - `curl -s https://raw.githubusercontent.com/PathOfBuildingCommunity/PathOfBuilding/master/README.md` (MIT license).
  - `curl -I https://raw.githubusercontent.com/PathOfBuildingCommunity/PathOfBuilding/dev/src/Modules/Data.lua` (shows the file exists).
  - `curl -s 'https://api.github.com/repos/PathOfBuildingCommunity/PathOfBuilding/commits?path=src/Modules/Data.lua&per_page=1'` (latest commit info).

## Shortlist recommendation
- **v2 core sources (must-have):**
  1. PoE trade data API - required to decode every listing category and validate search payloads without failing the official rate limits.
  2. poe.ninja valuations - provides current chaos/exalted equivalents and listing-count signals that bootstrap profitability heuristics for bronze tiers.
- **v2 optional enrichments:**
  1. Path of Building community data - use Lua tables for deep mod/item metadata that complements the trade and valuation layers.
  2. Path of Exile Wiki cargo API - backfill descriptive metadata (versions, skill trees, item tags) that are cumbersome to source via trade data alone.
  3. PoEDB (optional) - enrich mod/craft descriptions and hideout itineraries when the JSON exports are available, but treat as fragile.

## Legal & compliance notes (scraping vs API use)
- Grind Gear Games' Terms of Use clause 7 expressly forbids unauthorized data gathering, framing, or scraping of game data and mandates prior written approval for any deviation from the documented APIs.
- The developer docs reiterate that applications must obey the OAuth/user-agent contract, parse `X-Rate-Limit` headers, and avoid invalid (4xx) bursts to maintain access.
- Always prefer the documented APIs above HTML scraping; where community sites (poe.ninja, PoEDB, Fandom, PoB) are used, honor their stated licenses (CC BY-NC-SA or site disclaimers) and treat them as supplemental enrichment layers, not primary ingestion feeds.
