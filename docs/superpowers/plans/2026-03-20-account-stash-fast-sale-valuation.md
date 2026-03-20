# Account Stash Fast-Sale Valuation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify single-item price checks and scan-triggered account-stash valuation behind one backend pricing contract that returns fast-sale price, confidence, and error-band fields, while publishing stash results atomically and preserving per-item valuation history.

**Architecture:** Reuse the existing `predict_one` serving path as the canonical single-item estimator, wrap it in an account-stash valuation service that computes stable item fingerprints, and persist full scan-scoped stash snapshots plus valuation rows in ClickHouse. Trigger stash valuation from the private account-stash flow rather than the public strategy scanner, publish only after a full successful run, and expose scan freshness/progress plus append-only item history through backend APIs.

**Tech Stack:** Python 3.11, ClickHouse SQL migrations, existing `poe_trade.api`/`poe_trade.services` modules, pytest.

---

## File Structure Map

- Create: `schema/migrations/0051_account_stash_valuation_runs_v1.sql` - additive tables/views for scan runs, scanned stash items, valuation rows, and published-snapshot pointer data.
- Create: `poe_trade/stash_valuation.py` - shared stash valuation contract, item fingerprinting, run persistence helpers, and scan orchestration helpers.
- Modify: `poe_trade/api/stash.py` - return published valuation snapshot metadata, enrich stash items with `pricedAt`/band fields, expose scan freshness, and add item-history payload helper.
- Modify: `poe_trade/api/app.py` - add HTTP routes for scan-triggered stash valuation status/history endpoints.
- Modify: `poe_trade/services/account_stash_harvester.py` - add a scan-mode entry point that harvests the latest private stash snapshot and then runs valuation atomically.
- Modify: `poe_trade/ingestion/account_stash_harvester.py` - stop pretending listed price is the canonical estimate; keep raw stash facts required for later valuation and persist deterministic fingerprints if needed.
- Test: `tests/unit/test_stash_valuation.py` - shared valuation contract, fingerprinting, run publish semantics, and history payload tests.
- Test: `tests/unit/test_api_stash.py` - API payload shape, published-snapshot-only behavior, and status freshness fields.
- Test: `tests/unit/test_account_stash_harvester.py` - ensure raw stash ingestion still writes source facts, persists stable identity inputs, and does not claim authoritative estimated prices.
- Test: `tests/unit/test_account_stash_service.py` - service wiring for scan-triggered account-stash valuation.
- Modify: `README.md` - document scan-triggered stash valuation behavior and freshness/history endpoints.

### Task 1: Add ClickHouse Tables For Valuation Runs, Published Snapshots, And History

**Files:**
- Create: `schema/migrations/0051_account_stash_valuation_runs_v1.sql`
- Test: `tests/unit/test_migrations.py`

- [ ] **Step 1: Write the failing migration test**

```python
def test_migration_0051_account_stash_valuation_runs_is_listed() -> None:
    assert any(path.name == "0051_account_stash_valuation_runs_v1.sql" for path in migration_files)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_migrations.py -k 0051 -v`
Expected: FAIL because migration `0051_account_stash_valuation_runs_v1.sql` does not exist yet.

- [ ] **Step 3: Write the additive migration**

