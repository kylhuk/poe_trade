import { cn } from '@/lib/utils';

export function StatusDot({ status }: { status: string }) {
  return (
    <span className={cn(
      'inline-block h-2.5 w-2.5 rounded-full',
      status === 'running' && 'bg-success status-glow-running',
      status === 'stopped' && 'bg-muted-foreground',
      status === 'error' && 'bg-destructive status-glow-error',
      status === 'starting' && 'bg-warning animate-pulse-gold',
      status === 'stopping' && 'bg-warning',
    )} />
  );
}

export function Freshness({ iso }: { iso: string | null }) {
  if (!iso) return <span className="text-muted-foreground text-xs">N/A</span>;
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  const color = mins < 10 ? 'text-success' : mins < 60 ? 'text-warning' : 'text-destructive';
  const label = mins < 60 ? `${mins}m ago` : `${Math.round(mins / 60)}h ago`;
  return <span className={cn('text-xs font-mono', color)}>{label}</span>;
}

export function ConfidenceBadge({ value }: { value: number }) {
  const color = value >= 80 ? 'bg-success/20 text-success' : value >= 50 ? 'bg-warning/20 text-warning' : 'bg-destructive/20 text-destructive';
  return <span className={cn('text-xs px-2 py-0.5 rounded-full font-mono', color)}>{value}%</span>;
}

export function CurrencyValue({ value, currency = 'div' }: { value: number; currency?: string }) {
  return (
    <span className="font-mono text-gold-bright font-medium">
      {value.toFixed(1)} <span className="text-muted-foreground text-xs">{currency}</span>
    </span>
  );
}

export function GradeBadge({ grade }: { grade: 'green' | 'yellow' | 'red' }) {
  const styles = {
    green: 'bg-success/20 text-success border-success/30',
    yellow: 'bg-warning/20 text-warning border-warning/30',
    red: 'bg-destructive/20 text-destructive border-destructive/30',
  };
  return <span className={cn('text-xs px-2 py-0.5 rounded border font-medium uppercase', styles[grade])}>{grade}</span>;
}
