import React, { forwardRef, useCallback, useEffect, useState } from 'react';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { api } from '@/services/api';
import type {
  PoeItem,
  StashItemHistoryResponse,
  StashScanStatus,
  StashScanValuationsResponse,
  StashStatus,
  StashTab,
  StashTabMeta,
  SpecialLayout,
} from '@/types/api';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import {
  ChevronDown, Copy, Loader2, History, Coins, type LucideIcon,
} from 'lucide-react';
import { RenderState } from '@/components/shared/RenderState';
import NormalGrid from '@/components/stash/NormalGrid';
import SpecialLayoutGrid from '@/components/stash/SpecialLayoutGrid';
import SpecialGrid from '@/components/stash/SpecialGrid';
import PriceSparkline from '@/components/economy/PriceSparkline';

const FLOW_GRID_TYPES = new Set([
  'currency', 'map', 'fragment', 'essence', 'divination',
  'unique', 'delve', 'blight', 'ultimatum', 'delirium', 'metamorph',
  'flask', 'gem',
]);

const API_SCHEMA = `{
  "scanId": "string | null",
  "publishedAt": "ISO-8601 | null",
  "isStale": false,
  "scanStatus": {
    "status": "idle | running | publishing | published | failed"
  },
  "stashTabs": []
}`;

const EMPTY_SCAN_STATUS: StashScanStatus = {
  status: 'idle',
  activeScanId: null,
  publishedScanId: null,
  startedAt: null,
  updatedAt: null,
  publishedAt: null,
  error: null,
  progress: {
    tabsProcessed: 0,
    tabsTotal: 0,
    itemsProcessed: 0,
    itemsTotal: 0,
  },
};

function pickReturnedTab(payload: { stashTabs: StashTab[] }, requestedIndex: number): StashTab | null {
  if (payload.stashTabs.length === 0) {
    return null;
  }
  return payload.stashTabs.find((tab) => tab.returnedIndex === requestedIndex)
    ?? payload.stashTabs[requestedIndex]
    ?? payload.stashTabs[0]
    ?? null;
}

function getSpecialLayout(tab: StashTab): SpecialLayout | null {
  return tab.currencyLayout
    ?? tab.fragmentLayout
    ?? tab.essenceLayout
    ?? tab.deliriumLayout
    ?? tab.blightLayout
    ?? tab.ultimatumLayout
    ?? tab.mapLayout
    ?? tab.divinationLayout
    ?? tab.uniqueLayout
    ?? tab.delveLayout
    ?? tab.metamorphLayout
    ?? null;
}

/**
 * Approximate chaos equivalents for common PoE currencies.
 * Divine rate fluctuates; 200c is a reasonable mid-league default.
 * This map is used to normalise listedPrice to chaos for comparison with chaosMedian.
 */
const CHAOS_RATE: Record<string, number> = {
  chaos: 1,
  c: 1,
  divine: 200,
  div: 200,
  d: 200,
  exalted: 12,
  exa: 12,
  ex: 12,
};

/** Convert a price + currency to chaos equivalent */
function toChaos(price: number, currency?: string | null): number {
  if (!currency) return price; // assume chaos
  const rate = CHAOS_RATE[currency.toLowerCase()] ?? 1;
  return price * rate;
}

/**
 * Parse PoE tab-name pricing syntax like "~price 12 chaos" or "~b/o 5 divine".
 * Returns { price, currency } or null if the tab name doesn't contain pricing.
 */
function parseTabNamePrice(tabName: string): { price: number; currency: string } | null {
  const match = tabName.match(/~(?:price|b\/o)\s+([\d.]+)\s+(chaos|divine|div|exalted|exa)/i);
  if (!match) return null;
  const price = parseFloat(match[1]);
  if (isNaN(price) || price <= 0) return null;
  const rawCur = match[2].toLowerCase();
  const currency = (rawCur === 'divine' || rawCur === 'div') ? 'div'
    : (rawCur === 'exalted' || rawCur === 'exa') ? 'exa' : 'chaos';
  return { price, currency };
}