```sql
CREATE TABLE IF NOT EXISTS poe_trade.account_stash_valuation_runs (
    scan_id String,
    account_name String,
    league String,
    realm String,
    status LowCardinality(String),
    started_at DateTime64(3, 'UTC'),
    completed_at Nullable(DateTime64(3, 'UTC')),
    failed_at Nullable(DateTime64(3, 'UTC')),
    tabs_total UInt32,
    tabs_processed UInt32,
    items_total UInt32,
    items_processed UInt32,
    error_message String,
    published_at Nullable(DateTime64(3, 'UTC'))
) ENGINE = ReplacingMergeTree(started_at)
PARTITION BY (league, toYYYYMMDD(started_at))
ORDER BY (account_name, realm, league, scan_id);

CREATE TABLE IF NOT EXISTS poe_trade.account_stash_scan_items (
    scan_id String,
    account_name String,
    league String,
    realm String,
    tab_id String,
    tab_name String,
    tab_type String,
    item_fingerprint String,
    item_id Nullable(String),
    item_name String,
    item_class String,
    rarity LowCardinality(String),
    x UInt16,
    y UInt16,
    w UInt16,
    h UInt16,
    listed_price Nullable(Float64),
    currency LowCardinality(String),
    icon_url String,
    source_observed_at DateTime64(3, 'UTC'),
    payload_json String
) ENGINE = MergeTree()
PARTITION BY (league, toYYYYMMDD(source_observed_at))
ORDER BY (account_name, realm, league, scan_id, tab_id, item_fingerprint);

CREATE TABLE IF NOT EXISTS poe_trade.account_stash_item_valuations (
    scan_id String,
    account_name String,
    league String,
    realm String,
    tab_id String,
    item_fingerprint String,
    item_id Nullable(String),
    item_name String,
    item_class String,
    rarity LowCardinality(String),
    listed_price Nullable(Float64),
    predicted_price Float64,
    confidence Float64,
    price_p10 Nullable(Float64),
    price_p90 Nullable(Float64),
    comparable_count UInt32,
    fallback_reason String,
    priced_at DateTime64(3, 'UTC'),
    payload_json String
) ENGINE = MergeTree()
PARTITION BY (league, toYYYYMMDD(priced_at))
ORDER BY (account_name, realm, league, item_fingerprint, priced_at, scan_id);

CREATE TABLE IF NOT EXISTS poe_trade.account_stash_active_scans (
    account_name String,
    league String,
    realm String,
    scan_id String,
    published_at DateTime64(3, 'UTC')
) ENGINE = ReplacingMergeTree(published_at)
PARTITION BY league
ORDER BY (account_name, realm, league);
```

- [ ] **Step 4: Grant reader/writer access in the same migration**

```sql
GRANT SELECT, INSERT ON poe_trade.account_stash_valuation_runs TO poe_api_reader;
GRANT SELECT, INSERT ON poe_trade.account_stash_scan_items TO poe_api_reader;
GRANT SELECT, INSERT ON poe_trade.account_stash_item_valuations TO poe_api_reader;
GRANT SELECT, INSERT ON poe_trade.account_stash_active_scans TO poe_api_reader;
GRANT INSERT ON poe_trade.account_stash_valuation_runs TO poe_ingest_writer;
GRANT INSERT ON poe_trade.account_stash_scan_items TO poe_ingest_writer;
GRANT INSERT ON poe_trade.account_stash_item_valuations TO poe_ingest_writer;
GRANT INSERT ON poe_trade.account_stash_active_scans TO poe_ingest_writer;
```

- [ ] **Step 5: Run tests to verify the migration is wired in**

Run: `.venv/bin/pytest tests/unit/test_migrations.py -k "0051 or account_stash" -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add schema/migrations/0051_account_stash_valuation_runs_v1.sql tests/unit/test_migrations.py
git commit -m "feat: add stash valuation run storage"
```

### Task 2: Build A Shared Stash Valuation Contract And Stable Item Fingerprinting

**Files:**
- Create: `poe_trade/stash_valuation.py`
- Test: `tests/unit/test_stash_valuation.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_fingerprint_prefers_item_id_when_present() -> None:
    item = {"id": "abc", "name": "Chaos Orb", "x": 0, "y": 0}
    assert fingerprint_item(item, account_name="qa", tab_id="t1") == "item:abc"

def test_fingerprint_falls_back_to_deterministic_content_hash() -> None:
    item = {"name": "Hubris Circlet", "typeLine": "Hubris Circlet", "x": 1, "y": 2}
    assert fingerprint_item(item, account_name="qa", tab_id="t2").startswith("fp:")

def test_stash_prediction_contract_keeps_price_confidence_and_band_fields() -> None:
    result = normalize_stash_prediction({"predictedValue": 10.0, "confidence": 82.0, "interval": {"p10": 8.0, "p90": 14.0}})
    assert result.price_p10 == 8.0
    assert result.price_p90 == 14.0
    assert result.confidence == 82.0

def test_serialize_stash_item_to_predict_one_clipboard_contains_name_and_mod_lines() -> None:
    item = {"name": "Grim Bane", "typeLine": "Hubris Circlet", "explicitMods": ["+93 to maximum Life"]}
    clipboard = serialize_stash_item_to_clipboard(item)
    assert "Grim Bane" in clipboard
    assert "Hubris Circlet" in clipboard
    assert "+93 to maximum Life" in clipboard
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_stash_valuation.py -v`
Expected: FAIL because `poe_trade.stash_valuation` does not exist.

