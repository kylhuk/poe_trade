import type {
  ApiService,
  AppMessage,
  DashboardResponse,
  HealthResponse,
  MlAutomationHistory,
  MlAutomationObservability,
  MlAutomationStatus,
  MlContractResponse,
  MlLeagueStatusResponse,
  MlPredictOneRequest,
  MlPredictOneResponse,
  PriceCheckRequest,
  PriceCheckResponse,
  PricingOutliersQuery,
  PricingOutliersQueryPayload,
  PricingOutliersRequest,
  PricingOutliersResponse,
  ScannerRecommendationsRequest,
  ScannerRecommendationsResponse,
  ScannerSummary,
  SearchHistoryRequest,
  SearchHistoryResponse,
  SearchSuggestionsResponse,
  Service,
  StashItemHistoryResponse,
  StashScanStartResponse,
  StashScanStatus,
  StashScanValuationsResponse,
  StashStatus,
  StashTabMeta,
  StashTabsResponse,
  PoeItem,
  StashTab,
} from '@/types/api';

export interface IngestionRow {
  queue_key: string;
  feed_kind: string;
  status: string;
  last_ingest_at: string;
}

export interface ScannerRow {
  strategy_id: string;
  enabled: boolean;
  recommendation_count: number;
  accepted_count: number;
  rejected_count: number;
  candidate_count: number;
  top_rejection_reason: string | null;
}

export interface GateRejection {
  decision_reason: string;
  rejection_count: number;
}

export interface ComplexityTier {
  complexity_tier: string | null;
  tier_count: number;
}

export interface ScannerAnalyticsResponse {
  latestRunId: string | null;
  rows: ScannerRow[];
  gateRejections: GateRejection[];
  complexityTiers: ComplexityTier[];
}

type ApiErrorPayload = {
  error?: {
    code?: string;
    message?: string;
    details?: unknown;
  };
};

type ContractPayload = {
  primary_league?: string;
};

type RequestOptions = {
  skipErrorCodes?: string[];
};

import { logApiError } from './apiErrorLog';
import { supabase, SUPABASE_PROJECT_ID } from '@/lib/supabaseClient';





async function request<T>(path: string, init?: RequestInit, options: RequestOptions = {}): Promise<T> {
  const method = init?.method || 'GET';
  let response: Response;
  try {
    const { data: { session } } = await supabase.auth.getSession();
    const token = session?.access_token;
    if (!token) {
      throw new Error('Not authenticated');
    }

    const url = `https://${SUPABASE_PROJECT_ID}.supabase.co/functions/v1/api-proxy`;

    response = await fetch(url, {
      ...init,
      credentials: 'include',
      signal: init?.signal,
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
        'x-proxy-path': path,
        ...(init?.headers || {}),
      },
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') {
      throw err;
    }
    const rawMessage = err instanceof Error ? err.message : 'Network error';
    const detail = `${method} ${path}: ${rawMessage}`;
    logApiError({ method, path, errorCode: 'network_error', message: rawMessage });
    throw new Error(detail);
  }
  if (!response.ok) {
    let payload: ApiErrorPayload = {};
    try {
      payload = (await response.json()) as ApiErrorPayload;
    } catch {
      payload = {};
    }
    const code = payload.error?.code || 'request_failed';
    const baseMessage = payload.error?.message || `Request failed (${response.status})`;
    const detail = formatApiErrorDetail(payload.error?.details);
    const message = detail ? `${baseMessage} (${detail})` : baseMessage;
    if (!options.skipErrorCodes?.includes(code)) {
      logApiError({ method, path, statusCode: response.status, errorCode: code, message });
    }
    throw new Error(`${code}: ${message}`);
  }
  if (response.status === 204) {
    return {} as T;
  }
  return (await response.json()) as T;
}

function formatApiErrorDetail(details: unknown): string | null {
  if (typeof details === 'string' && details.trim()) {
    return details.trim();
  }
  if (
    details &&
    typeof details === 'object' &&
    'reason' in details &&
    typeof details.reason === 'string' &&
    details.reason.trim()
  ) {
    return details.reason.trim();
  }
  return null;
}

async function primaryLeague(): Promise<string> {
  // Use the user-selected league from the top-level league selector
  const { getSelectedLeague } = await import('@/services/league');
  return getSelectedLeague();
}

export async function getAnalyticsIngestion() {
  const payload = await request<{ rows: IngestionRow[] }>('/api/v1/ops/analytics/ingestion');
  return payload.rows;
}

export async function getAnalyticsScanner() {
  const payload = await request<unknown>('/api/v1/ops/analytics/scanner');
  const source = asObject(payload);
  const rawRows = Array.isArray(source.rows) ? source.rows : [];
  const rawGateRejections = Array.isArray(source.gateRejections) ? source.gateRejections : [];
  const rawComplexityTiers = Array.isArray(source.complexityTiers) ? source.complexityTiers : [];

  return {
    latestRunId: optString(source.latestRunId),
    rows: rawRows.map((entry) => {
      const row = asObject(entry);
      return {
        strategy_id: optString(row.strategy_id ?? row.strategyId) ?? 'unknown',
        enabled: typeof row.enabled === 'boolean' ? row.enabled : false,
        recommendation_count: optNumber(row.recommendation_count ?? row.recommendationCount) ?? 0,
        accepted_count: optNumber(row.accepted_count ?? row.acceptedCount) ?? 0,
        rejected_count: optNumber(row.rejected_count ?? row.rejectedCount) ?? 0,
        candidate_count: optNumber(row.candidate_count ?? row.candidateCount) ?? 0,
        top_rejection_reason: optString(row.top_rejection_reason ?? row.topRejectionReason),
      };
    }),
    gateRejections: rawGateRejections.map((entry) => {
      const row = asObject(entry);
      return {
        decision_reason: optString(row.decision_reason ?? row.decisionReason) ?? 'unknown',
        rejection_count: optNumber(row.rejection_count ?? row.rejectionCount) ?? 0,
      };
    }),
    complexityTiers: rawComplexityTiers.map((entry) => {
      const row = asObject(entry);
      return {
        complexity_tier: optString(row.complexity_tier ?? row.complexityTier),
        tier_count: optNumber(row.tier_count ?? row.tierCount) ?? 0,
      };
    }),
  };
}


