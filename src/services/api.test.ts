import { afterEach, describe, expect, test, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  getSessionMock: vi.fn(),
}));

vi.mock('@/lib/supabaseClient', () => ({
  supabase: {
    auth: {
      getSession: mocks.getSessionMock,
    },
  },
  SUPABASE_PROJECT_ID: 'project-id',
}));

vi.mock('@/services/auth', () => ({}));

import {
  api,
  getAnalyticsPricingOutliers,
  getAnalyticsSearchHistory,
} from './api';
import type { ScannerRecommendation } from '@/types/api';

const sampleRecommendation: ScannerRecommendation = {
  scannerRunId: 'scan-1',
  strategyId: 'strategy-1',
  league: 'Mirage',
  itemOrMarketKey: 'Unique Item',
  whyItFired: 'opportunity',
  buyPlan: 'buy',
  maxBuy: 1,
  transformPlan: 'keep',
  exitPlan: 'sell',
  executionVenue: 'exchange',
  expectedProfitChaos: 50,
  expectedProfitPerMinuteChaos: 5,
  expectedRoi: 0.12,
  expectedHoldTime: '~5m',
  expectedHoldMinutes: 5,
  confidence: 0.85,
  recordedAt: '2026-03-15T00:00:00Z',
};

const createResponse = (payload: unknown) =>
  Promise.resolve({
    ok: true,
    status: 200,
    headers: { get: () => null },
    json: async () => payload,
  } as unknown as Response);

describe('api.getScannerRecommendations', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllEnvs();
  });

  test('serializes filters into backend query params and returns metadata', async () => {
    vi.stubEnv('VITE_SUPABASE_PROJECT_ID', 'project-id');
    mocks.getSessionMock.mockResolvedValue({ data: { session: { access_token: 'token-123' } } });
    const responsePayload = {
      recommendations: [sampleRecommendation],
      meta: {
        nextCursor: 'cursor-123',
        hasMore: true,
      },
    };
    const fetchMock = vi.fn(() => createResponse(responsePayload));
    vi.stubGlobal('fetch', fetchMock);

    const result = await api.getScannerRecommendations({
      sort: 'liquidity_score',
      limit: 5,
      cursor: 'cursor-123',
      league: 'Mirage',
      strategyId: 'strategy-1',
      minConfidence: 0.75,
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const calledUrl = (fetchMock.mock.calls[0] as unknown[])[0];
    const init = (fetchMock.mock.calls[0] as unknown[])[1] as RequestInit;
    const parsedUrl = new URL(String(calledUrl));
    expect(parsedUrl.pathname).toBe('/functions/v1/api-proxy');
    expect((init.headers as Record<string, string>)['x-proxy-path']).toContain('/api/v1/ops/scanner/recommendations');
    const proxiedUrl = new URL(`https://example.com${(init.headers as Record<string, string>)['x-proxy-path']}`);
    expect(proxiedUrl.searchParams.get('sort')).toBe('liquidity_score');
    expect(proxiedUrl.searchParams.get('limit')).toBe('5');
    expect(proxiedUrl.searchParams.get('cursor')).toBe('cursor-123');
    expect(proxiedUrl.searchParams.get('league')).toBe('Mirage');
    expect(proxiedUrl.searchParams.get('strategy_id')).toBe('strategy-1');
    expect(proxiedUrl.searchParams.get('min_confidence')).toBe('0.75');
    expect(result).toEqual(responsePayload);
  });

  test('propagates invalid cursor metadata errors instead of swallowing them', async () => {
    vi.stubEnv('VITE_SUPABASE_PROJECT_ID', 'project-id');
    mocks.getSessionMock.mockResolvedValue({ data: { session: { access_token: 'token-123' } } });
    const fetchMock = vi.fn(() =>
      Promise.resolve({
        ok: false,
        status: 400,
        headers: { get: () => null },
        json: async () => ({
          error: {
            code: 'invalid_input',
            message: 'cursor invalid',
            details: { reason: 'cursor malformed' },
          },
        }),
      } as unknown as Response)
    );
    vi.stubGlobal('fetch', fetchMock);

    await expect(api.getScannerRecommendations()).rejects.toThrow(/invalid_input/);
  });
});

