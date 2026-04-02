import { forwardRef, useCallback, useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { api } from '@/services/api';
import type { AppMessage, MessageSeverity } from '@/types/api';
import { cn } from '@/lib/utils';
import { Filter } from 'lucide-react';
import { RenderState } from '@/components/shared/RenderState';
import { useMouseGlow } from '@/hooks/useMouseGlow';
import { useToast } from '@/hooks/use-toast';

const severityStyles: Record<MessageSeverity, string> = {
  critical: 'border-l-destructive bg-destructive/5',
  warning: 'border-l-warning bg-warning/5',
  info: 'border-l-info bg-info/5',
};

const severityDot: Record<MessageSeverity, string> = {
  critical: 'bg-destructive status-glow-error',
  warning: 'bg-warning',
  info: 'bg-info',
};

const MessagesTab = forwardRef<HTMLDivElement, Record<string, never>>(function MessagesTab(_props, ref) {
  const [messages, setMessages] = useState<AppMessage[]>([]);
  const [filter, setFilter] = useState<MessageSeverity | 'all'>('all');
  const [error, setError] = useState<string | null>(null);
  const mouseGlow = useMouseGlow();
  const { toast } = useToast();

  const load = useCallback(() => {
    api.getMessages()
      .then((rows) => {
        setMessages(rows);
        setError(null);
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : 'Backend unavailable');
      });
  }, []);

  useEffect(() => {
    load();
    const iv = setInterval(load, 5_000);
    return () => clearInterval(iv);
  }, [load]);

  const filtered = filter === 'all' ? messages : messages.filter(m => m.severity === filter);
  const formatTime = (iso: string) => {
    const d = new Date(iso);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  const acknowledge = async (id: string) => {
    try {
      await api.ackAlert(id);
      toast({ title: 'Success', description: 'Alert acknowledged' });
      load();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to acknowledge alert';
      toast({ title: 'Action failed', description: message });
    }
  };

  return (
    <div ref={ref} className="space-y-4" data-testid="panel-messages-root">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h2 className="text-lg font-semibold font-sans text-foreground">Messages & Alerts</h2>
        <div className="flex items-center gap-1">
          <Filter className="h-4 w-4 text-muted-foreground" />
          {(['all', 'critical', 'warning', 'info'] as const).map(f => (
            <Button
              key={f}
              size="sm"
              variant={filter === f ? 'default' : 'outline'}
              className="text-xs capitalize h-7 btn-game"
              onClick={() => setFilter(f)}
            >
              {f}
            </Button>
          ))}
        </div>
      </div>

      <div className="space-y-2">
        {error && <RenderState kind="degraded" message={error} />}
        {filtered.map(m => (
          <Card key={m.id} data-testid={`message-${m.id}`} className={cn('border-l-4 card-game', severityStyles[m.severity])} onMouseMove={mouseGlow}>
            <CardContent className="p-3">
              <div className="flex items-start gap-3">
                <span className={cn('mt-1.5 h-2 w-2 rounded-full shrink-0', severityDot[m.severity])} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-xs font-mono text-muted-foreground">{formatTime(m.timestamp)}</span>
                    <span className="text-xs bg-secondary px-2 py-0.5 rounded">{m.sourceModule}</span>
                    <span className="text-xs capitalize text-muted-foreground">{m.severity}</span>
                  </div>
                  <p className="text-sm text-foreground">{m.message}</p>
                  <p className="text-xs text-primary mt-1">→ {m.suggestedAction}</p>
                  {m.severity === 'critical' && (
                    <Button
                      data-testid={`message-${m.id}-ack`}
                      size="sm"
                      variant="outline"
                      className="mt-2 h-7 text-xs btn-game"
                      onClick={() => acknowledge(m.id)}
                    >
                      Acknowledge
                    </Button>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
        {filtered.length === 0 && <RenderState kind="empty" message="No messages matching filter" />}
      </div>
    </div>
  );
});

MessagesTab.displayName = 'MessagesTab';
export default MessagesTab;
