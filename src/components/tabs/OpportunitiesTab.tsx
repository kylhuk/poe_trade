import { forwardRef, useCallback, useEffect, useRef, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { RenderState } from '../shared/RenderState';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Slider } from '../ui/slider';
import { api } from '../../services/api';
import type {
  ScannerRecommendation,
  ScannerRecommendationsRequest,
  ScannerRecommendationsResponse,
} from '../../types/api';
import { useMouseGlow } from '../../hooks/useMouseGlow';
import { Filter, X } from 'lucide-react';

type ScannerSort =
  | 'expected_profit_per_operation_chaos'
  | 'expected_profit_chaos'
  | 'expected_profit_per_minute_chaos'
  | 'expected_roi'
  | 'confidence'
  | 'freshness_minutes'
  | 'liquidity_score';

const SORT_OPTIONS: Array<{ value: ScannerSort; label: string; testId: string }> = [
  {
    value: 'expected_profit_per_operation_chaos',
    label: 'Profit / Op',
    testId: 'scanner-sort-profit-per-op',
  },
  {
    value: 'expected_profit_chaos',
    label: 'Profit',
    testId: 'scanner-sort-profit',
  },
  {
    value: 'expected_profit_per_minute_chaos',
    label: 'Profit / min',
    testId: 'scanner-sort-profit-per-minute',
  },
  {
    value: 'expected_roi',
    label: 'ROI',
    testId: 'scanner-sort-roi',
  },
  {
    value: 'confidence',
    label: 'Confidence',
    testId: 'scanner-sort-confidence',
  },
  {
    value: 'freshness_minutes',
    label: 'Freshness',
    testId: 'scanner-sort-freshness',
  },
];

const QA_SCANNER_RECOMMENDATIONS_PAGE_SIZE = (() => {
  const rawValue = import.meta.env.VITE_SCANNER_RECOMMENDATIONS_PAGE_SIZE;
  if (typeof rawValue !== 'string' || rawValue.trim() === '') {
    return undefined;
  }
  const parsedValue = Number.parseInt(rawValue, 10);
  return Number.isInteger(parsedValue) && parsedValue > 0 ? parsedValue : undefined;
})();

function createEmptyResponse(): ScannerRecommendationsResponse {
  return {
    recommendations: [],
    meta: {
      nextCursor: null,
      hasMore: false,
    },
  };
}

function formatChaos(value: number | null): string {
  return value !== null ? `${value}c` : 'N/A';
}

function buildRequest(
  sort: ScannerSort,
  cursor?: string,
  opts?: { limit?: number; strategyId?: string; minConfidence?: number },
): ScannerRecommendationsRequest {
  const request: ScannerRecommendationsRequest = { sort };
  const limit = opts?.limit ?? QA_SCANNER_RECOMMENDATIONS_PAGE_SIZE;
  if (limit !== undefined) {
    request.limit = limit;
  }
  if (cursor) {
    request.cursor = cursor;
  }
  if (opts?.strategyId) {
    request.strategyId = opts.strategyId;
  }
  if (opts?.minConfidence !== undefined && opts.minConfidence > 0) {
    request.minConfidence = opts.minConfidence;
  }
  return request;
}

