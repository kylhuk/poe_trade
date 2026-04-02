import { expect, test } from '@playwright/test';

const AUTH_STORAGE_KEY = 'sb-bzgqnwkxtyhcklwbgfaz-auth-token';

type Role = 'member' | 'admin';

function authSession(email = 'qa@example.com') {
  return {
    access_token: 'token-123',
    token_type: 'bearer',
    expires_in: 3600,
    expires_at: Math.floor(Date.now() / 1000) + 3600,
    refresh_token: 'refresh-123',
    user: {
      id: 'user-123',
      email,
      role: 'authenticated',
    },
  };
}

async function installSupabaseMocks(page: import('@playwright/test').Page, options: { approved: boolean; role: Role }) {
  await page.route('**/rest/v1/approved_users**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(options.approved ? [{ id: 'approved-1' }] : []),
    });
  });

  await page.route('**/rest/v1/user_roles**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([{ role: options.role }]),
    });
  });

  await page.route('**/auth/v1/logout**', async (route) => {
    await route.fulfill({ status: 204, body: '' });
  });

  await page.route('**/auth/v1/token?grant_type=refresh_token**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(authSession()),
    });
  });
}

async function installLoginMocks(page: import('@playwright/test').Page, captures: { signIn: string[]; signUp: string[] }) {
  await page.route('**/auth/v1/token?grant_type=password**', async (route) => {
    captures.signIn.push(await route.request().postData() ?? '');
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(authSession()),
    });
  });

  await page.route('**/auth/v1/signup**', async (route) => {
    captures.signUp.push(await route.request().postData() ?? '');
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ user: authSession().user, session: authSession() }),
    });
  });

  await page.route('**/auth/v1/user**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(authSession().user),
    });
  });
}

async function loginThroughForm(page: import('@playwright/test').Page, email: string) {
  await page.goto('/login');
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password').fill('secret-1');
  await page.getByRole('button', { name: 'Sign In' }).click();
}

