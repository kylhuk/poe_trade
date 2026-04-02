import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Card, CardContent } from '../ui/card';
import { Input } from '../ui/input';
import { Slider } from '../ui/slider';
import { Button } from '../ui/button';
import { Progress } from '../ui/progress';
import { RenderState } from '../shared/RenderState';
import { getAnalyticsPricingOutliers } from '../../services/api';
import type { PricingOutliersResponse, PricingOutlierRow, PricingOutlierWeek } from '../../types/api';
import {
  ArrowUpDown, ArrowUp, ArrowDown, ChevronDown, ChevronRight,
  TrendingUp, DollarSign, Percent, BarChart3, Search, X,
} from 'lucide-react';

type SortField = 'itemName' | 'entryPrice' | 'median' | 'spread' | 'expectedProfit' | 'roi' | 'underpricedRate' | 'itemsPerWeek' | 'itemsTotal';
type SortDir = 'asc' | 'desc';

const PAGE_SIZE = 50;

function roiColor(roi: number | null): string {
  if (roi == null) return 'text-muted-foreground';
  if (roi >= 1) return 'text-success';
  if (roi >= 0.5) return 'text-warning';
  return 'text-destructive';
}

function roiBg(roi: number | null): string {
  if (roi == null) return 'bg-muted';
  if (roi >= 1) return 'bg-success/15';
  if (roi >= 0.5) return 'bg-warning/15';
  return 'bg-destructive/15';
}

function fmtChaos(v: number | null): string {
  if (v == null) return '—';
  return v >= 1000 ? `${(v / 1000).toFixed(1)}k` : v.toFixed(1);
}

function fmtPct(v: number | null): string {
  if (v == null) return '—';
  return `${(v * 100).toFixed(0)}%`;
}