/** Apply tab-level listed price to items that don't have their own listedPrice */
function applyTabLevelPricing(items: PoeItem[], tabName: string): PoeItem[] {
  const tabPrice = parseTabNamePrice(tabName);
  if (!tabPrice) return items;
  return items.map(item => {
    if (item.listedPrice != null) return item;
    return { ...item, listedPrice: tabPrice.price, currency: tabPrice.currency };
  });
}

/** Compute price evaluation from listed vs estimated delta, normalising currencies to chaos */
function computeEvaluation(
  listedPrice: number | null | undefined,
  estimatedPrice: number | null | undefined,
  currency?: string | null,
): PoeItem['priceEvaluation'] {
  if (listedPrice == null || listedPrice <= 0) return undefined;
  if (estimatedPrice == null || estimatedPrice <= 0) return undefined;
  const listedChaos = toChaos(listedPrice, currency);
  const delta = Math.abs(listedChaos - estimatedPrice) / estimatedPrice;
  if (delta <= 0.10) return 'well_priced';
  if (delta <= 0.25) return 'could_be_better';
  return 'mispriced';
}

/** Merge valuation items into displayed PoeItems by id or fingerprint */
function mergeValuationIntoItems(items: PoeItem[], valItems: Record<string, unknown>[]): PoeItem[] {
  const byFingerprint = new Map<string, Record<string, unknown>>();
  const byId = new Map<string, Record<string, unknown>>();
  for (const vi of valItems) {
    const fp = vi.fingerprint as string | undefined;
    const id = vi.id as string | undefined;
    if (fp) byFingerprint.set(fp, vi);
    if (id) byId.set(id, vi);
  }

  return items.map(item => {
    const match = (item.fingerprint && byFingerprint.get(item.fingerprint)) || byId.get(item.id);
    if (!match) return item;

    // Primary price: chaosMedian from valuation API
    const chaosMedian = typeof match.chaosMedian === 'number' ? match.chaosMedian
      : (typeof match.chaos_median === 'number' ? match.chaos_median : null);

    // Affix fallback medians
    const affixFallbackMedians = (match.affixFallbackMedians ?? match.affix_fallback_medians) as PoeItem['affixFallbackMedians'] | undefined;

    // Day series for sparkline
    const daySeries = (match.daySeries ?? match.day_series) as PoeItem['daySeries'] | undefined;

    const estimatedPrice = chaosMedian != null && chaosMedian > 0 ? chaosMedian : 0;

    // Determine currency — prefer item's own, fall back to valuation's
    const itemCurrency = item.currency ?? (typeof match.currency === 'string' ? match.currency : undefined);

    // Compute evaluation client-side: only when chaosMedian exists
    const priceEvaluation = chaosMedian != null && chaosMedian > 0
      ? computeEvaluation(item.listedPrice, chaosMedian, itemCurrency)
      : undefined;

    // Compute delta in chaos (normalise listedPrice to chaos first)
    const listedChaos = (item.listedPrice != null) ? toChaos(item.listedPrice, itemCurrency) : null;
    const priceDeltaChaos = (chaosMedian && chaosMedian > 0 && listedChaos != null)
      ? Math.round(listedChaos - chaosMedian) : null;
    const priceDeltaPercent = (chaosMedian && chaosMedian > 0 && listedChaos != null)
      ? Math.round(((listedChaos - chaosMedian) / chaosMedian) * 100) : null;

    return {
      ...item,
      estimatedPrice,
      chaosMedian,
      daySeries,
      affixFallbackMedians,
      priceEvaluation,
      priceDeltaChaos,
      priceDeltaPercent,
      currency: itemCurrency,
    };
  });
}

