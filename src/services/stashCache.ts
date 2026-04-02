import type { PoeItem, StashTabMeta, StashItemHistoryEntry } from '@/types/api';
import { api } from './api';
import type { SparklinePoint } from '@/components/economy/PriceSparkline';

const CACHE_KEY_PREFIX = 'stash-cache-';

export interface ItemCategory {
  key: string;
  label: string;
  group: 'general' | 'equipment' | 'other';
  items: PoeItem[];
}

// ── Categorization ────────────────────────────────

const WEAPON_KEYWORDS = ['sword', 'axe', 'mace', 'bow', 'claw', 'dagger', 'staff', 'wand', 'sceptre', 'flail', 'rapier', 'warstaff'];
const ARMOUR_KEYWORDS = ['helmet', 'boots', 'gloves', 'body armour', 'shield', 'buckler', 'spirit shield', 'tower shield', 'cap', 'mask', 'helm', 'hat', 'circlet', 'crown', 'hood', 'plate', 'vest', 'robe', 'coat', 'jacket', 'garb', 'regalia', 'greaves', 'sabatons', 'slippers', 'gauntlets', 'mitts', 'wraps', 'evasion', 'armour', 'chainmail'];
const ACCESSORY_KEYWORDS = ['ring', 'amulet', 'belt', 'quiver', 'talisman'];
const JEWEL_KEYWORDS = ['jewel'];
const FLASK_KEYWORDS = ['flask'];
const MAP_KEYWORDS = ['map'];

function classifyEquipment(item: PoeItem): string {
  const bt = (item.baseType || item.typeLine || '').toLowerCase();
  if (JEWEL_KEYWORDS.some(k => bt.includes(k))) return 'jewels';
  if (FLASK_KEYWORDS.some(k => bt.includes(k))) return 'flasks';
  if (MAP_KEYWORDS.some(k => bt.includes(k))) return 'maps';
  if (WEAPON_KEYWORDS.some(k => bt.includes(k))) return 'weapons';
  if (ARMOUR_KEYWORDS.some(k => bt.includes(k))) return 'armour';
  if (ACCESSORY_KEYWORDS.some(k => bt.includes(k))) return 'accessories';
  return 'other';
}

function getCategoryKey(item: PoeItem): string {
  switch (item.frameType) {
    case 5: return 'currency';
    case 6: return 'divination';
    case 4: return 'gems';
    case 9: return 'relics';
    case 3: {
      const slot = classifyEquipment(item);
      return `unique_${slot}`;
    }
    default: {
      const slot = classifyEquipment(item);
      return `rare_${slot}`;
    }
  }
}

const CATEGORY_LABELS: Record<string, string> = {
  currency: 'Currency',
  divination: 'Divination Cards',
  gems: 'Gems',
  relics: 'Relics',
  unique_weapons: 'Unique Weapons',
  unique_armour: 'Unique Armour',
  unique_accessories: 'Unique Accessories',
  unique_jewels: 'Unique Jewels',
  unique_flasks: 'Unique Flasks',
  unique_maps: 'Unique Maps',
  unique_other: 'Unique Other',
  rare_weapons: 'Rare Weapons',
  rare_armour: 'Rare Armour',
  rare_accessories: 'Rare Accessories',
  rare_jewels: 'Rare Jewels',
  rare_flasks: 'Rare Flasks',
  rare_maps: 'Maps',
  rare_other: 'Other Equipment',
};

const CATEGORY_GROUP: Record<string, 'general' | 'equipment' | 'other'> = {
  currency: 'general',
  divination: 'general',
  gems: 'general',
  relics: 'general',
};

export function categorizeItems(items: PoeItem[]): ItemCategory[] {
  const buckets = new Map<string, PoeItem[]>();

  for (const item of items) {
    const key = getCategoryKey(item);
    const list = buckets.get(key) || [];
    list.push(item);
    buckets.set(key, list);
  }

  const categories: ItemCategory[] = [];
  for (const [key, catItems] of buckets) {
    categories.push({
      key,
      label: CATEGORY_LABELS[key] || key,
      group: CATEGORY_GROUP[key] || (key.startsWith('unique_') ? 'equipment' : 'other'),
      items: catItems,
    });
  }

  // Sort: general first, then equipment, then other; within group by count desc
  const groupOrder = { general: 0, equipment: 1, other: 2 };
  categories.sort((a, b) => {
    const g = groupOrder[a.group] - groupOrder[b.group];
    if (g !== 0) return g;
    return b.items.length - a.items.length;
  });

  return categories;
}

