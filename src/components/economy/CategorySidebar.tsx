import React from 'react';
import type { ItemCategory } from '@/services/stashCache';
import { cn } from '@/lib/utils';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Coins, Sparkles, Gem, Map, Sword, ShieldHalf,
  CircleDot, FlaskConical, Crown, FileText, Package,
} from 'lucide-react';

const CATEGORY_ICON: Record<string, React.ElementType> = {
  currency: Coins,
  divination: FileText,
  gems: Gem,
  relics: Crown,
  unique_weapons: Sword,
  unique_armour: ShieldHalf,
  unique_accessories: CircleDot,
  unique_jewels: Sparkles,
  unique_flasks: FlaskConical,
  unique_maps: Map,
  rare_weapons: Sword,
  rare_armour: ShieldHalf,
  rare_accessories: CircleDot,
  rare_jewels: Sparkles,
  rare_flasks: FlaskConical,
  rare_maps: Map,
};

interface Props {
  categories: ItemCategory[];
  activeKey: string | null;
  onSelect: (key: string | null) => void;
}

export default function CategorySidebar({ categories, activeKey, onSelect }: Props) {
  const groups = {
    general: categories.filter(c => c.group === 'general'),
    equipment: categories.filter(c => c.group === 'equipment'),
    other: categories.filter(c => c.group === 'other'),
  };

  const totalCount = categories.reduce((s, c) => s + c.items.length, 0);

  return (
    <ScrollArea className="h-full">
      <div className="p-2 space-y-3">
        {/* All items button */}
        <button
          onClick={() => onSelect(null)}
          className={cn(
            'economy-sidebar-item w-full',
            activeKey === null && 'economy-sidebar-item-active',
          )}
        >
          <Package className="h-4 w-4 shrink-0" />
          <span className="truncate flex-1 text-left">All Items</span>
          <span className="text-muted-foreground font-mono text-[10px]">{totalCount}</span>
        </button>

        {groups.general.length > 0 && (
          <div>
            <div className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider px-2 mb-1">General</div>
            {groups.general.map(c => {
              const Icon = CATEGORY_ICON[c.key] || Package;
              return (
                <button
                  key={c.key}
                  onClick={() => onSelect(c.key)}
                  className={cn(
                    'economy-sidebar-item w-full',
                    activeKey === c.key && 'economy-sidebar-item-active',
                  )}
                >
                  <Icon className="h-4 w-4 shrink-0" />
                  <span className="truncate flex-1 text-left">{c.label}</span>
                  <span className="text-muted-foreground font-mono text-[10px]">{c.items.length}</span>
                </button>
              );
            })}
          </div>
        )}

        {groups.equipment.length > 0 && (
          <div>
            <div className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider px-2 mb-1">Equipment</div>
            {groups.equipment.map(c => {
              const Icon = CATEGORY_ICON[c.key] || Package;
              return (
                <button
                  key={c.key}
                  onClick={() => onSelect(c.key)}
                  className={cn(
                    'economy-sidebar-item w-full',
                    activeKey === c.key && 'economy-sidebar-item-active',
                  )}
                >
                  <Icon className="h-4 w-4 shrink-0" />
                  <span className="truncate flex-1 text-left">{c.label}</span>
                  <span className="text-muted-foreground font-mono text-[10px]">{c.items.length}</span>
                </button>
              );
            })}
          </div>
        )}

        {groups.other.length > 0 && (
          <div>
            <div className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider px-2 mb-1">Other</div>
            {groups.other.map(c => {
              const Icon = CATEGORY_ICON[c.key] || Package;
              return (
                <button
                  key={c.key}
                  onClick={() => onSelect(c.key)}
                  className={cn(
                    'economy-sidebar-item w-full',
                    activeKey === c.key && 'economy-sidebar-item-active',
                  )}
                >
                  <Icon className="h-4 w-4 shrink-0" />
                  <span className="truncate flex-1 text-left">{c.label}</span>
                  <span className="text-muted-foreground font-mono text-[10px]">{c.items.length}</span>
                </button>
              );
            })}
          </div>
        )}
      </div>
    </ScrollArea>
  );
}