- [ ] **Step 3: Implement the valuation dataclass and fingerprint helpers**

```python
@dataclass(frozen=True)
class StashValuationResult:
    predicted_price: float
    currency: str
    confidence: float
    price_p10: float | None
    price_p90: float | None
    comparable_count: int
    fallback_reason: str
    priced_at: str

def fingerprint_item(item: Mapping[str, Any], *, account_name: str, tab_id: str) -> str:
    item_id = str(item.get("id") or "").strip()
    if item_id:
        return f"item:{item_id}"
    stable_payload = {
        "account_name": account_name,
        "tab_id": tab_id,
        "name": str(item.get("name") or item.get("typeLine") or ""),
        "rarity": item.get("frameType"),
        "x": int(item.get("x") or 0),
        "y": int(item.get("y") or 0),
        "w": int(item.get("w") or 1),
        "h": int(item.get("h") or 1),
    }
    return "fp:" + sha256(json.dumps(stable_payload, sort_keys=True).encode("utf-8")).hexdigest()

def serialize_stash_item_to_clipboard(item: Mapping[str, Any]) -> str:
    lines = [
        f"Rarity: {_rarity_label(item.get('frameType'))}",
        str(item.get("name") or "").strip(),
        str(item.get("typeLine") or item.get("baseType") or item.get("name") or "Unknown"),
        "--------",
    ]
    for section in ("implicitMods", "explicitMods", "craftedMods", "enchantMods", "fracturedMods"):
        values = item.get(section)
        if isinstance(values, list):
            lines.extend(str(value) for value in values if str(value).strip())
    return "\n".join(line for line in lines if line)
```

- [ ] **Step 4: Add a normalizer for `fetch_predict_one()` payloads**

```python
def normalize_stash_prediction(payload: Mapping[str, Any], *, comparable_count: int = 0) -> StashValuationResult:
    interval = payload.get("interval") if isinstance(payload.get("interval"), Mapping) else {}
    return StashValuationResult(
        predicted_price=float(payload.get("predictedValue") or payload.get("price_p50") or 0.0),
        currency=str(payload.get("currency") or "chaos"),
        confidence=float(payload.get("confidence") or payload.get("confidence_percent") or 0.0),
        price_p10=_opt_float(interval.get("p10") or payload.get("price_p10")),
        price_p90=_opt_float(interval.get("p90") or payload.get("price_p90")),
        comparable_count=comparable_count,
        fallback_reason=str(payload.get("fallbackReason") or payload.get("fallback_reason") or ""),
        priced_at=datetime.now(timezone.utc).isoformat(),
    )
```

- [ ] **Step 5: Run tests to verify pass**

Run: `.venv/bin/pytest tests/unit/test_stash_valuation.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add poe_trade/stash_valuation.py tests/unit/test_stash_valuation.py
git commit -m "feat: add stash valuation contract"
```

### Task 3: Wrap `predict_one` So Price Check And Stash Scan Share The Same Estimator

**Files:**
- Modify: `poe_trade/stash_valuation.py`
- Modify: `poe_trade/api/ops.py:641`
- Test: `tests/unit/test_stash_valuation.py`

- [ ] **Step 1: Write the failing shared-estimator test**

```python
def test_estimate_item_uses_fetch_predict_one_contract(monkeypatch) -> None:
    monkeypatch.setattr(
        "poe_trade.stash_valuation.fetch_predict_one",
        lambda *_args, **_kwargs: {"predictedValue": 12.0, "confidence": 77.0, "interval": {"p10": 9.0, "p90": 16.0}},
    )
    result = estimate_item(client=object(), league="Mirage", item_text="Rarity: Rare")
    assert result.predicted_price == 12.0
    assert result.price_p90 == 16.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_stash_valuation.py -k estimate_item -v`
