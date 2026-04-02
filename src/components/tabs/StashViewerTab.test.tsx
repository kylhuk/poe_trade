// @vitest-environment jsdom

import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ButtonHTMLAttributes, HTMLAttributes, InputHTMLAttributes } from 'react';
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';
import StashViewerTab from './StashViewerTab';

const {
  getStashStatusMock,
  getStashScanResultMock,
  startStashScanMock,
  getStashScanStatusMock,
  getStashItemHistoryMock,
  startStashValuationsMock,
  getStashValuationsResultMock,
  getStashValuationsStatusMock,
} = vi.hoisted(() => ({
  getStashStatusMock: vi.fn(),
  getStashScanResultMock: vi.fn(),
  startStashScanMock: vi.fn(),
  getStashScanStatusMock: vi.fn(),
  getStashItemHistoryMock: vi.fn(),
  startStashValuationsMock: vi.fn(),
  getStashValuationsResultMock: vi.fn(),
  getStashValuationsStatusMock: vi.fn(),
}));

vi.mock('../shared/RenderState', () => ({
  RenderState: ({ kind, message }: { kind: string; message?: string }) => (
    <div data-testid={`state-${kind}`}>{message ?? kind}</div>
  ),
}));

vi.mock('../ui/button', () => ({
  Button: ({ children, className, size: _size, variant: _variant, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { size?: string; variant?: string }) => (
    <button className={className} {...props}>{children}</button>
  ),
}));

vi.mock('../ui/input', () => ({
  Input: (props: InputHTMLAttributes<HTMLInputElement>) => <input {...props} />,
}));

vi.mock('../ui/label', () => ({
  Label: ({ children, ...props }: HTMLAttributes<HTMLLabelElement>) => <label {...props}>{children}</label>,
}));

vi.mock('../ui/hover-card', () => ({
  HoverCard: ({ children }: HTMLAttributes<HTMLDivElement>) => <div>{children}</div>,
  HoverCardTrigger: ({ children }: HTMLAttributes<HTMLDivElement>) => <div>{children}</div>,
  HoverCardContent: ({ children }: HTMLAttributes<HTMLDivElement>) => <div>{children}</div>,
}));

vi.mock('../ui/collapsible', () => ({
  Collapsible: ({ children }: HTMLAttributes<HTMLDivElement>) => <div>{children}</div>,
  CollapsibleTrigger: ({ children }: HTMLAttributes<HTMLDivElement>) => <div>{children}</div>,
  CollapsibleContent: ({ children }: HTMLAttributes<HTMLDivElement>) => <div>{children}</div>,
}));

vi.mock('../ui/dialog', () => ({
  Dialog: ({ children }: HTMLAttributes<HTMLDivElement>) => <div>{children}</div>,
  DialogContent: ({ children }: HTMLAttributes<HTMLDivElement>) => <div>{children}</div>,
  DialogHeader: ({ children }: HTMLAttributes<HTMLDivElement>) => <div>{children}</div>,
  DialogTitle: ({ children }: HTMLAttributes<HTMLHeadingElement>) => <h2>{children}</h2>,
  DialogDescription: ({ children }: HTMLAttributes<HTMLParagraphElement>) => <p>{children}</p>,
}));

vi.mock('../../services/api', () => ({
  api: {
    getStashStatus: getStashStatusMock,
    getStashScanResult: getStashScanResultMock,
    startStashScan: startStashScanMock,
    getStashScanStatus: getStashScanStatusMock,
    getStashItemHistory: getStashItemHistoryMock,
    startStashValuations: startStashValuationsMock,
    getStashValuationsResult: getStashValuationsResultMock,
    getStashValuationsStatus: getStashValuationsStatusMock,
  },
}));

vi.mock('../economy/PriceSparkline', () => ({
  default: () => <svg data-testid="sparkline" />,
}));

const publishedTabsPayload = {
  scanId: 'scan-1',
  publishedAt: '2026-03-21T12:00:00Z',
  isStale: false,
  scanStatus: null,
  stashTabs: [
    {
      id: 'tab-2',
      name: 'Currency',
      type: 'currency',
      returnedIndex: 0,
      items: [
        {
          id: 'item-1',
          fingerprint: 'sig:item-1',
          name: 'Grim Bane',
          x: 0,
          y: 0,
          w: 1,
          h: 1,
          itemClass: 'Helmet',
          rarity: 'rare',
          listedPrice: 40,
          estimatedPrice: 45,
          estimatedPriceConfidence: 82,
          priceDeltaChaos: 5,
          priceDeltaPercent: 12.5,
          priceEvaluation: 'mispriced',
          currency: 'chaos',
          iconUrl: 'https://web.poecdn.com/item.png',
          interval: { p10: 39, p90: 51 },
        },
      ],
    },
  ],
  tabsMeta: [
    { id: 'tab-2', tabIndex: 0, name: 'Currency', type: 'CurrencyStash' },
    { id: 'tab-9', tabIndex: 1, name: 'Dump', type: 'QuadStash' },
  ],
  numTabs: 2,
};

const emptyValuationResult = {
  structuredMode: true,
  scanId: 'scan-1',
  stashId: 'scan-1',
  items: [],
};

beforeEach(() => {
  getStashStatusMock.mockResolvedValue({
    status: 'connected_populated',
    connected: true,
    tabCount: 2,
    itemCount: 1,
    session: { accountName: 'qa-exile', expiresAt: '2099-01-01T00:00:00Z' },
    publishedScanId: 'scan-1',
    publishedAt: '2026-03-21T12:00:00Z',
    scanStatus: null,
  });
  getStashScanResultMock.mockResolvedValue(publishedTabsPayload);
  getStashValuationsResultMock.mockResolvedValue(emptyValuationResult);
  getStashValuationsStatusMock.mockResolvedValue({ status: 'published' });
  startStashScanMock.mockResolvedValue({
    scanId: 'scan-2',
    status: 'running',
    startedAt: '2026-03-21T12:01:00Z',
    accountName: 'qa-exile',
    league: 'Mirage',
    realm: 'pc',
  });
  getStashItemHistoryMock.mockResolvedValue({
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
  });
  startStashValuationsMock.mockResolvedValue(undefined);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.useRealTimers();
});

describe('StashViewerTab', () => {
  test('keeps rendering the last published stash while a new scan is running', async () => {
    getStashScanStatusMock.mockResolvedValue({
      status: 'running',
      activeScanId: 'scan-2',
      publishedScanId: 'scan-1',
      startedAt: '2026-03-21T12:01:00Z',
      updatedAt: '2026-03-21T12:02:00Z',
      publishedAt: null,
      progress: { tabsTotal: 8, tabsProcessed: 3, itemsTotal: 120, itemsProcessed: 44 },
      error: null,
    });

    render(<StashViewerTab />);

    expect(await screen.findByTestId('stash-panel-grid')).toBeInTheDocument();
    vi.useFakeTimers();

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /scan/i }));
      await Promise.resolve();
      await Promise.resolve();
    });

    await act(async () => {
      vi.advanceTimersByTime(1600);
      await Promise.resolve();
    });

    expect(screen.getByTestId('stash-panel-grid')).toBeInTheDocument();
    expect(getStashScanStatusMock).toHaveBeenCalled();
  });

  test('renders tabs in backend order and paints stash item art', async () => {
    render(<StashViewerTab />);

    await waitFor(() => {
      const tabs = screen.getAllByTestId(/stash-tab-/);
      expect(tabs[0]).toHaveTextContent('Currency');
      expect(tabs[1]).toHaveTextContent('Dump');
    });

    expect(await screen.findByAltText('Grim Bane')).toBeInTheDocument();
  });

  test('starts a scan, polls status, and refreshes once the scan publishes', async () => {
    getStashScanStatusMock
      .mockResolvedValueOnce({
        status: 'running',
        activeScanId: 'scan-2',
        publishedScanId: 'scan-1',
        startedAt: '2026-03-21T12:01:00Z',
        updatedAt: '2026-03-21T12:02:00Z',
        publishedAt: null,
        progress: { tabsTotal: 8, tabsProcessed: 4, itemsTotal: 120, itemsProcessed: 60 },
        error: null,
      })
      .mockResolvedValueOnce({
        status: 'published',
        activeScanId: null,
        publishedScanId: 'scan-2',
        startedAt: '2026-03-21T12:01:00Z',
        updatedAt: '2026-03-21T12:03:00Z',
        publishedAt: '2026-03-21T12:03:00Z',
        progress: { tabsTotal: 8, tabsProcessed: 8, itemsTotal: 120, itemsProcessed: 120 },
        error: null,
      });
    getStashScanResultMock
      .mockResolvedValueOnce(publishedTabsPayload)
      .mockResolvedValueOnce({
        ...publishedTabsPayload,
        scanId: 'scan-2',
        publishedAt: '2026-03-21T12:03:00Z',
      });

    render(<StashViewerTab />);
    expect(await screen.findByTestId('stash-panel-grid')).toBeInTheDocument();
    vi.useFakeTimers();

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /scan/i }));
      await Promise.resolve();
      await Promise.resolve();
    });

    await act(async () => {
      vi.advanceTimersByTime(1600);
      await Promise.resolve();
      vi.advanceTimersByTime(1600);
      await Promise.resolve();
    });

    // getStashScanResult called for initial load + after scan publish
    expect(getStashScanResultMock.mock.calls.length).toBeGreaterThanOrEqual(2);
    // startStashValuations called with no arguments (new API)
    expect(startStashValuationsMock).toHaveBeenCalledWith();
  });

  test('selects the requested tab instead of always using the first returned tab', async () => {
    getStashScanResultMock.mockResolvedValue({
      scanId: 'scan-1',
      publishedAt: '2026-03-21T12:00:00Z',
      isStale: false,
      scanStatus: null,
      stashTabs: [
        {
          id: 'tab-1',
          name: 'Empty',
          type: 'normal',
          items: [],
        },
        {
          id: 'tab-2',
          name: 'Gear',
          type: 'normal',
          items: [
            {
              id: 'item-1',
              fingerprint: 'sig:item-1',
              name: 'Grim Bane',
              x: 0,
              y: 0,
              w: 1,
              h: 1,
              itemClass: 'Helmet',
              rarity: 'rare',
              listedPrice: 40,
              estimatedPrice: 45,
              estimatedPriceConfidence: 82,
              priceDeltaChaos: 5,
              priceDeltaPercent: 12.5,
              priceEvaluation: 'mispriced',
              currency: 'chaos',
              iconUrl: 'https://web.poecdn.com/item.png',
              interval: { p10: 39, p90: 51 },
            },
          ],
        },
      ],
      tabsMeta: [
        { id: 'tab-1', tabIndex: 0, name: 'Empty', type: 'normal' },
        { id: 'tab-2', tabIndex: 1, name: 'Gear', type: 'normal' },
      ],
      numTabs: 2,
    });

    render(<StashViewerTab />);

    await waitFor(() => {
      const tabs = screen.getAllByTestId(/stash-tab-/);
      expect(tabs[0]).toHaveTextContent('Empty');
      expect(tabs[1]).toHaveTextContent('Gear');
    });

    await act(async () => {
      fireEvent.click(screen.getByTestId('stash-tab-tab-2'));
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(await screen.findByAltText('Grim Bane')).toBeInTheDocument();
  });

  test('shows stash data even when scan status reports 0 progress', async () => {
    getStashStatusMock.mockResolvedValue({
      status: 'connected_populated',
      connected: true,
      tabCount: 19,
      itemCount: 796,
      session: { accountName: 'qa-exile', expiresAt: '2099-01-01T00:00:00Z' },
      publishedScanId: 'scan-1',
      publishedAt: '2026-03-21T12:00:00Z',
      scanStatus: {
        status: 'running',
        activeScanId: 'scan-3',
        publishedScanId: 'scan-1',
        startedAt: '2026-03-21T12:01:00Z',
        updatedAt: '2026-03-21T12:02:00Z',
        publishedAt: null,
        progress: { tabsTotal: 19, tabsProcessed: 0, itemsTotal: 0, itemsProcessed: 0 },
        error: null,
      },
    });

    render(<StashViewerTab />);

    expect(await screen.findByTestId('stash-panel-grid')).toBeInTheDocument();
    expect(screen.getByText(/showing last available stash data/i)).toBeInTheDocument();
  });

  test('shows mismatch warning when backend returns wrong tab index', async () => {
    const mismatchPayload = {
      ...publishedTabsPayload,
      stashTabs: [{
        ...publishedTabsPayload.stashTabs[0],
        returnedIndex: 0,
      }],
    };
    getStashScanResultMock
      .mockResolvedValueOnce(publishedTabsPayload)
      .mockResolvedValueOnce(mismatchPayload);

    render(<StashViewerTab />);
    await screen.findByTestId('stash-panel-grid');

    await act(async () => {
      fireEvent.click(screen.getByTestId('stash-tab-tab-9'));
      await Promise.resolve();
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(screen.getByTestId('tab-mismatch-warning')).toBeInTheDocument();
    });
  });

  test('renders Valuate button that is enabled when a published scan exists', async () => {
    render(<StashViewerTab />);
    await screen.findByTestId('stash-panel-grid');

    const valuateBtn = screen.getByRole('button', { name: /valuate/i });
    expect(valuateBtn).toBeInTheDocument();
    expect(valuateBtn).not.toBeDisabled();
  });

  test('Valuate button calls startStashValuations with no arguments', async () => {
    render(<StashViewerTab />);
    await screen.findByTestId('stash-panel-grid');

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /valuate/i }));
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(startStashValuationsMock).toHaveBeenCalledWith();
  });
});
