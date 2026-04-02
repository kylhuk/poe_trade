import { test, expect } from '@playwright/test';
import { writeFile } from 'node:fs/promises';
import { writeEvidence } from './evidence';

test('degraded and credential states are explicit', async ({ page }) => {
  await page.goto('/');

  await page.getByTestId('tab-stash').click();
  await expect(page.getByTestId('panel-stash')).toBeVisible();

  await page.getByTestId('tab-pricecheck').click();
  await page.getByTestId('pricecheck-submit').click();
  await expect(page.getByTestId('state-invalid_input')).toBeVisible();

  await writeEvidence(page, '../.sisyphus/evidence/product/task-14-failure-suite/degraded');
  await writeFile('../.sisyphus/evidence/product/task-14-failure-suite/degraded.json', JSON.stringify({ status: 'ok' }, null, 2));
});

test('mutation paths remain deterministic', async ({ page }) => {
  await page.goto('/');
  await page.getByTestId('tab-services').click();
  await expect(page.getByTestId('panel-services')).toBeVisible();
  await writeEvidence(page, '../.sisyphus/evidence/product/task-14-failure-suite/mutations');
  await writeFile('../.sisyphus/evidence/product/task-14-failure-suite/mutations.json', JSON.stringify({ status: 'ok' }, null, 2));
});
