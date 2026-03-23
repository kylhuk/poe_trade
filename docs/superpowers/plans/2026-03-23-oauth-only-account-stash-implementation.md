# OAuth-Only Account Stash Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace all POESESSID-based private stash auth with OAuth-only login/token flow and bearer-auth account stash access, while keeping frontend session UX working through `https://api.poe.lama-lan.ch/api/v1/`.

**Architecture:** Backend owns OAuth transaction state, code exchange, token refresh, and stash bearer authentication. Frontend uses a thin callback relay at `https://poe.lama-lan.ch` and never stores PoE refresh tokens. Existing app-session cookie remains the browser contract, and stash APIs continue using backend session/account scope.

**Tech Stack:** Python 3.11, pytest, existing file-based auth state/session storage, React + TypeScript + Vitest, Supabase edge proxy, OpenAPI YAML.

---

## File Structure And Responsibilities

- `poe_trade/api/auth_session.py`
  - OAuth login transaction lifecycle, code exchange, token persistence, refresh lifecycle, session create/read/clear.
- `poe_trade/api/app.py`
  - HTTP contract for `/api/v1/auth/login`, `/api/v1/auth/callback`, `/api/v1/auth/session`, `/api/v1/auth/logout` and stash auth checks.
- `poe_trade/services/account_stash_harvester.py`
  - Service startup wiring: read token state, set bearer token, call harvester.
- `poe_trade/ingestion/account_stash_harvester.py`
  - Private stash retrieval endpoint behavior and request contract against PoE account stash API.
- `scripts/private_stash_scan_smoke.py`
  - Operator smoke script aligned with OAuth access-token flow.
- `frontend/src/services/auth.tsx`
  - Frontend auth context; remove POESESSID persistence and add OAuth login start/callback completion workflow.
- `frontend/src/components/UserMenu.tsx`
  - OAuth-only connect/logout controls; remove POESESSID input UI.
- `frontend/src/pages/AuthCallback.tsx`
  - Thin relay from `code/state` query params to backend callback endpoint.
- `frontend/src/services/api.ts`
  - Remove `x-poe-session` transport and keep backend-session forwarding only.
- `frontend/supabase/functions/api-proxy/index.ts`
  - Stop accepting/forwarding `x-poe-session` and `POESESSID` cookie injection.
- `frontend/apispec.yml`
  - OAuth-only auth route definitions; remove POESESSID bootstrap payloads.
- `README.md`
  - Remove POESESSID guidance, document OAuth-only private stash workflow.

## Task 1: Lock OAuth Transaction + Token Storage Contract

**Files:**
- Modify: `poe_trade/api/auth_session.py`
- Test: `tests/unit/test_auth_session.py`

- [ ] **Step 1: Write failing transaction lifecycle tests**

```python
def test_begin_login_persists_state_record_with_expiry(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    tx = begin_login(settings)
    rows = _load_json(_transactions_path(settings))
    row = rows[tx.state]
    assert row["state"] == tx.state
    assert row["code_verifier"]
    assert row["created_at"]
    assert row["expires_at"]
    assert row["used_at"] is None


def test_consume_login_state_is_one_time_use(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    tx = begin_login(settings)
    first = consume_login_state(settings, state=tx.state)
    assert first.code_verifier == tx.code_verifier
    with pytest.raises(OAuthExchangeError, match="state already used"):
        consume_login_state(settings, state=tx.state)


def test_consume_login_state_rejects_expired_or_unknown_state(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    with pytest.raises(OAuthExchangeError, match="invalid state"):
        consume_login_state(settings, state="missing")


def test_prune_login_transactions_removes_expired_and_used(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    tx = begin_login(settings)
    _ = consume_login_state(settings, state=tx.state)
    removed = prune_login_transactions(settings, now=_now() + timedelta(days=1))
    assert removed >= 1
```

- [ ] **Step 2: Run tests to confirm failure**

Run: `.venv/bin/pytest tests/unit/test_auth_session.py -k "consume_login_state or begin_login" -v`
Expected: FAIL due to missing keyed transaction store, consume semantics, and prune helper.

- [ ] **Step 3: Implement minimal transaction/token storage updates**

