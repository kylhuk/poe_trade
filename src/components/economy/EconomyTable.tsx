import React, { useMemo, useState } from 'react';
import type { PoeItem } from '@/types/api';
import type { ItemHistoryData } from '@/services/stashCache';
import PriceSparkline from './PriceSparkline';
import { cn } from '@/lib/utils';
import { ChevronUp, ChevronDown, ChevronsUpDown } from 'lucide-react';
import { Button } from '@/components/ui/button';

const EVAL_LABEL: Record<string, string> = {
  well_priced: 'Well Priced',
  could_be_better: 'Improve',
  mispriced: 'Mispriced',
};

const EVAL_COLOR: Record<string, string> = {
  well_priced: 'text-success',
  could_be_better: 'text-warning',
  mispriced: 'text-destructive',
};

const RARITY_BORDER: Record<number, string> = {
  0: 'border-l-muted-foreground/30',
  1: 'border-l-info',
  2: 'border-l-warning',
  3: 'border-l-[hsl(30_80%_65%)]',
  4: 'border-l-[hsl(180_70%_70%)]',
  5: 'border-l-primary',
  6: 'border-l-[hsl(200_50%_72%)]',
  9: 'border-l-[hsl(15_80%_65%)]',
};

type SortField = 'name' | 'value' | 'delta' | 'ilvl' | 'listed' | 'qty' | 'change24h';
type SortDir = 'asc' | 'desc';

interface Props {
  items: PoeItem[];
  onItemClick: (item: PoeItem) => void;
  historyMap?: Map<string, ItemHistoryData>;
  historyLoading?: boolean;
}

const PAGE_SIZE = 50;

