import React from 'react';
import type { PoeItem } from '@/types/api';
import StashItemCell from './StashItemCell';

interface NormalGridProps {
  items: PoeItem[];
  gridSize: number; // 12 for normal, 24 for quad
  onItemClick?: (item: PoeItem) => void;
}

export default function NormalGrid({ items, gridSize, onItemClick }: NormalGridProps) {
  const isQuad = gridSize === 24;

  return (
    <div className="stash-frame" data-testid="stash-panel-grid">
      <div
        className="stash-grid"
        style={{
          gridTemplateColumns: `repeat(${gridSize}, 1fr)`,
          gridTemplateRows: `repeat(${gridSize}, 1fr)`,
          gap: isQuad ? '0px' : '1px',
        }}
      >
        {/* Empty cell bg */}
        {Array.from({ length: gridSize * gridSize }).map((_, i) => (
          <div
            key={`e${i}`}
            className="stash-empty-cell"
            style={{
              gridColumn: (i % gridSize) + 1,
              gridRow: Math.floor(i / gridSize) + 1,
            }}
          />
        ))}
        {/* Items */}
        {items.map(item => (
          <StashItemCell
            key={item.id}
            item={item}
            isQuad={isQuad}
            onItemClick={onItemClick}
            style={{
              gridColumn: `${item.x + 1} / span ${item.w}`,
              gridRow: `${item.y + 1} / span ${item.h}`,
              zIndex: 1,
            }}
          />
        ))}
      </div>
    </div>
  );
}
