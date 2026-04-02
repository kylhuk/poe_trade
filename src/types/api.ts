// ========== Service Management ==========
export type ServiceStatus = 'running' | 'stopped' | 'error' | 'starting' | 'stopping';

export interface Service {
  id: string;
  name: string;
  description: string;
  status: ServiceStatus;
  uptime: number | null; // seconds
  lastCrawl: string | null; // ISO timestamp
  rowsInDb: number | null;
  containerInfo: string | null;
  type: string;
  allowedActions?: Array<'start' | 'stop' | 'restart'>;
}


// ========== Price Check ==========
export interface PriceCheckRequest {
  itemText: string;
}

export interface PriceComparable {
  name: string;
  price: number;
  currency: string;
  league?: string;
  addedOn?: string | null;
}

export interface PriceCheckResponse {
  predictedValue: number | null;
  currency: string;
  confidence: number | null;
  comparables: PriceComparable[];
  interval?: { p10: number | null; p90: number | null };
  saleProbabilityPercent?: number | null;
  priceRecommendationEligible?: boolean;
  fallbackReason?: string;
  mlPredicted?: boolean;
  predictionSource?: string;
  estimateTrust?: string;
  estimateWarning?: string | null;
  fairValueP50?: number | null;
  fastSale24hPrice?: number | null;
}

// ========== ML Predict One ==========
export interface MlPredictOneRequest {
  itemText: string;
}

export interface MlPredictOneResponse {
  predictedValue: number;
  currency: string;
  confidence: number;
  interval?: { p10: number | null; p90: number | null };
  saleProbabilityPercent?: number | null;
  fallbackReason?: string;
  priceRecommendationEligible?: boolean;
  league?: string;
  route?: string;
  mlPredicted?: boolean;
  predictionSource?: string;
  estimateTrust?: string;
  estimateWarning?: string | null;
}

// ========== Search History Analytics ==========
export interface SearchSuggestion {
  itemName: string;
  itemKind: string;
  matchCount: number;
}

export interface SearchSuggestionsResponse {
  query: string;
  suggestions: SearchSuggestion[];
}

export interface SearchHistoryPriceBucket {
  bucketStart: number;
  bucketEnd: number;
  count: number;
}

export interface SearchHistoryDatetimeBucket {
  bucketStart: string;
  bucketEnd: string;
  count: number;
}

export interface SearchHistoryRow {
  itemName: string;
  league: string;
  listedPrice: number;
  currency: string;
  addedOn: string;
}

export interface SearchHistoryResponse {
  query: {
    text: string;
    league: string;
    sort: string;
    order: 'asc' | 'desc';
  };
  filters: {
    leagueOptions: string[];
    price: { min: number; max: number };
    datetime: { min: string | null; max: string | null };
  };
  histograms: {
    price: SearchHistoryPriceBucket[];
    datetime: SearchHistoryDatetimeBucket[];
  };
  rows: SearchHistoryRow[];
}

export interface SearchHistoryRequest {
  query: string;
  league?: string;
  sort?: string;
  order?: 'asc' | 'desc';
  priceMin?: number;
  priceMax?: number;
  timeFrom?: string;
  timeTo?: string;
  limit?: number;
}

// ========== Pricing Outlier Analytics ==========
export interface PricingOutlierRow {
  itemName: string;
  affixAnalyzed: string | null;
  p10: number;
  median: number;
  p90: number;
  itemsPerWeek: number;
  itemsTotal: number;
  analysisLevel: string;
  entryPrice: number | null;
  expectedProfit: number | null;
  roi: number | null;
  underpricedRate: number | null;
}

export interface PricingOutlierWeek {
  weekStart: string;
  tooCheapCount: number;
}

export interface PricingOutliersQuery {
  query?: string;
  league?: string;
  sort?: string;
  order?: 'asc' | 'desc';
  minTotal?: number;
  limit?: number;
}

export interface PricingOutliersQueryPayload extends PricingOutliersQuery {
  min_total?: number;
}

export interface PricingOutliersResponse {
  query: PricingOutliersQuery;
  rows: PricingOutlierRow[];
  weekly: PricingOutlierWeek[];
}

export interface PricingOutliersRequest {
  query?: string;
  league?: string;
  sort?: string;
  order?: 'asc' | 'desc';
  minTotal?: number;
  limit?: number;
}