```python
@dataclass(frozen=True)
class ConsumedLoginState:
    state: str
    code_verifier: str


def consume_login_state(settings: Settings, *, state: str) -> ConsumedLoginState:
    rows = _load_json(_transactions_path(settings))
    payload = rows.get(state) if isinstance(rows, dict) else None
    if not isinstance(payload, dict):
        raise OAuthExchangeError("invalid state", code="invalid_state", status=400)
    if payload.get("used_at"):
        raise OAuthExchangeError(
            "state already used", code="state_already_used", status=400
        )
    # expiry checks, then set used_at and persist keyed by state


def prune_login_transactions(settings: Settings, *, now: datetime | None = None) -> int:
    ...
```

- [ ] **Step 4: Add OAuth credential-state helpers and tests**

```python
def load_oauth_credential_state(settings: Settings) -> dict[str, Any]:
    ...


def save_oauth_credential_state(
    settings: Settings,
    *,
    account_name: str,
    access_token: str,
    refresh_token: str,
    token_type: str,
    scope: str,
    expires_at: str,
    status: str,
) -> dict[str, Any]:
    ...
```

- [ ] **Step 5: Run tests to verify pass**

Run: `.venv/bin/pytest tests/unit/test_auth_session.py -v`
Expected: PASS for new transaction + token-state tests.

- [ ] **Step 6: Commit**

```bash
git add tests/unit/test_auth_session.py poe_trade/api/auth_session.py
git commit -m "feat: enforce one-time oauth state and token persistence contract"
```

## Task 2: Enable OAuth Auth Routes And Remove POESESSID Bootstrap

**Files:**
- Modify: `poe_trade/api/app.py`
- Modify: `poe_trade/api/auth_session.py`
- Test: `tests/unit/test_api_auth_oauth.py`
- Test: `tests/unit/test_api_auth.py`

- [ ] **Step 1: Write failing API contract tests for login/callback/session POST rejection**

```python
def test_auth_login_returns_authorize_url_json() -> None:
    response = app.handle(method="POST", raw_path="/api/v1/auth/login", ...)
    payload = json.loads(response.body.decode("utf-8"))
    assert "authorizeUrl" in payload


def test_auth_callback_exchanges_code_and_sets_session_cookie() -> None:
    body = json.dumps({"code": "code-123", "state": "state-123"}).encode("utf-8")
    response = app.handle(method="POST", raw_path="/api/v1/auth/callback", ...)
    assert response.status == 200
    assert "Set-Cookie" in response.headers


def test_auth_callback_maps_provider_error_payload() -> None:
    body = json.dumps({"error": "invalid_request", "error_description": "bad"}).encode("utf-8")
    with pytest.raises(ApiError) as exc:
        app.handle(method="POST", raw_path="/api/v1/auth/callback", ...)
    assert exc.value.code == "oauth_callback_failed"


def test_auth_callback_rejects_invalid_state_without_creating_session() -> None:
    body = json.dumps({"code": "code-123", "state": "wrong"}).encode("utf-8")
    with pytest.raises(ApiError) as exc:
        app.handle(method="POST", raw_path="/api/v1/auth/callback", ...)
    assert exc.value.code == "invalid_state"


def test_auth_callback_returns_missing_code_verifier_for_stale_state() -> None:
    body = json.dumps({"code": "code-123", "state": "state-123"}).encode("utf-8")
    with pytest.raises(ApiError) as exc:
        app.handle(method="POST", raw_path="/api/v1/auth/callback", ...)
    assert exc.value.code == "missing_code_verifier"


def test_auth_session_post_rejects_legacy_poe_session_payload() -> None:
    body = json.dumps({"poeSessionId": "legacy"}).encode("utf-8")
    with pytest.raises(ApiError, match="oauth-only"):
        app.handle(method="POST", raw_path="/api/v1/auth/session", ...)
```

- [ ] **Step 2: Run focused auth tests and confirm failure**

Run: `.venv/bin/pytest tests/unit/test_api_auth_oauth.py tests/unit/test_api_auth.py -k "auth_login or auth_callback or auth_session" -v`
Expected: FAIL because routes are disabled and session POST still bootstraps POESESSID.

- [ ] **Step 3: Implement route/method contract**

