import { expect, test } from '@playwright/test';

test('auth callback relay calls the proxy callback endpoint and clears query params', async ({ page }) => {
  const seenPaths: string[] = [];

  await page.route('**/functions/v1/api-proxy', async (route) => {
    const request = route.request();
    expect(request.method()).toBe('GET');
    const proxyPath = request.headers()['x-proxy-path'];
    seenPaths.push(proxyPath || '');

    if (proxyPath === '/api/v1/auth/session') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'connected', accountName: 'qa-exile' }),
      });
      return;
    }

    expect(proxyPath).toBe('/api/v1/auth/callback?code=code-123&state=state-456');

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'connected' }),
    });
  });

  await page.goto('/auth/callback?code=code-123&state=state-456');

  await expect(page).toHaveURL(/\/auth\/callback$/);
  await expect(page.getByText('Path of Exile connected. Closing window…')).toBeVisible();
  expect(seenPaths).toEqual(
    expect.arrayContaining([
      '/api/v1/auth/callback?code=code-123&state=state-456',
      '/api/v1/auth/session',
    ]),
  );
});

test('connect path of exile opens a popup and completes the session flow', async ({ page, context }) => {
  const seenPaths: string[] = [];

  await context.route('**/functions/v1/api-proxy', async (route) => {
    const request = route.request();
    const proxyPath = request.headers()['x-proxy-path'];
    seenPaths.push(proxyPath || '');

    if (proxyPath === '/api/v1/auth/login') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ authorizeUrl: '/auth/callback?code=code-123&state=state-456' }),
      });
      return;
    }

    if (proxyPath === '/api/v1/auth/callback?code=code-123&state=state-456') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'connected',
          accountName: 'qa-exile',
          expiresAt: '2026-01-01T00:00:00Z',
          scope: ['account:profile', 'account:stashes'],
        }),
      });
      return;
    }

    if (proxyPath === '/api/v1/auth/session') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'connected', accountName: 'qa-exile' }),
      });
      return;
    }

    throw new Error(`Unexpected proxy path: ${proxyPath ?? 'missing'}`);
  });

  await page.goto('/');
  await expect(page.getByRole('button', { name: 'Connect Path of Exile' })).toBeVisible();

  const popupPromise = page.waitForEvent('popup');
  await page.getByRole('button', { name: 'Connect Path of Exile' }).click();
  const popup = await popupPromise;
  const closePromise = popup.waitForEvent('close');

  await expect(popup).toHaveURL(/\/auth\/callback\?code=code-123&state=state-456/);
  await expect(popup.getByText('Path of Exile connected. Closing window…')).toBeVisible();
  await closePromise;
  expect(seenPaths).toEqual(
    expect.arrayContaining([
      '/api/v1/auth/login',
      '/api/v1/auth/callback?code=code-123&state=state-456',
      '/api/v1/auth/session',
    ]),
  );
});