// ========== Stash Viewer ==========
export type PriceEvaluation = 'well_priced' | 'could_be_better' | 'mispriced';

// Raw PoE API item shape
export interface PoeItemProperty {
  name: string;
  values: [string, number][];
  displayMode: number;
  type?: number;
}

export interface PoeItemSocket {
  group: number;
  attr: string;
  sColour: 'R' | 'G' | 'B' | 'W' | 'A' | 'DV';
}

export interface PoeItemRequirement {
  name: string;
  values: [string, number][];
  displayMode: number;
  type?: number;
}

export interface PoeItem {
  id: string;
  fingerprint?: string;
  name: string;
  typeLine: string;
  baseType?: string;
  icon: string;
  iconUrl?: string;
  x: number;
  y: number;
  w: number;
  h: number;
  frameType: number;
  stackSize?: number;
  maxStackSize?: number;
  ilvl?: number;
  identified?: boolean;
  corrupted?: boolean;
  duplicated?: boolean;
  properties?: PoeItemProperty[];
  requirements?: PoeItemRequirement[];
  implicitMods?: string[];
  explicitMods?: string[];
  craftedMods?: string[];
  enchantMods?: string[];
  fracturedMods?: string[];
  utilityMods?: string[];
  descrText?: string;
  flavourText?: string[];
  sockets?: PoeItemSocket[];
  listedPrice?: number | null;
  estimatedPrice?: number | null;
  estimatedPriceConfidence?: number | null;
  priceDeltaChaos?: number | null;
  priceDeltaPercent?: number | null;
  priceEvaluation?: PriceEvaluation;
  currency?: string;
  chaosMedian?: number | null;
  daySeries?: StashScanValuationDaySeries[];
  affixFallbackMedians?: StashScanValuationAffixFallback[];
}

export interface SpecialLayoutSlot {
  x: number;
  y: number;
  w: number;
  h: number;
  scale?: number;
  section?: string;
  hidden?: boolean;
}

export interface SpecialLayout {
  sections?: string[];
  layout: Record<string, SpecialLayoutSlot>;
}

export interface StashItem {
  id: string;
  fingerprint?: string;
  name: string;
  x: number;
  y: number;
  w: number;
  h: number;
  itemClass?: string;
  rarity: 'normal' | 'magic' | 'rare' | 'unique';
  listedPrice: number | null;
  estimatedPrice: number;
  estimatedPriceConfidence: number;
  priceDeltaChaos: number;
  priceDeltaPercent: number;
  priceEvaluation: PriceEvaluation;
  currency: string;
  iconUrl?: string;
  pricedAt?: string;
  interval?: { p10: number | null; p90: number | null };
  priceRecommendationEligible?: boolean;
  estimateTrust?: string;
  estimateWarning?: string;
  fallbackReason?: string;
}

export type StashTabType =
  | 'normal' | 'quad' | 'currency' | 'map' | 'fragment'
  | 'essence' | 'delirium' | 'blight' | 'ultimatum'
  | 'divination' | 'unique' | 'delve' | 'metamorph'
  | 'flask' | 'gem';

export interface StashTab {
  id: string;
  name: string;
  type: StashTabType;
  returnedIndex?: number;
  items: PoeItem[];
  quadLayout?: boolean;
  currencyLayout?: SpecialLayout;
  fragmentLayout?: SpecialLayout;
  essenceLayout?: SpecialLayout;
  deliriumLayout?: SpecialLayout;
  blightLayout?: SpecialLayout;
  ultimatumLayout?: SpecialLayout;
  mapLayout?: SpecialLayout;
  divinationLayout?: SpecialLayout;
  uniqueLayout?: SpecialLayout;
  delveLayout?: SpecialLayout;
  metamorphLayout?: SpecialLayout;
}

export interface StashStatus {
  status: 'connected_populated' | 'connected_empty' | 'disconnected' | 'session_expired' | 'feature_unavailable';
  connected: boolean;
  tabCount: number;
  itemCount: number;
  session: { accountName: string; expiresAt: string } | null;
  publishedScanId?: string | null;
  publishedAt?: string | null;
  scanStatus?: StashScanStatus | null;
}

export interface StashScanStatus {
  status: 'idle' | 'running' | 'publishing' | 'published' | 'failed';
  activeScanId: string | null;
  publishedScanId: string | null;
  startedAt: string | null;
  updatedAt: string | null;
  publishedAt: string | null;
  progress: {
    tabsTotal: number;
    tabsProcessed: number;
    itemsTotal: number;
    itemsProcessed: number;
  };
  error: string | null;
}