Expected: FAIL because `estimate_item()` does not exist yet.

- [ ] **Step 3: Implement the shared estimator wrapper**

```python
def estimate_item(client: ClickHouseClient, *, league: str, item_text: str) -> StashValuationResult:
    payload = fetch_predict_one(
        client,
        league=league,
        request_payload={
            "input_format": "poe-clipboard",
            "payload": item_text,
            "output_mode": "json",
        },
    )
    comparable_count = len(payload.get("comparables") or []) if isinstance(payload.get("comparables"), list) else 0
    return normalize_stash_prediction(payload, comparable_count=comparable_count)

def estimate_stash_item(client: ClickHouseClient, *, league: str, item: Mapping[str, Any]) -> StashValuationResult:
    return estimate_item(client, league=league, item_text=serialize_stash_item_to_clipboard(item))
```

- [ ] **Step 4: Make `price_check_payload()` use the same normalization path for band/confidence fields**

```python
valuation = estimate_item(client, league=league, item_text=item_text)
return {
    "predictedValue": valuation.predicted_price,
    "confidence": valuation.confidence,
    "interval": {"p10": valuation.price_p10, "p90": valuation.price_p90},
    ...
}
```

- [ ] **Step 5: Run tests to verify pass**

Run: `.venv/bin/pytest tests/unit/test_stash_valuation.py tests/unit/test_api_stash.py -k "estimate_item or estimate_stash_item or price_check" -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add poe_trade/stash_valuation.py poe_trade/api/ops.py tests/unit/test_stash_valuation.py tests/unit/test_api_stash.py
git commit -m "refactor: share single item pricing contract"
```

### Task 4: Implement Atomic Account-Stash Scan Runs And Publication Rules

**Files:**
- Modify: `poe_trade/stash_valuation.py`
- Modify: `poe_trade/services/account_stash_harvester.py`
- Modify: `poe_trade/ingestion/account_stash_harvester.py`
- Test: `tests/unit/test_stash_valuation.py`
- Test: `tests/unit/test_account_stash_service.py`

- [ ] **Step 1: Write the failing run-lifecycle tests**

```python
def test_publish_keeps_old_scan_when_new_run_is_running() -> None:
    state = FakeRunStore(active_scan_id="old-scan")
    begin_scan(state, scan_id="new-scan")
    assert state.active_scan_id == "old-scan"

def test_publish_switches_active_scan_only_after_success() -> None:
    state = FakeRunStore(active_scan_id="old-scan")
    complete_scan(state, scan_id="new-scan", success=True)
    assert state.active_scan_id == "new-scan"

def test_failed_scan_does_not_replace_last_successful_snapshot() -> None:
    state = FakeRunStore(active_scan_id="old-scan")
    complete_scan(state, scan_id="new-scan", success=False)
    assert state.active_scan_id == "old-scan"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_stash_valuation.py -k "publish or scan" -v`
Expected: FAIL because run lifecycle helpers are missing.

- [ ] **Step 3: Implement run persistence helpers and scanned-item snapshot writes**

```python
def start_scan(...):
    insert_run(status="running", tabs_processed=0, items_processed=0)

def stage_scan_item(...):
    insert_scan_item(
        scan_id=scan_id,
        item_fingerprint=fingerprint_item(item, account_name=account_name, tab_id=tab_id),
        source_observed_at=observed_at,
        payload_json=json.dumps(item),
        ...,
    )

def record_item_valuation(...):
    insert_run_scoped_row(scan_id=scan_id, item_fingerprint=fingerprint, predicted_price=result.predicted_price, ...)

def complete_scan(..., success: bool):
    if success:
        upsert_active_scan(scan_id=scan_id, published_at=now_utc())
        update_run(status="completed", completed_at=now_utc(), published_at=now_utc())
    else:
        update_run(status="failed", failed_at=now_utc(), error_message=error_message)
```

- [ ] **Step 4: Trigger valuation from the private account-stash flow, not the public scanner**