```python
self.router.add("/api/v1/auth/login", ("POST", "OPTIONS"), self._auth_login)
self.router.add("/api/v1/auth/callback", ("POST", "OPTIONS"), self._auth_callback)

def _auth_login(self, context: Mapping[str, object]) -> Response:
    tx = begin_login(self.settings)
    return json_response({"authorizeUrl": authorize_redirect(self.settings, tx)})
```

- [ ] **Step 4: Implement callback behavior and stable callback-error mapping**

```python
def _auth_callback(self, context: Mapping[str, object]) -> Response:
    body = _read_json_body(...)
    if body.get("error") == "access_denied":
        raise ApiError(status=401, code="oauth_access_denied", message="oauth access denied")
    if body.get("error"):
        raise ApiError(status=400, code="oauth_callback_failed", message="oauth callback failed")
    # consume_login_state must raise stable missing_code_verifier when verifier data is absent
    result = exchange_oauth_code(...)
    save_oauth_credential_state(...)
    session = create_session(...)
    return json_response({...}, headers={"Set-Cookie": _session_set_cookie(...)})
```

- [ ] **Step 5: Replace session POST bootstrap with explicit rejection**

```python
if method == "POST":
    raise ApiError(
        status=400,
        code="invalid_input",
        message="OAuth-only login; POESESSID bootstrap is not supported",
    )
```

- [ ] **Step 6: Run auth tests to verify pass**

Run: `.venv/bin/pytest tests/unit/test_api_auth_oauth.py tests/unit/test_api_auth.py -v`
Expected: PASS for OAuth-only auth contract behavior.

- [ ] **Step 7: Commit**

```bash
git add poe_trade/api/app.py poe_trade/api/auth_session.py tests/unit/test_api_auth_oauth.py tests/unit/test_api_auth.py
git commit -m "feat: enable oauth-only auth routes and reject legacy bootstrap"
```

## Task 3: Enforce Session Cookie And Session-Fixation Security Contract

**Files:**
- Modify: `poe_trade/api/app.py`
- Modify: `poe_trade/api/auth_session.py`
- Test: `tests/unit/test_api_auth.py`
- Test: `tests/unit/test_api_auth_oauth.py`

- [ ] **Step 1: Write failing auth security tests**

```python
def test_callback_sets_secure_http_only_cookie_flags() -> None:
    response = app.handle(method="POST", raw_path="/api/v1/auth/callback", ...)
    cookie = response.headers["Set-Cookie"]
    assert "HttpOnly" in cookie
    assert "SameSite=" in cookie
    assert "Path=/" in cookie


def test_callback_rotates_session_id_after_successful_login() -> None:
    before = get_session(settings, session_id=existing)
    response = app.handle(method="POST", raw_path="/api/v1/auth/callback", ...)
    after_cookie = response.headers["Set-Cookie"]
    assert extract_session_id(after_cookie) != existing


def test_logout_clears_session_cookie() -> None:
    response = app.handle(method="POST", raw_path="/api/v1/auth/logout", ...)
    assert "Set-Cookie" in response.headers
    assert "Max-Age=0" in response.headers["Set-Cookie"]


def test_terminal_refresh_failure_clears_session_cookie() -> None:
    # force token/session into terminal refresh failure path before request
    response = app.handle(method="GET", raw_path="/api/v1/auth/session", ...)
    assert "Set-Cookie" in response.headers
    assert "Max-Age=0" in response.headers["Set-Cookie"]
```

- [ ] **Step 2: Run focused auth tests to confirm failure**

Run: `.venv/bin/pytest tests/unit/test_api_auth.py tests/unit/test_api_auth_oauth.py -k "cookie or session_id or callback" -v`
Expected: FAIL until cookie flags and rotation semantics are enforced.

- [ ] **Step 3: Implement secure cookie/rotation behavior**

```python
session = create_session(self.settings, account_name=account_name)
cookie = _session_set_cookie(..., secure=self.settings.auth_cookie_secure)
# ensure helper emits HttpOnly, SameSite=Lax (or stricter), Path=/
# ensure logout and terminal refresh failure both emit clear-cookie headers
```

- [ ] **Step 4: Re-run security tests and pass**

