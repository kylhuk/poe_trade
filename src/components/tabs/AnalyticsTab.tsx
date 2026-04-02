import { forwardRef, useCallback, useEffect, useState } from 'react';
import { Slider } from '@/components/ui/slider';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Freshness } from '@/components/shared/StatusIndicators';
import { CheckCircle2, XCircle } from 'lucide-react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { 
  getAnalyticsIngestion, 
  getAnalyticsScanner, 
  getAnalyticsPricingOutliers,
  getAnalyticsSearchHistory,
  getAnalyticsSearchSuggestions,
  type IngestionRow,
  type ScannerAnalyticsResponse,
} from '@/services/api';
import { api } from '@/services/api';
import type { MlAutomationStatus, MlAutomationHistory, MlAutomationObservability, PricingOutliersResponse, SearchHistoryResponse, SearchSuggestion } from '@/types/api';
import { RenderState } from '@/components/shared/RenderState';
import { Progress } from '@/components/ui/progress';

interface AnalyticsTabProps {
  subtab?: string;
  onSubtabChange?: (subtab: string) => void;
}

const AnalyticsTab = forwardRef<HTMLDivElement, AnalyticsTabProps>(function AnalyticsTab({ subtab, onSubtabChange }, ref) {
  const activeSubtab = subtab || "ingestion";
  const handleSubtabChange = (value: string) => {
    if (onSubtabChange) onSubtabChange(value);
  };
  return (
    <div ref={ref}>
    <Tabs value={activeSubtab} onValueChange={handleSubtabChange} className="space-y-4">
      <TabsList className="flex-wrap h-auto gap-1 bg-secondary/50 p-1">
        <TabsTrigger data-testid="analytics-tab-ingestion" value="ingestion" className="tab-game text-xs">Ingestion</TabsTrigger>
        <TabsTrigger data-testid="analytics-tab-scanner" value="scanner" className="tab-game text-xs">Scanner</TabsTrigger>
        <TabsTrigger data-testid="analytics-tab-ml" value="ml" className="tab-game text-xs">ML</TabsTrigger>
        <TabsTrigger data-testid="analytics-tab-search" value="search" className="tab-game text-xs">Search</TabsTrigger>
        <TabsTrigger data-testid="analytics-tab-outliers" value="outliers" className="tab-game text-xs">Outliers</TabsTrigger>
      </TabsList>

      <TabsContent data-testid="analytics-panel-ingestion" value="ingestion"><IngestionPanel /></TabsContent>
      <TabsContent data-testid="analytics-panel-scanner" value="scanner"><ScannerPanel /></TabsContent>
      <TabsContent data-testid="analytics-panel-ml" value="ml"><MlPanel /></TabsContent>
      <TabsContent data-testid="analytics-panel-search" value="search"><SearchHistoryPanel /></TabsContent>
      <TabsContent data-testid="analytics-panel-outliers" value="outliers"><PricingOutliersPanel /></TabsContent>
    </Tabs>
    </div>
  );
});

AnalyticsTab.displayName = 'AnalyticsTab';
export default AnalyticsTab;

