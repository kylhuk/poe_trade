import React, { useState } from 'react';
import type { PoeItem, SpecialLayout } from '@/types/api';
import StashItemCell from './StashItemCell';
import { cn } from '@/lib/utils';

interface SpecialLayoutGridProps {
  items: PoeItem[];
  layout: SpecialLayout;
  onItemClick?: (item: PoeItem) => void;
}

// PoE special tabs use a fixed coordinate system (~569px viewport)
const VIEWPORT_SIZE = 569;

export default function SpecialLayoutGrid({ items, layout, onItemClick }: SpecialLayoutGridProps) {
  const sections = layout.sections ?? [];
  const [activeSection, setActiveSection] = useState(sections[0] ?? '');

  // Build a map of slot key → item by matching item.x to slot index
  const itemBySlotIndex = new Map<number, PoeItem>();
  for (const item of items) {
    itemBySlotIndex.set(item.x, item);
  }

  // Get visible slots for current section
  const visibleSlots = Object.entries(layout.layout).filter(([, slot]) => {
    if (slot.hidden) return false;
    if (sections.length > 0 && activeSection && slot.section && slot.section !== activeSection) return false;
    return true;
  });

  return (
    <div className="stash-frame" data-testid="stash-panel-grid">
      {/* Section sub-tabs */}
      {sections.length > 1 && (
        <div className="flex items-center gap-0 mb-0">
          {sections.map(section => (
            <button
              key={section}
              onClick={() => setActiveSection(section)}
              className={cn(
                'px-3 py-1.5 text-[10px] font-display tracking-wider uppercase border border-b-0 transition-all',
                section === activeSection
                  ? 'bg-gold-dim/25 text-gold-bright border-gold-dim/60 shadow-[0_-1px_4px_hsl(38_55%_42%/0.15)]'
                  : 'bg-[hsl(25_10%_6%)] text-muted-foreground border-[hsl(25_8%_12%)] hover:text-gold hover:bg-gold-dim/10'
              )}
            >
              {section}
            </button>
          ))}
        </div>
      )}

      {/* Absolute-positioned grid */}
      <div
        className="stash-special-layout"
        style={{ paddingBottom: '100%' }}
      >
        {visibleSlots.map(([key, slot]) => {
          // Parse slot index: could be "0" or "0,0" format
          const slotIndex = parseInt(key.split(',')[0], 10);
          const item = itemBySlotIndex.get(slotIndex);
          const scale = slot.scale ?? 1;
          const cellW = slot.w * scale;
          const cellH = slot.h * scale;

          const leftPct = (slot.x / VIEWPORT_SIZE) * 100;
          const topPct = (slot.y / VIEWPORT_SIZE) * 100;
          const widthPct = (cellW / VIEWPORT_SIZE) * 100;
          const heightPct = (cellH / VIEWPORT_SIZE) * 100;

          return (
            <div
              key={key}
              className="absolute"
              style={{
                left: `${leftPct}%`,
                top: `${topPct}%`,
                width: `${widthPct}%`,
                height: `${heightPct}%`,
              }}
            >
              {item ? (
                <StashItemCell
                  item={item}
                  className="w-full h-full"
                  onItemClick={onItemClick}
                />
              ) : (
                <div className="stash-empty-cell w-full h-full" />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