Run: `.venv/bin/pytest tests/unit/test_api_auth.py tests/unit/test_api_auth_oauth.py -k "cookie or session_id or callback" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add poe_trade/api/app.py poe_trade/api/auth_session.py tests/unit/test_api_auth.py tests/unit/test_api_auth_oauth.py
git commit -m "fix: enforce oauth session cookie security and rotation"
```

## Task 4: Implement OAuth Refresh-On-401 Contract

**Files:**
- Modify: `poe_trade/api/auth_session.py`
- Modify: `poe_trade/services/account_stash_harvester.py`
- Test: `tests/unit/test_auth_session.py`
- Test: `tests/unit/test_account_stash_service.py`

- [ ] **Step 1: Write failing tests for refresh rotation and disconnected terminal state**

```python
def test_refresh_rotates_refresh_token_and_persists_atomically(tmp_path: Path) -> None:
    state = save_oauth_credential_state(...)
    refreshed = refresh_oauth_access_token(settings)
    assert refreshed["refresh_token"] != state["refresh_token"]


def test_refresh_failure_marks_disconnected(tmp_path: Path) -> None:
    save_oauth_credential_state(...)
    with pytest.raises(OAuthExchangeError):
        refresh_oauth_access_token(settings)
    state = load_oauth_credential_state(settings)
    assert state["status"] == "disconnected"


def test_refresh_allows_single_inflight_request_with_waiters(tmp_path: Path) -> None:
    # one caller refreshes, concurrent caller waits and reuses result
    result = run_two_refresh_callers(settings)
    assert result.owner_called_once is True
    assert result.waiter_received_token is True
```

- [ ] **Step 2: Run focused tests to confirm failure**

Run: `.venv/bin/pytest tests/unit/test_auth_session.py tests/unit/test_account_stash_service.py -k "refresh or credential_state" -v`
Expected: FAIL because refresh helpers, lock semantics, and OAuth token usage are missing.

- [ ] **Step 3: Implement refresh helper in auth session module**

```python
def refresh_oauth_access_token(settings: Settings) -> dict[str, Any]:
    state = load_oauth_credential_state(settings)
    # per-account lock: one in-flight refresh only
    # POST grant_type=refresh_token, replace access+refresh atomically
    # waiter timeout path uses owner result; terminal owner failure marks disconnected
```

- [ ] **Step 4: Wire service startup to OAuth token state instead of POESESSID state**

```python
oauth_state = load_oauth_credential_state(cfg)
token = str(oauth_state.get("access_token") or "").strip()
if not token:
    return 0
client.set_bearer_token(token)
```

- [ ] **Step 5: Re-run focused tests and pass**

Run: `.venv/bin/pytest tests/unit/test_auth_session.py tests/unit/test_account_stash_service.py -v`
Expected: PASS including refresh-state transitions.

- [ ] **Step 6: Commit**

```bash
git add poe_trade/api/auth_session.py poe_trade/services/account_stash_harvester.py tests/unit/test_auth_session.py tests/unit/test_account_stash_service.py
git commit -m "feat: add oauth token refresh lifecycle for stash services"
```

## Task 5: Migrate Private Stash Ingestion To Bearer Account API

**Files:**
- Modify: `poe_trade/ingestion/account_stash_harvester.py`
- Test: `tests/unit/test_account_stash_harvester.py`

- [ ] **Step 1: Write failing ingestion tests for endpoint shape and bearer headers**

