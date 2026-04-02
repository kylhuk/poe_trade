

## Plan: Migrate All API Calls to New Spec Endpoints

### What Changed in the Spec

Three endpoints are now **deprecated** and must be removed:
1. `POST /api/v1/stash/scan` → use `POST /api/v1/stash/scan/start` (already exists)
2. `GET /api/v1/stash/tabs` → use `GET /api/v1/stash/scan/result` (already exists)
3. `POST /api/v1/stash/scan/valuations` (with body) → use `POST /api/v1/stash/scan/valuations/start` (no body)

**Critical change**: The new scan endpoints (`/scan/result`, `/scan/start`, `/scan/status`, `/valuations/*`) take **no query parameters** — no `league`, no `realm`, no `tabIndex`. Only `/stash/status` and `/stash/items/{fp}/history` still accept `league`/`realm`.

### Changes

**1. `src/services/api.ts`** — Core API cleanup
- `getStashScanResult()`: Remove `league`, `realm`, `tabIndex` query params. No parameters at all.
- `startStashScan()`: Call only `/api/v1/stash/scan/start` with POST, no query params, no fallback to deprecated `/stash/scan`.
- `getStashScanStatus()`: Remove `league`/`realm` query params.
- `startStashValuationsNew()` → rename to `startStashValuations()`: Remove `league`/`realm` query params.
- `getStashValuationsResult()`: Remove `league`/`realm` query params.
- `getStashValuationsStatus()`: Remove `league`/`realm` query params.
- **Delete** old `getStashTabs()` method entirely.
- **Delete** old `startStashValuations(req)` method (the one with body/thresholds).
- `getStashStatus()`: Keep `league`/`realm` (still in spec).
- `getStashItemHistory()`: Keep `league`/`realm`/`limit` (still in spec).
- Remove `isMissingRouteError` helper (no more fallback logic).

**2. `src/types/api.ts`** — Interface cleanup
- Remove `getStashTabs` from `ApiService`.
- Remove old `startStashValuations(req)` from `ApiService`.
- Rename `startStashValuationsNew` → `startStashValuations`.
- Remove `StashScanValuationsRequest` type (no longer needed — start takes no body).
- Remove `tabIndex` param from `getStashScanResult` signature (API no longer accepts it).

**3. `src/services/stashCache.ts`**
- Replace `api.getStashTabs(tabIndex)` with `api.getStashScanResult()` in `loadAllStashItems`. Since the new endpoint returns all tabs at once (no tabIndex param), refactor to fetch once and extract items from all returned tabs.

**4. `src/components/tabs/StashViewerTab.tsx`**
- Update `loadTab` to call `api.getStashScanResult()` without tabIndex.
- Update valuation trigger to call `api.startStashValuations()` (renamed from `startStashValuationsNew`).
- Since there's no `tabIndex` server-side filtering, select the correct tab client-side from the full response.

**5. `src/components/tabs/EconomyTab.tsx`**
- Update `getStashScanResult` call (remove tabIndex if used).

**6. `src/components/tabs/StashViewerTab.test.tsx`**
- Update mocks: remove `getStashTabs`, rename `startStashValuations` references, update call expectations to match new signatures (no body, no tabIndex).

**7. `src/services/api.stash.test.ts`**
- Update test expectations to match new endpoint paths (no query params on scan endpoints).