async function installAppProxyMocks(page: import('@playwright/test').Page, role: Role) {
  const serviceRows = [
    {
      id: 'svc-ingest',
      name: 'Ingest',
      description: 'Ingests data',
      status: 'running',
      type: 'worker',
      uptime: 3600,
      lastCrawl: '2026-03-21T12:00:00Z',
      rowsInDb: 1200,
      containerInfo: 'svc-ingest',
      allowedActions: ['stop', 'restart'],
    },
    {
      id: 'svc-scan',
      name: 'Scanner',
      description: 'Scores listings',
      status: 'stopped',
      type: 'worker',
      uptime: null,
      lastCrawl: '2026-03-21T11:30:00Z',
      rowsInDb: 300,
      containerInfo: 'svc-scan',
      allowedActions: ['start', 'restart'],
    },
  ];

  const messages = [
    {
      id: 'msg-1',
      timestamp: '2026-03-21T12:00:00Z',
      severity: 'critical',
      sourceModule: 'scanner',
      message: 'Critical alert',
      suggestedAction: 'Acknowledge it',
    },
    {
      id: 'msg-2',
      timestamp: '2026-03-21T12:01:00Z',
      severity: 'warning',
      sourceModule: 'ingestion',
      message: 'Warning alert',
      suggestedAction: 'Watch it',
    },
    {
      id: 'msg-3',
      timestamp: '2026-03-21T12:02:00Z',
      severity: 'info',
      sourceModule: 'dashboard',
      message: 'Info alert',
      suggestedAction: 'Ignore it',
    },
  ];

  await page.route('**/functions/v1/debug-traffic-reader**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          id: 'traffic-1',
          created_at: '2026-03-21T12:00:00Z',
          method: 'POST',
          path: '/api/v1/stash/scan',
          request_headers: {},
          request_body: '{"ok":true}',
          response_status: 202,
          response_headers: {},
          response_body: '{"status":"running"}',
        },
      ]),
    });
  });

  await page.route('**/functions/v1/api-proxy', async (route) => {
    const request = route.request();
    const path = request.headers()['x-proxy-path'] || '';
    const respond = async (body: unknown, status = 200) => route.fulfill({
      status,
      contentType: 'application/json',
      body: JSON.stringify(body),
    });

    if (path === '/api/v1/auth/session') {
      await respond({ status: 'disconnected' });
      return;
    }
    if (path === '/api/v1/auth/login') {
      await respond({ authorizeUrl: '/auth/callback?code=code-123&state=state-456' });
      return;
    }
    if (path.startsWith('/api/v1/auth/callback?')) {
      await respond({ status: 'connected', accountName: 'qa-exile', expiresAt: '2026-01-01T00:00:00Z' });
      return;
    }
    if (path === '/api/v1/ops/contract') {
      await respond({ primary_league: 'Mirage' });
      return;
    }
    if (path === '/api/v1/ops/dashboard') {
      await respond({
        services: serviceRows,
        summary: { running: 1, total: 2, errors: 0, criticalAlerts: 1, topOpportunity: 'flip:scarab' },
        topOpportunities: [{ scannerRunId: 'run-1', strategyId: 'flip', itemOrMarketKey: 'scarab', whyItFired: 'Cheap scarab', buyPlan: 'Buy', transformPlan: 'List', exitPlan: 'Sell' }],
      });
      return;
    }
    if (path === '/api/v1/ops/services') {
      await respond({ services: serviceRows });
      return;
    }
    if (/^\/api\/v1\/actions\/services\/.+\/(start|stop|restart)$/.test(path)) {
      await respond({ ok: true });
      return;
    }
    if (path === '/api/v1/ops/messages') {
      await respond(messages);
      return;
    }
    if (/^\/api\/v1\/ops\/alerts\/.+\/ack$/.test(path)) {
      await respond({ alertId: 'msg-1', status: 'acknowledged' });
      return;
    }
    if (path.startsWith('/api/v1/ops/analytics/ingestion')) {
      await respond([{ queue_key: 'stash:pc', feed_kind: 'stash', status: 'ok', last_ingest_at: '2026-03-21T12:00:00Z' }]);
      return;
    }
    if (path.startsWith('/api/v1/ops/analytics/scanner')) {
      await respond({ latestRunId: 'run-1', rows: [{ strategy_id: 'flip', enabled: true, recommendation_count: 2, accepted_count: 1, rejected_count: 1, candidate_count: 10, top_rejection_reason: 'spread_too_low' }], gateRejections: [{ decision_reason: 'spread_too_low', rejection_count: 1 }], complexityTiers: [{ complexity_tier: 'simple', tier_count: 1 }] });
      return;
    }
    if (path.startsWith('/api/v1/ml/leagues/Mirage/automation/status')) {
      await respond({ league: 'Mirage', status: 'running', observability: { datasetRows: 10, promotedModels: 1, evalRuns: 1, evalSampleRows: 10, evaluationAvailable: true } });
      return;
    }
    if (path.startsWith('/api/v1/ml/leagues/Mirage/automation/history')) {
      await respond({ league: 'Mirage', mode: 'live', history: [], summary: { runsLast7d: 1, runsLast30d: 1, trendDirection: 'unknown' }, qualityTrend: [], trainingCadence: [], routeMetrics: [], datasetCoverage: { totalRows: 10, supportedRows: 10, coverageRatio: 1, routes: [] }, promotions: [], observability: { datasetRows: 10, promotedModels: 1, evalRuns: 1, evalSampleRows: 10, evaluationAvailable: true } });
      return;
    }
    if (path.startsWith('/api/v1/ops/analytics/search-suggestions')) {
      await respond({ suggestions: [{ text: 'Headhunter' }] });
      return;
    }
    if (path.startsWith('/api/v1/ops/analytics/search-history')) {
      await respond({ rows: [{ query: 'Headhunter', searchedAt: '2026-03-21T12:00:00Z', resultCount: 1 }], suggestions: ['Headhunter'] });
      return;
    }
    if (path.startsWith('/api/v1/ops/analytics/pricing-outliers')) {
      await respond({
        query: { league: 'Mirage', sort: 'expected_profit', order: 'desc', minTotal: 5, limit: 500 },
        rows: [{ itemName: 'Divine Orb', entryPrice: 100, median: 120, p10: 110, p90: 130, expectedProfit: 20, roi: 0.2, underpricedRate: 0.5, itemsPerWeek: 10, itemsTotal: 20, affixAnalyzed: null }],
        weekly: [{ weekStart: '2026-03-01', tooCheapCount: 2 }],
      });
      return;
    }
    if (path.startsWith('/api/v1/ops/scanner/recommendations')) {
      await respond({ rows: [{ scannerRunId: 'run-1', strategyId: 'flip', itemOrMarketKey: 'essence:bulk', whyItFired: 'Bulk discount', buyPlan: 'Buy', transformPlan: 'None', exitPlan: 'Sell', executionVenue: 'trade', expectedProfitChaos: 10, expectedProfitPerMinuteChaos: 5, expectedRoi: 0.2, expectedHoldTime: '10m', expectedHoldMinutes: 10, confidence: 0.9, recordedAt: '2026-03-21T12:00:00Z' }], meta: { nextCursor: null, hasMore: false } });
      return;
    }
    if (path.startsWith('/api/v1/ops/leagues/Mirage/price-check')) {
      await respond({ predictedValue: 45, currency: 'chaos', confidence: 82, comparables: [{ name: 'Grim Bane', price: 40, currency: 'chaos', league: 'Mirage', addedOn: '2026-03-21T12:00:00Z' }], interval: { p10: 39, p90: 51 }, mlPredicted: true, estimateTrust: 'normal', priceRecommendationEligible: true });
      return;
    }
    if (path.startsWith('/api/v1/stash/status')) {
      await respond({ status: 'connected_populated', connected: true, tabCount: 2, itemCount: 2, session: { accountName: 'qa-exile', expiresAt: '2099-01-01T00:00:00Z' }, publishedScanId: 'scan-1', publishedAt: '2026-03-21T12:00:00Z', scanStatus: null });
      return;
    }
    if (path.startsWith('/api/v1/stash/tabs')) {
      await respond({ scanId: 'scan-1', publishedAt: '2026-03-21T12:00:00Z', isStale: false, scanStatus: null, stashTabs: [{ id: 'tab-1', name: 'Currency', type: 'currency', items: [{ id: 'item-1', fingerprint: 'sig:item-1', name: 'Grim Bane', x: 0, y: 0, w: 1, h: 1, itemClass: 'Helmet', rarity: 'rare', listedPrice: 40, estimatedPrice: 45, estimatedPriceConfidence: 82, priceDeltaChaos: 5, priceDeltaPercent: 12.5, priceEvaluation: 'mispriced', currency: 'chaos', iconUrl: 'https://web.poecdn.com/item.png', interval: { p10: 39, p90: 51 } }] }], tabsMeta: [{ id: 'tab-1', tabIndex: 0, name: 'Currency', type: 'CurrencyStash' }, { id: 'tab-2', tabIndex: 1, name: 'Gear', type: 'NormalStash' }], numTabs: 2 });
      return;
    }
    if (path.startsWith('/api/v1/stash/scan/start')) {
      await respond({ error: { code: 'route_not_found', message: 'route not found', details: null } }, 404);
      return;
    }
    if (path.startsWith('/api/v1/stash/scan?')) {
      await respond({ scanId: 'scan-2', status: 'running', startedAt: '2026-03-21T12:01:00Z', accountName: 'qa-exile', league: 'Mirage', realm: 'pc', deduplicated: false }, 202);
      return;
    }
    if (path.startsWith('/api/v1/stash/scan/status')) {
      await respond({ status: 'published', activeScanId: null, publishedScanId: 'scan-2', startedAt: '2026-03-21T12:01:00Z', updatedAt: '2026-03-21T12:03:00Z', publishedAt: '2026-03-21T12:03:00Z', progress: { tabsTotal: 2, tabsProcessed: 2, itemsTotal: 2, itemsProcessed: 2 }, error: null });
      return;
    }
    if (path.startsWith('/api/v1/stash/scan/valuations')) {
      await respond({ structuredMode: true, scanId: 'scan-2', stashId: 'scan-2', chaosMedian: 45, items: [{ fingerprint: 'sig:item-1', chaosMedian: 45 }] });
      return;
    }
    if (path.startsWith('/api/v1/stash/items/sig%3Aitem-1/history')) {
      await respond({ fingerprint: 'sig:item-1', item: { name: 'Grim Bane', itemClass: 'Helmet', rarity: 'rare', iconUrl: 'https://web.poecdn.com/item.png' }, history: [{ scanId: 'scan-1', pricedAt: '2026-03-21T12:00:00Z', predictedValue: 45, listedPrice: 40, currency: 'chaos', confidence: 82, interval: { p10: 39, p90: 51 }, priceRecommendationEligible: true, estimateTrust: 'normal', estimateWarning: '', fallbackReason: '' }] });
      return;
    }

    if (role !== 'admin' && (path.startsWith('/api/v1/ops/') || path.startsWith('/api/v1/actions/'))) {
      await respond({ error: { code: 'forbidden', message: 'forbidden', details: null } }, 403);
      return;
    }

    throw new Error(`Unhandled proxy path: ${path}`);
  });
}