```python
def test_private_scan_uses_account_api_stash_endpoints() -> None:
    client = StubClient(sequence=[
        {"stashes": [{"id": "t1", "name": "Trade", "type": "normal"}]},
        {"stash": {"id": "t1", "items": []}},
    ])
    harvester = build_harvester(client)
    harvester.run_private_scan(realm="pc", league="Mirage", price_item=lambda _i: BASE_PRICE)
    assert client.calls[0][1] == "stash/Mirage"
    assert client.calls[1][1] == "stash/Mirage/t1"


def test_private_scan_uses_console_realm_prefix_only_for_xbox_or_sony() -> None:
    assert stash_endpoint("pc", "Mirage") == "stash/Mirage"
    assert stash_endpoint("xbox", "Mirage") == "stash/xbox/Mirage"
    assert stash_endpoint("sony", "Mirage") == "stash/sony/Mirage"


def test_private_scan_does_not_send_cookie_headers() -> None:
    client = StubClient(sequence=[{"stashes": []}])
    harvester = build_harvester(client)
    _ = harvester.run_private_scan(realm="pc", league="Mirage", price_item=lambda _i: BASE_PRICE)
    assert client.calls[0][2] is None


def test_private_scan_retries_once_after_401_refresh_and_succeeds() -> None:
    client = StubClient(sequence=[RuntimeError("PoE client error 401"), {"stashes": []}])
    harvester = build_harvester(client)
    token_provider = StubTokenProvider(refresh_result="new-token")
    _ = harvester.run_private_scan(realm="pc", league="Mirage", price_item=lambda _i: BASE_PRICE)
    assert token_provider.refresh_calls == 1


def test_private_scan_401_refresh_retry_401_marks_disconnected_and_raises_auth_required() -> None:
    client = StubClient(sequence=[RuntimeError("PoE client error 401"), RuntimeError("PoE client error 401")])
    harvester = build_harvester(client)
    token_provider = StubTokenProvider(refresh_result="new-token", fail_on_retry=True)
    with pytest.raises(RuntimeError, match="auth_required"):
        harvester.run_private_scan(realm="pc", league="Mirage", price_item=lambda _i: BASE_PRICE)
    assert token_provider.marked_disconnected is True


def test_private_scan_returns_scope_error_on_403_without_forcing_logout() -> None:
    client = StubClient(sequence=[RuntimeError("PoE client error 403")])
    harvester = build_harvester(client)
    with pytest.raises(ValueError, match="insufficient_scope"):
        harvester.run_private_scan(realm="pc", league="Mirage", price_item=lambda _i: BASE_PRICE)


def test_private_scan_surfaces_transient_error_on_429_or_5xx() -> None:
    client = StubClient(sequence=[RuntimeError("PoE client error 429")])
    harvester = build_harvester(client)
    with pytest.raises(RuntimeError, match="upstream_rate_limited"):
        harvester.run_private_scan(realm="pc", league="Mirage", price_item=lambda _i: BASE_PRICE)
```

- [ ] **Step 2: Run stash harvester tests and verify failure**

Run: `.venv/bin/pytest tests/unit/test_account_stash_harvester.py -v`
Expected: FAIL because implementation still calls `character-window/get-stash-items` and cookie headers.

- [ ] **Step 3: Implement account stash API retrieval flow**

```python
tabs_payload = self._client.request("GET", stash_endpoint(realm, league), headers=self._request_headers)
for tab in tabs:
    payload = self._client.request(
        "GET",
        stash_endpoint(realm, league, tab_id=str(tab.get("id") or "")),
        headers=self._request_headers,
    )
```

- [ ] **Step 4: Normalize tab/item extraction for new payload shape**

```python
raw_tabs = tabs_payload.get("stashes") if isinstance(tabs_payload, dict) else []
tabs = normalize_account_tabs(raw_tabs)
```

- [ ] **Step 5: Implement upstream error mapping contract**

```python
except RuntimeError as exc:
    message = str(exc)
    if message.startswith("PoE client error 401"):
        # refresh once + retry once
        # if retry still 401: mark disconnected + raise auth_required
    elif message.startswith("PoE client error 403"):
        raise ValueError("insufficient_scope")
    elif message.startswith("PoE client error 429"):
        raise RuntimeError("upstream_rate_limited")
```

- [ ] **Step 6: Re-run stash harvester tests and pass**

Run: `.venv/bin/pytest tests/unit/test_account_stash_harvester.py -v`
Expected: PASS with account API endpoint assertions.

- [ ] **Step 7: Commit**

```bash
git add poe_trade/ingestion/account_stash_harvester.py tests/unit/test_account_stash_harvester.py
git commit -m "feat: switch private stash ingestion to oauth bearer account api"
```

## Task 6: Frontend Auth Context OAuth-Only Conversion

**Files:**
- Modify: `frontend/src/services/auth.tsx`
- Test: `frontend/src/services/api.test.ts`
- Test: `frontend/src/services/api.stash.test.ts`

