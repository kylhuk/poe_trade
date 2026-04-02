import React from 'react';
import type { PoeItem } from '@/types/api';
import StashItemCell from './StashItemCell';

interface SpecialGridProps {
  items: PoeItem[];
  tabType: string;
  onItemClick?: (item: PoeItem) => void;
}

/**
 * Flow-based grid for special stash tab types (Currency, Essence, Map, etc.)
 * that don't have layout definitions. Items are sorted by slot index and
 * rendered in a responsive flex-wrap container.
 */
export default function SpecialGrid({ items, tabType, onItemClick }: SpecialGridProps) {
  const sorted = [...items].sort((a, b) => {
    if (a.y !== b.y) return a.y - b.y;
    return a.x - b.x;
  });

  return (
    <div className="stash-frame" data-testid="stash-panel-grid">
      <div className="stash-flow-grid">
        {sorted.map(item => (
          <StashItemCell
            key={item.id}
            item={item}
            className="stash-flow-cell"
            onItemClick={onItemClick}
          />
        ))}
        {sorted.length === 0 && (
          <p className="text-xs text-muted-foreground p-4">No items in this tab</p>
        )}
      </div>
    </div>
  );
}