const StashViewerTab = forwardRef<HTMLDivElement, Record<string, never>>(function StashViewerTab(_props, ref) {
  const [tabsMeta, setTabsMeta] = useState<StashTabMeta[]>([]);
  const [activeTab, setActiveTab] = useState<StashTab | null>(null);
  const [activeTabIndex, setActiveTabIndex] = useState(0);
  const [tabLoading, setTabLoading] = useState(false);
  const [tabMismatch, setTabMismatch] = useState<string | null>(null);
  const [status, setStatus] = useState<StashStatus['status'] | 'loading' | 'degraded'>('loading');
  const [schemaOpen, setSchemaOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [publishedScanId, setPublishedScanId] = useState<string | null>(null);
  const [publishedAt, setPublishedAt] = useState<string | null>(null);
  const [scanStatus, setScanStatus] = useState<StashScanStatus>(EMPTY_SCAN_STATUS);
  const [scanBusy, setScanBusy] = useState(false);
  const [valuationPhase, setValuationPhase] = useState<'idle' | 'running' | 'done' | 'failed'>('idle');
  const [valuationResult, setValuationResult] = useState<StashScanValuationsResponse | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyPayload, setHistoryPayload] = useState<StashItemHistoryResponse | null>(null);

  // Race guard for tab loading — incremented on each loadTab call
  const loadTokenRef = React.useRef(0);
  // AbortController for in-flight tab requests — abort old ones on tab switch
  const tabAbortRef = React.useRef<AbortController | null>(null);

  /** Fetch existing valuation results (no computation) */
  const fetchValuationResults = useCallback(async (signal?: AbortSignal) => {
    try {
      const valResult = await api.getStashValuationsResult(signal);
      setValuationResult(valResult);
      console.log('[Stash] Valuation result keys:', Object.keys(valResult));
      console.log('[Stash] Valuation items count:', valResult.items?.length ?? 0);
      if (valResult.items?.length) {
        setActiveTab(prev => {
          if (!prev) return prev;
          return { ...prev, items: mergeValuationIntoItems(prev.items, valResult.items) };
        });
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return;
      console.warn('[Stash] No existing valuation results:', err instanceof Error ? err.message : err);
    }
  }, []);

  /** Start a new valuation computation and poll until done */
  const runValuation = useCallback(async () => {
    setValuationPhase('running');
    try {
      await api.startStashValuations();
      // Poll valuation status
      const poll = async (): Promise<void> => {
        const vs = await api.getStashValuationsStatus();
        if (vs.status === 'published' || vs.status === 'idle') {
          return;
        }
        if (vs.status === 'failed') {
          throw new Error(vs.error ?? 'Valuation failed');
        }
        await new Promise(r => setTimeout(r, 1500));
        return poll();
      };
      await poll();
      // Fetch final results
      await fetchValuationResults();
      setValuationPhase('done');
      toast.success('Valuations complete');
    } catch (valErr) {
      setValuationPhase('failed');
      toast.error(valErr instanceof Error ? valErr.message : 'Valuation failed');
    }
  }, [fetchValuationResults]);

  const valuationResultRef = React.useRef(valuationResult);
  valuationResultRef.current = valuationResult;

  const loadTab = useCallback(async (tabIndex: number) => {
    // Cancel any in-flight tab request before starting a new one
    if (tabAbortRef.current) {
      tabAbortRef.current.abort();
    }
    const ac = new AbortController();
    tabAbortRef.current = ac;

    const token = ++loadTokenRef.current;
    setTabLoading(true);
    setTabMismatch(null);

    // 1) Load and render tab payload first (do not block UI on valuations endpoint)
    try {
      const payload = await api.getStashScanResult(ac.signal);
      // Race guard: discard if a newer loadTab was fired
      if (token !== loadTokenRef.current) return;

      console.log('[Stash] Tab payload keys:', Object.keys(payload));
      const returned = pickReturnedTab(payload, tabIndex);
      if (returned) {
        console.log('[Stash] Active tab items count:', returned.items.length);
        returned.items = applyTabLevelPricing(returned.items, returned.name);
        if (returned.items.length > 0) {
          const sample = returned.items[0];
          console.log('[Stash] Sample item fields:', {
            id: sample.id, fingerprint: sample.fingerprint, name: sample.name,
            estimatedPrice: sample.estimatedPrice, listedPrice: sample.listedPrice,
            priceEvaluation: sample.priceEvaluation, priceDeltaChaos: sample.priceDeltaChaos,
            currency: sample.currency, stackSize: sample.stackSize,
          });
        }
        setActiveTab(returned);
        if (returned.returnedIndex != null && returned.returnedIndex !== tabIndex) {
          setTabMismatch(`Requested tab index ${tabIndex}, but backend returned index ${returned.returnedIndex} ("${returned.name}")`);
        }
      } else {
        setActiveTab(null);
      }
      if (payload.tabsMeta.length > 0) {
        setTabsMeta(payload.tabsMeta);
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return;
      if (token !== loadTokenRef.current) return;
      toast.error(err instanceof Error ? err.message : 'Failed to load tab');
      return;
    } finally {
      if (token === loadTokenRef.current) setTabLoading(false);
    }

    // 2) Fetch valuation result in background and merge when available
    void (async () => {
      try {
        const valResult = await api.getStashValuationsResult(ac.signal);
        if (token !== loadTokenRef.current) return;
        setValuationResult(valResult);
        if (valResult.items?.length) {
          setActiveTab(prev => {
            if (!prev) return prev;
            return { ...prev, items: mergeValuationIntoItems(prev.items, valResult.items) };
          });
        }
      } catch (err) {
        if (err instanceof DOMException && err.name === 'AbortError') return;
        // Non-blocking by design: keep tab visible even if valuation endpoint is slow/failing.
      }
    })();
  }, []);

  const pollStatus = useCallback(async () => {
    const stashStatus = await api.getStashStatus();
    setStatus(stashStatus.status);
    setPublishedScanId(stashStatus.publishedScanId ?? null);
    setPublishedAt(stashStatus.publishedAt ?? null);
    setScanStatus(stashStatus.scanStatus ?? EMPTY_SCAN_STATUS);
    if (!stashStatus.connected) {
      setActiveTab(null);
      setTabsMeta([]);
    }
    setError(null);
    return stashStatus;
  }, []);

  const initialLoadDone = React.useRef(false);

  useEffect(() => {
    if (initialLoadDone.current) return;
    initialLoadDone.current = true;
    (async () => {
      try {
        const stashStatus = await pollStatus();
        if (stashStatus.connected) {
          // loadTab now fetches both scan result and valuations in parallel
          await loadTab(0);
        }
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : 'Stash feature unavailable');
        setStatus('degraded');
      }
    })();
  }, [pollStatus, loadTab]);

  useEffect(() => {
    if (!scanBusy) {
      return;
    }
    const timer = window.setInterval(async () => {
      try {
        const next = await api.getStashScanStatus();
        setScanStatus(next);
        if (next.status === 'published') {
          window.clearInterval(timer);
          setScanBusy(false);
          await loadTab(activeTabIndex);
          // Phase 2: trigger valuations (start computation + poll + fetch results)
          await runValuation();
        }
        if (next.status === 'failed') {
          window.clearInterval(timer);
          setScanBusy(false);
          if (next.error) {
            toast.error(next.error);
          }
        }
      } catch (err) {
        window.clearInterval(timer);
        setScanBusy(false);
        toast.error(err instanceof Error ? err.message : 'Failed to fetch scan status');
      }
    }, 1500);
    return () => window.clearInterval(timer);
  }, [scanBusy, loadTab, activeTabIndex, runValuation]);

  const startScan = useCallback(async () => {
    try {
      setValuationPhase('idle');
      setValuationResult(null);
      const next = await api.startStashScan();
      setScanStatus((current) => ({
        ...current,
        status: 'running',
        activeScanId: next.scanId,
        startedAt: next.startedAt,
        updatedAt: next.startedAt,
        error: null,
      }));
      setScanBusy(true);
      toast.success(next.deduplicated ? 'Scan already running' : 'Scan started');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to start scan');
    }
  }, []);

  const startValuateOnly = useCallback(async () => {
    if (!publishedScanId) {
      toast.error('No published scan to valuate. Run a scan first.');
      return;
    }
    await runValuation();
  }, [publishedScanId, runValuation]);

  const openHistory = useCallback(async (item: PoeItem) => {
    if (!item.fingerprint) {
      return;
    }
    setHistoryLoading(true);
    setHistoryOpen(true);
    try {
      const payload = await api.getStashItemHistory(item.fingerprint);
      setHistoryPayload(payload);
    } catch (err) {
      setHistoryOpen(false);
      toast.error(err instanceof Error ? err.message : 'Failed to load history');
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  const activeTabRef = React.useRef(activeTab);
  activeTabRef.current = activeTab;
  const activeTabIndexRef = React.useRef(activeTabIndex);
  activeTabIndexRef.current = activeTabIndex;

  useEffect(() => {
    const iv = window.setInterval(async () => {
      try {
        const st = await pollStatus();
        if (st.connected && !activeTabRef.current) {
          await loadTab(activeTabIndexRef.current);
        }
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : 'Stash feature unavailable');
        setStatus('degraded');
      }
    }, 5_000);
    return () => clearInterval(iv);
  }, [pollStatus, loadTab]);

  const tab = activeTab;
  const specialLayout = tab ? getSpecialLayout(tab) : null;
  const isGrid = tab && !specialLayout;
  const gridSize = (() => {
    if (!tab) return 12;
    if (tab.quadLayout || tab.type === 'quad') return 24;
    const maxCoord = tab.items.reduce((max, item) => Math.max(max, item.x + item.w, item.y + item.h), 0);
    return maxCoord > 12 ? 24 : 12;
  })();
  const runningScan = scanBusy || scanStatus.status === 'running' || scanStatus.status === 'publishing';
  const anyPhaseBusy = runningScan || valuationPhase === 'running';

  // Convert daySeries to sparkline points
  const daySeriesPoints = valuationResult?.daySeries?.map(d => ({
    timestamp: d.date,
    value: d.chaosMedian ?? 0,
  })).filter(p => p.value > 0) ?? [];

  // History sparkline from historyPayload
  const historySparklinePoints = historyPayload?.history?.map(h => ({
    timestamp: h.pricedAt,
    value: h.predictedValue,
  })) ?? [];

  return (
    <div ref={ref} className="space-y-3" data-testid="panel-stash-root">
      {/* Header bar */}
      <div className="flex flex-col gap-3 rounded border border-gold-dim/20 bg-card/60 p-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="space-y-1 flex-1">
          <p className="text-sm font-semibold text-foreground">Private Stash</p>
          <p className="text-xs text-muted-foreground">
            {publishedScanId ? `Published ${publishedScanId}` : 'No published scan yet'}
            {publishedAt ? ` · ${publishedAt}` : ''}
          </p>
          {(runningScan || scanStatus.error) && (
            <p className="text-xs text-muted-foreground">
              {scanStatus.status === 'failed'
                ? `Last scan failed${scanStatus.error ? `: ${scanStatus.error}` : ''}`
                : tab
                  ? `Phase 1: Scanning items — ${scanStatus.status} (showing last available stash data)`
                  : `Phase 1: Scanning items — ${scanStatus.progress.tabsProcessed}/${scanStatus.progress.tabsTotal} tabs · ${scanStatus.progress.itemsProcessed}/${scanStatus.progress.itemsTotal} items`}
            </p>
          )}
          {valuationPhase === 'running' && (
            <p className="text-xs text-muted-foreground flex items-center gap-1">
              <Loader2 className="h-3 w-3 animate-spin" />
              Phase 2: Valuating items…
            </p>
          )}
          {valuationPhase === 'done' && (
            <div className="flex items-center gap-3">
              <p className="text-xs text-success">
                Valuations complete{valuationResult?.items?.length ? ` · ${valuationResult.items.length} items priced` : ''}
                {valuationResult?.chaosMedian != null ? ` · median ${valuationResult.chaosMedian}c` : ''}
              </p>
              {daySeriesPoints.length >= 2 && (
                <PriceSparkline points={daySeriesPoints} width={100} height={24} />
              )}
            </div>
          )}
          {valuationPhase === 'failed' && (
            <p className="text-xs text-destructive">Valuation failed</p>
          )}

          {/* Affix fallback medians */}
          {valuationResult?.affixFallbackMedians && valuationResult.affixFallbackMedians.length > 0 && (
            <div className="flex items-center gap-2 flex-wrap mt-1">
              <span className="text-[10px] text-muted-foreground">Affix medians:</span>
              {valuationResult.affixFallbackMedians.map(af => (
                <span key={af.affix} className="text-[10px] font-mono text-muted-foreground bg-muted/30 px-1 rounded">
                  {af.affix}: {af.chaosMedian}c
                </span>
              ))}
            </div>
          )}
        </div>

        {/* Action buttons */}
        <div className="flex items-center gap-2 shrink-0">
          <Button onClick={startScan} disabled={anyPhaseBusy} className="gap-2" aria-label="Scan">
            {runningScan ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <History className="h-3.5 w-3.5" />}
            Scan
          </Button>
          <Button
            onClick={startValuateOnly}
            disabled={anyPhaseBusy || !publishedScanId}
            variant="outline"
            className="gap-2"
            aria-label="Valuate"
          >
            {valuationPhase === 'running' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Coins className="h-3.5 w-3.5" />}
            Valuate
          </Button>
        </div>
      </div>




      {/* Tab navigation */}
      <div className="flex items-end gap-0 flex-wrap">
        {tabsMeta.map((t, i) => (
          <button
            type="button"
            data-testid={`stash-tab-${t.id}`}
            key={t.id}
            onClick={() => {
              setActiveTabIndex(t.tabIndex);
              loadTab(t.tabIndex);
            }}
            className={cn(
              'px-4 py-1.5 text-xs font-display tracking-wide border border-b-0 transition-all relative -mb-px',
              t.tabIndex === activeTabIndex
                ? 'bg-gold-dim/30 text-gold-bright border-gold-dim z-10'
                : 'bg-card text-muted-foreground border-gold-dim/30 hover:text-gold hover:bg-gold-dim/10'
            )}
            style={t.colour ? { borderTopColor: `#${t.colour}`, borderTopWidth: 2 } : undefined}
          >
            {t.name}
            {t.type === 'QuadStash' && <span className="ml-1 text-[9px] opacity-50">(Q)</span>}
          </button>
        ))}
      </div>

      {/* Status states */}
      {error && <RenderState kind="degraded" message={error} />}
      {!error && status === 'disconnected' && <RenderState kind="disconnected" message="Connect account to view stash" />}
      {!error && status === 'session_expired' && <RenderState kind="session_expired" message="Session expired, login again" />}
      {!error && status === 'feature_unavailable' && <RenderState kind="feature_unavailable" message="Stash feature unavailable" />}
      {!error && tabsMeta.length === 0 && !tab && status === 'connected_empty' && <RenderState kind="empty" message="Connected but stash is empty" />}
      {tabLoading && <RenderState kind="loading" message="Loading tab..." />}
      {tabMismatch && (
        <div className="rounded border border-warning/40 bg-warning/10 px-3 py-2 text-xs text-warning" data-testid="tab-mismatch-warning">
          ⚠ {tabMismatch}
        </div>
      )}

      {/* Grid / Special layout rendering */}
      {tab && specialLayout && (
        <SpecialLayoutGrid items={tab.items} layout={specialLayout} onItemClick={openHistory} />
      )}
      {tab && !specialLayout && FLOW_GRID_TYPES.has(tab.type) && (
        <SpecialGrid items={tab.items} tabType={tab.type} onItemClick={openHistory} />
      )}
      {tab && isGrid && !FLOW_GRID_TYPES.has(tab.type) && (
        <NormalGrid items={tab.items} gridSize={gridSize} onItemClick={openHistory} />
      )}

      {/* Legend */}
      {tab && (
        <div className="flex items-center gap-4 mt-2 px-1 text-[10px] text-muted-foreground">
          <span className="flex items-center gap-1"><span className="w-3 h-2 rounded-sm bg-success/30" /> Well priced</span>
          <span className="flex items-center gap-1"><span className="w-3 h-2 rounded-sm bg-warning/30" /> Could be better</span>
          <span className="flex items-center gap-1"><span className="w-3 h-2 rounded-sm bg-destructive/30" /> Mispriced</span>
          <span className="text-[9px] italic">Click item for price history</span>
        </div>
      )}

      <Collapsible open={schemaOpen} onOpenChange={setSchemaOpen}>
        <CollapsibleTrigger asChild>
          <Button variant="ghost" size="sm" className="text-xs text-muted-foreground gap-1.5">
            <ChevronDown className={cn('h-3 w-3 transition-transform', schemaOpen && 'rotate-180')} />
            API JSON Schema
          </Button>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="relative mt-2">
            <Button
              variant="outline"
              size="sm"
              className="absolute top-2 right-2 h-7 text-[10px] gap-1"
              onClick={() => { navigator.clipboard.writeText(API_SCHEMA); toast.success('Schema copied'); }}
            >
              <Copy className="h-3 w-3" /> Copy
            </Button>
            <pre className="bg-background border border-gold-dim/20 rounded p-4 text-[11px] font-mono text-muted-foreground overflow-x-auto whitespace-pre">
              {API_SCHEMA}
            </pre>
          </div>
        </CollapsibleContent>
      </Collapsible>

      {/* History dialog */}
      <Dialog open={historyOpen} onOpenChange={setHistoryOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{historyPayload?.item.name || 'Item history'}</DialogTitle>
            <DialogDescription>
              {historyPayload?.item.itemClass || ''}
              {historyPayload?.item.rarity ? ` · ${historyPayload.item.rarity}` : ''}
            </DialogDescription>
          </DialogHeader>
          {historyLoading && <p className="text-sm text-muted-foreground">Loading history...</p>}
          {!historyLoading && historyPayload && (
            <div className="space-y-3">
              {/* Sparkline of historical prices */}
              {historySparklinePoints.length >= 2 && (
                <div className="flex items-center gap-2 p-2 rounded bg-muted/20 border border-border">
                  <span className="text-[10px] text-muted-foreground">Price trend</span>
                  <PriceSparkline points={historySparklinePoints} width={200} height={32} />
                </div>
              )}
              {historyPayload.history.map(entry => (
                <div key={`${entry.scanId}-${entry.pricedAt}`} className="rounded border border-border p-3 text-sm">
                  <div className="flex items-center justify-between gap-3">
                    <span className="font-medium font-mono">
                      {entry.predictedValue}{entry.currency === 'div' ? ' div' : ' c'}
                    </span>
                    {entry.listedPrice != null && (
                      <span className="text-xs text-muted-foreground font-mono">
                        listed: {entry.listedPrice}{entry.currency === 'div' ? ' div' : ' c'}
                      </span>
                    )}
                    <span className="text-xs text-muted-foreground ml-auto">{entry.pricedAt}</span>
                  </div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    Confidence {entry.confidence}% · p10 {entry.interval.p10 ?? 'n/a'} · p90 {entry.interval.p90 ?? 'n/a'}
                    {entry.estimateTrust ? ` · ${entry.estimateTrust}` : ''}
                  </div>
                  {entry.estimateWarning && (
                    <div className="mt-0.5 text-[10px] text-warning">{entry.estimateWarning}</div>
                  )}
                </div>
              ))}
              {historyPayload.history.length === 0 && (
                <p className="text-xs text-muted-foreground">No price history available for this item.</p>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
});

StashViewerTab.displayName = 'StashViewerTab';

export default StashViewerTab;
