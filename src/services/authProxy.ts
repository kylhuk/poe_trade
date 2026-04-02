import { supabase, SUPABASE_PROJECT_ID } from '@/lib/supabaseClient';

export const POE_OAUTH_MESSAGE = 'poe-oauth-result';
export const POE_OAUTH_RESULT_STORAGE_KEY = 'poe-oauth-result';

export type OAuthRelayResult = {
  type: typeof POE_OAUTH_MESSAGE;
  state?: string | null;
  status: 'success' | 'error';
  message?: string | null;
  accountName?: string | null;
  expiresAt?: string | null;
};

export function getAuthProxyUrl(): string {
  return `https://${SUPABASE_PROJECT_ID}.supabase.co/functions/v1/api-proxy`;
}

export async function authProxyFetch(path: string, init?: RequestInit): Promise<Response> {
  const {
    data: { session },
  } = await supabase.auth.getSession();
  const token = session?.access_token;

  return fetch(getAuthProxyUrl(), {
    ...init,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      'x-proxy-path': `/api/v1/auth${path}`,
      ...(init?.headers || {}),
    },
  });
}

export function getOAuthPopupFeatures(): string {
  const width = 560;
  const height = 760;
  const left = window.screenX + Math.max(0, Math.round((window.outerWidth - width) / 2));
  const top = window.screenY + Math.max(0, Math.round((window.outerHeight - height) / 2));

  return [
    'popup=yes',
    'resizable=yes',
    'scrollbars=yes',
    `width=${width}`,
    `height=${height}`,
    `left=${left}`,
    `top=${top}`,
  ].join(',');
}

export function persistOAuthRelayResult(result: OAuthRelayResult): void {
  window.localStorage.setItem(POE_OAUTH_RESULT_STORAGE_KEY, JSON.stringify(result));
}

export function consumeOAuthRelayResult(): OAuthRelayResult | null {
  const raw = window.localStorage.getItem(POE_OAUTH_RESULT_STORAGE_KEY);
  if (!raw) return null;
  window.localStorage.removeItem(POE_OAUTH_RESULT_STORAGE_KEY);
  try {
    const parsed = JSON.parse(raw) as OAuthRelayResult;
    if (parsed && parsed.type === POE_OAUTH_MESSAGE && (parsed.status === 'success' || parsed.status === 'error')) {
      return parsed;
    }
  } catch {
    return null;
  }
  return null;
}
