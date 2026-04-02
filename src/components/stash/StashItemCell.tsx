import React from 'react';
import type { PoeItem } from '@/types/api';
import { cn } from '@/lib/utils';
import { formatCurrencyShort } from '@/lib/currency';
import { HoverCard, HoverCardContent, HoverCardTrigger } from '@/components/ui/hover-card';
import ItemTooltip from './ItemTooltip';

const FRAME_TYPE_BORDER: Record<number, string> = {
  0: 'border-muted-foreground/30',
  1: 'border-info/50',
  2: 'border-exalt/50',
  3: 'border-chaos/60',
  4: 'border-divine/50',
  5: 'border-gold/40',
  6: 'border-divine/40',
  9: 'border-[hsl(15,70%,50%)]/50',
};

const EVAL_BG: Record<string, string> = {
  well_priced: 'bg-success/8',
  could_be_better: 'bg-warning/8',
  mispriced: 'bg-destructive/10',
};

const EVAL_BORDER: Record<string, string> = {
  well_priced: 'ring-1 ring-inset ring-success/40',
  could_be_better: 'ring-1 ring-inset ring-warning/40',
  mispriced: 'ring-1 ring-inset ring-destructive/50 animate-pulse',
};

const EVAL_BADGE_BG: Record<string, string> = {
  well_priced: 'bg-success/80 text-success-foreground',
  could_be_better: 'bg-warning/80 text-warning-foreground',
  mispriced: 'bg-destructive/90 text-destructive-foreground',
};

interface StashItemCellProps {
  item: PoeItem;
  isQuad?: boolean;
  style?: React.CSSProperties;
  className?: string;
  onItemClick?: (item: PoeItem) => void;
}

export default function StashItemCell({ item, isQuad, style, className, onItemClick }: StashItemCellProps) {
  const hasPrice = item.estimatedPrice != null && item.estimatedPrice > 0;
  const hasEval = hasPrice && !!item.priceEvaluation;
  const evalBg = hasEval ? EVAL_BG[item.priceEvaluation!] : '';
  const evalRing = hasEval ? EVAL_BORDER[item.priceEvaluation!] : '';
  const borderClass = FRAME_TYPE_BORDER[item.frameType] ?? 'border-muted-foreground/20';
  const displayName = item.name || item.typeLine;
  const iconSrc = item.icon || item.iconUrl;
  const cur = formatCurrencyShort(item.currency);

  return (
    <HoverCard openDelay={80} closeDelay={50}>
      <HoverCardTrigger asChild>
        <div
          className={cn(
            'stash-item-cell group relative',
            borderClass,
            evalBg,
            evalRing,
            onItemClick && item.fingerprint ? 'cursor-pointer' : '',
            className,
          )}
          style={style}
          onClick={onItemClick && item.fingerprint ? () => onItemClick(item) : undefined}
        >
          {/* Official icon */}
          {iconSrc && (
            <img
              src={iconSrc}
              alt={displayName}
              className="w-full h-full object-contain pointer-events-none select-none"
              loading="lazy"
              draggable={false}
            />
          )}

          {/* Stack size badge */}
          {item.stackSize != null && item.stackSize > 1 && (
            <span className={cn(
              'absolute top-0 left-0.5 z-10 font-mono font-bold text-foreground',
              'drop-shadow-[0_1px_2px_rgba(0,0,0,0.9)] drop-shadow-[0_0_4px_rgba(0,0,0,0.8)]',
              isQuad ? 'text-[5px]' : 'text-[9px]',
            )}>
              {item.stackSize}
            </span>
          )}

          {/* Price badge overlay */}
          {hasPrice && (
            <span className={cn(
              'absolute bottom-0 inset-x-0 text-center font-mono font-bold leading-none truncate',
              'drop-shadow-[0_1px_2px_rgba(0,0,0,0.95)]',
              isQuad ? 'text-[4px] px-0' : 'text-[7px] px-0.5',
              item.priceEvaluation
                ? EVAL_BADGE_BG[item.priceEvaluation]
                : 'bg-background/70 text-foreground',
            )}>
              {item.estimatedPrice! < 1000
                ? `${Math.round(item.estimatedPrice!)}${cur}`
                : `${(item.estimatedPrice! / 1000).toFixed(1)}k${cur}`}
            </span>
          )}

          {/* Delta percent label (normal tabs only) */}
          {!isQuad && hasPrice && item.priceDeltaPercent != null && Math.abs(item.priceDeltaPercent) >= 5 && (
            <span className={cn(
              'absolute top-0 right-0 font-mono font-bold leading-none',
              'text-[6px] px-0.5',
              'drop-shadow-[0_1px_2px_rgba(0,0,0,0.9)]',
              item.priceDeltaPercent > 0 ? 'text-success' : 'text-destructive',
            )}>
              {item.priceDeltaPercent > 0 ? '+' : ''}{Math.round(item.priceDeltaPercent)}%
            </span>
          )}
        </div>
      </HoverCardTrigger>
      <HoverCardContent side="right" className="w-64 p-0 bg-card border-gold-dim/50 shadow-lg shadow-black/50">
        <ItemTooltip item={item} />
      </HoverCardContent>
    </HoverCard>
  );
}