export interface StashScanStartResponse {
  scanId: string | null;
  status: 'running';
  startedAt: string | null;
  accountName: string;
  league: string;
  realm: string;
  deduplicated?: boolean;
}

export interface StashTabMeta {
  id: string;
  tabIndex: number;
  name: string;
  type: string;
  colour?: string;
}

export interface StashTabsResponse {
  scanId: string | null;
  publishedAt: string | null;
  isStale: boolean;
  scanStatus: StashScanStatus | null;
  stashTabs: StashTab[];
  tabsMeta: StashTabMeta[];
  numTabs: number;
}

export interface StashItemHistoryEntry {
  scanId: string;
  pricedAt: string;
  predictedValue: number;
  listedPrice: number | null;
  currency: string;
  confidence: number;
  interval: { p10: number | null; p90: number | null };
  priceRecommendationEligible: boolean;
  estimateTrust: string;
  estimateWarning: string;
  fallbackReason: string;
}

export interface StashItemHistoryResponse {
  fingerprint: string;
  item: {
    name: string;
    itemClass?: string;
    rarity: string;
    iconUrl?: string;
  };
  history: StashItemHistoryEntry[];
}

export interface ScannerSummary {
  status: 'ok' | 'empty' | 'stale';
  lastRunAt: string | null;
  recommendationCount: number;
  freshnessMinutes?: number | null;
}

export interface ScannerRecommendation {
  scannerRunId: string;
  strategyId: string;
  league: string;
  itemOrMarketKey: string;
  whyItFired: string;
  buyPlan: string;
  maxBuy: number | null;
  transformPlan: string;
  exitPlan: string;
  executionVenue: string;
  expectedProfitChaos: number | null;
  expectedProfitPerMinuteChaos: number | null;
  expectedRoi: number | null;
  expectedHoldTime: string;
  expectedHoldMinutes: number | null;
  confidence: number | null;
  recordedAt: string | null;
}

export interface ScannerRecommendationsMeta {
  nextCursor: string | null;
  hasMore: boolean;
  source?: string;
  primaryLeague?: string;
  generatedAt?: string;
}

export interface ScannerRecommendationsResponse {
  recommendations: ScannerRecommendation[];
  meta: ScannerRecommendationsMeta;
}

export interface ScannerRecommendationsRequest {
  sort?: string;
  limit?: number;
  cursor?: string;
  league?: string;
  strategyId?: string;
  minConfidence?: number;
}

// ========== Messages ==========
export type MessageSeverity = 'info' | 'warning' | 'critical';
export interface AppMessage {
  id: string;
  timestamp: string;
  severity: MessageSeverity;
  sourceModule: string;
  message: string;
  suggestedAction: string;
}

// ========== Dashboard ==========
export interface DashboardResponse {
  services: Service[];
  summary: {
    running: number;
    total: number;
    errors: number;
    criticalAlerts: number;
    topOpportunity: string;
  };
  topOpportunities: ScannerRecommendation[];
  deployment?: Record<string, unknown>;
}

// ========== ML Automation Observability ==========
export interface MlAutomationObservability {
  datasetRows: number;
  latestTrainingAsOf: string | null;
  promotedModels: number;
  latestPromotionAt: string | null;
  evalRuns: number;
  evalSampleRows: number;
  latestEvalAt: string | null;
  evaluationAvailable: boolean;
}

// ========== ML Automation ==========
export interface MlAutomationStatus {
  league: string;
  status?: string | null;
  activeModelVersion: string | null;
  latestRun?: {
    runId: string | null;
    status: string | null;
    stopReason?: string | null;
    updatedAt?: string | null;
  } | null;
  promotionVerdict?: string | null;
  routeHotspots: unknown[];
  observability: MlAutomationObservability;
  trainerRuntime?: {
    stage: string | null;
    status: string | null;
    updatedAt: string | null;
    details: Record<string, unknown>;
  } | null;
}

export interface MlAutomationHistoryRun {
  runId: string | null;
  status: string | null;
  stopReason: string | null;
  activeModelVersion: string | null;
  tuningConfigId?: string | null;
  evalRunId?: string | null;
  updatedAt: string | null;
  rowsProcessed?: number | null;
  avgMdape?: number | null;
  avgIntervalCoverage?: number | null;
  verdict?: string | null;
}