export default function EconomyTable({ items, onItemClick, historyMap, historyLoading }: Props) {
  const [sortField, setSortField] = useState<SortField>('value');
  const [sortDir, setSortDir] = useState<SortDir>('desc');
  const [page, setPage] = useState(0);

  const sorted = useMemo(() => {
    const arr = [...items];
    const dir = sortDir === 'asc' ? 1 : -1;
    arr.sort((a, b) => {
      switch (sortField) {
        case 'name':
          return dir * (a.name || a.typeLine).localeCompare(b.name || b.typeLine);
        case 'value':
          return dir * ((a.estimatedPrice ?? 0) - (b.estimatedPrice ?? 0));
        case 'listed':
          return dir * ((a.listedPrice ?? 0) - (b.listedPrice ?? 0));
        case 'delta':
          return dir * ((a.priceDeltaChaos ?? 0) - (b.priceDeltaChaos ?? 0));
        case 'ilvl':
          return dir * ((a.ilvl ?? 0) - (b.ilvl ?? 0));
        case 'qty':
          return dir * ((a.stackSize ?? 1) - (b.stackSize ?? 1));
        case 'change24h': {
          const aH = (a.fingerprint ? historyMap?.get(a.fingerprint)?.change24h : null) ?? 0;
          const bH = (b.fingerprint ? historyMap?.get(b.fingerprint)?.change24h : null) ?? 0;
          return dir * (aH - bH);
        }
        default:
          return 0;
      }
    });
    return arr;
  }, [items, sortField, sortDir, historyMap]);

  const pageCount = Math.max(1, Math.ceil(sorted.length / PAGE_SIZE));
  const safePage = Math.min(page, pageCount - 1);
  const pageItems = sorted.slice(safePage * PAGE_SIZE, (safePage + 1) * PAGE_SIZE);

  const toggleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDir('desc');
    }
    setPage(0);
  };

  const SortIcon = ({ field }: { field: SortField }) => {
    if (sortField !== field) return <ChevronsUpDown className="h-3 w-3 opacity-30" />;
    return sortDir === 'asc'
      ? <ChevronUp className="h-3 w-3 text-primary" />
      : <ChevronDown className="h-3 w-3 text-primary" />;
  };

  return (
    <div className="flex flex-col gap-2">
      <div className="border border-border rounded overflow-hidden">
        <table className="w-full text-xs">
          <thead>
            <tr className="bg-card border-b border-border text-muted-foreground">
              <th className="text-left py-2 px-3 font-medium w-8">#</th>
              <th className="text-left py-2 px-3 font-medium cursor-pointer select-none" onClick={() => toggleSort('name')}>
                <span className="inline-flex items-center gap-1">Item <SortIcon field="name" /></span>
              </th>
              <th className="text-right py-2 px-2 font-medium cursor-pointer select-none whitespace-nowrap" onClick={() => toggleSort('qty')}>
                <span className="inline-flex items-center gap-1 justify-end">Qty <SortIcon field="qty" /></span>
              </th>
              <th className="text-right py-2 px-2 font-medium cursor-pointer select-none whitespace-nowrap" onClick={() => toggleSort('value')}>
                <span className="inline-flex items-center gap-1 justify-end">Est. Value <SortIcon field="value" /></span>
              </th>
              <th className="text-right py-2 px-2 font-medium cursor-pointer select-none whitespace-nowrap" onClick={() => toggleSort('listed')}>
                <span className="inline-flex items-center gap-1 justify-end">Listed <SortIcon field="listed" /></span>
              </th>
              <th className="text-right py-2 px-2 font-medium cursor-pointer select-none whitespace-nowrap" onClick={() => toggleSort('delta')}>
                <span className="inline-flex items-center gap-1 justify-end">Δ <SortIcon field="delta" /></span>
              </th>
              <th className="text-right py-2 px-2 font-medium cursor-pointer select-none whitespace-nowrap" onClick={() => toggleSort('change24h')}>
                <span className="inline-flex items-center gap-1 justify-end">24h% <SortIcon field="change24h" /></span>
              </th>
              <th className="text-center py-2 px-2 font-medium whitespace-nowrap">7d</th>
              <th className="text-center py-2 px-2 font-medium whitespace-nowrap">Eval</th>
              <th className="text-right py-2 px-2 font-medium cursor-pointer select-none whitespace-nowrap" onClick={() => toggleSort('ilvl')}>
                <span className="inline-flex items-center gap-1 justify-end">iLvl <SortIcon field="ilvl" /></span>
              </th>
            </tr>
          </thead>
          <tbody>
            {pageItems.map((item, idx) => {
              const cur = item.currency === 'div' ? 'div' : 'c';
              const displayName = item.name || item.typeLine;
              const subtitle = item.name && item.typeLine && item.name !== item.typeLine ? item.typeLine : null;
              const rarityBorder = RARITY_BORDER[item.frameType] || '';
              const history = item.fingerprint ? historyMap?.get(item.fingerprint) : undefined;
              const change24h = history?.change24h ?? null;

              return (
                <tr
                  key={item.id}
                  onClick={() => onItemClick(item)}
                  className={cn('economy-row border-l-2', rarityBorder)}
                >
                  <td className="py-1.5 px-3 text-muted-foreground font-mono">{safePage * PAGE_SIZE + idx + 1}</td>
                  <td className="py-1.5 px-3">
                    <div className="flex items-center gap-2 min-w-0">
                      {item.icon && (
                        <img src={item.icon} alt="" className="w-8 h-8 object-contain shrink-0" loading="lazy" />
                      )}
                      <div className="min-w-0">
                        <div className="truncate font-medium text-foreground">{displayName}</div>
                        {subtitle && <div className="truncate text-[10px] text-muted-foreground">{subtitle}</div>}
                      </div>
                    </div>
                  </td>
                  <td className="py-1.5 px-2 text-right font-mono text-muted-foreground">
                    {item.stackSize != null && item.stackSize > 1 ? item.stackSize : '1'}
                  </td>
                  <td className="py-1.5 px-2 text-right font-mono text-gold-bright whitespace-nowrap">
                    {item.estimatedPrice != null ? `${item.estimatedPrice} ${cur}` : '—'}
                  </td>
                  <td className="py-1.5 px-2 text-right font-mono whitespace-nowrap">
                    {item.listedPrice != null ? `${item.listedPrice} ${cur}` : '—'}
                  </td>
                  <td className={cn(
                    'py-1.5 px-2 text-right font-mono whitespace-nowrap',
                    item.priceDeltaChaos != null && item.priceDeltaChaos > 0 ? 'text-success'
                      : item.priceDeltaChaos != null && item.priceDeltaChaos < 0 ? 'text-destructive'
                      : 'text-muted-foreground'
                  )}>
                    {item.priceDeltaChaos != null
                      ? `${item.priceDeltaChaos > 0 ? '+' : ''}${item.priceDeltaChaos}c`
                      : '—'}
                  </td>
                  <td className={cn(
                    'py-1.5 px-2 text-right font-mono whitespace-nowrap',
                    change24h != null && change24h > 0 ? 'text-success'
                      : change24h != null && change24h < 0 ? 'text-destructive'
                      : 'text-muted-foreground'
                  )}>
                    {change24h != null
                      ? `${change24h > 0 ? '+' : ''}${change24h.toFixed(1)}%`
                      : '—'}
                  </td>
                  <td className="py-1.5 px-2 text-center">
                    <PriceSparkline
                      points={history?.points}
                      loading={historyLoading && !history}
                    />
                  </td>
                  <td className="py-1.5 px-2 text-center">
                    {item.priceEvaluation && (
                      <span className={cn('text-[10px] font-semibold', EVAL_COLOR[item.priceEvaluation])}>
                        {EVAL_LABEL[item.priceEvaluation]}
                      </span>
                    )}
                  </td>
                  <td className="py-1.5 px-2 text-right font-mono text-muted-foreground">
                    {item.ilvl ?? '—'}
                  </td>
                </tr>
              );
            })}
            {pageItems.length === 0 && (
              <tr>
                <td colSpan={10} className="py-8 text-center text-muted-foreground">No items</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {pageCount > 1 && (
        <div className="flex items-center justify-between px-1">
          <span className="text-[10px] text-muted-foreground font-mono">
            {sorted.length} items · page {safePage + 1}/{pageCount}
          </span>
          <div className="flex gap-1">
            <Button variant="outline" size="sm" className="h-6 text-[10px] px-2" disabled={safePage === 0} onClick={() => setPage(p => p - 1)}>
              Prev
            </Button>
            <Button variant="outline" size="sm" className="h-6 text-[10px] px-2" disabled={safePage >= pageCount - 1} onClick={() => setPage(p => p + 1)}>
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
