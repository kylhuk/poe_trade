import React from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import type { PoeItem } from '@/types/api';
import ItemTooltip from '@/components/stash/ItemTooltip';

interface Props {
  item: PoeItem | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export default function ItemDetailDialog({ item, open, onOpenChange }: Props) {
  if (!item) return null;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm bg-card border-border p-0 overflow-hidden">
        <DialogHeader className="sr-only">
          <DialogTitle>{item.name || item.typeLine}</DialogTitle>
        </DialogHeader>
        <div className="flex justify-center p-4">
          {item.icon && (
            <img
              src={item.icon}
              alt={item.name || item.typeLine}
              className="w-16 h-16 object-contain mr-4"
            />
          )}
          <div className="flex-1 min-w-0">
            <ItemTooltip item={item} />
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