```python
parser.add_argument("--scan", action="store_true", help="Harvest latest stash snapshot and price the full account stash")

harvester.run(..., once=True)
if args.scan and not args.dry_run:
    run_account_stash_valuation_scan(
        clickhouse,
        league=args.league or cfg.account_stash_league,
        realm=args.realm or cfg.account_stash_realm,
        account_name=account_name,
    )
```

- [ ] **Step 5: Ensure the scan loop reports progress counters and never publishes partial rows**

Run: `.venv/bin/pytest tests/unit/test_stash_valuation.py tests/unit/test_account_stash_service.py -k "progress or publish or scan" -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add poe_trade/stash_valuation.py poe_trade/services/account_stash_harvester.py poe_trade/ingestion/account_stash_harvester.py tests/unit/test_stash_valuation.py tests/unit/test_account_stash_service.py
git commit -m "feat: add atomic stash valuation scans"
```

### Task 5: Expose Published Snapshot Freshness And Item History In Stash APIs

**Files:**
- Modify: `poe_trade/api/stash.py`
- Modify: `poe_trade/api/app.py`
- Test: `tests/unit/test_api_stash.py`

- [ ] **Step 1: Write the failing API tests**

```python
def test_stash_status_includes_last_successful_full_scan_and_active_progress() -> None:
    payload = stash_status_payload(...)
    assert payload["valuation"]["lastSuccessfulFullScanAt"] == "2026-03-20T10:00:00Z"
    assert payload["valuation"]["status"] == "running"
    assert payload["tabCount"] == 2
    assert payload["itemCount"] == 5

def test_fetch_stash_tabs_reads_only_published_snapshot_rows() -> None:
    result = fetch_stash_tabs(...)
    assert result["valuationScanId"] == "published-scan"
    assert result["stashTabs"][0]["items"][0]["itemFingerprint"] == "fp:abc"

def test_item_history_payload_returns_ordered_band_points() -> None:
    payload = stash_item_history_payload(...)
    assert payload["history"][0]["priceP10"] <= payload["history"][0]["predictedPrice"] <= payload["history"][0]["priceP90"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_api_stash.py -k "valuation or history" -v`
Expected: FAIL because status/history payloads do not expose valuation metadata yet.

- [ ] **Step 3: Extend `stash_status_payload()` with valuation metadata**

```python
return {
    "status": ...,
    "connected": True,
    "tabCount": published_tab_count,
    "itemCount": published_item_count,
    "valuation": {
        "status": "running",
        "activeScanId": "scan-123",
        "lastSuccessfulScanId": "scan-122",
        "lastSuccessfulFullScanAt": "2026-03-20T10:00:00Z",
        "tabsProcessed": 3,
        "tabsTotal": 10,
        "itemsProcessed": 45,
        "itemsTotal": 300,
    },
    ...
}
```

- [ ] **Step 4: Make `fetch_stash_tabs()` read only from the last successfully published scan snapshot**

```python
SELECT item.tab_id, item.tab_name, item.tab_type, item.item_fingerprint, item.payload_json,
       value.scan_id, value.predicted_price, value.confidence, value.price_p10, value.price_p90, value.priced_at
FROM poe_trade.account_stash_active_scans AS active
INNER JOIN poe_trade.account_stash_scan_items AS item
    ON item.scan_id = active.scan_id
LEFT JOIN poe_trade.account_stash_item_valuations AS value
    ON value.scan_id = item.scan_id AND value.item_fingerprint = item.item_fingerprint
WHERE active.account_name = {account_name} AND active.league = {league} AND active.realm = {realm}
```

- [ ] **Step 4a: Return the server-generated history key in stash item payloads**

```python
history_key = item_fingerprint  # server-computed opaque key returned by the API
return {
    "id": history_key,
    "itemFingerprint": history_key,
    "estimatedPrice": predicted_price,
    "estimatedPriceConfidence": confidence,
    "priceP10": price_p10,
    "priceP90": price_p90,
    ...,
}
```

- [ ] **Step 5: Add an item-history API helper and route**

```python
def stash_item_history_payload(..., item_fingerprint: str):
    return {
        "itemFingerprint": fingerprint,
        "history": [
            {"scanId": row["scan_id"], "predictedPrice": row["predicted_price"], "confidence": row["confidence"], "priceP10": row["price_p10"], "priceP90": row["price_p90"], "pricedAt": row["priced_at"]}
            for row in ordered_rows
        ],
    }
```