function IngestionPanel() {
  const [items, setItems] = useState<IngestionRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => {
    getAnalyticsIngestion()
      .then(setItems)
      .catch(err => setError(err instanceof Error ? err.message : 'Failed to load ingestion analytics'));
  }, []);
  useEffect(() => { load(); const iv = setInterval(load, 5_000); return () => clearInterval(iv); }, [load]);

  if (error) return <RenderState kind="degraded" message={error} />;
  if (items.length === 0) return <RenderState kind="empty" message="No ingestion data available" />;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      {items.map((item) => (
        <Card key={item.queue_key} className="card-game">
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm font-sans">{item.queue_key}</CardTitle>
              <span className="text-xs bg-secondary px-2 py-0.5 rounded">{item.feed_kind}</span>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex items-center justify-between text-xs">
              <span className="text-muted-foreground">Status: <span className="text-foreground font-mono">{item.status}</span></span>
              <Freshness iso={item.last_ingest_at} />
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function ScannerPanel() {
  const [data, setData] = useState<ScannerAnalyticsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => {
    getAnalyticsScanner()
      .then(setData)
      .catch(err => setError(err instanceof Error ? err.message : 'Failed to load scanner analytics'));
  }, []);
  useEffect(() => { load(); const iv = setInterval(load, 5_000); return () => clearInterval(iv); }, [load]);

  if (error) return <RenderState kind="degraded" message={error} />;
  if (!data || data.rows.length === 0) return <RenderState kind="empty" message="No scanner data available" />;

  const totalRecs = data.rows.reduce((s, r) => s + r.recommendation_count, 0);
  const totalCandidates = data.rows.reduce((s, r) => s + r.candidate_count, 0);
  const enabledCount = data.rows.filter(r => r.enabled).length;

  return (
    <div className="space-y-4">
      {/* Summary bar */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Card className="card-game">
          <CardContent className="p-3 text-center">
            <p className="text-[10px] text-muted-foreground">Strategies</p>
            <p className="text-lg font-mono text-foreground">{enabledCount}<span className="text-xs text-muted-foreground">/{data.rows.length}</span></p>
          </CardContent>
        </Card>
        <Card className="card-game">
          <CardContent className="p-3 text-center">
            <p className="text-[10px] text-muted-foreground">Recommendations</p>
            <p className="text-lg font-mono text-warning">{totalRecs}</p>
          </CardContent>
        </Card>
        <Card className="card-game">
          <CardContent className="p-3 text-center">
            <p className="text-[10px] text-muted-foreground">Candidates</p>
            <p className="text-lg font-mono text-foreground">{totalCandidates}</p>
          </CardContent>
        </Card>
        {data.latestRunId && (
          <Card className="card-game">
            <CardContent className="p-3 text-center">
              <p className="text-[10px] text-muted-foreground">Latest Run</p>
              <p className="text-xs font-mono text-foreground truncate">{data.latestRunId.slice(0, 12)}…</p>
            </CardContent>
          </Card>
        )}
      </div>

      {/* Strategy rows */}
      <Card className="card-game">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-sans">Strategies</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="text-xs">Strategy</TableHead>
                <TableHead className="text-xs text-center">Enabled</TableHead>
                <TableHead className="text-xs text-right">Recs</TableHead>
                <TableHead className="text-xs text-right">Accepted</TableHead>
                <TableHead className="text-xs text-right">Rejected</TableHead>
                <TableHead className="text-xs text-right">Candidates</TableHead>
                <TableHead className="text-xs">Top Rejection</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.rows.map((item, i) => (
                <TableRow key={i}>
                  <TableCell className="text-xs font-mono">{item.strategy_id}</TableCell>
                  <TableCell className="text-center">
                    {item.enabled
                      ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400 mx-auto" />
                      : <XCircle className="h-3.5 w-3.5 text-muted-foreground mx-auto" />}
                  </TableCell>
                  <TableCell className="text-xs text-right font-mono">{item.recommendation_count}</TableCell>
                  <TableCell className="text-xs text-right font-mono">{item.accepted_count}</TableCell>
                  <TableCell className="text-xs text-right font-mono">{item.rejected_count}</TableCell>
                  <TableCell className="text-xs text-right font-mono">{item.candidate_count}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">{item.top_rejection_reason ?? '—'}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Gate Rejections */}
      {data.gateRejections.length > 0 && (
        <Card className="card-game">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-sans">Gate Rejections</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {data.gateRejections.map((g, i) => (
                <div key={i} className="flex items-center justify-between text-xs rounded border border-border bg-secondary/30 px-3 py-2">
                  <span className="font-mono text-foreground">{g.decision_reason.replace(/_/g, ' ')}</span>
                  <Badge variant="outline" className="text-[10px] font-mono">{g.rejection_count}</Badge>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Complexity Tiers */}
      {data.complexityTiers.length > 0 && (
        <Card className="card-game">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-sans">Complexity Tiers</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex gap-3">
              {data.complexityTiers.map((t, i) => (
                <div key={i} className="text-xs text-center">
                  <span className="text-muted-foreground">{t.complexity_tier ?? 'unset'}</span>
                  <p className="font-mono text-foreground">{t.tier_count}</p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}


function statusColor(status: string): string {
  if (!status || status === 'unknown' || status === 'no_runs') return 'bg-muted text-muted-foreground border-border';
  if (status === 'completed' || status.startsWith('passed') || status === 'promoted' || status === 'succeeded' || status === 'ready') {
    return 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30';
  }
  if (status === 'running' || status.includes('running') || status === 'in_progress') {
    return 'bg-sky-500/20 text-sky-400 border-sky-500/30';
  }
  if (status === 'hold' || status.includes('hold') || status === 'failed_gates' || status === 'stopped_budget' || status === 'stopped_no_improvement') {
    return 'bg-amber-500/20 text-amber-400 border-amber-500/30';
  }
  return 'bg-destructive/20 text-destructive border-destructive/30';
}

function verdictColor(verdict: string): string {
  if (!verdict || verdict === 'unknown' || verdict === 'none') return 'bg-muted text-muted-foreground border-border';
  if (verdict === 'promote') return 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30';
  if (verdict === 'hold') return 'bg-amber-500/20 text-amber-400 border-amber-500/30';
  return 'bg-destructive/20 text-destructive border-destructive/30';
}

function humanize(s: string): string {
  return s.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function MlPanel() {
  const [status, setStatus] = useState<MlAutomationStatus | null>(null);
  const [history, setHistory] = useState<MlAutomationHistory | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    Promise.all([api.getMlAutomationStatus(), api.getMlAutomationHistory()])
      .then(([nextStatus, nextHistory]) => {
        setStatus(nextStatus);
        setHistory(nextHistory);
        setError(null);
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : 'Failed to load live ML data');
      })
      .finally(() => {
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    load();
    const iv = setInterval(load, 5_000);
    return () => clearInterval(iv);
  }, [load]);

  if (error) return <RenderState kind="degraded" message={error} />;
  if (loading && !status && !history) return <RenderState kind="loading" message="Loading live ML data…" />;

  return <MlAutomationPanel status={status} history={history} />;
}

function MlAutomationPanel({
  status,
  history,
}: {
  status: MlAutomationStatus | null;
  history: MlAutomationHistory | null;
}) {
  const summary = history?.summary ?? null;
  const qualityTrend = history?.qualityTrend ?? [];
  const trainingCadence = history?.trainingCadence ?? [];
  const routeMetrics = history?.routeMetrics ?? [];
  const datasetCoverage = history?.datasetCoverage ?? null;
  const promotions = history?.promotions ?? [];
  const runs = history?.history ?? [];
  const observability = status?.observability ?? history?.observability ?? null;

  const mdapeTrendData = qualityTrend
    .filter((point) => point.avgMdape != null)
    .map((point, index) => ({
      label: point.updatedAt ? formatMiniDate(point.updatedAt) : `Run ${index + 1}`,
      value: point.avgMdape != null ? Number((point.avgMdape * 100).toFixed(2)) : null,
    }));
  const coverageTrendData = qualityTrend
    .filter((point) => point.avgIntervalCoverage != null)
    .map((point, index) => ({
      label: point.updatedAt ? formatMiniDate(point.updatedAt) : `Run ${index + 1}`,
      value: point.avgIntervalCoverage != null ? Number((point.avgIntervalCoverage * 100).toFixed(2)) : null,
    }));
  const cadenceData = trainingCadence.map((point) => ({
    label: point.date.slice(5),
    runs: point.runs,
  }));
  const summaryCards = summary
    ? [
        { label: 'Runs / 7d', value: String(summary.runsLast7d) },
        { label: 'Runs / 30d', value: String(summary.runsLast30d) },
        summary.medianHoursBetweenRuns != null
          ? { label: 'Median cadence', value: `${summary.medianHoursBetweenRuns.toFixed(1)}h` }
          : null,
        summary.latestAvgMdape != null
          ? { label: 'Latest MDAPE', value: formatPct(summary.latestAvgMdape) }
          : null,
        summary.latestAvgIntervalCoverage != null
          ? { label: 'Latest coverage', value: formatPct(summary.latestAvgIntervalCoverage) }
          : null,
        summary.bestAvgMdape != null
          ? { label: 'Best MDAPE', value: formatPct(summary.bestAvgMdape) }
          : null,
        summary.trendDirection !== 'unknown'
          ? {
              label: 'Trend',
              value: humanize(summary.trendDirection),
              detail: summary.mdapeDeltaVsPrevious != null
                ? `${summary.mdapeDeltaVsPrevious >= 0 ? '+' : ''}${(summary.mdapeDeltaVsPrevious * 100).toFixed(1)} pts`
                : undefined,
            }
          : null,
      ].filter(Boolean) as Array<{ label: string; value: string; detail?: string }>
    : [];
  const hasDatasetCoverage = Boolean(
    datasetCoverage && (
      datasetCoverage.totalRows > 0 ||
      datasetCoverage.supportedRows > 0 ||
      datasetCoverage.routes.length > 0
    )
  );

  return (
    <div className="space-y-4">
      {status && (
        <Card className="card-game">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-sans">Automation Status</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-x-6 gap-y-3 text-xs">
              {hasText(status.league) && (
                <div>
                  <span className="text-muted-foreground">League</span>
                  <p className="font-mono text-foreground">{status.league}</p>
                </div>
              )}
              {hasText(status.activeModelVersion) && (
                <div>
                  <span className="text-muted-foreground">Active Model</span>
                  <p className="font-mono text-foreground">{status.activeModelVersion}</p>
                </div>
              )}
              {hasText(status.status) && (
                <div>
                  <span className="text-muted-foreground">Status</span>
                  <div className="mt-0.5">
                    <Badge className={statusColor(status.status ?? '')}>{humanize(status.status ?? '')}</Badge>
                  </div>
                </div>
              )}
              {hasText(status.promotionVerdict) && (
                <div>
                  <span className="text-muted-foreground">Verdict</span>
                  <div className="mt-0.5">
                    <Badge className={verdictColor(status.promotionVerdict ?? '')}>{humanize(status.promotionVerdict ?? '')}</Badge>
                  </div>
                </div>
              )}
              {status.latestRun && (
                <div className="col-span-2 sm:col-span-4">
                  <span className="text-muted-foreground">Latest Run</span>
                  <div className="flex flex-wrap items-center gap-3 mt-1">
                    {hasText(status.latestRun.runId) && <span className="font-mono text-foreground truncate">{status.latestRun.runId}</span>}
                    {hasText(status.latestRun.status) && (
                      <Badge className={statusColor(status.latestRun.status ?? '')}>{humanize(status.latestRun.status ?? '')}</Badge>
                    )}
                    {hasText(status.latestRun.updatedAt) && (
                      <span className="text-muted-foreground">{formatDateTimeShort(status.latestRun.updatedAt ?? '')}</span>
                    )}
                    {hasText(status.latestRun.stopReason) && (
                      <span className="text-muted-foreground">{humanize(status.latestRun.stopReason ?? '')}</span>
                    )}
                  </div>
                </div>
              )}
              {status.trainerRuntime && hasRenderableTrainerRuntime(status.trainerRuntime) && (
                <div className="col-span-2 sm:col-span-4 border-t border-border pt-3 mt-1">
                  <span className="text-muted-foreground font-medium">Trainer Runtime</span>
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-2 mt-2">
                    {hasText(status.trainerRuntime.stage) && (
                      <div>
                        <span className="text-muted-foreground">Stage</span>
                        <p className="font-mono text-foreground">{status.trainerRuntime.stage}</p>
                      </div>
                    )}
                    {hasText(status.trainerRuntime.status) && (
                      <div>
                        <span className="text-muted-foreground">Status</span>
                        <div className="mt-0.5">
                          <Badge className={statusColor(status.trainerRuntime.status ?? '')}>{humanize(status.trainerRuntime.status ?? '')}</Badge>
                        </div>
                      </div>
                    )}
                    {hasText(status.trainerRuntime.updatedAt) && (
                      <div>
                        <span className="text-muted-foreground">Updated</span>
                        <p className="font-mono text-foreground">{formatDateTimeShort(status.trainerRuntime.updatedAt ?? '')}</p>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {summaryCards.length > 0 && (
        <div className="grid grid-cols-2 xl:grid-cols-5 gap-4">
          {summaryCards.map((card) => (
            <MlSummaryMetricCard key={card.label} label={card.label} value={card.value} detail={card.detail} />
          ))}
        </div>
      )}

      {(mdapeTrendData.length > 0 || coverageTrendData.length > 0 || cadenceData.length > 0) && (
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
          {mdapeTrendData.length > 0 && <MlLineChartCard title="MDAPE trend" data={mdapeTrendData} emptyMessage="No MDAPE data" suffix="%" />}
          {coverageTrendData.length > 0 && <MlLineChartCard title="Coverage trend" data={coverageTrendData} emptyMessage="No coverage data" suffix="%" />}
          {cadenceData.length > 0 && <MlBarChartCard title="Training cadence" data={cadenceData} emptyMessage="No cadence data" />}
        </div>
      )}

      {hasDatasetCoverage && datasetCoverage && (
        <Card className="card-game">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-sans">Dataset coverage</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 xl:grid-cols-4 gap-4 text-xs">
              <div>
                <span className="text-muted-foreground">Total Rows</span>
                <p className="font-mono text-foreground">{formatCompact(datasetCoverage.totalRows)}</p>
              </div>
              <div>
                <span className="text-muted-foreground">Supported Rows</span>
                <p className="font-mono text-foreground">{formatCompact(datasetCoverage.supportedRows)}</p>
              </div>
              <div>
                <span className="text-muted-foreground">Coverage Ratio</span>
                <p className="font-mono text-foreground">{formatPct(datasetCoverage.coverageRatio)}</p>
              </div>
              {datasetCoverage.baseTypeCount != null && (
                <div>
                  <span className="text-muted-foreground">Base Types</span>
                  <p className="font-mono text-foreground">{formatCompact(datasetCoverage.baseTypeCount)}</p>
                </div>
              )}
            </div>
            {datasetCoverage.routes.length > 0 && (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="text-xs">Route</TableHead>
                    <TableHead className="text-xs text-right">Rows</TableHead>
                    <TableHead className="text-xs text-right">Share</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {datasetCoverage.routes.map((route) => (
                    <TableRow key={route.route ?? 'unknown'}>
                      <TableCell className="text-xs font-mono">{route.route ?? 'unknown'}</TableCell>
                      <TableCell className="text-xs font-mono text-right">{formatCompact(route.rows)}</TableCell>
                      <TableCell className="text-xs font-mono text-right">{formatPct(route.share)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      )}

      {routeMetrics.length > 0 && (
        <Card className="card-game">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-sans">Route metrics</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-xs">Route</TableHead>
                  <TableHead className="text-xs text-right">Samples</TableHead>
                  <TableHead className="text-xs text-right">MDAPE</TableHead>
                  <TableHead className="text-xs text-right">Coverage</TableHead>
                  <TableHead className="text-xs text-right">Abstain</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {routeMetrics.map((route) => (
                  <TableRow key={route.route ?? 'unknown'}>
                    <TableCell className="text-xs font-mono">{route.route ?? 'unknown'}</TableCell>
                    <TableCell className="text-xs font-mono text-right">{route.sampleCount != null ? formatCompact(route.sampleCount) : ''}</TableCell>
                    <TableCell className="text-xs font-mono text-right">{formatPct(route.avgMdape)}</TableCell>
                    <TableCell className="text-xs font-mono text-right">{formatPct(route.avgIntervalCoverage)}</TableCell>
                    <TableCell className="text-xs font-mono text-right">{formatPct(route.avgAbstainRate)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {promotions.length > 0 && (
        <Card className="card-game">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-sans">Model promotions</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-xs">Model</TableHead>
                  <TableHead className="text-xs">Promoted At</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {promotions.map((row) => (
                  <TableRow key={`${row.modelVersion ?? 'unknown'}-${row.promotedAt ?? 'none'}`}>
                    <TableCell className="text-xs font-mono">{row.modelVersion ?? ''}</TableCell>
                    <TableCell className="text-xs text-muted-foreground">{row.promotedAt ? formatDateTimeShort(row.promotedAt) : ''}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {observability && <ObservabilityPanel observability={observability} />}

      {runs.length > 0 && (
        <Card className="card-game">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-sans">Run History</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-xs">Run ID</TableHead>
                  <TableHead className="text-xs">Status</TableHead>
                  <TableHead className="text-xs">Verdict</TableHead>
                  <TableHead className="text-xs text-right">Rows</TableHead>
                  <TableHead className="text-xs text-right">MDAPE</TableHead>
                  <TableHead className="text-xs text-right">Coverage</TableHead>
                  <TableHead className="text-xs">Updated</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {runs.map((run) => (
                  <TableRow key={run.runId ?? 'unknown'}>
                    <TableCell className="text-xs font-mono truncate max-w-[160px]">{run.runId ?? ''}</TableCell>
                    <TableCell>
                      {hasText(run.status) ? <Badge className={`text-xs ${statusColor(run.status ?? '')}`}>{humanize(run.status ?? '')}</Badge> : null}
                    </TableCell>
                    <TableCell>
                      {hasText(run.verdict) ? <Badge className={`text-xs ${verdictColor(run.verdict ?? '')}`}>{humanize(run.verdict ?? '')}</Badge> : null}
                    </TableCell>
                    <TableCell className="text-xs font-mono text-right">{run.rowsProcessed != null ? formatCompact(run.rowsProcessed) : ''}</TableCell>
                    <TableCell className="text-xs font-mono text-right">{formatPct(run.avgMdape)}</TableCell>
                    <TableCell className="text-xs font-mono text-right">{formatPct(run.avgIntervalCoverage)}</TableCell>
                    <TableCell className="text-xs text-muted-foreground">{run.updatedAt ? formatDateTimeShort(run.updatedAt) : ''}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function ObservabilityPanel({ observability }: { observability: MlAutomationObservability }) {
  return (
    <Card className="card-game">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-sans">Observability</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-x-6 gap-y-3 text-xs">
          <div>
            <span className="text-muted-foreground">Dataset Rows</span>
            <p className="font-mono text-foreground">{formatCompact(observability.datasetRows)}</p>
          </div>
          <div>
            <span className="text-muted-foreground">Promoted Models</span>
            <p className="font-mono text-foreground">{observability.promotedModels}</p>
          </div>
          <div>
            <span className="text-muted-foreground">Eval Runs</span>
            <p className="font-mono text-foreground">{observability.evalRuns}</p>
          </div>
          <div>
            <span className="text-muted-foreground">Eval Sample Rows</span>
            <p className="font-mono text-foreground">{formatCompact(observability.evalSampleRows)}</p>
          </div>
          <div>
            <span className="text-muted-foreground">Evaluation Available</span>
            <div className="mt-0.5">
              {observability.evaluationAvailable
                ? <span className="text-emerald-400">Yes</span>
                : <span className="text-muted-foreground">No</span>}
            </div>
          </div>
          {observability.latestTrainingAsOf && (
            <div>
              <span className="text-muted-foreground">Latest Training</span>
              <p className="font-mono text-foreground">{formatDateTimeShort(observability.latestTrainingAsOf)}</p>
            </div>
          )}
          {observability.latestPromotionAt && (
            <div>
              <span className="text-muted-foreground">Latest Promotion</span>
              <p className="font-mono text-foreground">{formatDateTimeShort(observability.latestPromotionAt)}</p>
            </div>
          )}
          {observability.latestEvalAt && (
            <div>
              <span className="text-muted-foreground">Latest Eval</span>
              <p className="font-mono text-foreground">{formatDateTimeShort(observability.latestEvalAt)}</p>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}



function MlSummaryMetricCard({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <Card className="card-game">
      <CardContent className="p-4">
        <span className="text-xs text-muted-foreground">{label}</span>
        <p className="text-lg font-mono text-foreground">{value}</p>
        {detail ? <p className="text-[11px] text-muted-foreground mt-1">{detail}</p> : null}
      </CardContent>
    </Card>
  );
}

function MlLineChartCard({ title, data, emptyMessage, suffix }: { title: string; data: Array<{ label: string; value: number | null }>; emptyMessage: string; suffix?: string }) {
  return (
    <Card className="card-game">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-sans">{title}</CardTitle>
      </CardHeader>
      <CardContent className="h-56">
        {data.length > 0 ? (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-border/40" />
              <XAxis dataKey="label" tick={{ fontSize: 11 }} minTickGap={16} />
              <YAxis tick={{ fontSize: 11 }} width={40} />
              <RechartsTooltip formatter={(value: number) => [`${value.toFixed(1)}${suffix ?? ''}`, title]} />
              <Line type="monotone" dataKey="value" stroke="#60a5fa" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <RenderState kind="empty" message={emptyMessage} />
        )}
      </CardContent>
    </Card>
  );
}

function MlBarChartCard({ title, data, emptyMessage }: { title: string; data: Array<{ label: string; runs: number }>; emptyMessage: string }) {
  return (
    <Card className="card-game">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-sans">{title}</CardTitle>
      </CardHeader>
      <CardContent className="h-56">
        {data.length > 0 ? (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-border/40" />
              <XAxis dataKey="label" tick={{ fontSize: 11 }} minTickGap={12} />
              <YAxis tick={{ fontSize: 11 }} allowDecimals={false} width={32} />
              <RechartsTooltip formatter={(value: number) => [value, 'Runs']} />
              <Bar dataKey="runs" fill="#34d399" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <RenderState kind="empty" message={emptyMessage} />
        )}
      </CardContent>
    </Card>
  );
}

function formatPct(value: number | null | undefined): string {
  if (value == null) return '—';
  return `${(value * 100).toFixed(1)}%`;
}

function hasText(value: string | null | undefined): value is string {
  return typeof value === 'string' && value.trim().length > 0;
}

function hasRenderableTrainerRuntime(runtime: MlAutomationStatus['trainerRuntime']): boolean {
  return Boolean(
    runtime.stage || runtime.status || runtime.updatedAt || Object.keys(runtime.details || {}).length > 0
  );
}

function formatCompact(value: number): string {
  return Intl.NumberFormat(undefined, { notation: 'compact', maximumFractionDigits: 1 }).format(value);
}

function formatDateTimeShort(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
}

function formatMiniDate(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return `${parsed.getMonth() + 1}/${parsed.getDate()}`;
}

const OUTLIERS_DEFAULTS = {
  sort: 'expected_profit',
  order: 'desc' as const,
  minTotal: 25,
  
  limit: 100,
};

const OUTLIER_SORT_OPTIONS = [
  { value: 'expected_profit', label: 'Expected Profit' },
  { value: 'roi', label: 'ROI' },
  { value: 'underpriced_rate', label: 'Underpriced Rate' },
  { value: 'items_total', label: 'Items Total' },
  { value: 'item_name', label: 'Item name' },
] as const;

const OUTLIER_ORDER_OPTIONS = [
  { value: 'desc', label: 'Descending' },
  { value: 'asc', label: 'Ascending' },
] as const;


type HistogramBucket = {
  bucketStart: number | string;
  bucketEnd: number | string;
  count: number;
};

const SEARCH_HISTORY_DEFAULTS = {
  sort: 'item_name',
  order: 'asc' as const,
};

function SearchHistoryPanel() {
  const [query, setQuery] = useState('');
  const [suggestions, setSuggestions] = useState<SearchSuggestion[]>([]);
  const [data, setData] = useState<SearchHistoryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [league, setLeague] = useState('');
  const [sort, setSort] = useState(SEARCH_HISTORY_DEFAULTS.sort);
  const [order, setOrder] = useState<'asc' | 'desc'>(SEARCH_HISTORY_DEFAULTS.order);
  const [priceMin, setPriceMin] = useState<number | undefined>();
  const [priceMax, setPriceMax] = useState<number | undefined>();
  const [committedPriceMin, setCommittedPriceMin] = useState<number | undefined>();
  const [committedPriceMax, setCommittedPriceMax] = useState<number | undefined>();
  const [timeFrom, setTimeFrom] = useState<string | undefined>();
  const [timeTo, setTimeTo] = useState<string | undefined>();
  const [committedTimeFrom, setCommittedTimeFrom] = useState<string | undefined>();
  const [committedTimeTo, setCommittedTimeTo] = useState<string | undefined>();

  useEffect(() => {
    const normalizedQuery = query.trim();
    if (normalizedQuery.length < 2) {
      setSuggestions([]);
      return;
    }
    let cancelled = false;
    const timer = window.setTimeout(() => {
      getAnalyticsSearchSuggestions(normalizedQuery)
        .then(payload => {
          if (!cancelled) {
            setSuggestions(payload.suggestions);
          }
        })
        .catch(() => {
          if (!cancelled) {
            setSuggestions([]);
          }
        });
    }, 150);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [query]);

  useEffect(() => {
    const normalizedQuery = query.trim();
    if (normalizedQuery.length < 2) {
      setData(null);
      setError(null);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setData(null);
    setError(null);
    setLoading(true);
    const timer = window.setTimeout(() => {
      getAnalyticsSearchHistory({
        query: normalizedQuery,
        league,
        sort,
        order,
        priceMin: committedPriceMin,
        priceMax: committedPriceMax,
        timeFrom: committedTimeFrom,
        timeTo: committedTimeTo,
        limit: 100,
      })
        .then(payload => {
          if (!cancelled) {
            setData(payload);
            setError(null);
          }
        })
        .catch(err => {
          if (!cancelled) {
            setData(null);
            setError(err instanceof Error ? err.message : 'Failed to load search history');
          }
        })
        .finally(() => { if (!cancelled) setLoading(false); });
    }, 250);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [query, league, sort, order, committedPriceMin, committedPriceMax, committedTimeFrom, committedTimeTo]);

  const priceFloor = data?.filters.price.min ?? 0;
  const priceCeiling = Math.max(data?.filters.price.max ?? 0, priceFloor);
  const priceStep = calculateStep(priceFloor, priceCeiling);

  const timeRangeMin = toUnixMs(data?.filters.datetime.min);
  const timeRangeMax = toUnixMs(data?.filters.datetime.max);
  const hasTimeRange = timeRangeMin !== null && timeRangeMax !== null && timeRangeMax >= timeRangeMin;
  const timeStep = hasTimeRange && timeRangeMin !== null && timeRangeMax !== null
    ? calculateStep(timeRangeMin, timeRangeMax)
    : 1;

  const applyHistorySort = (nextSort: string) => {
    if (sort === nextSort) {
      setOrder(current => current === 'asc' ? 'desc' : 'asc');
      return;
    }
    setSort(nextSort);
    setOrder(nextSort === 'added_on' ? 'desc' : 'asc');
  };

  const resetFilters = () => {
    setLeague('');
    setPriceMin(undefined);
    setPriceMax(undefined);
    setCommittedPriceMin(undefined);
    setCommittedPriceMax(undefined);
    setTimeFrom(undefined);
    setTimeTo(undefined);
    setCommittedTimeFrom(undefined);
    setCommittedTimeTo(undefined);
    setSort(SEARCH_HISTORY_DEFAULTS.sort);
    setOrder(SEARCH_HISTORY_DEFAULTS.order);
  };

  return (
    <div className="space-y-4">
      <Card className="card-game">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-sans">Global Item Search</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 lg:grid-cols-[minmax(0,2fr)_minmax(180px,1fr)_auto] items-end">
            <label className="text-xs text-muted-foreground space-y-1">
              <span>Item name</span>
              <input
                data-testid="search-history-input"
                list="search-history-item-suggestions"
                value={query}
                onChange={event => setQuery(event.target.value)}
                placeholder="Start typing an item name"
                title="Suggestions come from ClickHouse and help you choose the exact item name."
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground"
              />
              <datalist id="search-history-item-suggestions">
                {suggestions.map(suggestion => (
                  <option key={`${suggestion.itemKind}-${suggestion.itemName}`} value={suggestion.itemName}>
                    {`${suggestion.itemKind} · ${suggestion.matchCount}`}
                  </option>
                ))}
              </datalist>
            </label>

            <label className="text-xs text-muted-foreground space-y-1">
              <span>League</span>
              <select
                data-testid="search-history-league"
                value={league}
                onChange={event => setLeague(event.target.value)}
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground"
              >
                <option value="">Default league</option>
                {(data?.filters.leagueOptions ?? []).map(option => (
                  <option key={option} value={option}>{option}</option>
                ))}
              </select>
            </label>

            <Button type="button" variant="outline" className="w-full lg:w-auto" onClick={resetFilters}>
              Reset filters
            </Button>
          </div>

          {suggestions.length > 0 && (
            <div data-testid="search-history-suggestions" className="flex flex-wrap gap-2">
              {suggestions.map(suggestion => (
                <button
                  key={`${suggestion.itemKind}-${suggestion.itemName}`}
                  data-testid="search-history-suggestion"
                  type="button"
                  title={`${suggestion.itemKind} · ${suggestion.matchCount} matches`}
                  className="rounded-full border border-border px-3 py-1 text-xs text-foreground hover:bg-secondary"
                  onClick={() => setQuery(suggestion.itemName)}
                >
                  {suggestion.itemName}
                </button>
              ))}
            </div>
          )}

            <div className="space-y-1 text-xs text-muted-foreground">
              <p>Exact item matches first, then close name matches, so the default view starts with the cleanest historical comps.</p>
              <p>Relevance-first suggestions come directly from the API payload, and leaving league blank uses the backend default league.</p>
            </div>
        </CardContent>
      </Card>

      {error && <RenderState kind="degraded" message={error} />}
      {loading && <RenderState kind="loading" message="Querying ClickHouse…" />}
      {!error && !loading && !data && (
        <RenderState kind="empty" message="Type at least two characters to search the historical listings index." />
      )}

      {data && data.rows.length === 0 && (
        <RenderState
          kind="empty"
          message="No matching historical listings found for this search. Try a broader item name or reset the filters."
        />
      )}

      {data && data.rows.length > 0 && (
        <>
          <div className="grid gap-4 xl:grid-cols-2">
            <Card className="card-game">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-sans">Listed Price Distribution</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <MiniHistogram
                  dataTestId="search-history-price-histogram"
                  title="Listed price"
                  buckets={data.histograms.price}
                  formatLabel={value => typeof value === 'number' ? `${value.toFixed(1)}c` : String(value)}
                />
                <div className="space-y-2">
                  <div className="flex items-center justify-between text-xs text-muted-foreground">
                    <span>{(priceMin ?? priceFloor).toFixed(1)}c</span>
                    <span>{(priceMax ?? priceCeiling).toFixed(1)}c</span>
                  </div>
                  <Slider
                    min={priceFloor}
                    max={priceCeiling}
                    step={priceStep}
                    value={[priceMin ?? priceFloor, priceMax ?? priceCeiling]}
                    onValueChange={([lo, hi]) => { setPriceMin(lo); setPriceMax(hi); }}
                    onValueCommit={([lo, hi]) => { setCommittedPriceMin(lo); setCommittedPriceMax(hi); }}
                    disabled={priceFloor === priceCeiling}
                  />
                </div>
              </CardContent>
            </Card>

            <Card className="card-game">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-sans">Added On Distribution</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <MiniHistogram
                  dataTestId="search-history-time-histogram"
                  title="Added on"
                  buckets={data.histograms.datetime}
                  formatLabel={value => formatShortDate(String(value))}
                />
                {hasTimeRange ? (
                  <div className="space-y-2">
                    <div className="flex items-center justify-between text-xs text-muted-foreground gap-3">
                      <span>{formatShortDate(new Date(toUnixMs(timeFrom) ?? timeRangeMin!).toISOString())}</span>
                      <span>{formatShortDate(new Date(toUnixMs(timeTo) ?? timeRangeMax!).toISOString())}</span>
                    </div>
                    <Slider
                      min={timeRangeMin!}
                      max={timeRangeMax!}
                      step={timeStep}
                      value={[toUnixMs(timeFrom) ?? timeRangeMin!, toUnixMs(timeTo) ?? timeRangeMax!]}
                      onValueChange={([lo, hi]) => {
                        setTimeFrom(new Date(lo).toISOString());
                        setTimeTo(new Date(hi).toISOString());
                      }}
                      onValueCommit={([lo, hi]) => {
                        setCommittedTimeFrom(new Date(lo).toISOString());
                        setCommittedTimeTo(new Date(hi).toISOString());
                      }}
                      disabled={timeRangeMin === timeRangeMax}
                    />
                  </div>
                ) : (
                  <p className="text-xs text-muted-foreground">No datetime buckets available for the current search.</p>
                )}
              </CardContent>
            </Card>
          </div>

          <Card className="card-game" data-testid="search-history-results">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between gap-3">
                <CardTitle className="text-sm font-sans">Historical Results</CardTitle>
                <span className="text-xs text-muted-foreground">{data.rows.length} rows · {order.toUpperCase()}</span>
              </div>
            </CardHeader>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="text-xs">
                      <button type="button" onClick={() => applyHistorySort('item_name')}>Item Name{sort === 'item_name' ? ` ${sortArrow(order)}` : ''}</button>
                    </TableHead>
                    <TableHead className="text-xs">
                      <button type="button" onClick={() => applyHistorySort('league')}>League{sort === 'league' ? ` ${sortArrow(order)}` : ''}</button>
                    </TableHead>
                    <TableHead className="text-xs">
                      <button type="button" onClick={() => applyHistorySort('listed_price')}>Listed Price{sort === 'listed_price' ? ` ${sortArrow(order)}` : ''}</button>
                    </TableHead>
                    <TableHead className="text-xs">
                      <button type="button" onClick={() => applyHistorySort('added_on')}>Added On{sort === 'added_on' ? ` ${sortArrow(order)}` : ''}</button>
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.rows.map((row, index) => (
                    <TableRow key={`${row.itemName}-${row.addedOn}-${index}`}>
                      <TableCell className="text-xs font-medium text-foreground">{row.itemName}</TableCell>
                      <TableCell className="text-xs">{row.league}</TableCell>
                      <TableCell className="text-xs font-mono">{row.listedPrice} {row.currency}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">{formatDisplayDate(row.addedOn)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}

function PricingOutliersPanel() {
  const [query, setQuery] = useState('');
  const [league, setLeague] = useState('');
  const [sort, setSort] = useState(OUTLIERS_DEFAULTS.sort);
  const [order, setOrder] = useState<'asc' | 'desc'>(OUTLIERS_DEFAULTS.order);
  const [minTotal, setMinTotal] = useState(OUTLIERS_DEFAULTS.minTotal);
  
  const [data, setData] = useState<PricingOutliersResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const timer = window.setTimeout(() => {
      if (!cancelled) {
        setError(null);
        setData(null);
      }
        getAnalyticsPricingOutliers({
          query: query.trim() || undefined,
          league: league.trim() || undefined,
          sort,
          order,
          minTotal,
          limit: OUTLIERS_DEFAULTS.limit,
        })
        .then(payload => {
          if (!cancelled) {
            setData(payload);
            setError(null);
          }
        })
        .catch(err => {
          if (!cancelled) {
            setData(null);
            setError(err instanceof Error ? err.message : 'Failed to load pricing outliers');
          }
        });
    }, 250);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [query, league, sort, order, minTotal]);

  const hasMissingOpportunityMetrics = Boolean(
    data?.rows.some(row => row.entryPrice == null || row.expectedProfit == null || row.roi == null || row.underpricedRate == null)
  );

  return (
    <div className="space-y-4">
      <Card className="card-game">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-sans">Low-Investment Flip Opportunities</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 lg:grid-cols-[minmax(0,2fr)_160px_160px_180px_180px_180px] items-end">
            <label className="text-xs text-muted-foreground space-y-1">
              <span>Item filter</span>
              <input
                value={query}
                onChange={event => setQuery(event.target.value)}
                placeholder="Optional item name filter"
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground"
              />
            </label>
            <label className="text-xs text-muted-foreground space-y-1">
              <span>League</span>
              <input
                value={league}
                onChange={event => setLeague(event.target.value)}
                placeholder="Default league"
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground"
              />
            </label>
            <label className="text-xs text-muted-foreground space-y-1">
              <span>Sort</span>
              <select
                value={sort}
                onChange={event => setSort(event.target.value)}
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground"
              >
                {OUTLIER_SORT_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </label>
            <label className="text-xs text-muted-foreground space-y-1">
              <span>Minimum sample size</span>
              <input
                type="number"
                min={1}
                value={minTotal}
                onChange={event => setMinTotal(Math.max(1, Number(event.target.value) || 1))}
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground"
              />
            </label>
            <label className="text-xs text-muted-foreground space-y-1">
              <span>Order</span>
              <select
                value={order}
                onChange={event => setOrder(event.target.value as 'asc' | 'desc')}
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground"
              >
                {OUTLIER_ORDER_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </label>
          </div>

          <p className="text-xs text-muted-foreground">
            Focus on sub-100 chaos entries with the strongest expected resale edge. Fair value comes from the backend median, while profit and ROI show how much room remains above the suggested buy-in.
          </p>
        </CardContent>
      </Card>

      {error && <RenderState kind="degraded" message={error} />}
      {!error && !data && <RenderState kind="loading" message="Loading low-investment opportunities…" />}
      {!error && hasMissingOpportunityMetrics && (
        <RenderState kind="degraded" message="Missing opportunity metrics from analytics backend." />
      )}

      {data && !hasMissingOpportunityMetrics && (
        <>
          <Card className="card-game">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-sans">Low-Investment Activity</CardTitle>
            </CardHeader>
            <CardContent>
              {data.weekly.length > 0 ? (
                <MiniHistogram
                  dataTestId="pricing-outliers-weekly-chart"
                  title="Too-cheap item-name matches per week"
                  buckets={data.weekly.map(entry => ({
                    bucketStart: entry.weekStart,
                    bucketEnd: entry.weekStart,
                    count: entry.tooCheapCount,
                  }))}
                  formatLabel={value => formatShortDate(String(value))}
                />
              ) : (
                <p className="text-xs text-muted-foreground">Weekly trend is available for item-name matches only.</p>
              )}
            </CardContent>
          </Card>

          {data.rows.length === 0 ? (
            <RenderState kind="empty" message="No cheap opportunities found under the current cap." />
          ) : (
            <Card className="card-game" data-testid="pricing-outliers-results">
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between gap-3">
                  <CardTitle className="text-sm font-sans">Opportunity Results</CardTitle>
                  <span className="text-xs text-muted-foreground">{data.rows.length} rows · {order.toUpperCase()}</span>
                </div>
              </CardHeader>
              <CardContent className="p-0">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="text-xs">Buy-In</TableHead>
                      <TableHead className="text-xs">Fair Value</TableHead>
                      <TableHead className="text-xs">Expected Profit</TableHead>
                      <TableHead className="text-xs">ROI</TableHead>
                      <TableHead className="text-xs">Underpriced Rate</TableHead>
                      <TableHead className="text-xs">Sample Size</TableHead>
                      <TableHead className="text-xs">Item Name</TableHead>
                      <TableHead className="text-xs">Affix Analyzed</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.rows.map((row, index) => (
                      <TableRow key={`${row.itemName}-${row.affixAnalyzed ?? 'base'}-${index}`}>
                        <TableCell className="text-xs font-mono">{row.entryPrice?.toFixed(2) ?? '—'}</TableCell>
                        <TableCell className="text-xs font-mono">{row.median.toFixed(2)}</TableCell>
                        <TableCell className="text-xs font-mono">{row.expectedProfit?.toFixed(2) ?? '—'}</TableCell>
                        <TableCell className="text-xs font-mono">{formatPct(row.roi)}</TableCell>
                        <TableCell className="text-xs font-mono">{formatPct(row.underpricedRate)}</TableCell>
                        <TableCell className="text-xs font-mono">{row.itemsTotal}</TableCell>
                        <TableCell className="text-xs font-medium text-foreground">{row.itemName}</TableCell>
                        <TableCell className="text-xs text-muted-foreground">
                          <div className="flex items-center gap-2">
                            <span>{row.affixAnalyzed ?? 'All item rolls'}</span>
                            <Badge variant="outline" className="text-[10px] uppercase tracking-wide">{row.analysisLevel}</Badge>
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  );
}

function MiniHistogram({
  title,
  buckets,
  formatLabel,
  dataTestId,
}: {
  title: string;
  buckets: HistogramBucket[];
  formatLabel: (value: number | string) => string;
  dataTestId: string;
}) {
  if (buckets.length === 0) {
    return <p className="text-xs text-muted-foreground">No histogram data available.</p>;
  }
  const maxCount = buckets.reduce((current, bucket) => Math.max(current, bucket.count), 1);
  return (
    <div className="space-y-2" data-testid={dataTestId}>
      <p className="text-xs text-muted-foreground">{title}</p>
      <div className="flex items-end gap-1 h-32">
        {buckets.map((bucket, index) => (
          <div key={`${String(bucket.bucketStart)}-${index}`} className="flex-1 h-full flex items-end">
            <div
              title={`${formatLabel(bucket.bucketStart)} → ${formatLabel(bucket.bucketEnd)} · ${bucket.count}`}
              className="w-full rounded-t bg-primary/60 border border-primary/20"
              style={{ height: `${Math.max(12, (bucket.count / maxCount) * 100)}%` }}
            />
          </div>
        ))}
      </div>
      <div className="flex items-center justify-between gap-2 text-[10px] text-muted-foreground">
        <span>{formatLabel(buckets[0].bucketStart)}</span>
        <span>{formatLabel(buckets[buckets.length - 1].bucketEnd)}</span>
      </div>
    </div>
  );
}

function calculateStep(minValue: number, maxValue: number): number {
  const distance = Math.max(maxValue - minValue, 1);
  return Math.max(Math.floor(distance / 100), 1);
}

function clampNumber(value: number, minValue: number, maxValue: number): number {
  if (maxValue < minValue) {
    return minValue;
  }
  return Math.min(Math.max(value, minValue), maxValue);
}

function toUnixMs(value: string | null | undefined): number | null {
  if (!value) {
    return null;
  }
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? null : parsed;
}

function formatDisplayDate(value: string | null | undefined): string {
  if (!value) {
    return '—';
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString();
}

function formatShortDate(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleDateString();
}

function sortArrow(order: 'asc' | 'desc'): string {
  return order === 'asc' ? '↑' : '↓';
}