describe('analytics api helpers', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllEnvs();
  });

  test('normalizes nested search-history query payloads', async () => {
    vi.stubEnv('VITE_SUPABASE_PROJECT_ID', 'project-id');
    mocks.getSessionMock.mockResolvedValue({ data: { session: { access_token: 'token-123' } } });
    const fetchMock = vi.fn(() => createResponse({
      query: { text: 'Mageblood', league: 'Mirage', sort: 'item_name', order: 'asc' },
      filters: {
        leagueOptions: ['Mirage'],
        price: { min: 1, max: 100 },
        datetime: { min: null, max: null },
      },
      histograms: { price: [], datetime: [] },
      rows: [],
    }));
    vi.stubGlobal('fetch', fetchMock);

    const result = await getAnalyticsSearchHistory({ query: 'Mageblood' });

    expect(result.query).toEqual({ text: 'Mageblood', league: 'Mirage', sort: 'item_name', order: 'asc' });
  });

  test('serializes analytics pricing outliers max_buy_in and normalizes nested query payload', async () => {
    vi.stubEnv('VITE_SUPABASE_PROJECT_ID', 'project-id');
    mocks.getSessionMock.mockResolvedValue({ data: { session: { access_token: 'token-123' } } });
    const fetchMock = vi.fn(() => createResponse({
      query: {
        query: 'Mageblood',
        league: 'Mirage',
        sort: 'expected_profit',
        order: 'desc',
        minTotal: 20,
        maxBuyIn: 100,
        limit: 100,
      },
      rows: [{
        itemName: 'Mageblood',
        affixAnalyzed: '',
        p10: 90,
        median: 150,
        p90: 220,
        itemsPerWeek: 1.5,
        itemsTotal: 40,
        analysisLevel: 'item',
        entryPrice: 90,
        expectedProfit: 60,
        roi: 0.6667,
        underpricedRate: 0.4,
      }],
      weekly: [],
    }));
    vi.stubGlobal('fetch', fetchMock);

    const result = await getAnalyticsPricingOutliers({ query: 'Mageblood' });

    expect(result.rows[0].expectedProfit).toBe(60);
    expect(result.rows[0].expectedProfit).toBe(60);
  });

  test('normalizes older pricing outlier payloads without derived fields', async () => {
    vi.stubEnv('VITE_SUPABASE_PROJECT_ID', 'project-id');
    mocks.getSessionMock.mockResolvedValue({ data: { session: { access_token: 'token-123' } } });
    const fetchMock = vi.fn(() => createResponse({
      query: {
        query: 'Mageblood',
        league: 'Mirage',
        sort: 'median',
        order: 'desc',
        minTotal: 20,
        maxBuyIn: 100,
        limit: 100,
      },
      rows: [{
        itemName: 'Mageblood',
        affixAnalyzed: '',
        p10: 90,
        median: 150,
        p90: 220,
        itemsPerWeek: 1.5,
        itemsTotal: 40,
        analysisLevel: 'item',
      }],
      weekly: [],
    }));
    vi.stubGlobal('fetch', fetchMock);

    const result = await getAnalyticsPricingOutliers({ query: 'Mageblood' });

    expect(result.rows[0].entryPrice).toBeNull();
    expect(result.rows[0].expectedProfit).toBeNull();
    expect(result.rows[0].roi).toBeNull();
    expect(result.rows[0].underpricedRate).toBeNull();
  });

  test('does not invent omitted nested pricing outlier query fields', async () => {
    vi.stubEnv('VITE_SUPABASE_PROJECT_ID', 'project-id');
    mocks.getSessionMock.mockResolvedValue({ data: { session: { access_token: 'token-123' } } });
    const fetchMock = vi.fn(() => createResponse({
      query: {
        league: 'Mirage',
        sort: 'expected_profit',
        order: 'desc',
        minTotal: 20,
      },
      rows: [],
      weekly: [],
    }));
    vi.stubGlobal('fetch', fetchMock);

    const result = await getAnalyticsPricingOutliers();

    expect(result.query).toEqual({
      league: 'Mirage',
      sort: 'expected_profit',
      order: 'desc',
      minTotal: 20,
    });
    expect(result.query.query).toBeUndefined();
    expect(result.query.limit).toBeUndefined();
    expect(result.query.limit).toBeUndefined();
  });

  test('falls back to top-level pricing outlier query metadata when nested fields are absent', async () => {
    vi.stubEnv('VITE_SUPABASE_PROJECT_ID', 'project-id');
    mocks.getSessionMock.mockResolvedValue({ data: { session: { access_token: 'token-123' } } });
    const fetchMock = vi.fn(() => createResponse({
      query: {
        league: 'Mirage',
        sort: 'expected_profit',
        order: 'desc',
        minTotal: 20,
      },
      maxBuyIn: 75,
      limit: 50,
      rows: [],
      weekly: [],
    }));
    vi.stubGlobal('fetch', fetchMock);

    const result = await getAnalyticsPricingOutliers();

    expect(result.query).toEqual({
      league: 'Mirage',
      sort: 'expected_profit',
      order: 'desc',
      minTotal: 20,
      limit: 50,
    });
  });
});

describe('ml predict-one and price-check hybrid contract', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllEnvs();
  });

  test('normalizes core prediction fields without non-spec extras', async () => {
    vi.stubEnv('VITE_SUPABASE_PROJECT_ID', 'project-id');
    mocks.getSessionMock.mockResolvedValue({ data: { session: { access_token: 'token-123' } } });
    const fetchMock = vi.fn(() => createResponse({
      predictedValue: 101,
      currency: 'chaos',
      confidence: 0.61,
      interval: { p10: 90, p90: 120 },
    }));
    vi.stubGlobal('fetch', fetchMock);

    const payload = await api.mlPredictOne({ itemText: 'Rarity: Rare' });

    expect(payload.predictedValue).toBe(101);
    expect(payload.confidence).toBe(0.61);
    expect(payload.interval).toEqual({ p10: 90, p90: 120 });
  });
});
