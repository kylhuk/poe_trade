import { describe, expect, test } from 'vitest';

import { rewriteProxySetCookie } from '../../supabase/functions/api-proxy/cookies';

describe('rewriteProxySetCookie', () => {
  test('rewrites SameSite=Lax cookies for cross-site proxy use', () => {
    const rewritten = rewriteProxySetCookie(
      'poe_session=session-123; Path=/; HttpOnly; SameSite=Lax; Max-Age=604800'
    );

    expect(rewritten).toContain('SameSite=None');
    expect(rewritten).toContain('Secure');
    expect(rewritten).not.toContain('SameSite=Lax');
  });

  test('adds SameSite=None and Secure when missing', () => {
    const rewritten = rewriteProxySetCookie('poe_session=session-123; Path=/; HttpOnly');

    expect(rewritten).toContain('SameSite=None');
    expect(rewritten).toContain('Secure');
  });
});
