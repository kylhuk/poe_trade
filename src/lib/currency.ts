const CURRENCY_ALIASES: Record<string, string> = {
  c: 'chaos',
  chaos: 'chaos',
  'chaos orb': 'chaos',
  d: 'divine',
  div: 'divine',
  divine: 'divine',
  'divine orb': 'divine',
  ex: 'exalted',
  exa: 'exalted',
  exalted: 'exalted',
  'exalted orb': 'exalted',
  alch: 'alchemy',
  alchemy: 'alchemy',
  fusing: 'fusing',
  fuse: 'fusing',
  chrom: 'chromatic',
  chromatic: 'chromatic',
  jew: 'jeweller',
  jeweller: 'jeweller',
  "jeweller's": 'jeweller',
  vaal: 'vaal',
};

const CURRENCY_SHORT_LABEL: Record<string, string> = {
  chaos: 'c',
  divine: 'div',
  exalted: 'exa',
  alchemy: 'alch',
  fusing: 'fus',
  chromatic: 'chrom',
  jeweller: 'jew',
  vaal: 'vaal',
};

const CHAOS_RATES: Record<string, number> = {
  chaos: 1,
  divine: 200,
  exalted: 12,
  alchemy: 0.25,
  fusing: 0.7,
  chromatic: 0.1,
  jeweller: 0.12,
  vaal: 1,
};

export function normalizeCurrency(currency?: string | null): string | undefined {
  if (!currency || !currency.trim()) {
    return undefined;
  }
  const normalized = currency.trim().toLowerCase();
  return CURRENCY_ALIASES[normalized] ?? normalized;
}

export function formatCurrencyShort(currency?: string | null): string {
  const normalized = normalizeCurrency(currency);
  if (!normalized) {
    return 'c';
  }
  return CURRENCY_SHORT_LABEL[normalized] ?? normalized;
}

export function toChaosValue(value: number, currency?: string | null): number | null {
  const normalized = normalizeCurrency(currency);
  if (!normalized) {
    return value;
  }
  const rate = CHAOS_RATES[normalized];
  if (rate == null) {
    return null;
  }
  return value * rate;
}