test('public routes and controls work', async ({ page }) => {
  const captures = { signIn: [] as string[], signUp: [] as string[] };
  await installLoginMocks(page, captures);
  await page.route('**/functions/v1/api-proxy', async (route) => {
    const path = route.request().headers()['x-proxy-path'] || '';
    if (path === '/api/v1/auth/session') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'disconnected' }) });
      return;
    }
    if (path.startsWith('/api/v1/auth/callback?')) {
      await route.fulfill({ status: 401, contentType: 'application/json', body: JSON.stringify({ error: { code: 'oauth_access_denied', message: 'Path of Exile login was cancelled', details: null } }) });
      return;
    }
    if (path === '/api/v1/ops/contract') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ primary_league: 'Mirage' }) });
      return;
    }
    if (path.startsWith('/api/v1/ops/leagues/Mirage/price-check')) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ predictedValue: 45, currency: 'chaos', confidence: 80, comparables: [], interval: { p10: 40, p90: 50 }, mlPredicted: true, estimateTrust: 'normal', priceRecommendationEligible: true }) });
      return;
    }
    throw new Error(`Unhandled public proxy path: ${path}`);
  });

  await page.goto('/does-not-exist');
  await expect(page.getByTestId('panel-pricecheck')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Sign In' })).toBeVisible();

  await page.getByRole('button', { name: 'Sign In' }).click();
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByLabel('Email')).toBeVisible();
  await expect(page.getByLabel('Password')).toBeVisible();
  await page.getByRole('button', { name: /don\'t have an account\? sign up/i }).click();
  await expect(page.getByRole('button', { name: 'Sign Up' })).toBeVisible();
  await page.getByRole('button', { name: /already have an account\? sign in/i }).click();
  await expect(page.getByRole('button', { name: 'Sign In' })).toBeVisible();

  await page.goto('/auth/callback?code=code-123&state=state-456');
  await expect(page.getByText('Path of Exile login was cancelled')).toBeVisible();
  await page.getByRole('button', { name: 'Return to app' }).click();
  await expect(page).toHaveURL(/\/pricecheck$/);
});

