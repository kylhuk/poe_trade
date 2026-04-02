import { forwardRef, useCallback, useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { StatusDot, Freshness } from '@/components/shared/StatusIndicators';
import { api } from '@/services/api';
import type { Service } from '@/types/api';
import { Play, Square, RotateCcw, PlayCircle, StopCircle } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { RenderState } from '@/components/shared/RenderState';
import { useMouseGlow } from '@/hooks/useMouseGlow';

const ServicesTab = forwardRef<HTMLDivElement, Record<string, never>>(function ServicesTab(_props, ref) {
  const [services, setServices] = useState<Service[]>([]);
  const [loading, setLoading] = useState<Record<string, boolean>>({});
  const [error, setError] = useState<string | null>(null);
  const { toast } = useToast();
  const mouseGlow = useMouseGlow();

  const load = useCallback(() => api.getServices().then((next) => {
    setServices(next);
    setError(null);
  }).catch((err: unknown) => {
    setError(err instanceof Error ? err.message : 'Backend unavailable');
  }), []);

  useEffect(() => {
    load();
    const iv = setInterval(load, 5_000);
    return () => clearInterval(iv);
  }, [load]);

  const act = async (id: string, action: 'start' | 'stop' | 'restart') => {
    setLoading(l => ({ ...l, [id]: true }));
    try {
      if (action === 'start') await api.startService(id);
      else if (action === 'stop') await api.stopService(id);
      else await api.restartService(id);
      toast({ title: `Service ${action}ed`, description: `Action completed for ${services.find(s => s.id === id)?.name}` });
      await load();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Service action failed';
      toast({ title: 'Action failed', description: message });
    } finally {
      setLoading(l => ({ ...l, [id]: false }));
    }
  };

  const formatUptime = (s: number | null) => {
    if (!s) return '—';
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    return `${h}h ${m}m`;
  };

  return (
    <div ref={ref} className="space-y-4" data-testid="panel-services-root">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold font-sans text-foreground">Services</h2>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" className="gap-1.5 btn-game" onClick={() => services.forEach(s => s.status !== 'running' && s.allowedActions?.includes('start') && act(s.id, 'start'))}>
            <PlayCircle className="h-4 w-4" /> Start All
          </Button>
          <Button size="sm" variant="outline" className="gap-1.5 btn-game" onClick={() => services.forEach(s => s.status === 'running' && s.allowedActions?.includes('stop') && act(s.id, 'stop'))}>
            <StopCircle className="h-4 w-4" /> Stop All
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {error && <RenderState kind="degraded" message={error} />}
          {services.map(s => (
          <Card key={s.id} data-testid={`service-${s.id}`} className={`card-game ${s.status === 'error' ? 'glow-destructive' : ''}`} onMouseMove={mouseGlow}>
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <StatusDot status={s.status} />
                  <CardTitle className="text-sm font-sans font-semibold">{s.name}</CardTitle>
                </div>
                <span className="text-xs text-muted-foreground capitalize bg-secondary px-2 py-0.5 rounded">{s.type}</span>
              </div>
            </CardHeader>
            <CardContent>
              <p className="text-xs text-muted-foreground mb-3">{s.description}</p>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs mb-3">
                <div>
                  <span className="text-muted-foreground">Status</span>
                  <p className="font-mono text-foreground capitalize">{s.status}</p>
                </div>
                <div>
                  <span className="text-muted-foreground">Uptime</span>
                  <p className="font-mono text-foreground">{formatUptime(s.uptime)}</p>
                </div>
                <div>
                  <span className="text-muted-foreground">Last Crawl</span>
                  <Freshness iso={s.lastCrawl} />
                </div>
                <div>
                  <span className="text-muted-foreground">DB Rows</span>
                  <p className="font-mono text-foreground">{s.rowsInDb?.toLocaleString() ?? '—'}</p>
                </div>
              </div>
              {s.containerInfo && <p className="text-xs text-muted-foreground font-mono mb-3">📦 {s.containerInfo}</p>}
              <div className="flex gap-2">
                <Button data-testid={`service-${s.id}-start`} size="sm" variant="outline" className="gap-1 btn-game" disabled={s.status === 'running' || loading[s.id] || !s.allowedActions?.includes('start')} onClick={() => act(s.id, 'start')}>
                  <Play className="h-3 w-3" /> Start
                </Button>
                <Button data-testid={`service-${s.id}-stop`} size="sm" variant="outline" className="gap-1 btn-game" disabled={s.status === 'stopped' || loading[s.id] || !s.allowedActions?.includes('stop')} onClick={() => act(s.id, 'stop')}>
                  <Square className="h-3 w-3" /> Stop
                </Button>
                <Button data-testid={`service-${s.id}-restart`} size="sm" variant="outline" className="gap-1 btn-game" disabled={loading[s.id] || !s.allowedActions?.includes('restart')} onClick={() => act(s.id, 'restart')}>
                  <RotateCcw className="h-3 w-3" /> Restart
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
});

ServicesTab.displayName = 'ServicesTab';
export default ServicesTab;