export interface MlAutomationHistoryTrendPoint {
  runId: string | null;
  updatedAt: string | null;
  avgMdape: number | null;
  avgIntervalCoverage: number | null;
  verdict: string | null;
  activeModelVersion: string | null;
}

export interface MlAutomationHistory {
  league: string;
  mode: string | null;
  history: MlAutomationHistoryRun[];
  summary: {
    activeModelVersion: string | null;
    lastRunAt: string | null;
    lastPromotedAt: string | null;
    runsLast7d: number;
    runsLast30d: number;
    medianHoursBetweenRuns: number | null;
    latestAvgMdape: number | null;
    latestAvgIntervalCoverage: number | null;
    bestAvgMdape: number | null;
    mdapeDeltaVsPrevious: number | null;
    trendDirection: string;
  };
  qualityTrend: MlAutomationHistoryTrendPoint[];
  trainingCadence: Array<{
    date: string;
    runs: number;
  }>;
  routeMetrics: Array<{
    route: string | null;
    sampleCount: number | null;
    avgMdape: number | null;
    avgIntervalCoverage: number | null;
    avgAbstainRate: number | null;
    recordedAt: string | null;
  }>;
  datasetCoverage: {
    totalRows: number;
    supportedRows: number;
    coverageRatio: number;
    baseTypeCount: number | null;
    routes: Array<{
      route: string | null;
      rows: number;
      share: number;
    }>;
  };
  promotions: Array<{
    modelVersion: string | null;
    promotedAt: string | null;
  }>;
  observability: MlAutomationObservability;
  charts?: {
    mdapeHistory: Record<string, unknown>[];
    coverageHistory: Record<string, unknown>[];
  };
}

// ========== Health ==========
export interface HealthResponse {
  status: 'ok' | 'degraded';
  service: string;
  version: string;
  ml: Record<string, unknown>;
}

// ========== ML Contract ==========
export interface MlContractResponse {
  [key: string]: unknown;
}

// ========== ML League Status ==========
export interface MlLeagueStatusResponse {
  [key: string]: unknown;
}

// ========== Stash Scan Valuations ==========
export interface StashScanValuationDaySeries {
  date: string;
  chaosMedian: number | null;
}

export interface StashScanValuationAffixFallback {
  affix: string;
  chaosMedian: number;
}

export interface StashScanValuationsResponse {
  structuredMode: boolean;
  scanId: string;
  stashId: string;
  itemId?: string | null;
  scanDatetime?: string | null;
  chaosMedian?: number | null;
  daySeries?: StashScanValuationDaySeries[];
  affixFallbackMedians?: StashScanValuationAffixFallback[];
  items: Record<string, unknown>[];
}

// ========== API Service Interface ==========
export interface ApiService {
  getHealthz(): Promise<HealthResponse>;
  getDashboard(): Promise<DashboardResponse>;
  getScannerSummary(): Promise<ScannerSummary>;
  getScannerRecommendations(
    request?: ScannerRecommendationsRequest
  ): Promise<ScannerRecommendationsResponse>;
  ackAlert(alertId: string): Promise<void>;
  getStashStatus(): Promise<StashStatus>;
  getMlAutomationStatus(): Promise<MlAutomationStatus>;
  getMlAutomationHistory(): Promise<MlAutomationHistory>;
  getMlContract(): Promise<MlContractResponse>;
  getMlLeagueStatus(): Promise<MlLeagueStatusResponse>;

  getServices(): Promise<Service[]>;
  startService(id: string): Promise<void>;
  stopService(id: string): Promise<void>;
  restartService(id: string): Promise<void>;

  priceCheck(req: PriceCheckRequest): Promise<PriceCheckResponse>;
  mlPredictOne(req: MlPredictOneRequest): Promise<MlPredictOneResponse>;

  startStashScan(): Promise<StashScanStartResponse>;
  getStashScanStatus(): Promise<StashScanStatus>;
  getStashItemHistory(fingerprint: string): Promise<StashItemHistoryResponse>;

  getStashScanResult(signal?: AbortSignal): Promise<StashTabsResponse>;
  startStashValuations(): Promise<void>;
  getStashValuationsResult(signal?: AbortSignal): Promise<StashScanValuationsResponse>;
  getStashValuationsStatus(): Promise<StashScanStatus>;

  getMessages(): Promise<AppMessage[]>;
}