```sql
SELECT value.scan_id, value.predicted_price, value.confidence, value.price_p10, value.price_p90, value.priced_at
FROM poe_trade.account_stash_item_valuations AS value
INNER JOIN poe_trade.account_stash_valuation_runs AS run
    ON run.scan_id = value.scan_id
WHERE value.account_name = {account_name}
  AND value.league = {league}
  AND value.realm = {realm}
  AND value.item_fingerprint = {item_fingerprint}
  AND run.status = 'completed'
  AND run.published_at IS NOT NULL
ORDER BY value.priced_at ASC
```

- [ ] **Step 6: Run tests to verify pass**

Run: `.venv/bin/pytest tests/unit/test_api_stash.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add poe_trade/api/stash.py poe_trade/api/app.py tests/unit/test_api_stash.py
git commit -m "feat: expose stash valuation freshness and history"
```

### Task 6: Keep Raw Account Stash Ingestion Focused On Source Facts And Identity Inputs

**Files:**
- Modify: `poe_trade/ingestion/account_stash_harvester.py`
- Test: `tests/unit/test_account_stash_harvester.py`

- [ ] **Step 1: Write the failing ingestion test**

```python
def test_harvest_does_not_claim_listed_price_as_authoritative_estimate() -> None:
    harvester.run(...)
    assert '"estimated_price": 10.0' not in clickhouse.queries[1]
    assert '"item_id": "i1"' in clickhouse.queries[1]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_account_stash_harvester.py -k authoritative -v`
Expected: FAIL because the harvester still copies listed price into `estimated_price`.

- [ ] **Step 3: Remove authoritative-estimate behavior from ingestion**

```python
flat_rows.append(
    {
        ...,
        "listed_price": listed[0] if listed else None,
        "estimated_price": 0.0,
        "estimated_price_confidence": 0,
        ...,
    }
)
```

- [ ] **Step 4: Run focused tests to verify pass**

Run: `.venv/bin/pytest tests/unit/test_account_stash_harvester.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add poe_trade/ingestion/account_stash_harvester.py tests/unit/test_account_stash_harvester.py
git commit -m "refactor: keep stash ingestion raw-only"
```

### Task 7: Document The New Backend Contract And Verify End-To-End Behavior

**Files:**
- Modify: `README.md`
- Test: `tests/unit/test_stash_valuation.py`
- Test: `tests/unit/test_api_stash.py`
- Test: `tests/unit/test_account_stash_harvester.py`
- Test: `tests/unit/test_account_stash_service.py`

- [ ] **Step 1: Write the failing backend contract test for scan freshness fields**

```python
def test_readme_mentions_published_snapshot_and_history_fields() -> None:
    text = Path("README.md").read_text()
    assert "last successful full scan" in text
    assert "p10/p90" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_stash_valuation.py -k contract -v`
Expected: FAIL because the backend contract documentation does not yet mention valuation freshness/history fields.

- [ ] **Step 3: Update backend docs**

```md
- `account_stash_harvester --once --scan` harvests the newest private stash snapshot and prices the full account stash with the same backend estimator as `price-check`
- stash APIs serve only the last successful full scan snapshot
- per-item valuation history includes predicted price, confidence, and p10/p90 band fields
```

- [ ] **Step 4: Run the focused verification suite**

Run: `.venv/bin/pytest tests/unit/test_stash_valuation.py tests/unit/test_api_stash.py tests/unit/test_account_stash_harvester.py tests/unit/test_account_stash_service.py -v`
Expected: PASS.

- [ ] **Step 5: Run migration status verification**

Run: `.venv/bin/poe-migrate --status --dry-run`
Expected: output includes `0051_account_stash_valuation_runs_v1.sql` as pending or applied with no parsing errors.

- [ ] **Step 6: Commit**

```bash
git add README.md tests/unit/test_stash_valuation.py tests/unit/test_api_stash.py tests/unit/test_account_stash_harvester.py tests/unit/test_account_stash_service.py
git commit -m "docs: document stash valuation backend contract"
```
