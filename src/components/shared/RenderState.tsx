import { forwardRef, type ReactNode } from 'react';
import { AlertTriangle, CircleOff, Loader2, ShieldAlert, Unplug } from 'lucide-react';

type RenderStateKind =
  | 'loading'
  | 'empty'
  | 'degraded'
  | 'error'
  | 'feature_unavailable'
  | 'disconnected'
  | 'session_expired'
  | 'credentials_missing'
  | 'invalid_input';

const LABELS: Record<RenderStateKind, string> = {
  loading: 'Loading',
  empty: 'Empty',
  degraded: 'Degraded',
  error: 'Error',
  feature_unavailable: 'Feature unavailable',
  disconnected: 'Disconnected',
  session_expired: 'Session expired',
  credentials_missing: 'Credentials missing',
  invalid_input: 'Invalid input',
};

const ICONS: Record<RenderStateKind, ReactNode> = {
  loading: <Loader2 className="h-4 w-4 animate-spin" />,
  empty: <CircleOff className="h-4 w-4" />,
  degraded: <AlertTriangle className="h-4 w-4" />,
  error: <AlertTriangle className="h-4 w-4" />,
  feature_unavailable: <ShieldAlert className="h-4 w-4" />,
  disconnected: <Unplug className="h-4 w-4" />,
  session_expired: <ShieldAlert className="h-4 w-4" />,
  credentials_missing: <ShieldAlert className="h-4 w-4" />,
  invalid_input: <AlertTriangle className="h-4 w-4" />,
};

export const RenderState = forwardRef<HTMLDivElement, { kind: RenderStateKind; message?: string }>(
  ({ kind, message }, ref) => (
    <div
      ref={ref}
      data-testid={`state-${kind}`}
      className="rounded border border-border bg-secondary/30 px-3 py-2 text-xs text-muted-foreground flex items-center gap-2"
    >
      {ICONS[kind]}
      <span>{message || LABELS[kind]}</span>
    </div>
  )
);

RenderState.displayName = 'RenderState';
