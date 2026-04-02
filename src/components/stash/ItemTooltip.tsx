import React from 'react';
import type { PoeItem } from '@/types/api';
import { cn } from '@/lib/utils';
import { formatCurrencyShort } from '@/lib/currency';
import PriceSparkline from '@/components/economy/PriceSparkline';

const FRAME_HEADER_CLASS: Record<number, string> = {
  0: 'poe-tooltip-header-normal',
  1: 'poe-tooltip-header-magic',
  2: 'poe-tooltip-header-rare',
  3: 'poe-tooltip-header-unique',
  4: 'poe-tooltip-header-gem',
  5: 'poe-tooltip-header-currency',
  6: 'poe-tooltip-header-divination',
  9: 'poe-tooltip-header-relic',
};

const RARITY_NAME: Record<number, string> = {
  0: 'Normal', 1: 'Magic', 2: 'Rare', 3: 'Unique', 4: 'Gem', 5: 'Currency', 6: 'Divination Card', 9: 'Relic',
};

const SOCKET_COLOR: Record<string, string> = {
  R: 'bg-red-500', G: 'bg-green-500', B: 'bg-blue-500', W: 'bg-white', A: 'bg-white', DV: 'bg-primary',
};

const EVAL_LABEL: Record<string, string> = {
  well_priced: 'Well Priced', could_be_better: 'Could Be Better', mispriced: 'Mispriced',
};

const EVAL_COLOR: Record<string, string> = {
  well_priced: 'text-success', could_be_better: 'text-warning', mispriced: 'text-destructive',
};

interface ItemTooltipProps {
  item: PoeItem;
}