// ── Cache ─────────────────────────────────────────

function cacheKey(scanId: string) {
  return `${CACHE_KEY_PREFIX}${scanId}`;
}

export function getCachedItems(scanId: string): PoeItem[] | null {
  try {
    const raw = sessionStorage.getItem(cacheKey(scanId));
    if (!raw) return null;
    return JSON.parse(raw) as PoeItem[];
  } catch {
    return null;
  }
}

function setCachedItems(scanId: string, items: PoeItem[]) {
  try {
    // Clear old caches first
    for (let i = sessionStorage.length - 1; i >= 0; i--) {
      const k = sessionStorage.key(i);
      if (k && k.startsWith(CACHE_KEY_PREFIX) && k !== cacheKey(scanId)) {
        sessionStorage.removeItem(k);
      }
    }
    sessionStorage.setItem(cacheKey(scanId), JSON.stringify(items));
  } catch {
    // sessionStorage full — that's okay, we still have in-memory
  }
}

export function invalidateCache() {
  for (let i = sessionStorage.length - 1; i >= 0; i--) {
    const k = sessionStorage.key(i);
    if (k && k.startsWith(CACHE_KEY_PREFIX)) {
      sessionStorage.removeItem(k);
    }
  }
}

// ── History Cache ─────────────────────────────────

export interface ItemHistoryData {
  points: SparklinePoint[];
  change24h: number | null;
}

const historyCache = new Map<string, ItemHistoryData>();

function deriveChange24h(entries: StashItemHistoryEntry[]): number | null {
  if (entries.length < 2) return null;
  const sorted = [...entries].sort((a, b) => new Date(a.pricedAt).getTime() - new Date(b.pricedAt).getTime());
  const now = Date.now();
  const cutoff = now - 24 * 60 * 60 * 1000;
  const recent = sorted.filter(e => new Date(e.pricedAt).getTime() >= cutoff);
  if (recent.length < 2) {
    // Fall back to last two entries
    const prev = sorted[sorted.length - 2].predictedValue;
    const curr = sorted[sorted.length - 1].predictedValue;
    if (prev === 0) return null;
    return ((curr - prev) / prev) * 100;
  }
  const first = recent[0].predictedValue;
  const last = recent[recent.length - 1].predictedValue;
  if (first === 0) return null;
  return ((last - first) / first) * 100;
}

export async function fetchItemHistories(
  fingerprints: string[],
): Promise<Map<string, ItemHistoryData>> {
  const result = new Map<string, ItemHistoryData>();
  const toFetch = fingerprints.filter(fp => {
    if (historyCache.has(fp)) {
      result.set(fp, historyCache.get(fp)!);
      return false;
    }
    return true;
  });

  for (const fp of toFetch) {
    try {
      const resp = await api.getStashItemHistory(fp);
      const points: SparklinePoint[] = resp.history.map(e => ({
        timestamp: e.pricedAt,
        value: e.predictedValue,
      }));
      const data: ItemHistoryData = {
        points,
        change24h: deriveChange24h(resp.history),
      };
      historyCache.set(fp, data);
      result.set(fp, data);
    } catch {
      // Skip failed fetches
      historyCache.set(fp, { points: [], change24h: null });
      result.set(fp, { points: [], change24h: null });
    }
  }

  return result;
}

export interface LoadProgress {
  loaded: number;
  total: number;
}

export async function loadAllStashItems(
  tabsMeta: StashTabMeta[],
  scanId: string,
  onProgress?: (p: LoadProgress) => void,
): Promise<PoeItem[]> {
  // Check cache first
  const cached = getCachedItems(scanId);
  if (cached) return cached;

  onProgress?.({ loaded: 0, total: tabsMeta.length });

  // New API returns all tabs in one call
  const resp = await api.getStashScanResult();
  const allItems: PoeItem[] = [];
  for (const tab of resp.stashTabs) {
    allItems.push(...tab.items);
  }

  onProgress?.({ loaded: tabsMeta.length, total: tabsMeta.length });

  setCachedItems(scanId, allItems);
  return allItems;
}
