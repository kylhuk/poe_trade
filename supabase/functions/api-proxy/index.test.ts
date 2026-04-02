import { afterEach, describe, expect, test, vi } from 'vitest';

vi.stubGlobal('Deno', {
  env: { get: vi.fn() },
  serve: vi.fn(),
});

describe('api proxy contract', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  test('allows the live poe.lama-lan.ch origin', async () => {
    const { getCorsHeaders } = await import('./contract');

    const corsHeaders = getCorsHeaders(
      new Request('https://example.test', {
        method: 'OPTIONS',
        headers: { origin: 'https://poe.lama-lan.ch' },
      }),
    );

    expect(corsHeaders['Access-Control-Allow-Origin']).toBe('https://poe.lama-lan.ch');
  });

  test('forwards only the existing cookie header', async () => {
    const { buildForwardHeaders, getCorsHeaders } = await import('./contract');

    const corsHeaders = getCorsHeaders(new Request('https://example.test', { method: 'OPTIONS' }));
    expect(corsHeaders['Access-Control-Allow-Headers']).not.toContain('x-poe-session');

    const forwarded = buildForwardHeaders({
      existingCookie: 'foo=bar',
    });

    expect(forwarded.Cookie).toBe('foo=bar');
  });

  test('preserves query strings in proxy paths', async () => {
    const { normalizeProxyPath } = await import('./contract');

    expect(normalizeProxyPath('/api/v1/auth/callback?code=code-123&state=state-456')).toBe(
      '/api/v1/auth/callback?code=code-123&state=state-456',
    );
  });
});