export default function ItemTooltip({ item }: ItemTooltipProps) {
  const headerClass = FRAME_HEADER_CLASS[item.frameType] ?? 'poe-tooltip-header-normal';
  const safeName = item.name && item.name.toLowerCase() !== 'unknown' ? item.name : '';
  const displayName = safeName || (item.typeLine && item.typeLine.toLowerCase() !== 'unknown' ? item.typeLine : '');
  const showTypeLine = safeName && item.typeLine && item.typeLine.toLowerCase() !== 'unknown' && safeName !== item.typeLine;
  const cur = formatCurrencyShort(item.currency);
  const listedCur = formatCurrencyShort(item.currency);

  const hasMedian = item.estimatedPrice != null && item.estimatedPrice > 0;
  const hasAffixFallbacks = !hasMedian && item.affixFallbackMedians && item.affixFallbackMedians.length > 0;

  // Build sparkline points from per-item daySeries
  const sparklinePoints = item.daySeries
    ?.filter(d => d.chaosMedian != null && d.chaosMedian > 0)
    .map(d => ({ timestamp: d.date, value: d.chaosMedian! })) ?? [];

  return (
    <div className="poe-tooltip text-xs">
      {/* Header */}
      <div className={cn('poe-tooltip-header', headerClass)}>
        <div className="font-semibold text-sm leading-tight">{displayName}</div>
        {showTypeLine && <div className="text-[11px] opacity-80">{item.typeLine}</div>}
      </div>

      <div className="px-3 py-2 space-y-1.5">
        {/* Properties */}
        {item.properties && item.properties.length > 0 && (
          <div className="space-y-0.5">
            {item.properties.map((prop, i) => (
              <div key={i} className="flex justify-between text-muted-foreground">
                <span>{prop.name}</span>
                {prop.values.length > 0 && (
                  <span className="text-info font-mono">{prop.values.map(v => v[0]).join(', ')}</span>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Requirements */}
        {item.requirements && item.requirements.length > 0 && (
          <>
            <div className="poe-tooltip-separator" />
            <div className="text-muted-foreground">
              <span>Requires </span>
              {item.requirements.map((req, i) => (
                <span key={i}>
                  {i > 0 && ', '}
                  {req.name} <span className="text-foreground">{req.values.map(v => v[0]).join(', ')}</span>
                </span>
              ))}
            </div>
          </>
        )}

        {/* Sockets */}
        {item.sockets && item.sockets.length > 0 && (
          <>
            <div className="poe-tooltip-separator" />
            <div className="flex items-center gap-0.5 flex-wrap">
              {item.sockets.map((socket, i) => {
                const prevSocket = i > 0 ? item.sockets![i - 1] : null;
                const isLinked = prevSocket && prevSocket.group === socket.group;
                return (
                  <React.Fragment key={i}>
                    {isLinked && <span className="w-1.5 h-0.5 bg-muted-foreground/50" />}
                    {!isLinked && i > 0 && <span className="w-1" />}
                    <span className={cn(
                      'w-3 h-3 rounded-full border border-muted-foreground/30 inline-block',
                      SOCKET_COLOR[socket.sColour] ?? 'bg-muted',
                    )} />
                  </React.Fragment>
                );
              })}
            </div>
          </>
        )}

        {/* Implicit mods */}
        {item.implicitMods && item.implicitMods.length > 0 && (
          <>
            <div className="poe-tooltip-separator" />
            <div className="space-y-0.5">
              {item.implicitMods.map((mod, i) => (
                <div key={i} className="text-info">{mod}</div>
              ))}
            </div>
          </>
        )}

        {/* Explicit mods */}
        {item.explicitMods && item.explicitMods.length > 0 && (
          <>
            <div className="poe-tooltip-separator" />
            <div className="space-y-0.5">
              {item.explicitMods.map((mod, i) => (
                <div key={i} className="text-info">{mod}</div>
              ))}
            </div>
          </>
        )}

        {/* Crafted mods */}
        {item.craftedMods && item.craftedMods.length > 0 && (
          <div className="space-y-0.5">
            {item.craftedMods.map((mod, i) => (
              <div key={i} className="text-info/70">{mod}</div>
            ))}
          </div>
        )}

        {/* Enchant mods */}
        {item.enchantMods && item.enchantMods.length > 0 && (
          <div className="space-y-0.5">
            {item.enchantMods.map((mod, i) => (
              <div key={i} className="text-info/70">{mod}</div>
            ))}
          </div>
        )}

        {/* Flavour text */}
        {item.flavourText && item.flavourText.length > 0 && (
          <>
            <div className="poe-tooltip-separator" />
            <div className="italic text-chaos/70 text-[10px] leading-tight">
              {item.flavourText.map((line, i) => <div key={i}>{line}</div>)}
            </div>
          </>
        )}

        {/* Corrupted / Unidentified */}
        {item.corrupted && <div className="text-destructive font-semibold">Corrupted</div>}
        {item.identified === false && <div className="text-destructive font-semibold">Unidentified</div>}

        {/* Item level */}
        {item.ilvl != null && (
          <div className="text-muted-foreground text-[10px]">Item Level: {item.ilvl}</div>
        )}

        {/* Description */}
        {item.descrText && (
          <div className="text-muted-foreground text-[10px] italic">{item.descrText}</div>
        )}

        {/* Price section: Median available */}
        {hasMedian && (
          <>
            <div className="poe-tooltip-separator" />
            <div className="space-y-0.5 pt-0.5">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Median</span>
                <span className="font-mono text-gold-bright">{item.estimatedPrice}{cur}</span>
              </div>
              {item.listedPrice != null && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Listed</span>
                  <span className="font-mono">{item.listedPrice} {listedCur}</span>
                </div>
              )}
              {item.priceDeltaChaos != null && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Delta</span>
                  <span className={cn('font-mono', item.priceDeltaChaos > 0 ? 'text-success' : item.priceDeltaChaos < 0 ? 'text-destructive' : 'text-muted-foreground')}>
                    {item.priceDeltaChaos > 0 ? '+' : ''}{item.priceDeltaChaos}c
                    {item.priceDeltaPercent != null && ` (${item.priceDeltaPercent > 0 ? '+' : ''}${item.priceDeltaPercent}%)`}
                  </span>
                </div>
              )}
              {item.priceEvaluation && (
                <div className={cn('text-[10px] font-semibold', EVAL_COLOR[item.priceEvaluation])}>
                  {EVAL_LABEL[item.priceEvaluation]}
                </div>
              )}
              {/* Inline sparkline from daySeries */}
              {sparklinePoints.length >= 2 && (
                <div className="pt-1">
                  <PriceSparkline points={sparklinePoints} width={200} height={28} />
                </div>
              )}
            </div>
          </>
        )}

        {/* Affix fallback medians: no overall median, show per-affix breakdown */}
        {hasAffixFallbacks && (
          <>
            <div className="poe-tooltip-separator" />
            <div className="space-y-0.5 pt-0.5">
              <div className="text-[10px] text-muted-foreground font-semibold">Affix Medians (manual review)</div>
              {item.affixFallbackMedians!.map((af, i) => (
                <div key={i} className="flex justify-between">
                  <span className="text-muted-foreground truncate max-w-[160px]">{af.affix}</span>
                  <span className="font-mono text-gold-bright">{af.chaosMedian}c</span>
                </div>
              ))}
              {item.listedPrice != null && (
                <div className="flex justify-between pt-0.5">
                  <span className="text-muted-foreground">Listed</span>
                  <span className="font-mono">{item.listedPrice} {listedCur}</span>
                </div>
              )}
            </div>
          </>
        )}

        {/* Show listed price only when no median AND no affix fallbacks */}
        {!hasMedian && !hasAffixFallbacks && item.listedPrice != null && (
          <>
            <div className="poe-tooltip-separator" />
            <div className="flex justify-between pt-0.5">
              <span className="text-muted-foreground">Listed</span>
              <span className="font-mono">{item.listedPrice} {listedCur}</span>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