const OpportunitiesTab = forwardRef<HTMLDivElement, Record<string, never>>(function OpportunitiesTab(_props, ref) {
  const [recommendationResponse, setRecommendationResponse] = useState<ScannerRecommendationsResponse>(createEmptyResponse);
  const [sort, setSort] = useState<ScannerSort>('expected_profit_per_operation_chaos');
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showFilters, setShowFilters] = useState(false);
  const [strategyId, setStrategyId] = useState('');
  const [minConfidence, setMinConfidence] = useState(0);
  const [limit, setLimit] = useState(50);
  const mouseGlow = useMouseGlow();
  const requestVersionRef = useRef(0);

  const fetchInitial = useCallback((currentSort: ScannerSort, opts?: { limit?: number; strategyId?: string; minConfidence?: number }) => {
    const requestVersion = ++requestVersionRef.current;
    setLoading(true);
    setLoadingMore(false);
    setError(null);
    setRecommendationResponse(createEmptyResponse());

    api.getScannerRecommendations(buildRequest(currentSort, undefined, opts))
      .then(nextResponse => {
        if (requestVersionRef.current !== requestVersion) return;
        setRecommendationResponse(nextResponse);
      })
      .catch((err: unknown) => {
        if (requestVersionRef.current !== requestVersion) return;
        setError(err instanceof Error ? err.message : 'Failed to load opportunities');
      })
      .finally(() => {
        if (requestVersionRef.current === requestVersion) setLoading(false);
      });
  }, []);

  useEffect(() => {
    fetchInitial(sort, { limit, strategyId: strategyId.trim() || undefined, minConfidence });
  }, [fetchInitial, sort, limit, strategyId, minConfidence]);

  useEffect(() => {
    const refresh = () => {
      if (document.visibilityState !== 'visible') {
        return;
      }
      fetchInitial(sort, { limit, strategyId: strategyId.trim() || undefined, minConfidence });
    };

    const intervalId = window.setInterval(refresh, 30000);
    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        refresh();
      }
    };

    document.addEventListener('visibilitychange', onVisibilityChange);
    return () => {
      window.clearInterval(intervalId);
      document.removeEventListener('visibilitychange', onVisibilityChange);
    };
  }, [fetchInitial, sort, strategyId, minConfidence, limit]);

  const applyFilters = () => {
    fetchInitial(sort, { limit, strategyId: strategyId.trim() || undefined, minConfidence });
  };

  const clearFilters = () => {
    setSort('expected_profit_per_operation_chaos');
    setMinConfidence(0);
    setStrategyId('');
    setLimit(50);
    fetchInitial('expected_profit_per_operation_chaos');
  };

  const loadMore = async () => {
    const nextCursor = recommendationResponse.meta.nextCursor;
    if (loading || loadingMore || !recommendationResponse.meta.hasMore || !nextCursor) return;

    const requestVersion = requestVersionRef.current;
    setLoadingMore(true);
    setError(null);

    try {
      const nextResponse = await api.getScannerRecommendations(
        buildRequest(sort, nextCursor, { limit, strategyId: strategyId.trim() || undefined, minConfidence }),
      );
      if (requestVersionRef.current !== requestVersion) return;
      setRecommendationResponse(prev => {
        if (!prev.meta.hasMore || prev.meta.nextCursor !== nextCursor) return prev;
        return {
          recommendations: [...prev.recommendations, ...nextResponse.recommendations],
          meta: nextResponse.meta,
        };
      });
    } catch (err: unknown) {
      if (requestVersionRef.current !== requestVersion) return;
      setError(err instanceof Error ? err.message : 'Failed to load opportunities');
    } finally {
      if (requestVersionRef.current === requestVersion) setLoadingMore(false);
    }
  };

  const recommendations = recommendationResponse.recommendations;
  const canLoadMore = recommendationResponse.meta.hasMore && recommendationResponse.meta.nextCursor;

  if (loading) {
    return <div ref={ref} data-testid="panel-opportunities-root"><RenderState kind="loading" message="Scanning market..." /></div>;
  }

  if (error) {
    return <div ref={ref} data-testid="panel-opportunities-root"><RenderState kind="degraded" message={error} /></div>;
  }

  return (
    <div ref={ref} className="space-y-6" data-testid="panel-opportunities-root">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-lg font-semibold font-sans text-foreground">Market Opportunities</h2>
          <p className="text-xs text-muted-foreground">Scanner-backed recommendations with profit and time-efficiency signals.</p>
        </div>
        <div className="flex items-center gap-2 rounded-md border border-border bg-secondary/30 p-1">
          {SORT_OPTIONS.map(option => (
            <Button
              key={option.value}
              data-testid={option.testId}
              type="button"
              size="sm"
              variant={sort === option.value ? 'default' : 'outline'}
              className="h-8 px-3 text-xs btn-game"
              onClick={() => setSort(option.value)}
            >
              {option.label}
            </Button>
          ))}
        </div>
        <Button variant="ghost" size="sm" className="gap-1.5 text-xs" onClick={() => setShowFilters(!showFilters)}>
          <Filter className="h-3.5 w-3.5" />
          Filters
        </Button>
      </div>

      {/* Filter controls */}
      {showFilters && (
        <Card className="card-game animate-scale-fade-in">
          <CardContent className="p-4 space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <div className="space-y-1.5">
                <Label className="text-xs">Sort</Label>
                <Select value={sort} onValueChange={(v) => setSort(v as ScannerSort)}>
                  <SelectTrigger className="h-8 text-xs">
                    <SelectValue placeholder="Default" />
                  </SelectTrigger>
                  <SelectContent>
                    {SORT_OPTIONS.map(o => (
                      <SelectItem key={o.value} value={o.value} className="text-xs">{o.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Strategy ID</Label>
                <Input
                  value={strategyId}
                  onChange={e => setStrategyId(e.target.value)}
                  placeholder="e.g. stale_listing"
                  className="h-8 text-xs font-mono"
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Min Confidence: {minConfidence}%</Label>
                <Slider
                  value={[minConfidence]}
                  onValueChange={([v]) => setMinConfidence(v)}
                  min={0}
                  max={100}
                  step={5}
                  className="mt-2"
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Limit</Label>
                <Input
                  type="number"
                  value={limit}
                  onChange={e => setLimit(Number(e.target.value) || 50)}
                  min={1}
                  max={500}
                  className="h-8 text-xs font-mono"
                />
              </div>
            </div>
            <div className="flex gap-2">
              <Button size="sm" className="text-xs h-7 btn-game" onClick={applyFilters}>Apply</Button>
              <Button size="sm" variant="ghost" className="text-xs h-7 gap-1" onClick={clearFilters}>
                <X className="h-3 w-3" /> Clear
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {recommendations.length === 0 ? (
        <RenderState kind="empty" message="No opportunities found in the latest scan." />
      ) : (
        <div className="space-y-4">
          <div className="grid grid-cols-1 gap-4">
            {recommendations.map(r => (
              <OpportunityCard key={`${r.scannerRunId}-${r.itemOrMarketKey}`} recommendation={r} mouseGlow={mouseGlow} />
            ))}
          </div>
          {canLoadMore ? (
            <div className="flex justify-center">
              <Button
                data-testid="scanner-load-more"
                type="button"
                variant="outline"
                className="min-w-40 btn-game"
                disabled={loadingMore}
                onClick={() => { void loadMore(); }}
              >
                {loadingMore ? 'Loading...' : 'Load More'}
              </Button>
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
});

OpportunitiesTab.displayName = 'OpportunitiesTab';
export default OpportunitiesTab;

function OpportunityCard({
  recommendation,
  mouseGlow,
}: {
  recommendation: ScannerRecommendation;
  mouseGlow: (event: React.MouseEvent<HTMLElement>) => void;
}) {
  const displayName = recommendation.itemOrMarketKey;
  const confPct = recommendation.confidence != null ? `${Math.round(recommendation.confidence * 100)}%` : 'N/A';

  return (
    <Card className="card-game" onMouseMove={mouseGlow}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="text-sm font-sans">{displayName}</CardTitle>
          <div className="flex items-center gap-2">
            <span className="text-xs font-mono text-muted-foreground">{recommendation.strategyId}</span>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm text-foreground">{recommendation.whyItFired}</p>

        <div className="grid grid-cols-2 gap-4 rounded border border-border bg-secondary/30 p-3 sm:grid-cols-3 xl:grid-cols-6">
          <div>
            <p className="text-xs text-muted-foreground">Buy Plan</p>
            <p className="text-sm font-medium text-success">{recommendation.buyPlan}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Transform</p>
            <p className="text-sm font-medium text-foreground">{recommendation.transformPlan}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Exit Plan</p>
            <p className="text-sm font-medium text-foreground">{recommendation.exitPlan}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Expected Profit</p>
            <p className="text-sm font-medium text-warning">{formatChaos(recommendation.expectedProfitChaos)}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Profit / min</p>
            <p className="text-sm font-medium text-primary">{formatChaos(recommendation.expectedProfitPerMinuteChaos)}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Hold Window</p>
            <p className="text-sm font-medium text-foreground">{recommendation.expectedHoldTime || 'N/A'}</p>
          </div>
        </div>

        {/* Secondary metrics row */}
        <div className="flex flex-wrap items-center gap-3 text-[10px] text-muted-foreground px-1">
          <span>Conf: <span className="text-foreground font-medium">{confPct}</span></span>
          {recommendation.expectedRoi != null && (
            <span>ROI: <span className="text-foreground font-medium">{(recommendation.expectedRoi * 100).toFixed(1)}%</span></span>
          )}
          {recommendation.executionVenue && (
            <span>Venue: <span className="text-foreground font-medium">{recommendation.executionVenue}</span></span>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