export interface OpportunitiesAnalytics {
  [key: string]: unknown;
}

export async function getAnalyticsOpportunities(): Promise<OpportunitiesAnalytics> {
  return request<OpportunitiesAnalytics>('/api/v1/ops/analytics/opportunities');
}



function normalizeTrustFields(source: Record<string, unknown>) {
  return {
    mlPredicted: typeof (source.mlPredicted ?? source.ml_predicted) === 'boolean'
      ? (source.mlPredicted ?? source.ml_predicted) as boolean
      : undefined,
    predictionSource: optString(source.predictionSource ?? source.prediction_source) ?? undefined,
    estimateTrust: optString(source.estimateTrust ?? source.estimate_trust) ?? undefined,
    estimateWarning: optString(source.estimateWarning ?? source.estimate_warning) ?? null,
  };
}

function normalizeMlPredictOneResponse(payload: unknown): MlPredictOneResponse {
  const source = (payload && typeof payload === 'object') ? payload as Record<string, unknown> : {};
  const intervalSource = (source.interval && typeof source.interval === 'object')
    ? source.interval as Record<string, unknown>
    : {};
  const p10 = typeof intervalSource.p10 === 'number'
    ? intervalSource.p10
    : (typeof source.price_p10 === 'number' ? source.price_p10 : null);
  const p90 = typeof intervalSource.p90 === 'number'
    ? intervalSource.p90
    : (typeof source.price_p90 === 'number' ? source.price_p90 : null);

  return {
    predictedValue: typeof source.predictedValue === 'number'
      ? source.predictedValue
      : (typeof source.price_p50 === 'number' ? source.price_p50 : 0),
    currency: typeof source.currency === 'string' && source.currency.trim() ? source.currency : 'chaos',
    confidence: typeof source.confidence === 'number'
      ? source.confidence
      : (typeof source.confidence_percent === 'number' ? source.confidence_percent : 0),
    interval: { p10, p90 },
    saleProbabilityPercent: typeof source.saleProbabilityPercent === 'number'
      ? source.saleProbabilityPercent
      : (typeof source.sale_probability_percent === 'number' ? source.sale_probability_percent : null),
    priceRecommendationEligible: typeof source.priceRecommendationEligible === 'boolean'
      ? source.priceRecommendationEligible
      : Boolean(source.price_recommendation_eligible),
    fallbackReason: typeof source.fallbackReason === 'string'
      ? source.fallbackReason
      : (typeof source.fallback_reason === 'string' ? source.fallback_reason : ''),
    league: optString(source.league) ?? undefined,
    route: optString(source.route) ?? undefined,
    ...normalizeTrustFields(source),
  };
}

function normalizePriceCheckResponse(payload: unknown): PriceCheckResponse {
  const source = (payload && typeof payload === 'object') ? payload as Record<string, unknown> : {};
  const intervalSource = (source.interval && typeof source.interval === 'object')
    ? source.interval as Record<string, unknown>
    : {};
  const p10 = typeof intervalSource.p10 === 'number' ? intervalSource.p10 : null;
  const p90 = typeof intervalSource.p90 === 'number' ? intervalSource.p90 : null;
  const rawComparables = Array.isArray(source.comparables) ? source.comparables : [];

  return {
    predictedValue: typeof source.predictedValue === 'number' ? source.predictedValue : 0,
    currency: typeof source.currency === 'string' && source.currency.trim() ? source.currency : 'chaos',
    confidence: typeof source.confidence === 'number' ? source.confidence : 0,
    interval: { p10, p90 },
    comparables: rawComparables.map((c: unknown) => {
      const o = asObject(c);
      return {
        name: optString(o.name) ?? '',
        price: typeof o.price === 'number' ? o.price : 0,
        currency: optString(o.currency) ?? 'chaos',
        league: optString(o.league) ?? undefined,
        addedOn: optString(o.addedOn ?? o.added_on) ?? null,
      };
    }),
    saleProbabilityPercent: typeof source.saleProbabilityPercent === 'number'
      ? source.saleProbabilityPercent
      : (typeof source.sale_probability_percent === 'number' ? source.sale_probability_percent : null),
    priceRecommendationEligible: typeof source.priceRecommendationEligible === 'boolean'
      ? source.priceRecommendationEligible
      : Boolean(source.price_recommendation_eligible),
    fallbackReason: typeof source.fallbackReason === 'string'
      ? source.fallbackReason
      : (typeof source.fallback_reason === 'string' ? source.fallback_reason : ''),
    fairValueP50: optNumber(source.fairValueP50 ?? source.fair_value_p50),
    fastSale24hPrice: optNumber(source.fastSale24hPrice ?? source.fast_sale_24h_price),
    ...normalizeTrustFields(source),
  };
}