- [ ] **Step 1: Write failing tests for removed `x-poe-session` header behavior**

```ts
test('request does not forward x-poe-session header', async () => {
  const init = fetchMock.mock.calls[0][1] as RequestInit
  expect((init.headers as Record<string, string>)['x-poe-session']).toBeUndefined()
})
```

- [ ] **Step 2: Run frontend API tests to confirm failure**

Run: `npm --prefix frontend run test -- src/services/api.test.ts src/services/api.stash.test.ts`
Expected: FAIL before header and auth-context changes.

- [ ] **Step 3: Remove POESESSID state, persistence, and login(payload) path**

```ts
// remove setPoeSessionId/getPoeSessionId and user_poe_sessions persistence calls
const startOAuthLogin = async (): Promise<void> => {
  const response = await proxyFetch('/api/v1/auth/login', { method: 'POST' })
  const { authorizeUrl } = await response.json()
  window.location.assign(authorizeUrl)
}
```

- [ ] **Step 4: Keep backend-session header transport only**

```ts
if (_poeBackendSession) {
  extraHeaders['x-poe-backend-session'] = _poeBackendSession
}
```

- [ ] **Step 5: Re-run focused frontend tests and pass**

Run: `npm --prefix frontend run test -- src/services/api.test.ts src/services/api.stash.test.ts`
Expected: PASS and no references to `x-poe-session`.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/services/auth.tsx frontend/src/services/api.ts frontend/src/services/api.test.ts frontend/src/services/api.stash.test.ts
git commit -m "feat: convert frontend auth context to oauth-only flow"
```

## Task 7: Frontend Callback Relay And User Menu Cleanup

**Files:**
- Modify: `frontend/src/pages/AuthCallback.tsx`
- Modify: `frontend/src/components/UserMenu.tsx`
- Modify: `frontend/src/App.tsx` (only if route/messaging adjustments are required)
- Test: `frontend/src/test/playwright/inventory.spec.ts`

- [ ] **Step 1: Write failing UI tests for callback relay and POESESSID removal**

```ts
test('settings menu no longer renders POESESSID input', async () => {
  await expect(page.getByLabel('POESESSID')).toHaveCount(0)
})
```

- [ ] **Step 2: Run targeted Playwright test and verify failure**

Run: `npm --prefix frontend exec playwright test src/test/playwright/inventory.spec.ts`
Expected: FAIL because POESESSID UI still exists.

- [ ] **Step 3: Implement callback relay POST**

```ts
const params = new URLSearchParams(window.location.search)
const payload = {
  code: params.get('code'),
  state: params.get('state'),
  error: params.get('error'),
  error_description: params.get('error_description'),
}
await fetch(`${API_BASE}/api/v1/auth/callback`, { method: 'POST', body: JSON.stringify(payload), ... })
```

- [ ] **Step 4: Remove POESESSID inputs/actions from UserMenu and keep OAuth connect button**

```tsx
<Button onClick={handleOAuthLogin}>Login with PoE Account</Button>
```

- [ ] **Step 5: Re-run targeted Playwright test and pass**

Run: `npm --prefix frontend exec playwright test src/test/playwright/inventory.spec.ts`
Expected: PASS with OAuth-only menu and callback behavior.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/AuthCallback.tsx frontend/src/components/UserMenu.tsx frontend/src/App.tsx frontend/src/test/playwright/inventory.spec.ts
git commit -m "feat: add oauth callback relay and remove poesessid ui"
```

## Task 8: Supabase Proxy Header Contract Cleanup

**Files:**
- Modify: `frontend/supabase/functions/api-proxy/index.ts`
- Create: `frontend/supabase/functions/api-proxy/index.test.ts`

- [ ] **Step 1: Add failing proxy test for header/cookie forwarding contract**

```ts
test('proxy allow headers and forwarded cookie exclude poesessid path', async () => {
  const headers = getCorsHeaders(new Request('https://example.test', { method: 'OPTIONS' }))
  expect(headers['Access-Control-Allow-Headers']).not.toContain('x-poe-session')

  const forwarded = buildForwardHeaders({
    existingCookie: 'foo=bar',
    backendSession: 'session-1',
  })
  expect(forwarded.Cookie).toContain('poe_session=session-1')
  expect(forwarded.Cookie).not.toContain('POESESSID=')
})
```

