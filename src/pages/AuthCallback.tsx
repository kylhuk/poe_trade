import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/services/auth';
import { authProxyFetch, persistOAuthRelayResult, POE_OAUTH_MESSAGE } from '@/services/authProxy';

type CallbackState = 'loading' | 'success' | 'error';

function getErrorMessage(body: unknown, fallback: string): string {
  if (!body || typeof body !== 'object') {
    return fallback;
  }

  const record = body as Record<string, unknown>;
  const message = record.message;
  if (typeof message === 'string' && message.trim()) {
    return message;
  }

  const error = record.error;
  if (typeof error === 'string' && error.trim()) {
    return error;
  }

  if (error && typeof error === 'object') {
    const errorRecord = error as Record<string, unknown>;
    const nestedMessage = errorRecord.message;
    if (typeof nestedMessage === 'string' && nestedMessage.trim()) {
      return nestedMessage;
    }
    const code = errorRecord.code;
    if (typeof code === 'string' && code.trim()) {
      return code;
    }
  }

  return fallback;
}

const AuthCallback = () => {
  const [state, setState] = useState<CallbackState>('loading');
  const [message, setMessage] = useState('Completing PoE login…');
  const navigate = useNavigate();
  const { refreshSession } = useAuth();

  useEffect(() => {
    let cancelled = false;
    const params = new URLSearchParams(window.location.search);
    const code = params.get('code');
    const stateParam = params.get('state');
    const error = params.get('error');
    const errorDescription = params.get('error_description');

    window.history.replaceState({}, '', window.location.pathname);

    const notifyOpener = (status: 'success' | 'error', detailMessage?: string) => {
      if (window.opener && !window.opener.closed) {
        window.opener.postMessage({ type: POE_OAUTH_MESSAGE, status, message: detailMessage }, window.location.origin);
      }
    };

    if (error) {
      persistOAuthRelayResult({
        type: POE_OAUTH_MESSAGE,
        state: stateParam,
        status: 'error',
        message: errorDescription || error,
      });
      setState('error');
      setMessage(errorDescription || error);
      notifyOpener('error', errorDescription || error);
      return;
    }

    if (!code || !stateParam) {
      persistOAuthRelayResult({
        type: POE_OAUTH_MESSAGE,
        status: 'error',
        message: 'Missing OAuth parameters',
      });
      setState('error');
      setMessage('Missing OAuth parameters');
      notifyOpener('error', 'Missing OAuth parameters');
      return;
    }

    const relay = async () => {
      try {
        const response = await authProxyFetch(`/callback?code=${encodeURIComponent(code)}&state=${encodeURIComponent(stateParam)}`);
        if (!response.ok) {
          const body = await response.json().catch(() => ({}));
          throw new Error(getErrorMessage(body, `Callback failed (${response.status})`));
        }

        const body = await response.json().catch(() => ({}));

        let confirmed = null;
        for (let attempt = 0; attempt < 5; attempt += 1) {
          const session = await refreshSession();
          if (session && session.status === 'connected' && session.accountName) {
            confirmed = session;
            break;
          }
          if (attempt < 4) {
            await new Promise((resolve) => window.setTimeout(resolve, 200));
          }
        }

        if (!confirmed) {
          throw new Error('Path of Exile session was not confirmed');
        }

        persistOAuthRelayResult({
          type: POE_OAUTH_MESSAGE,
          state: stateParam,
          status: 'success',
          accountName: confirmed.accountName,
          expiresAt: confirmed.expiresAt ?? body.expiresAt ?? null,
          message: 'Path of Exile connected. Closing window…',
        });

        if (cancelled) return;
        setState('success');
        setMessage('Path of Exile connected. Closing window…');
        notifyOpener('success');

        window.setTimeout(() => {
          window.close();
          navigate('/', { replace: true });
        }, 400);
      } catch (err) {
        if (cancelled) return;
        const detail = err instanceof Error ? err.message : 'Login failed';
        persistOAuthRelayResult({
          type: POE_OAUTH_MESSAGE,
          state: stateParam,
          status: 'error',
          message: detail,
        });
        setState('error');
        setMessage(detail);
        notifyOpener('error', detail);
      }
    };

    void relay();
    return () => {
      cancelled = true;
    };
  }, [navigate, refreshSession]);

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      <div className="max-w-sm text-center space-y-3">
        {state === 'loading' && (
          <div className="flex items-center justify-center gap-2">
            <div className="h-4 w-4 border-2 border-primary border-t-transparent rounded-full animate-spin" />
            <p className="text-muted-foreground text-sm font-mono">{message}</p>
          </div>
        )}
        {state === 'success' && <p className="text-primary text-sm font-mono">{message}</p>}
        {state === 'error' && (
          <>
            <p className="text-destructive text-sm font-mono">{message}</p>
            <button
              type="button"
              onClick={() => navigate('/', { replace: true })}
              className="text-xs text-muted-foreground hover:text-foreground underline transition-colors"
            >
              Return to app
            </button>
          </>
        )}
      </div>
    </div>
  );
};

export default AuthCallback;