function buildQueryString(params: Record<string, string | number | undefined>): string {
  const entries = Object.entries(params).filter(([, v]) => v !== undefined && v !== '');
  if (entries.length === 0) return '';
  return '?' + entries.map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`).join('&');
}

function normalizePriceRange(source: Record<string, unknown>): { min: number; max: number } {
  return {
    min: optNumber(source.min) ?? 0,
    max: optNumber(source.max) ?? 0,
  };
}

function normalizeDatetimeRange(source: Record<string, unknown>): { min: string | null; max: string | null } {
  return {
    min: optString(source.min),
    max: optString(source.max),
  };
}

function normalizePriceBuckets(payload: unknown): SearchHistoryResponse['histograms']['price'] {
  const buckets = Array.isArray(payload) ? payload : [];
  return buckets.map((entry) => {
    const bucket = asObject(entry);
    return {
      bucketStart: optNumber(bucket.bucketStart ?? bucket.bucket_start) ?? 0,
      bucketEnd: optNumber(bucket.bucketEnd ?? bucket.bucket_end) ?? 0,
      count: optNumber(bucket.count) ?? 0,
    };
  });
}

function normalizeDatetimeBuckets(payload: unknown): SearchHistoryResponse['histograms']['datetime'] {
  const buckets = Array.isArray(payload) ? payload : [];
  return buckets.map((entry) => {
    const bucket = asObject(entry);
    return {
      bucketStart: optString(bucket.bucketStart ?? bucket.bucket_start) ?? '',
      bucketEnd: optString(bucket.bucketEnd ?? bucket.bucket_end) ?? '',
      count: optNumber(bucket.count) ?? 0,
    };
  });
}

function normalizeSearchHistoryRows(payload: unknown): SearchHistoryResponse['rows'] {
  const rows = Array.isArray(payload) ? payload : [];
  return rows.map((entry) => {
    const row = asObject(entry);
    return {
      itemName: optString(row.itemName ?? row.item_name) ?? '',
      league: optString(row.league) ?? '',
      listedPrice: optNumber(row.listedPrice ?? row.listed_price) ?? 0,
      currency: optString(row.currency) ?? 'chaos',
      addedOn: optString(row.addedOn ?? row.added_on) ?? '',
    };
  });
}

function normalizePricingOutlierRows(payload: unknown): PricingOutliersResponse['rows'] {
  const rows = Array.isArray(payload) ? payload : [];
  return rows.map((entry) => {
    const row = asObject(entry);
    return {
      itemName: optString(row.itemName ?? row.item_name) ?? '',
      affixAnalyzed: optString(row.affixAnalyzed ?? row.affix_analyzed),
      p10: optNumber(row.p10) ?? 0,
      median: optNumber(row.median) ?? 0,
      p90: optNumber(row.p90) ?? 0,
      itemsPerWeek: optNumber(row.itemsPerWeek ?? row.items_per_week) ?? 0,
      itemsTotal: optNumber(row.itemsTotal ?? row.items_total) ?? 0,
      analysisLevel: optString(row.analysisLevel ?? row.analysis_level) ?? 'item',
      entryPrice: optNumber(row.entryPrice ?? row.entry_price),
      expectedProfit: optNumber(row.expectedProfit ?? row.expected_profit),
      roi: optNumber(row.roi),
      underpricedRate: optNumber(row.underpricedRate ?? row.underpriced_rate),
    };
  });
}

function normalizePricingOutlierWeeks(payload: unknown): PricingOutliersResponse['weekly'] {
  const rows = Array.isArray(payload) ? payload : [];
  return rows.map((entry) => {
    const row = asObject(entry);
    return {
      weekStart: optString(row.weekStart ?? row.week_start) ?? '',
      tooCheapCount: optNumber(row.tooCheapCount ?? row.too_cheap_count) ?? 0,
    };
  });
}

function normalizeSearchHistoryResponse(payload: unknown): SearchHistoryResponse {
  const source = asObject(payload);
  const query = asObject(source.query);
  const filters = asObject(source.filters);
  const histograms = asObject(source.histograms);
  return {
    query: {
      text: optString(query.text ?? source.query) ?? '',
      league: optString(query.league ?? source.league) ?? '',
      sort: optString(query.sort ?? source.sort) ?? 'item_name',
      order: optString(query.order ?? source.order) === 'asc' ? 'asc' : 'desc',
    },
    filters: {
      leagueOptions: Array.isArray(filters.leagueOptions ?? filters.league_options)
        ? ((filters.leagueOptions ?? filters.league_options) as unknown[]).filter((value): value is string => typeof value === 'string')
        : [],
      price: normalizePriceRange(asObject(filters.price)),
      datetime: normalizeDatetimeRange(asObject(filters.datetime)),
    },
    histograms: {
      price: normalizePriceBuckets(histograms.price),
      datetime: normalizeDatetimeBuckets(histograms.datetime),
    },
    rows: normalizeSearchHistoryRows(source.rows),
  };
}

function normalizePricingOutliersResponse(payload: unknown): PricingOutliersResponse {
  const source = asObject(payload);
  const query = asObject(source.query) as PricingOutliersQueryPayload;
  const topLevelLimit = optNumber(source.limit);
  const normalizedQuery = {
    ...(optString(query.query) ? { query: optString(query.query) } : {}),
    ...(optString(query.league ?? source.league) ? { league: optString(query.league ?? source.league) } : {}),
    ...(optString(query.sort ?? source.sort) ? { sort: optString(query.sort ?? source.sort) } : {}),
    ...((query.order ?? source.order) === 'asc' || (query.order ?? source.order) === 'desc'
      ? { order: (query.order ?? source.order) as 'asc' | 'desc' }
      : {}),
    ...(optNumber(query.minTotal ?? query.min_total ?? source.minTotal ?? source.min_total) != null
      ? { minTotal: optNumber(query.minTotal ?? query.min_total ?? source.minTotal ?? source.min_total) as number }
      : {}),
    ...((optNumber(query.limit) ?? topLevelLimit) != null
      ? { limit: (optNumber(query.limit) ?? topLevelLimit) as number }
      : {}),
  } satisfies PricingOutliersQuery;
  return {
    query: normalizedQuery,
    rows: normalizePricingOutlierRows(source.rows),
    weekly: normalizePricingOutlierWeeks(source.weekly),
  };
}

function frameTypeFromRarity(value: unknown): number {
  switch (value) {
    case 'magic':
      return 1;
    case 'rare':
      return 2;
    case 'unique':
      return 3;
    default:
      return 0;
  }
}

function normalizePoeItem(raw: unknown): PoeItem {
  const item = asObject(raw);
  const name = optString(item.name) ?? '';
  const typeLine = optString(item.typeLine ?? item.type_line ?? item.itemClass ?? item.item_class) ?? name;
  const iconUrl = optString(item.icon ?? item.iconUrl ?? item.icon_url) ?? '';

  return {
    id: optString(item.id) ?? crypto.randomUUID(),
    fingerprint: optString(item.fingerprint) ?? undefined,
    name,
    typeLine,
    baseType: optString(item.baseType ?? item.base_type) ?? undefined,
    icon: iconUrl,
    iconUrl: iconUrl || undefined,
    x: optNumber(item.x) ?? 0,
    y: optNumber(item.y) ?? 0,
    w: optNumber(item.w) ?? 1,
    h: optNumber(item.h) ?? 1,
    frameType: optNumber(item.frameType ?? item.frame_type) ?? frameTypeFromRarity(item.rarity),
    stackSize: optNumber(item.stackSize ?? item.stack_size) ?? undefined,
    maxStackSize: optNumber(item.maxStackSize ?? item.max_stack_size) ?? undefined,
    ilvl: optNumber(item.ilvl) ?? undefined,
    identified: typeof item.identified === 'boolean' ? item.identified : undefined,
    corrupted: typeof item.corrupted === 'boolean' ? item.corrupted : undefined,
    duplicated: typeof item.duplicated === 'boolean' ? item.duplicated : undefined,
    properties: Array.isArray(item.properties) ? item.properties as PoeItem['properties'] : undefined,
    requirements: Array.isArray(item.requirements) ? item.requirements as PoeItem['requirements'] : undefined,
    implicitMods: Array.isArray(item.implicitMods ?? item.implicit_mods) ? (item.implicitMods ?? item.implicit_mods) as string[] : undefined,
    explicitMods: Array.isArray(item.explicitMods ?? item.explicit_mods) ? (item.explicitMods ?? item.explicit_mods) as string[] : undefined,
    craftedMods: Array.isArray(item.craftedMods ?? item.crafted_mods) ? (item.craftedMods ?? item.crafted_mods) as string[] : undefined,
    enchantMods: Array.isArray(item.enchantMods ?? item.enchant_mods) ? (item.enchantMods ?? item.enchant_mods) as string[] : undefined,
    fracturedMods: Array.isArray(item.fracturedMods ?? item.fractured_mods) ? (item.fracturedMods ?? item.fractured_mods) as string[] : undefined,
    utilityMods: Array.isArray(item.utilityMods ?? item.utility_mods) ? (item.utilityMods ?? item.utility_mods) as string[] : undefined,
    descrText: optString(item.descrText ?? item.descr_text) ?? undefined,
    flavourText: Array.isArray(item.flavourText ?? item.flavour_text) ? (item.flavourText ?? item.flavour_text) as string[] : undefined,
    sockets: Array.isArray(item.sockets) ? item.sockets as PoeItem['sockets'] : undefined,
    listedPrice: optNumber(item.listedPrice ?? item.listed_price),
    // Pricing fields intentionally omitted from scan result normalization.
    // They are only populated via mergeValuationIntoItems from the /valuations/result endpoint.
    estimatedPrice: undefined,
    estimatedPriceConfidence: undefined,
    priceDeltaChaos: undefined,
    priceDeltaPercent: undefined,
    priceEvaluation: undefined,
    currency: optString(item.currency) ?? undefined,
  };
}

function mapPoeStashType(rawType: string): StashTab['type'] {
  const map: Record<string, StashTab['type']> = {
    QuadStash: 'quad',
    NormalStash: 'normal',
    PremiumStash: 'normal',
    CurrencyStash: 'currency',
    FragmentStash: 'fragment',
    MapStash: 'map',
    EssenceStash: 'essence',
    DivinationCardStash: 'divination',
    UniqueStash: 'unique',
    DelveStash: 'delve',
    FlaskStash: 'flask',
    GemStash: 'gem',
    BlightStash: 'blight',
    UltimatumStash: 'ultimatum',
    DeliriumStash: 'delirium',
    MetamorphStash: 'metamorph',
  };
  return map[rawType] ?? (rawType as StashTab['type']) ?? 'normal';
}

function normalizeStashTab(raw: unknown, fallbackIndex?: number): StashTab {
  const tab = asObject(raw);
  const rawItems = Array.isArray(tab.items) ? tab.items : [];
  const rawType = optString(tab.type) ?? 'normal';
  const mappedType = mapPoeStashType(rawType);

  return {
    id: optString(tab.id) ?? crypto.randomUUID(),
    name: optString(tab.name) ?? 'Tab',
    type: mappedType,
    returnedIndex: optNumber(tab.index ?? tab.tabIndex ?? tab.tab_index) ?? fallbackIndex,
    items: rawItems.map(normalizePoeItem),
    quadLayout: mappedType === 'quad' || (typeof tab.quadLayout === 'boolean' ? tab.quadLayout : Boolean(tab.quad_layout)),
    currencyLayout: (tab.currencyLayout ?? tab.currency_layout) as StashTab['currencyLayout'],
    fragmentLayout: (tab.fragmentLayout ?? tab.fragment_layout) as StashTab['fragmentLayout'],
    essenceLayout: (tab.essenceLayout ?? tab.essence_layout) as StashTab['essenceLayout'],
    deliriumLayout: (tab.deliriumLayout ?? tab.delirium_layout) as StashTab['deliriumLayout'],
    blightLayout: (tab.blightLayout ?? tab.blight_layout) as StashTab['blightLayout'],
    ultimatumLayout: (tab.ultimatumLayout ?? tab.ultimatum_layout) as StashTab['ultimatumLayout'],
    mapLayout: (tab.mapLayout ?? tab.map_layout) as StashTab['mapLayout'],
    divinationLayout: (tab.divinationLayout ?? tab.divination_layout) as StashTab['divinationLayout'],
    uniqueLayout: (tab.uniqueLayout ?? tab.unique_layout) as StashTab['uniqueLayout'],
    delveLayout: (tab.delveLayout ?? tab.delve_layout) as StashTab['delveLayout'],
    metamorphLayout: (tab.metamorphLayout ?? tab.metamorph_layout) as StashTab['metamorphLayout'],
  };
}

function normalizeTabsMeta(rawTabs: unknown[]): StashTabMeta[] {
  return rawTabs.map((entry) => {
    const t = asObject(entry);
    const meta = asObject(t.metadata);
    return {
      id: optString(t.id) ?? '',
      tabIndex: optNumber(t.tab_index ?? t.tabIndex ?? t.index) ?? 0,
      name: optString(t.name) ?? 'Tab',
      type: optString(t.type) ?? 'NormalStash',
      colour: optString(meta.colour as unknown) ?? undefined,
    };
  });
}

function normalizeStashTabsResponse(payload: unknown): StashTabsResponse {
  const source = asObject(payload);
  const rawTabsMeta = Array.isArray(source.tabs) ? source.tabs as unknown[] : [];
  const tabsMeta = normalizeTabsMeta(rawTabsMeta);

  // Top-level items array (per API spec: items is a required top-level field)
  const topLevelItems = Array.isArray(source.items) ? (source.items as unknown[]).map(normalizePoeItem) : [];

  // New raw PoE schema: { stash: {single tab object}, tabs: [...], items: [...], numTabs }
  if (source.stash && typeof source.stash === 'object' && !Array.isArray(source.stash)) {
    const tab = normalizeStashTab(source.stash, 0);
    // Merge top-level items if the stash object itself had none
    if (tab.items.length === 0 && topLevelItems.length > 0) {
      tab.items = topLevelItems;
    }
    const effectiveTabsMeta = tabsMeta.length > 0
      ? tabsMeta
      : [{ id: tab.id, tabIndex: 0, name: tab.name, type: tab.type }];
    const numTabs = optNumber(source.numTabs ?? source.num_tabs) ?? effectiveTabsMeta.length;
    return {
      scanId: optString(source.scanId ?? source.scan_id),
      publishedAt: optString(source.publishedAt ?? source.published_at),
      isStale: typeof source.isStale === 'boolean' ? source.isStale : Boolean(source.is_stale),
      scanStatus: (source.scanStatus ?? source.scan_status) as StashTabsResponse['scanStatus'],
      stashTabs: [tab],
      tabsMeta: effectiveTabsMeta,
      numTabs,
    };
  }

  // Legacy format: { stashTabs: [...] }
  const rawTabs = Array.isArray(source.stashTabs ?? source.stash_tabs) ? (source.stashTabs ?? source.stash_tabs) as unknown[] : [];
  const stashTabs = rawTabs.map((tab, index) => normalizeStashTab(tab, index));
  const effectiveTabsMeta = tabsMeta.length > 0
    ? tabsMeta
    : stashTabs.map((tab, index) => ({
        id: tab.id,
        tabIndex: index,
        name: tab.name,
        type: tab.type,
      }));
  const numTabs = optNumber(source.numTabs ?? source.num_tabs) ?? effectiveTabsMeta.length;

  return {
    scanId: optString(source.scanId ?? source.scan_id),
    publishedAt: optString(source.publishedAt ?? source.published_at),
    isStale: typeof source.isStale === 'boolean' ? source.isStale : Boolean(source.is_stale),
    scanStatus: (source.scanStatus ?? source.scan_status) as StashTabsResponse['scanStatus'],
    stashTabs,
    tabsMeta: effectiveTabsMeta,
    numTabs,
  };
}

export async function getAnalyticsSearchSuggestions(query: string) {
  const queryString = buildQueryString({ query });
  return request<SearchSuggestionsResponse>(`/api/v1/ops/analytics/search-suggestions${queryString}`);
}

export async function getAnalyticsSearchHistory(params: SearchHistoryRequest) {
  const queryString = buildQueryString({
    query: params.query,
    league: params.league,
    sort: params.sort,
    order: params.order,
    price_min: params.priceMin,
    price_max: params.priceMax,
    time_from: params.timeFrom,
    time_to: params.timeTo,
    limit: params.limit,
  });
  return normalizeSearchHistoryResponse(
    await request<unknown>(`/api/v1/ops/analytics/search-history${queryString}`)
  );
}

export async function getAnalyticsPricingOutliers(params: PricingOutliersRequest = {}) {
  const queryString = buildQueryString({
    query: params.query,
    league: params.league,
    sort: params.sort,
    order: params.order,
    min_total: params.minTotal,
    limit: params.limit,
  });
  return normalizePricingOutliersResponse(
    await request<unknown>(`/api/v1/ops/analytics/pricing-outliers${queryString}`)
  );
}


function asObject(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' ? value as Record<string, unknown> : {};
}

function optString(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null;
}

function optNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function normalizeMlAutomationObservability(raw: unknown): MlAutomationObservability {
  const o = asObject(raw);
  return {
    datasetRows: optNumber(o.datasetRows ?? o.dataset_rows) ?? 0,
    latestTrainingAsOf: optString(o.latestTrainingAsOf ?? o.latest_training_as_of),
    promotedModels: optNumber(o.promotedModels ?? o.promoted_models) ?? 0,
    latestPromotionAt: optString(o.latestPromotionAt ?? o.latest_promotion_at),
    evalRuns: optNumber(o.evalRuns ?? o.eval_runs) ?? 0,
    evalSampleRows: optNumber(o.evalSampleRows ?? o.eval_sample_rows) ?? 0,
    latestEvalAt: optString(o.latestEvalAt ?? o.latest_eval_at),
    evaluationAvailable: typeof (o.evaluationAvailable ?? o.evaluation_available) === 'boolean'
      ? (o.evaluationAvailable ?? o.evaluation_available) as boolean
      : false,
  };
}

function normalizeMlAutomationStatus(payload: unknown): MlAutomationStatus {
  const source = asObject(payload);
  const latest = asObject(source.latestRun ?? source.latest_run);
  const hasLatest = Object.keys(latest).length > 0;
  const rawTrainerRuntime = source.trainerRuntime ?? source.trainer_runtime;
  let trainerRuntime: MlAutomationStatus['trainerRuntime'] = null;
  if (rawTrainerRuntime && typeof rawTrainerRuntime === 'object') {
    const tr = rawTrainerRuntime as Record<string, unknown>;
    trainerRuntime = {
      stage: optString(tr.stage),
      status: optString(tr.status),
      updatedAt: optString(tr.updatedAt ?? tr.updated_at),
      details: (tr.details && typeof tr.details === 'object') ? tr.details as Record<string, unknown> : {},
    };
  }
  return {
    league: optString(source.league) ?? 'Mirage',
    status: optString(source.status),
    activeModelVersion: optString(source.activeModelVersion ?? source.active_model_version),
    latestRun: hasLatest ? {
      runId: optString(latest.runId ?? latest.run_id),
      status: optString(latest.status),
      stopReason: optString(latest.stopReason ?? latest.stop_reason),
      updatedAt: optString(latest.updatedAt ?? latest.updated_at),
    } : null,
    promotionVerdict: optString(source.promotionVerdict ?? source.promotion_verdict),
    routeHotspots: Array.isArray(source.routeHotspots ?? source.route_hotspots)
      ? (source.routeHotspots ?? source.route_hotspots) as unknown[]
      : [],
    observability: normalizeMlAutomationObservability(source.observability),
    trainerRuntime,
  };
}

function normalizeMlAutomationHistory(payload: unknown): MlAutomationHistory {
  const source = asObject(payload);
  const historyRows = Array.isArray(source.history) ? source.history : [];
  const summary = asObject(source.summary);
  const qualityTrend = Array.isArray(source.qualityTrend ?? source.quality_trend) ? (source.qualityTrend ?? source.quality_trend) as unknown[] : [];
  const trainingCadence = Array.isArray(source.trainingCadence ?? source.training_cadence) ? (source.trainingCadence ?? source.training_cadence) as unknown[] : [];
  const routeMetrics = Array.isArray(source.routeMetrics ?? source.route_metrics) ? (source.routeMetrics ?? source.route_metrics) as unknown[] : [];
  const datasetCoverage = asObject(source.datasetCoverage ?? source.dataset_coverage);
  const promotions = Array.isArray(source.promotions) ? source.promotions : [];
  return {
    league: optString(source.league) ?? 'Mirage',
    mode: optString(source.mode),
    history: historyRows.map((entry) => {
      const row = asObject(entry);
      return {
        runId: optString(row.runId ?? row.run_id),
        status: optString(row.status),
        stopReason: optString(row.stopReason ?? row.stop_reason),
        activeModelVersion: optString(row.activeModelVersion ?? row.active_model_version),
        tuningConfigId: optString(row.tuningConfigId ?? row.tuning_config_id),
        evalRunId: optString(row.evalRunId ?? row.eval_run_id),
        updatedAt: optString(row.updatedAt ?? row.updated_at),
        rowsProcessed: optNumber(row.rowsProcessed ?? row.rows_processed),
        avgMdape: optNumber(row.avgMdape ?? row.avg_mdape),
        avgIntervalCoverage: optNumber(row.avgIntervalCoverage ?? row.avg_interval_coverage),
        verdict: optString(row.verdict),
      };
    }),
    summary: {
      activeModelVersion: optString(summary.activeModelVersion ?? summary.active_model_version),
      lastRunAt: optString(summary.lastRunAt ?? summary.last_run_at),
      lastPromotedAt: optString(summary.lastPromotedAt ?? summary.last_promoted_at),
      runsLast7d: optNumber(summary.runsLast7d ?? summary.runs_last_7d) ?? 0,
      runsLast30d: optNumber(summary.runsLast30d ?? summary.runs_last_30d) ?? 0,
      medianHoursBetweenRuns: optNumber(summary.medianHoursBetweenRuns ?? summary.median_hours_between_runs),
      latestAvgMdape: optNumber(summary.latestAvgMdape ?? summary.latest_avg_mdape),
      latestAvgIntervalCoverage: optNumber(summary.latestAvgIntervalCoverage ?? summary.latest_avg_interval_coverage),
      bestAvgMdape: optNumber(summary.bestAvgMdape ?? summary.best_avg_mdape),
      mdapeDeltaVsPrevious: optNumber(summary.mdapeDeltaVsPrevious ?? summary.mdape_delta_vs_previous),
      trendDirection: optString(summary.trendDirection ?? summary.trend_direction) ?? 'unknown',
    },
    qualityTrend: qualityTrend.map((entry) => {
      const row = asObject(entry);
      return {
        runId: optString(row.runId ?? row.run_id),
        updatedAt: optString(row.updatedAt ?? row.updated_at),
        avgMdape: optNumber(row.avgMdape ?? row.avg_mdape),
        avgIntervalCoverage: optNumber(row.avgIntervalCoverage ?? row.avg_interval_coverage),
        verdict: optString(row.verdict),
        activeModelVersion: optString(row.activeModelVersion ?? row.active_model_version),
      };
    }),
    trainingCadence: trainingCadence.map((entry) => {
      const row = asObject(entry);
      return {
        date: optString(row.date) ?? '',
        runs: optNumber(row.runs) ?? 0,
      };
    }),
    routeMetrics: routeMetrics.map((entry) => {
      const row = asObject(entry);
      return {
        route: optString(row.route),
        sampleCount: optNumber(row.sampleCount ?? row.sample_count),
        avgMdape: optNumber(row.avgMdape ?? row.avg_mdape),
        avgIntervalCoverage: optNumber(row.avgIntervalCoverage ?? row.avg_interval_coverage),
        avgAbstainRate: optNumber(row.avgAbstainRate ?? row.avg_abstain_rate),
        recordedAt: optString(row.recordedAt ?? row.recorded_at),
      };
    }),
    datasetCoverage: {
      totalRows: optNumber(datasetCoverage.totalRows ?? datasetCoverage.total_rows) ?? 0,
      supportedRows: optNumber(datasetCoverage.supportedRows ?? datasetCoverage.supported_rows) ?? 0,
      coverageRatio: optNumber(datasetCoverage.coverageRatio ?? datasetCoverage.coverage_ratio) ?? 0,
      baseTypeCount: optNumber(datasetCoverage.baseTypeCount ?? datasetCoverage.base_type_count),
      routes: Array.isArray(datasetCoverage.routes) ? datasetCoverage.routes.map((entry) => {
        const row = asObject(entry);
        return {
          route: optString(row.route),
          rows: optNumber(row.rows) ?? 0,
          share: optNumber(row.share) ?? 0,
        };
      }) : [],
    },
    promotions: promotions.map((entry) => {
      const row = asObject(entry);
      return {
        modelVersion: optString(row.modelVersion ?? row.model_version),
        promotedAt: optString(row.promotedAt ?? row.promoted_at),
      };
    }),
    observability: normalizeMlAutomationObservability(source.observability),
    charts: (() => {
      const rawCharts = source.charts;
      if (!rawCharts || typeof rawCharts !== 'object') return undefined;
      const c = rawCharts as Record<string, unknown>;
      return {
        mdapeHistory: Array.isArray(c.mdapeHistory ?? c.mdape_history)
          ? (c.mdapeHistory ?? c.mdape_history) as Record<string, unknown>[]
          : [],
        coverageHistory: Array.isArray(c.coverageHistory ?? c.coverage_history)
          ? (c.coverageHistory ?? c.coverage_history) as Record<string, unknown>[]
          : [],
      };
    })(),
  };
}

const EMPTY_SCAN_STATUS_TEMPLATE: StashScanStatus = {
  status: 'idle',
  activeScanId: null,
  publishedScanId: null,
  startedAt: null,
  updatedAt: null,
  publishedAt: null,
  error: null,
  progress: { tabsProcessed: 0, tabsTotal: 0, itemsProcessed: 0, itemsTotal: 0 },
};

export const api: ApiService = {
  async getHealthz() {
    return request<HealthResponse>('/healthz');
  },

  async getDashboard() {
    return request<DashboardResponse>('/api/v1/ops/dashboard');
  },

  async getScannerSummary() {
    return request<ScannerSummary>('/api/v1/ops/scanner/summary');
  },

  async getScannerRecommendations(requestParams?: ScannerRecommendationsRequest) {
    const query = new URLSearchParams();
    if (requestParams?.sort) {
      query.set('sort', requestParams.sort);
    }
    if (requestParams?.limit !== undefined) {
      query.set('limit', String(requestParams.limit));
    }
    if (requestParams?.cursor !== undefined) {
      query.set('cursor', requestParams.cursor);
    }
    if (requestParams?.league) {
      query.set('league', requestParams.league);
    }
    if (requestParams?.strategyId !== undefined) {
      query.set('strategy_id', requestParams.strategyId);
    }
    if (requestParams?.minConfidence !== undefined) {
      const normalizedConfidence = requestParams.minConfidence > 1
        ? requestParams.minConfidence / 100
        : requestParams.minConfidence;
      query.set('min_confidence', String(normalizedConfidence));
    }
    const queryString = query.toString();
    const path = queryString
      ? `/api/v1/ops/scanner/recommendations?${queryString}`
      : '/api/v1/ops/scanner/recommendations';
    return request<ScannerRecommendationsResponse>(path);
  },

  async ackAlert(alertId: string) {
    await request<{ alertId: string; status: string }>(`/api/v1/ops/alerts/${encodeURIComponent(alertId)}/ack`, {
      method: 'POST',
    });
  },

  async getStashStatus() {
    const league = await primaryLeague();
    return request<StashStatus>(`/api/v1/stash/status?league=${encodeURIComponent(league)}&realm=pc`);
  },

  async startStashScan() {
    return request<StashScanStartResponse>('/api/v1/stash/scan/start', {
      method: 'POST',
    });
  },

  async getStashScanStatus() {
    return request<StashScanStatus>('/api/v1/stash/scan/status');
  },

  async getStashItemHistory(fingerprint: string) {
    const league = await primaryLeague();
    return request<StashItemHistoryResponse>(
      `/api/v1/stash/items/${encodeURIComponent(fingerprint)}/history?league=${encodeURIComponent(league)}&realm=pc`
    );
  },

  async getMlAutomationStatus() {
    const league = await primaryLeague();
    const payload = await request<Record<string, unknown>>(`/api/v1/ml/leagues/${encodeURIComponent(league)}/automation/status`);
    return normalizeMlAutomationStatus(payload);
  },

  async getMlAutomationHistory() {
    const league = await primaryLeague();
    const payload = await request<Record<string, unknown>>(`/api/v1/ml/leagues/${encodeURIComponent(league)}/automation/history`);
    return normalizeMlAutomationHistory(payload);
  },

  async getServices() {
    const payload = await request<{ services: Service[] }>('/api/v1/ops/services');
    return payload.services;
  },

  async startService(id) {
    await request<{ service: Service }>(`/api/v1/actions/services/${id}/start`, {
      method: 'POST',
    });
  },

  async stopService(id) {
    await request<{ service: Service }>(`/api/v1/actions/services/${id}/stop`, {
      method: 'POST',
    });
  },

  async restartService(id) {
    await request<{ service: Service }>(`/api/v1/actions/services/${id}/restart`, {
      method: 'POST',
    });
  },
  async getMlContract() {
    return request<MlContractResponse>('/api/v1/ml/contract');
  },

  async getMlLeagueStatus() {
    const league = await primaryLeague();
    return request<MlLeagueStatusResponse>(`/api/v1/ml/leagues/${encodeURIComponent(league)}/status`);
  },

  async priceCheck(req) {
    const league = await primaryLeague();
    const payload = await request<Record<string, unknown>>(`/api/v1/ops/leagues/${encodeURIComponent(league)}/price-check`, {
      method: 'POST',
      body: JSON.stringify({ itemText: req.itemText.trim() }),
    });
    return normalizePriceCheckResponse(payload);
  },

  async mlPredictOne(req) {
    const league = await primaryLeague();
    const payload = await request<Record<string, unknown>>(`/api/v1/ml/leagues/${encodeURIComponent(league)}/predict-one`, {
      method: 'POST',
      body: JSON.stringify({ itemText: req.itemText.trim() }),
    });
    return normalizeMlPredictOneResponse(payload);
  },

  async getStashScanResult(signal?: AbortSignal) {
    const payload = await request<unknown>(
      '/api/v1/stash/scan/result',
      signal ? { signal } : undefined,
    );
    return normalizeStashTabsResponse(payload);
  },

  async startStashValuations() {
    await request<unknown>('/api/v1/stash/scan/valuations/start', {
      method: 'POST',
    });
  },

  async getStashValuationsResult(signal?: AbortSignal) {
    return request<StashScanValuationsResponse>(
      '/api/v1/stash/scan/valuations/result',
      signal ? { signal } : undefined,
    );
  },

  async getStashValuationsStatus() {
    const raw = await request<Record<string, unknown>>(
      '/api/v1/stash/scan/valuations/status',
    );
    // Backend may return a status-shaped payload or a valuation-result-shaped payload.
    // Normalise both into StashScanStatus so polling works either way.
    if (typeof raw.status === 'string' && ['idle', 'running', 'publishing', 'published', 'failed'].includes(raw.status)) {
      return raw as unknown as StashScanStatus;
    }
    // If payload has items/scanId but no status field, treat as completed
    if (Array.isArray(raw.items) || raw.scanId || raw.scan_id) {
      return { ...EMPTY_SCAN_STATUS_TEMPLATE, status: 'published' as const } as StashScanStatus;
    }
    return raw as unknown as StashScanStatus;
  },

  async getMessages() {
    const payload = await request<unknown>('/api/v1/ops/messages');
    // Spec says OpsMessagesResponse is a plain array; handle both shapes
    if (Array.isArray(payload)) return payload as AppMessage[];
    const obj = payload as Record<string, unknown>;
    if (Array.isArray(obj.messages)) return obj.messages as AppMessage[];
    return [];
  },
};