- [ ] **Step 2: Implement minimal proxy changes**

```ts
"Access-Control-Allow-Headers": "..., x-proxy-path, x-poe-backend-session"
// remove x-poe-session lookup and POESESSID cookie injection
```

- [ ] **Step 3: Verify proxy builds/lints in existing frontend workflow**

Run: `npm --prefix frontend run test -- supabase/functions/api-proxy/index.test.ts src/services/api.test.ts`
Expected: PASS and no runtime dependency on `x-poe-session`.

- [ ] **Step 4: Commit**

```bash
git add frontend/supabase/functions/api-proxy/index.ts frontend/supabase/functions/api-proxy/index.test.ts
git commit -m "chore: remove legacy poesessid forwarding from api proxy"
```

## Task 9: OpenAPI Contract And Backend Docs Alignment

**Files:**
- Modify: `frontend/apispec.yml`
- Modify: `README.md`
- Modify: `scripts/private_stash_scan_smoke.py`

- [ ] **Step 1: Write failing contract expectations in tests/docs checks**

```bash
rg -n "POESESSID|poeSessionId|cf_clearance|x-poe-session" poe_trade frontend scripts README.md --glob '!docs/superpowers/**'
```

Expected: Matches found in runtime files before cleanup.

- [ ] **Step 2: Update OpenAPI auth routes and payloads**

```yaml
/api/v1/auth/login:
  post:
    responses:
      '200':
        schema:
          type: object
          properties:
            authorizeUrl: { type: string }
```

- [ ] **Step 3: Update README and smoke script to OAuth-only examples**

```python
access_token = os.environ.get("POE_ACCOUNT_ACCESS_TOKEN", "").strip()
client.set_bearer_token(access_token)
```

- [ ] **Step 4: Re-run grep to verify legacy strings removed**

Run: `rg -n "POESESSID|poeSessionId|cf_clearance|x-poe-session" poe_trade frontend scripts README.md --glob '!docs/superpowers/**'`
Expected: No runtime matches.

- [ ] **Step 5: Commit**

```bash
git add frontend/apispec.yml README.md scripts/private_stash_scan_smoke.py
git commit -m "docs: publish oauth-only auth and stash contract"
```

## Task 10: Full Verification Gate

**Files:**
- Modify if needed: any failing test file touched above

- [ ] **Step 1: Run backend auth/stash test suite**

Run: `.venv/bin/pytest tests/unit/test_api_auth.py tests/unit/test_api_auth_oauth.py tests/unit/test_auth_session.py tests/unit/test_account_stash_harvester.py tests/unit/test_account_stash_service.py -v`
Expected: PASS.

- [ ] **Step 2: Run broader backend regression slice**

Run: `.venv/bin/pytest tests/unit/test_api_ops_routes.py -v`
Expected: PASS with updated OAuth error/message expectations.

- [ ] **Step 3: Run frontend tests for touched auth/stash surfaces**

Run: `npm --prefix frontend run test -- src/services/api.test.ts src/services/api.stash.test.ts src/components/tabs/StashViewerTab.test.tsx`
Expected: PASS.

- [ ] **Step 4: Build frontend**

Run: `npm --prefix frontend run build`
Expected: PASS.

- [ ] **Step 5: Optional deterministic gate (if environment ready)**

Run: `make ci-deterministic`
Expected: PASS or documented `not run` with reason.

- [ ] **Step 6: Final commit for verification-driven fixes**

```bash
git add <any-fixes-from-verification>
git commit -m "test: align oauth-only migration with backend and frontend verification"
```

## Execution Notes

- Keep changes additive and scoped to OAuth-only migration; do not refactor unrelated modules.
- Preserve stable response envelopes (`{"error": {"code", "message"}}`) and existing stash payload shapes unless explicitly updated.
- Do not log secrets (`client_secret`, access tokens, refresh tokens, auth codes).
- If adding new env vars, update `poe_trade/config/constants.py`, `poe_trade/config/settings.py`, and alias tests.
- If callback redirect behavior conflicts with current frontend router state, keep relay logic in `AuthCallback.tsx` and avoid introducing new routes.