test('pending approval renders after authenticated but unapproved login', async ({ page }) => {
  const captures = { signIn: [] as string[], signUp: [] as string[] };
  await installLoginMocks(page, captures);
  await installSupabaseMocks(page, { approved: false, role: 'member' });

  await loginThroughForm(page, 'qa@example.com');
  await expect(page.getByText('Pending Approval')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Sign Out' })).toBeVisible();
});

test('authenticated catch-all renders not found and returns home', async ({ page }) => {
  const captures = { signIn: [] as string[], signUp: [] as string[] };
  await installLoginMocks(page, captures);
  await installSupabaseMocks(page, { approved: true, role: 'member' });
  await installAppProxyMocks(page, 'member');

  await loginThroughForm(page, 'qa@example.com');
  await page.goto('/does-not-exist/extra/deeper');
  await expect(page.getByText('404')).toBeVisible();
  await page.getByRole('link', { name: 'Return to Home' }).click();
  await expect(page).toHaveURL(/\/opportunities$/);
});

test('member and admin routes expose listed controls', async ({ page }) => {
  const captures = { signIn: [] as string[], signUp: [] as string[] };
  await installLoginMocks(page, captures);
  await installSupabaseMocks(page, { approved: true, role: 'admin' });
  await installAppProxyMocks(page, 'admin');

  await loginThroughForm(page, 'admin@example.com');
  await page.goto('/dashboard');
  await expect(page.getByTestId('panel-dashboard-root')).toBeVisible();
  await expect(page.getByText('Services Running')).toBeVisible();

  await page.getByLabel('API error log').click();
  await expect(page.getByText('No errors recorded')).toBeVisible();
  await page.keyboard.press('Escape');

  await page.getByTestId('settings-trigger').click();
  await expect(page.locator('[role="dialog"]').getByText('qa@example.com')).toBeVisible();
  await expect(page.getByText('Not connected')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Connect Path of Exile' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Sign Out' })).toBeVisible();
  await page.keyboard.press('Escape');

  await page.getByTestId('tab-opportunities').click();
  await expect(page.getByPlaceholder('Item name…')).toBeVisible();

  await page.getByPlaceholder('Item name…').fill('Divine');
  await page.getByRole('button', { name: 'Clear' }).click();

  await page.getByTestId('tab-services').click();
  await expect(page.getByTestId('panel-services-root')).toBeVisible();
  await page.getByRole('button', { name: 'Start All' }).click();
  await page.getByRole('button', { name: 'Stop All' }).click();
  await page.getByTestId('service-svc-scan-start').click();
  await page.getByTestId('service-svc-ingest-stop').click();
  await page.getByTestId('service-svc-scan-restart').click();

  await page.goto('/analytics/search');
  await page.getByTestId('search-history-input').fill('Head');
  await page.goto('/analytics/outliers');
  await expect(page.getByTestId('pricing-outliers-results')).toBeVisible();
  await page.goto('/analytics/session');
  await expect(page.getByText('Session analytics not supported by backend contract')).toBeVisible();

  await page.getByTestId('tab-pricecheck').click();
  await page.getByTestId('pricecheck-input').fill('Rarity: Rare\nGrim Bane\nHubris Circlet');
  await page.getByTestId('pricecheck-submit').click();
  await expect(page.getByText('ML Prediction')).toBeVisible();

  await page.getByTestId('tab-stash').click();
  await expect(page.getByTestId('panel-stash-root')).toBeVisible();
  await page.getByRole('button', { name: 'Scan' }).click();
  await expect(page.getByText('Valuations complete · 1 items priced · median 45c')).toBeVisible();
  await page.getByTestId('stash-tab-tab-1').click();
  await expect(page.getByTestId('stash-panel-grid')).toBeVisible();
  await page.getByRole('button', { name: 'API JSON Schema' }).click();
  await page.getByRole('button', { name: 'Copy' }).click();

  await page.getByTestId('tab-economy').click();
  await expect(page.getByPlaceholder('Search items…')).toBeVisible();
  await page.getByPlaceholder('Search items…').fill('Grim');
  await page.getByRole('button', { name: 'Reload' }).click();
  await page.getByRole('button', { name: /All Items/ }).click();
  await page.locator('.economy-row').first().click();
  await expect(page.getByRole('heading', { name: 'Grim Bane' })).toBeVisible();
  await page.keyboard.press('Escape');

  await page.getByTestId('tab-messages').click();
  await expect(page.getByTestId('panel-messages-root')).toBeVisible();
  for (const name of ['All', 'Critical', 'Warning', 'Info']) {
    await page.getByRole('button', { name }).click();
  }
  await page.getByRole('button', { name: 'Critical' }).click();
  await page.getByTestId('message-msg-1-ack').click();

  await page.getByTestId('tab-traffic').click();
  await expect(page.getByText('API Traffic Log')).toBeVisible();
  await page.locator('select').last().selectOption('250');
  await page.getByRole('button', { name: 'Auto' }).click();
  await page.getByRole('button').filter({ hasText: /^$/ }).last().click();
  await page.getByRole('button', { name: 'View body' }).first().click();

  await page.keyboard.press('Control+ArrowLeft');
  await expect(page).toHaveURL(/\/messages$/);
  await page.keyboard.press('Control+Home');
  await expect(page).toHaveURL(/\/dashboard$/);
  await page.keyboard.press('Control+End');
  await expect(page).toHaveURL(/\/traffic$/);
});
