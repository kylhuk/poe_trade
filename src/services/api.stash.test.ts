import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';
import { clearApiErrors, getApiErrors } from './apiErrorLog';

const { getSessionMock } = vi.hoisted(() => ({
  getSessionMock: vi.fn(),
}));

vi.mock('@/lib/supabaseClient', () => ({
  supabase: {
    auth: {
      getSession: getSessionMock,
    },
  },
  SUPABASE_PROJECT_ID: 'project-id',
}));

async function loadApi() {
  const { api } = await import('./api');
  return api;
}

describe('stash api methods', () => {
  beforeEach(() => {
    vi.resetModules();
    vi.stubEnv('VITE_SUPABASE_PROJECT_ID', 'project-id');
    getSessionMock.mockResolvedValue({ data: { session: { access_token: 'token-123' } } });
    clearApiErrors();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllEnvs();
  });

  test('starts a stash scan and returns scan metadata', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 202,
        json: async () => ({
          scanId: 'scan-2',
          status: 'running',
          startedAt: '2026-03-21T12:01:00Z',
          accountName: 'qa-exile',
          league: 'Mirage',
          realm: 'pc',
        }),
      } as Response);
    vi.stubGlobal('fetch', fetchMock);

    const api = await loadApi();
    const result = await api.startStashScan();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(result.scanId).toBe('scan-2');
    expect(result.accountName).toBe('qa-exile');
  });

  test('fetches stash scan status and item history', async () => {
    const fetchMock = vi
      .fn()
      // 1st call: getStashScanStatus -> /api/v1/stash/scan/status
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          status: 'running',
          activeScanId: 'scan-2',
          publishedScanId: 'scan-1',
          startedAt: '2026-03-21T12:01:00Z',
          updatedAt: '2026-03-21T12:02:00Z',
          publishedAt: null,
          progress: {
            tabsTotal: 8,
            tabsProcessed: 3,
            itemsTotal: 120,
            itemsProcessed: 44,
          },
          error: null,
        }),
      } as Response)
      // 2nd call: getStashItemHistory -> /api/v1/stash/items/{fp}/history
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          fingerprint: 'sig:item-1',
          item: {
            name: 'Grim Bane',
            itemClass: 'Helmet',
            rarity: 'rare',
            iconUrl: 'https://web.poecdn.com/item.png',
          },
          history: [
            {
              scanId: 'scan-2',
              pricedAt: '2026-03-21T12:00:00Z',
              predictedValue: 45,
              listedPrice: 40,
              currency: 'chaos',
              confidence: 82,
              interval: { p10: 39, p90: 51 },
              priceRecommendationEligible: true,
              estimateTrust: 'normal',
              estimateWarning: '',
              fallbackReason: '',
            },
          ],
        }),
      } as Response);
    vi.stubGlobal('fetch', fetchMock);

    const api = await loadApi();
    const status = await api.getStashScanStatus();
    const history = await api.getStashItemHistory('sig:item-1');

    expect(status.activeScanId).toBe('scan-2');
    expect(status.progress.itemsProcessed).toBe(44);
    expect(history.item.name).toBe('Grim Bane');
    expect(history.history[0].interval.p10).toBe(39);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  test('derives tabsMeta from stashTabs when backend omits tab metadata (via scan/result)', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          scanId: 'scan-2',
          publishedAt: '2026-03-21T12:03:00Z',
          isStale: false,
          scanStatus: null,
          stashTabs: [
            { id: 'tab-1', name: 'Empty', type: 'normal', items: [] },
            { id: 'tab-2', name: 'Gear', type: 'normal', items: [] },
          ],
        }),
      } as Response);
    vi.stubGlobal('fetch', fetchMock);

    const api = await loadApi();
    const result = await api.getStashScanResult();

    expect(result.tabsMeta).toEqual([
      { id: 'tab-1', tabIndex: 0, name: 'Empty', type: 'normal' },
      { id: 'tab-2', tabIndex: 1, name: 'Gear', type: 'normal' },
    ]);
    expect(result.stashTabs[1].returnedIndex).toBe(1);
  });
});
