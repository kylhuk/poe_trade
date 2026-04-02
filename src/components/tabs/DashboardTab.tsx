import React, { forwardRef, useCallback, useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { StatusDot, Freshness } from '../shared/StatusIndicators';
import { RenderState } from '../shared/RenderState';
import { api } from '../../services/api';
import type { DashboardResponse } from '../../types/api';
import { Activity, AlertTriangle, TrendingUp, Server } from 'lucide-react';
import { useMouseGlow } from '../../hooks/useMouseGlow';

const DashboardTab = forwardRef<HTMLDivElement, Record<string, never>>(function DashboardTab(_props, ref) {
  const [data, setData] = useState<DashboardResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const mouseGlow = useMouseGlow();

  const load = useCallback(() => {
    api.getDashboard()
      .then((response) => {
        setData(response);
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

  const services = data?.services ?? [];
  const summary = data?.summary;
  const topOpportunities = data?.topOpportunities ?? [];

  const running = summary?.running ?? services.filter(s => s.status === 'running').length;
  const total = summary?.total ?? services.length;
  const errors = summary?.errors ?? services.filter(s => s.status === 'error').length;
  const criticals = summary?.criticalAlerts ?? 0;
  const topOpp = summary?.topOpportunity ?? (topOpportunities[0] ? `${topOpportunities[0].strategyId}: ${topOpportunities[0].itemOrMarketKey}` : 'No opportunities');

  return (
    <div ref={ref} className="space-y-6" data-testid="panel-dashboard-root">
      {/* Summary row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <SummaryCard mouseGlow={mouseGlow} icon={<Server className="h-5 w-5 text-primary transition-transform hover:scale-110" />} label="Services Running" value={`${running}/${total}`} />
        <SummaryCard mouseGlow={mouseGlow} icon={<AlertTriangle className="h-5 w-5 text-destructive transition-transform hover:scale-110" />} label="Errors" value={String(errors)} accent={errors > 0 ? 'destructive' : undefined} />
        <SummaryCard mouseGlow={mouseGlow} icon={<Activity className="h-5 w-5 text-warning transition-transform hover:scale-110" />} label="Critical Alerts" value={String(criticals)} accent={criticals > 0 ? 'warning' : undefined} />
        <SummaryCard mouseGlow={mouseGlow} icon={<TrendingUp className="h-5 w-5 text-success transition-transform hover:scale-110" />} label="Top Opportunity" value={topOpp} />
      </div>

      {/* Service health strip */}
      <Card className="card-game" onMouseMove={mouseGlow}>
        <CardHeader className="pb-3">
          <CardTitle className="text-base font-sans font-semibold">Service Health</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-3">
            {error && <RenderState kind="degraded" message={error} />}
            {services.map(s => (
              <div key={s.id} data-testid={`service-${s.id}`} className="flex items-center gap-2 bg-secondary/50 rounded px-3 py-2 text-sm transition-colors hover:bg-secondary">
                <StatusDot status={s.status} />
                <span className="text-foreground">{s.name}</span>
                <Freshness iso={s.lastCrawl} />
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Top opportunities */}
      <Card className="card-game" onMouseMove={mouseGlow}>
        <CardHeader className="pb-3">
          <CardTitle className="text-base font-sans font-semibold">Top Opportunities</CardTitle>
          <p className="text-xs text-muted-foreground">Sorted by expected net chaos per minute of human time</p>
        </CardHeader>
        <CardContent className="space-y-3">
          {topOpportunities.slice(0, 3).map(r => (
            <div key={`${r.scannerRunId}-${r.itemOrMarketKey}`} className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 bg-secondary/30 rounded p-3 border border-border transition-colors hover:border-primary/30">
              <div className="flex-1">
                <span className="text-xs text-muted-foreground font-mono">{r.strategyId}</span>
                <p className="text-sm text-foreground">{r.whyItFired}</p>
              </div>
              <div className="text-right">
                <span className="text-xs px-2 py-1 rounded bg-success/20 text-success font-medium">{r.buyPlan}</span>
              </div>
            </div>
          ))}
          {topOpportunities.length === 0 && <RenderState kind="empty" message="No opportunities right now" />}
        </CardContent>
      </Card>
    </div>
  );
});

DashboardTab.displayName = 'DashboardTab';
export default DashboardTab;

function SummaryCard({ icon, label, value, accent, mouseGlow }: { icon: React.ReactNode; label: string; value: string; accent?: string; mouseGlow: (e: React.MouseEvent<HTMLElement>) => void }) {
  return (
    <Card className={`card-game ${accent === 'destructive' ? 'glow-destructive' : accent === 'warning' ? 'glow-gold' : ''}`} onMouseMove={mouseGlow}>
      <CardContent className="flex items-center gap-4 p-4">
        {icon}
        <div>
          <p className="text-xs text-muted-foreground">{label}</p>
          <p className="text-xl font-semibold font-mono text-foreground">{value}</p>
        </div>
      </CardContent>
    </Card>
  );
}
