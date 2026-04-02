import { expect, test } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import { writeScenarioArtifact } from './evidence';

type ScenarioRow = {
  id: string;
  selectorTarget: string;
  artifact: string;
};

async function responsePayload(response: import('@playwright/test').APIResponse): Promise<unknown> {
  const body = await response.text();
  if (!body) {
    return null;
  }
  try {
    return JSON.parse(body);
  } catch {
    return body;
  }
}

const toWorkspaceArtifactPath = (artifact: string): string => `../${artifact}`;
const qaOperatorToken = process.env.POE_API_OPERATOR_TOKEN ?? 'qa-operator-token';

async function openTab(page: import('@playwright/test').Page, name: string): Promise<void> {
  await page.getByTestId(`tab-${name}`).click();
  await expect(page.getByTestId(`panel-${name}`)).toBeVisible();
}

function isScannerRecommendationsResponse(
  response: import('@playwright/test').Response,
  sort: string,
): boolean {
  const url = new URL(response.url());
  return (
    url.pathname === '/api/v1/ops/scanner/recommendations'
    && url.searchParams.get('sort') === sort
  );
}

test('scenario inventory coverage emits evidence artifacts', async ({ page }) => {
  const inventoryRaw = await readFile(new URL('../scenario-inventory.json', import.meta.url), 'utf-8');
  const inventory = JSON.parse(inventoryRaw) as { scenarios: ScenarioRow[] };

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/');

  const apiResponses: Record<string, unknown> = {};

  for (const scenario of inventory.scenarios) {
    if (scenario.id === 'shell-tab-navigation') {
      for (const tab of ['dashboard', 'services', 'analytics', 'pricecheck', 'stash', 'messages']) {
        await openTab(page, tab);
      }
      await expect(page.locator(scenario.selectorTarget)).toBeVisible();
      await writeScenarioArtifact(page, toWorkspaceArtifactPath(scenario.artifact));
      continue;
    }

    if (scenario.id === 'dashboard-service-message-rollup') {
      await openTab(page, 'dashboard');
      await expect(page.locator(scenario.selectorTarget)).toBeVisible();
      await writeScenarioArtifact(page, toWorkspaceArtifactPath(scenario.artifact));
      continue;
    }

    if (scenario.id === 'services-list-refresh') {
      await openTab(page, 'services');
      await expect(page.locator(scenario.selectorTarget)).toBeVisible();
      await writeScenarioArtifact(page, toWorkspaceArtifactPath(scenario.artifact));
      continue;
    }

    if (scenario.id === 'services-start-action' || scenario.id === 'services-stop-action' || scenario.id === 'services-restart-action') {
      await openTab(page, 'services');
      const target = page.locator(scenario.selectorTarget).first();
      if (await target.count()) {
        await expect(target).toBeVisible();
        if (await target.isEnabled()) {
          await target.click();
        }
      }
      await writeScenarioArtifact(page, toWorkspaceArtifactPath(scenario.artifact));
      continue;
    }

    if (scenario.id.startsWith('analytics-')) {
      await openTab(page, 'analytics');
      const analyticsTabByScenario: Record<string, string> = {
        'analytics-ingestion-panel': 'ingestion',
        'analytics-scanner-panel': 'scanner',
        'analytics-alerts-panel': 'alerts',
        'analytics-backtests-panel': 'backtests',
        'analytics-shipment-panel': 'ml',
        'analytics-reports-panel': 'reports',
        'analytics-session-panel': 'session',
        'analytics-gear-simulation': 'session',
      };
      const targetTab = analyticsTabByScenario[scenario.id];
      if (targetTab) {
        await page.getByTestId(`analytics-tab-${targetTab}`).click();
      }

      if (scenario.id === 'analytics-automation-history-contract') {
        const response = await page.request.get('/api/v1/ml/leagues/Mirage/automation/history');
        apiResponses[scenario.id] = { status: response.status(), body: await responsePayload(response) };
        await writeScenarioArtifact(page, toWorkspaceArtifactPath(scenario.artifact), apiResponses[scenario.id]);
        continue;
      }

      await expect(page.locator(scenario.selectorTarget)).toBeVisible();
      await writeScenarioArtifact(page, toWorkspaceArtifactPath(scenario.artifact));
      continue;
    }

    if (scenario.id === 'messages-list-and-filter') {
      await openTab(page, 'messages');
      await expect(page.locator(scenario.selectorTarget)).toBeVisible();
      await page.getByRole('button', { name: 'critical' }).click();
      await writeScenarioArtifact(page, toWorkspaceArtifactPath(scenario.artifact));
      continue;
    }

    if (scenario.id === 'messages-ack-critical') {
      await openTab(page, 'messages');
      const ackButton = page.locator(scenario.selectorTarget).first();
      const ackButtonPresent = (await ackButton.count()) > 0;
      if (ackButtonPresent) {
        await ackButton.click();
      }
      await writeScenarioArtifact(
        page,
        toWorkspaceArtifactPath(scenario.artifact),
        { ackButtonPresent },
      );
      continue;
    }

    if (scenario.id === 'stash-status-gates' || scenario.id === 'stash-grid-load') {
      await openTab(page, 'stash');
      await expect(page.locator(scenario.selectorTarget).first()).toBeVisible();
      await writeScenarioArtifact(page, toWorkspaceArtifactPath(scenario.artifact));
      continue;
    }

    if (scenario.id === 'pricecheck-invalid-input') {
      await openTab(page, 'pricecheck');
      await page.getByTestId('pricecheck-submit').click();
      await expect(page.getByTestId('state-invalid_input')).toBeVisible();
      await writeScenarioArtifact(page, toWorkspaceArtifactPath(scenario.artifact));
      continue;
    }

    if (scenario.id === 'pricecheck-submit-live') {
      await openTab(page, 'pricecheck');
      await page.getByTestId('pricecheck-input').fill('Item Class: Maps\nRarity: Rare\nGrim Veil\nCemetery Map');
      await page.getByTestId('pricecheck-submit').click();
      await page.waitForTimeout(500);
      await writeScenarioArtifact(page, toWorkspaceArtifactPath(scenario.artifact));
      continue;
    }

    if (scenario.id === 'scanner-summary-contract') {
      const response = await page.request.get('/api/v1/ops/scanner/summary');
      apiResponses[scenario.id] = { status: response.status(), body: await responsePayload(response) };
      await writeScenarioArtifact(page, toWorkspaceArtifactPath(scenario.artifact), apiResponses[scenario.id]);
      continue;
    }

    if (scenario.id === 'opportunities-tab-load') {
      await openTab(page, 'opportunities');
      await expect(page.locator(scenario.selectorTarget)).toBeVisible();
      await expect(page.locator('[data-testid=panel-opportunities-root] h3').first()).toBeVisible();
      await writeScenarioArtifact(page, toWorkspaceArtifactPath(scenario.artifact));
      continue;
    }

    if (scenario.id === 'opportunities-sort-profit-per-minute') {
      await openTab(page, 'opportunities');
      const opportunitiesPanel = page.getByTestId('panel-opportunities-root');
      await expect(opportunitiesPanel).toBeVisible();
      await expect(opportunitiesPanel.locator('h3').first()).toBeVisible();

      const sortResponse = page.waitForResponse((response) => (
        isScannerRecommendationsResponse(response, 'expected_profit_per_minute_chaos')
      ));
      await page.getByTestId('scanner-sort-profit-per-minute').click();
      await sortResponse;

      await expect(page.locator(scenario.selectorTarget)).toBeVisible();
      const loadMoreButton = page.getByTestId('scanner-load-more');
      await expect(loadMoreButton).toBeVisible();
      await expect(loadMoreButton).toBeEnabled();
      await expect(opportunitiesPanel.getByText('essence:bulk')).toHaveCount(0);
      const paginationResponse = page.waitForResponse((response) => {
        if (!isScannerRecommendationsResponse(response, 'expected_profit_per_minute_chaos')) {
          return false;
        }
        const url = new URL(response.url());
        return url.searchParams.get('cursor') !== null;
      });
      await loadMoreButton.click();
      await paginationResponse;

      await expect(opportunitiesPanel.getByText('cluster_jewel:Malachite Cluster Jewel:chaos')).toBeVisible();
      await expect(opportunitiesPanel.getByText('essence:bulk')).toBeVisible();
      await expect(opportunitiesPanel.locator('h3').first()).toBeVisible();
      await writeScenarioArtifact(page, toWorkspaceArtifactPath(scenario.artifact));
      continue;
    }

    if (scenario.id === 'scanner-recommendations-invalid-cursor') {
      const response = await page.request.get(
        'http://127.0.0.1:8080/api/v1/ops/scanner/recommendations?sort=expected_profit_per_minute_chaos&cursor=broken',
        {
          headers: {
            Authorization: `Bearer ${qaOperatorToken}`,
            Origin: 'http://127.0.0.1:4173',
            Referer: 'http://127.0.0.1:4173/',
          },
        },
      );
      const body = await responsePayload(response);
      apiResponses[scenario.id] = { status: response.status(), body };

      expect(response.status()).toBe(400);
      expect(body).toEqual(expect.objectContaining({
        error: expect.objectContaining({
          code: 'invalid_input',
        }),
      }));

      await writeScenarioArtifact(page, toWorkspaceArtifactPath(scenario.artifact), apiResponses[scenario.id]);
      continue;
    }

    if (scenario.id === 'auth-session-state-indicator') {
      await expect(page.locator(scenario.selectorTarget)).toBeVisible();
      await writeScenarioArtifact(page, toWorkspaceArtifactPath(scenario.artifact));
      continue;
    }

    if (scenario.id === 'auth-settings-save-session-refresh') {
      await page.getByTestId('settings-trigger').click();
      await expect(page.getByLabel('POESESSID')).toHaveCount(0);
      await expect(page.getByRole('button', { name: 'Connect Path of Exile' })).toBeVisible();
      await writeScenarioArtifact(page, toWorkspaceArtifactPath(scenario.artifact));
      continue;
    }

    if (scenario.id === 'auth-settings-clear-logout') {
      await page.getByTestId('settings-trigger').click();
      const signOutButton = page.getByRole('button', { name: 'Sign Out' }).last();
      await expect(signOutButton).toBeVisible();
      await signOutButton.click({ force: true });
      await writeScenarioArtifact(page, toWorkspaceArtifactPath(scenario.artifact));
      continue;
    }

    throw new Error(`Unhandled scenario inventory row: ${scenario.id}`);
  }
});
