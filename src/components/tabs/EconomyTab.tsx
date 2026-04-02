import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '@/services/api';
import type { PoeItem, StashTabMeta } from '@/types/api';
import {
  loadAllStashItems,
  categorizeItems,
  fetchItemHistories,
  type ItemCategory,
  type LoadProgress,
  type ItemHistoryData,
} from '@/services/stashCache';
import CategorySidebar from '@/components/economy/CategorySidebar';
import EconomyTable from '@/components/economy/EconomyTable';
import ItemDetailDialog from '@/components/economy/ItemDetailDialog';
import { Input } from '@/components/ui/input';
import { Loader2, RefreshCw, Search } from 'lucide-react';
import { Button } from '@/components/ui/button';

type Phase = 'init' | 'loading' | 'ready' | 'error';

const PAGE_SIZE = 50;

export default function EconomyTab() {
  const [phase, setPhase] = useState<Phase>('init');
  const [progress, setProgress] = useState<LoadProgress>({ loaded: 0, total: 0 });
  const [allItems, setAllItems] = useState<PoeItem[]>([]);
  const [categories, setCategories] = useState<ItemCategory[]>([]);
  const [activeCategory, setActiveCategory] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [selectedItem, setSelectedItem] = useState<PoeItem | null>(null);
  const [errorMsg, setErrorMsg] = useState('');
  const [historyMap, setHistoryMap] = useState<Map<string, ItemHistoryData>>(new Map());
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyProgress, setHistoryProgress] = useState<{ loaded: number; total: number } | null>(null);

  const load = useCallback(async () => {
    setPhase('loading');
    setErrorMsg('');
    try {
      const status = await api.getStashStatus();
      if (!status.connected) {
        setErrorMsg('Stash not connected. Please connect your PoE session first.');
        setPhase('error');
        return;
      }
      const tabResp = await api.getStashScanResult();
      const tabsMeta: StashTabMeta[] = tabResp.tabsMeta;
      const scanId = tabResp.scanId || 'default';

      if (tabsMeta.length === 0) {
        setErrorMsg('No stash tabs found.');
        setPhase('error');
        return;
      }

      const items = await loadAllStashItems(tabsMeta, scanId, setProgress);
      setAllItems(items);
      setCategories(categorizeItems(items));
      setPhase('ready');
    } catch (e) {
      setErrorMsg(e instanceof Error ? e.message : 'Failed to load stash data');
      setPhase('error');
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const filteredItems = useMemo(() => {
    let items = allItems;
    if (activeCategory) {
      const cat = categories.find(c => c.key === activeCategory);
      items = cat ? cat.items : [];
    }
    if (search.trim()) {
      const q = search.toLowerCase().trim();
      items = items.filter(i =>
        (i.name || '').toLowerCase().includes(q) ||
        (i.typeLine || '').toLowerCase().includes(q) ||
        (i.baseType || '').toLowerCase().includes(q)
      );
    }
    return items;
  }, [allItems, activeCategory, categories, search]);

  // Background-load history for ALL items in batches
  useEffect(() => {
    if (phase !== 'ready' || allItems.length === 0) return;

    const allFingerprints = allItems
      .map(i => i.fingerprint)
      .filter((fp): fp is string => !!fp);
    const unique = [...new Set(allFingerprints)].filter(fp => !historyMap.has(fp));

    if (unique.length === 0) return;

    let cancelled = false;
    setHistoryLoading(true);

    const BATCH = 20;
    setHistoryProgress({ loaded: 0, total: unique.length });
    (async () => {
      for (let i = 0; i < unique.length; i += BATCH) {
        if (cancelled) return;
        const batch = unique.slice(i, i + BATCH);
        const result = await fetchItemHistories(batch);
        if (cancelled) return;
        const done = Math.min(i + BATCH, unique.length);
        setHistoryProgress({ loaded: done, total: unique.length });
        setHistoryMap(prev => {
          const next = new Map(prev);
          result.forEach((v, k) => next.set(k, v));
          return next;
        });
      }
      if (!cancelled) { setHistoryLoading(false); setHistoryProgress(null); }
    })();

    return () => { cancelled = true; };
  // Only run once when items are ready — historyMap excluded to avoid re-triggering
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase, allItems]);

  if (phase === 'init') {
    return (
      <div className="flex items-center justify-center py-20 text-muted-foreground gap-2">
        <Loader2 className="h-4 w-4 animate-spin" /> Initializing…
      </div>
    );
  }

  if (phase === 'loading') {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3">
        <Loader2 className="h-6 w-6 animate-spin text-primary" />
        <div className="text-sm text-muted-foreground font-mono">
          Loading tab {progress.loaded}/{progress.total}…
        </div>
        {progress.total > 0 && (
          <div className="w-48 h-1.5 bg-muted rounded-full overflow-hidden">
            <div
              className="h-full bg-primary transition-all duration-300"
              style={{ width: `${(progress.loaded / progress.total) * 100}%` }}
            />
          </div>
        )}
      </div>
    );
  }

  if (phase === 'error') {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3">
        <div className="text-sm text-destructive">{errorMsg}</div>
        <Button variant="outline" size="sm" onClick={load}>
          <RefreshCw className="h-3.5 w-3.5 mr-1.5" /> Retry
        </Button>
      </div>
    );
  }

  return (
    <div className="flex gap-4 min-h-[500px]">
      {/* Sidebar */}
      <div className="w-48 shrink-0 border border-border rounded bg-card hidden md:block">
        <CategorySidebar
          categories={categories}
          activeKey={activeCategory}
          onSelect={setActiveCategory}
        />
      </div>

      {/* Main */}
      <div className="flex-1 min-w-0 space-y-3">
        {/* Top bar */}
        <div className="flex items-center gap-2">
          <div className="relative flex-1 max-w-sm">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
            <Input
              placeholder="Search items…"
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="pl-8 h-8 text-xs"
            />
          </div>
          {/* Mobile category selector */}
          <select
            className="md:hidden bg-card border border-border rounded h-8 text-xs px-2 text-foreground"
            value={activeCategory || ''}
            onChange={e => setActiveCategory(e.target.value || null)}
          >
            <option value="">All Items ({allItems.length})</option>
            {categories.map(c => (
              <option key={c.key} value={c.key}>{c.label} ({c.items.length})</option>
            ))}
          </select>
          {historyProgress && (
            <span className="text-[10px] text-muted-foreground font-mono whitespace-nowrap">
              Loading prices: {historyProgress.loaded}/{historyProgress.total}
            </span>
          )}
          <Button variant="outline" size="sm" className="h-8 text-xs" onClick={load}>
            <RefreshCw className="h-3 w-3 mr-1" /> Reload
          </Button>
        </div>

        <EconomyTable
          items={filteredItems}
          onItemClick={setSelectedItem}
          historyMap={historyMap}
          historyLoading={historyLoading}
        />
      </div>

      <ItemDetailDialog
        item={selectedItem}
        open={!!selectedItem}
        onOpenChange={open => { if (!open) setSelectedItem(null); }}
      />
    </div>
  );
}
