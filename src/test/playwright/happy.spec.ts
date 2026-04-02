import { test, expect } from '@playwright/test';
import { writeFile } from 'node:fs/promises';
import { writeEvidence } from './evidence';

test('happy path desktop covers all top tabs', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/');

  const tabs = [
    'dashboard',
    'services',
    'analytics',
    'pricecheck',
    'stash',
    'messages',
  ] as const;

  for (const tab of tabs) {
    await page.getByTestId(`tab-${tab}`).click();
    await expect(page.getByTestId(`panel-${tab}`)).toBeVisible();
  }

  await writeEvidence(page, '../.sisyphus/evidence/product/task-13-happy-suite/happy-desktop');
  await writeFile('../.sisyphus/evidence/product/task-13-happy-suite/happy-desktop.json', JSON.stringify({ status: 'ok' }, null, 2));
});

test('happy path mobile shell renders tabs', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await expect(page.getByTestId('tab-dashboard')).toBeVisible();
  await expect(page.getByTestId('tab-stash')).toBeVisible();
  await writeEvidence(page, '../.sisyphus/evidence/product/task-13-happy-suite/happy-mobile');
  await writeFile('../.sisyphus/evidence/product/task-13-happy-suite/happy-mobile.json', JSON.stringify({ status: 'ok' }, null, 2));
});