export default function FlipFinderTab() {
  // ── API state ──
  const [data, setData] = useState<PricingOutliersResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const versionRef = useRef(0);

  // ── Filter state (triggers API) ──
  const [search, setSearch] = useState('');
  const [maxBuyIn, setMaxBuyIn] = useState(5000);
  const [minTotal, setMinTotal] = useState(5);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();

  // ── Client-side sort state ──
  const [sortField, setSortField] = useState<SortField>('expectedProfit');
  const [sortDir, setSortDir] = useState<SortDir>('desc');

  // ── Pagination ──
  const [page, setPage] = useState(0);

  // ── Expanded rows ──
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());

  const fetchData = useCallback((q?: string, mbi?: number, mt?: number) => {
    const v = ++versionRef.current;
    setLoading(true);
    setError(null);
    getAnalyticsPricingOutliers({
      query: q?.trim() || undefined,
      minTotal: mt,
      limit: 500,
      sort: 'expected_profit',
      order: 'desc',
    })
      .then(res => { if (versionRef.current === v) { setData(res); setPage(0); } })
      .catch(err => { if (versionRef.current === v) setError(err instanceof Error ? err.message : 'Failed'); })
      .finally(() => { if (versionRef.current === v) setLoading(false); });
  }, []);

  useEffect(() => { fetchData(search, maxBuyIn, minTotal); }, [fetchData]);

  const debouncedFetch = useCallback((q: string, mbi: number, mt: number) => {
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => fetchData(q, mbi, mt), 400);
  }, [fetchData]);

  const onSearchChange = (v: string) => { setSearch(v); debouncedFetch(v, maxBuyIn, minTotal); };
  const onMaxBuyInChange = (v: number[]) => { setMaxBuyIn(v[0]); debouncedFetch(search, v[0], minTotal); };
  const onMinTotalChange = (v: number[]) => { setMinTotal(v[0]); debouncedFetch(search, maxBuyIn, v[0]); };

  const clearFilters = () => {
    setSearch(''); setMaxBuyIn(5000); setMinTotal(5);
    fetchData('', 5000, 5);
  };

  // ── Client-side sort ──
  const sortedRows = useMemo(() => {
    if (!data?.rows) return [];
    const rows = [...data.rows];
    const dir = sortDir === 'asc' ? 1 : -1;
    rows.sort((a, b) => {
      let av: number | string | null, bv: number | string | null;
      switch (sortField) {
        case 'itemName': av = a.itemName; bv = b.itemName; return dir * (av ?? '').localeCompare(bv ?? ''); 
        case 'entryPrice': av = a.entryPrice; bv = b.entryPrice; break;
        case 'median': av = a.median; bv = b.median; break;
        case 'spread': av = (a.p90 - a.p10); bv = (b.p90 - b.p10); break;
        case 'expectedProfit': av = a.expectedProfit; bv = b.expectedProfit; break;
        case 'roi': av = a.roi; bv = b.roi; break;
        case 'underpricedRate': av = a.underpricedRate; bv = b.underpricedRate; break;
        case 'itemsPerWeek': av = a.itemsPerWeek; bv = b.itemsPerWeek; break;
        case 'itemsTotal': av = a.itemsTotal; bv = b.itemsTotal; break;
        default: av = a.expectedProfit; bv = b.expectedProfit;
      }
      return dir * ((av ?? -Infinity) > (bv ?? -Infinity) ? 1 : (av ?? -Infinity) < (bv ?? -Infinity) ? -1 : 0);
    });
    return rows;
  }, [data?.rows, sortField, sortDir]);

  const totalPages = Math.ceil(sortedRows.length / PAGE_SIZE);
  const pageRows = sortedRows.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  const toggleSort = (field: SortField) => {
    if (sortField === field) { setSortDir(d => d === 'asc' ? 'desc' : 'asc'); }
    else { setSortField(field); setSortDir('desc'); }
    setPage(0);
  };

  const toggleExpand = (key: string) => {
    setExpandedRows(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
  };

  // ── KPI computation ──
  const kpis = useMemo(() => {
    if (!data?.rows?.length) return null;
    const rows = data.rows.filter(r => r.expectedProfit != null && r.roi != null);
    if (!rows.length) return null;
    const bestRoi = rows.reduce((best, r) => (r.roi ?? 0) > (best.roi ?? 0) ? r : best, rows[0]);
    const bestProfit = rows.reduce((best, r) => (r.expectedProfit ?? 0) > (best.expectedProfit ?? 0) ? r : best, rows[0]);
    const avgUnderpriced = rows.reduce((s, r) => s + (r.underpricedRate ?? 0), 0) / rows.length;
    return {
      count: rows.length,
      bestRoiItem: bestRoi.itemName,
      bestRoiVal: bestRoi.roi,
      bestProfitItem: bestProfit.itemName,
      bestProfitVal: bestProfit.expectedProfit,
      avgUnderpriced,
    };
  }, [data?.rows]);

  // ── Weekly trend ──
  const weekly = data?.weekly ?? [];

  const SortIcon = ({ field }: { field: SortField }) => {
    if (sortField !== field) return <ArrowUpDown className="h-3 w-3 opacity-30" />;
    return sortDir === 'asc' ? <ArrowUp className="h-3 w-3 text-primary" /> : <ArrowDown className="h-3 w-3 text-primary" />;
  };

  if (loading && !data) {
    return <RenderState kind="loading" message="Scanning pricing outliers…" />;
  }

  if (error && !data) {
    return <RenderState kind="degraded" message={error} />;
  }

  return (
    <div className="space-y-4">
      {/* ── Filter Bar ── */}
      <div className="flex flex-wrap items-end gap-3 rounded-lg border border-border bg-card p-3">
        <div className="flex-1 min-w-[200px]">
          <label className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1 block">Search</label>
          <div className="relative">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
            <Input
              value={search}
              onChange={e => onSearchChange(e.target.value)}
              placeholder="Item name…"
              className="h-8 text-xs pl-7 font-mono bg-background"
            />
          </div>
        </div>
        <div className="w-48">
          <label className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1 block">
            Max Buy-in: <span className="text-foreground">{fmtChaos(maxBuyIn)}c</span>
          </label>
          <Slider value={[maxBuyIn]} onValueChange={onMaxBuyInChange} min={0} max={50000} step={100} />
        </div>
        <div className="w-36">
          <label className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1 block">
            Min Samples: <span className="text-foreground">{minTotal}</span>
          </label>
          <Slider value={[minTotal]} onValueChange={onMinTotalChange} min={1} max={100} step={1} />
        </div>
        <Button variant="ghost" size="sm" className="h-8 text-xs gap-1" onClick={clearFilters}>
          <X className="h-3 w-3" /> Clear
        </Button>
        {loading && <span className="text-[10px] text-muted-foreground animate-pulse">Refreshing…</span>}
      </div>

      {/* ── KPI Cards ── */}
      {kpis && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <KpiCard icon={<BarChart3 className="h-4 w-4 text-primary" />} label="Opportunities" value={String(kpis.count)} />
          <KpiCard icon={<Percent className="h-4 w-4 text-success" />} label="Best ROI" value={fmtPct(kpis.bestRoiVal)} sub={kpis.bestRoiItem} />
          <KpiCard icon={<DollarSign className="h-4 w-4 text-warning" />} label="Best Profit" value={`${fmtChaos(kpis.bestProfitVal)}c`} sub={kpis.bestProfitItem} />
          <KpiCard icon={<TrendingUp className="h-4 w-4 text-primary" />} label="Avg Underpriced" value={fmtPct(kpis.avgUnderpriced)} />
        </div>
      )}

      {/* ── Weekly Trend ── */}
      {weekly.length > 0 && <WeeklyTrend weekly={weekly} />}

      {/* ── Main Table ── */}
      {sortedRows.length === 0 ? (
        <RenderState kind="empty" message="No flip opportunities found for these filters." />
      ) : (
        <div className="rounded-lg border border-border overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="sticky top-0 z-10 bg-card border-b border-border">
                <tr>
                  <th className="w-6 px-2 py-2" />
                  <SortHeader field="itemName" label="Item" current={sortField} dir={sortDir} onSort={toggleSort} />
                  <SortHeader field="entryPrice" label="Entry" current={sortField} dir={sortDir} onSort={toggleSort} align="right" />
                  <SortHeader field="median" label="Fair Value" current={sortField} dir={sortDir} onSort={toggleSort} align="right" />
                  <SortHeader field="spread" label="Spread" current={sortField} dir={sortDir} onSort={toggleSort} align="right" />
                  <SortHeader field="expectedProfit" label="Profit" current={sortField} dir={sortDir} onSort={toggleSort} align="right" />
                  <SortHeader field="roi" label="ROI" current={sortField} dir={sortDir} onSort={toggleSort} align="right" />
                  <SortHeader field="underpricedRate" label="Underpriced" current={sortField} dir={sortDir} onSort={toggleSort} align="right" />
                  <SortHeader field="itemsPerWeek" label="Vol/wk" current={sortField} dir={sortDir} onSort={toggleSort} align="right" />
                  <SortHeader field="itemsTotal" label="Samples" current={sortField} dir={sortDir} onSort={toggleSort} align="right" />
                </tr>
              </thead>
              <tbody>
                {pageRows.map(row => {
                  const key = `${row.itemName}-${row.affixAnalyzed ?? ''}`;
                  const expanded = expandedRows.has(key);
                  return (
                    <FlipRow key={key} row={row} expanded={expanded} onToggle={() => toggleExpand(key)} />
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* ── Pagination ── */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between px-3 py-2 border-t border-border bg-card text-xs text-muted-foreground">
              <span>{sortedRows.length} items · Page {page + 1}/{totalPages}</span>
              <div className="flex gap-1">
                <Button variant="ghost" size="sm" className="h-6 px-2 text-xs" disabled={page === 0} onClick={() => setPage(p => p - 1)}>Prev</Button>
                <Button variant="ghost" size="sm" className="h-6 px-2 text-xs" disabled={page >= totalPages - 1} onClick={() => setPage(p => p + 1)}>Next</Button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ── Sub-components ── */

function KpiCard({ icon, label, value, sub }: { icon: React.ReactNode; label: string; value: string; sub?: string }) {
  return (
    <Card className="card-game">
      <CardContent className="p-3 flex items-center gap-3">
        <div className="rounded-md bg-secondary p-2">{icon}</div>
        <div className="min-w-0">
          <p className="text-[10px] text-muted-foreground uppercase tracking-wider">{label}</p>
          <p className="text-sm font-semibold text-foreground truncate">{value}</p>
          {sub && <p className="text-[10px] text-muted-foreground truncate">{sub}</p>}
        </div>
      </CardContent>
    </Card>
  );
}

function WeeklyTrend({ weekly }: { weekly: PricingOutlierWeek[] }) {
  const max = Math.max(...weekly.map(w => w.tooCheapCount), 1);
  return (
    <Card className="card-game">
      <CardContent className="p-3">
        <p className="text-[10px] text-muted-foreground uppercase tracking-wider mb-2">Underpriced Listings / Week</p>
        <div className="flex items-end gap-[2px] h-12">
          {weekly.map((w, i) => (
            <div
              key={i}
              className="flex-1 rounded-t-sm bg-primary/60 hover:bg-primary transition-colors"
              style={{ height: `${(w.tooCheapCount / max) * 100}%` }}
              title={`${w.weekStart}: ${w.tooCheapCount}`}
            />
          ))}
        </div>
        <div className="flex justify-between text-[9px] text-muted-foreground mt-1">
          <span>{weekly[0]?.weekStart?.slice(5) ?? ''}</span>
          <span>{weekly[weekly.length - 1]?.weekStart?.slice(5) ?? ''}</span>
        </div>
      </CardContent>
    </Card>
  );
}

function SortHeader({
  field, label, current, dir, onSort, align = 'left',
}: {
  field: SortField; label: string; current: SortField; dir: SortDir; onSort: (f: SortField) => void; align?: 'left' | 'right';
}) {
  const active = current === field;
  return (
    <th
      className={`px-2 py-2 cursor-pointer select-none whitespace-nowrap transition-colors hover:text-foreground ${
        align === 'right' ? 'text-right' : 'text-left'
      } ${active ? 'text-foreground' : 'text-muted-foreground'}`}
      onClick={() => onSort(field)}
    >
      <span className="inline-flex items-center gap-1">
        {label}
        {active
          ? dir === 'asc' ? <ArrowUp className="h-3 w-3 text-primary" /> : <ArrowDown className="h-3 w-3 text-primary" />
          : <ArrowUpDown className="h-3 w-3 opacity-30" />}
      </span>
    </th>
  );
}

function FlipRow({ row, expanded, onToggle }: { row: PricingOutlierRow; expanded: boolean; onToggle: () => void }) {
  const spread = row.p90 - row.p10;
  const underpricedPct = (row.underpricedRate ?? 0) * 100;

  return (
    <>
      <tr className="flip-row" onClick={onToggle}>
        <td className="px-2 py-1.5 text-muted-foreground">
          {expanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
        </td>
        <td className="px-2 py-1.5 font-medium text-foreground max-w-[200px] truncate">{row.itemName}</td>
        <td className="px-2 py-1.5 text-right font-mono text-primary">{fmtChaos(row.entryPrice)}<span className="text-muted-foreground">c</span></td>
        <td className="px-2 py-1.5 text-right font-mono">{fmtChaos(row.median)}<span className="text-muted-foreground">c</span></td>
        <td className="px-2 py-1.5 text-right font-mono text-muted-foreground">{fmtChaos(spread)}</td>
        <td className="px-2 py-1.5 text-right font-mono text-success font-medium">{fmtChaos(row.expectedProfit)}<span className="text-muted-foreground">c</span></td>
        <td className="px-2 py-1.5 text-right">
          <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold ${roiColor(row.roi)} ${roiBg(row.roi)}`}>
            {fmtPct(row.roi)}
          </span>
        </td>
        <td className="px-2 py-1.5 text-right">
          <div className="inline-flex items-center gap-1.5">
            <div className="w-14 h-1.5 rounded-full bg-secondary overflow-hidden">
              <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${Math.min(underpricedPct, 100)}%` }} />
            </div>
            <span className="font-mono text-[10px] w-8 text-right">{underpricedPct.toFixed(0)}%</span>
          </div>
        </td>
        <td className="px-2 py-1.5 text-right font-mono">{row.itemsPerWeek.toFixed(0)}</td>
        <td className="px-2 py-1.5 text-right font-mono text-muted-foreground">{row.itemsTotal}</td>
      </tr>
      {expanded && (
        <tr className="bg-muted/30">
          <td colSpan={10} className="px-4 py-3">
            <div className="flex flex-wrap gap-6 text-xs">
              {/* P10–P90 range bar */}
              <div className="space-y-1">
                <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Price Range</p>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-foreground">{fmtChaos(row.p10)}c</span>
                  <div className="w-32 h-2 rounded-full bg-secondary relative overflow-hidden">
                    {row.entryPrice != null && row.p90 > row.p10 && (
                      <div
                        className="absolute h-full bg-primary/50 rounded-full"
                        style={{
                          left: `${((row.p10 - row.p10) / (row.p90 - row.p10)) * 100}%`,
                          width: `${((row.median - row.p10) / (row.p90 - row.p10)) * 100}%`,
                        }}
                      />
                    )}
                    {row.entryPrice != null && row.p90 > row.p10 && (
                      <div
                        className="absolute h-full w-0.5 bg-success"
                        style={{ left: `${Math.min(((row.entryPrice - row.p10) / (row.p90 - row.p10)) * 100, 100)}%` }}
                        title={`Entry: ${row.entryPrice}c`}
                      />
                    )}
                  </div>
                  <span className="font-mono text-foreground">{fmtChaos(row.p90)}c</span>
                </div>
              </div>
              {row.affixAnalyzed && (
                <div>
                  <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Affix</p>
                  <p className="font-mono text-foreground">{row.affixAnalyzed}</p>
                </div>
              )}
              <div>
                <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Analysis</p>
                <p className="text-foreground">{row.analysisLevel}</p>
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}
