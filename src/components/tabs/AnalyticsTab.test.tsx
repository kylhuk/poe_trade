// @vitest-environment jsdom

import '@testing-library/jest-dom/vitest';
import { act, fireEvent, render, screen, within } from '@testing-library/react';
import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';

import AnalyticsTab from './AnalyticsTab';
import type { PricingOutliersResponse, SearchHistoryResponse, SearchSuggestionsResponse } from '@/types/api';

const {
  getAnalyticsSearchSuggestionsMock,
  getAnalyticsSearchHistoryMock,
  getAnalyticsPricingOutliersMock,
  getMlAutomationStatusMock,
  getMlAutomationHistoryMock,
} = vi.hoisted(() => ({
  getAnalyticsSearchSuggestionsMock: vi.fn(),
  getAnalyticsSearchHistoryMock: vi.fn(),
  getAnalyticsPricingOutliersMock: vi.fn(),
  getMlAutomationStatusMock: vi.fn(),
  getMlAutomationHistoryMock: vi.fn(),
}));

vi.mock('@/components/ui/card', () => ({
  Card: ({ children, ...props }: HTMLAttributes<HTMLDivElement>) => <div {...props}>{children}</div>,
  CardHeader: ({ children, ...props }: HTMLAttributes<HTMLDivElement>) => <div {...props}>{children}</div>,
  CardContent: ({ children, ...props }: HTMLAttributes<HTMLDivElement>) => <div {...props}>{children}</div>,
  CardTitle: ({ children, ...props }: HTMLAttributes<HTMLHeadingElement>) => <h3 {...props}>{children}</h3>,
}));

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...props }: ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button>,
}));

vi.mock('@/components/ui/table', () => ({
  Table: ({ children, ...props }: HTMLAttributes<HTMLTableElement>) => <table {...props}>{children}</table>,
  TableHeader: ({ children, ...props }: HTMLAttributes<HTMLTableSectionElement>) => <thead {...props}>{children}</thead>,
  TableBody: ({ children, ...props }: HTMLAttributes<HTMLTableSectionElement>) => <tbody {...props}>{children}</tbody>,
  TableRow: ({ children, ...props }: HTMLAttributes<HTMLTableRowElement>) => <tr {...props}>{children}</tr>,
  TableHead: ({ children, ...props }: HTMLAttributes<HTMLTableCellElement>) => <th {...props}>{children}</th>,
  TableCell: ({ children, ...props }: HTMLAttributes<HTMLTableCellElement>) => <td {...props}>{children}</td>,
}));

vi.mock('@/components/ui/slider', () => ({
  Slider: () => <div data-testid="slider" />,
}));

vi.mock('@/components/ui/tabs', async () => {
  const React = await import('react');
  const TabsContext = React.createContext<{ value: string; onValueChange?: (value: string) => void }>({ value: '' });
  return {
    Tabs: ({ children, value, onValueChange }: { children: ReactNode; value: string; onValueChange?: (value: string) => void }) => (
      <TabsContext.Provider value={{ value, onValueChange }}>{children}</TabsContext.Provider>
    ),
    TabsList: ({ children, ...props }: HTMLAttributes<HTMLDivElement>) => <div {...props}>{children}</div>,
    TabsTrigger: ({ children, value, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { value: string }) => {
      const context = React.useContext(TabsContext);
      return (
        <button type="button" aria-pressed={context.value === value} onClick={() => context.onValueChange?.(value)} {...props}>
          {children}
        </button>
      );
    },
    TabsContent: ({ children, value, ...props }: HTMLAttributes<HTMLDivElement> & { value: string }) => {
      const context = React.useContext(TabsContext);
      if (context.value !== value) {
        return null;
      }
      return <div {...props}>{children}</div>;
    },
  };
});

vi.mock('@/components/ui/badge', () => ({
  Badge: ({ children, ...props }: HTMLAttributes<HTMLDivElement>) => <div {...props}>{children}</div>,
}));

vi.mock('@/components/shared/StatusIndicators', () => ({
  Freshness: ({ iso }: { iso: string | null }) => <span>{iso ?? 'N/A'}</span>,
}));

vi.mock('@/components/shared/RenderState', () => ({
  RenderState: ({ kind, message }: { kind: string; message?: string }) => <div data-testid={`state-${kind}`}>{message ?? kind}</div>,
}));

vi.mock('@/components/ui/switch', () => ({
  Switch: () => <button type="button">switch</button>,
}));

vi.mock('@/components/ui/label', () => ({
  Label: ({ children, ...props }: HTMLAttributes<HTMLSpanElement>) => <span {...props}>{children}</span>,
}));

vi.mock('@/components/ui/progress', () => ({
  Progress: () => <div data-testid="progress" />,
}));

vi.mock('lucide-react', () => ({
  CheckCircle2: () => <span>check</span>,
  XCircle: () => <span>x</span>,
}));

vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  BarChart: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  Bar: () => null,
  CartesianGrid: () => null,
  LineChart: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  Line: () => null,
  Tooltip: () => null,
  XAxis: () => null,
  YAxis: () => null,
}));

vi.mock('@/services/api', () => ({
  getAnalyticsIngestion: vi.fn(),
  getAnalyticsScanner: vi.fn(),
  getAnalyticsPricingOutliers: getAnalyticsPricingOutliersMock,
  getAnalyticsSearchHistory: getAnalyticsSearchHistoryMock,
  getAnalyticsSearchSuggestions: getAnalyticsSearchSuggestionsMock,
  api: {
    getMlAutomationStatus: getMlAutomationStatusMock,
    getMlAutomationHistory: getMlAutomationHistoryMock,
  },
}));

function createMlAutomationStatus(overrides: Record<string, unknown> = {}) {
  return {
    league: 'Mirage',
    status: 'failed_gates',
    activeModelVersion: 'mirage-v3.11',
    latestRun: {
      runId: 'run-2',
      status: 'promoted',
      stopReason: 'complete',
      updatedAt: '2026-03-20T12:00:00Z',
    },
    promotionVerdict: 'hold',
    routeHotspots: [],
    observability: {
      datasetRows: 2700,
      latestTrainingAsOf: '2026-03-20T11:57:36Z',
      promotedModels: 2,
      latestPromotionAt: '2026-03-20T12:03:00Z',
      evalRuns: 4,
      evalSampleRows: 640,
      latestEvalAt: '2026-03-20T12:02:10Z',
      evaluationAvailable: true,
    },
    trainerRuntime: {
      stage: 'evaluate_models',
      status: 'running',
      updatedAt: '2026-03-20T12:04:00Z',
      details: { rows: 640 },
    },
    ...overrides,
  };
}

function createMlAutomationHistory(overrides: Record<string, unknown> = {}) {
  return {
    league: 'Mirage',
    mode: 'hybrid',
    history: [
      {
        runId: 'run-1',
        status: 'completed',
        stopReason: 'complete',
        activeModelVersion: 'mirage-v3.10',
        updatedAt: '2026-03-19T10:00:00Z',
        rowsProcessed: 1000,
        avgMdape: 0.14,
        avgIntervalCoverage: 0.62,
        verdict: 'hold',
      },
      {
        runId: 'run-2',
        status: 'promoted',
        stopReason: 'promotion_gate_passed',
        activeModelVersion: 'mirage-v3.11',
        updatedAt: '2026-03-20T10:00:00Z',
        rowsProcessed: 1200,
        avgMdape: 0.11,
        avgIntervalCoverage: 0.67,
        verdict: 'promote',
      },
    ],
    summary: {
      activeModelVersion: 'mirage-v3.11',
      lastRunAt: '2026-03-20T10:00:00Z',
      lastPromotedAt: '2026-03-20T10:15:00Z',
      runsLast7d: 2,
      runsLast30d: 2,
      medianHoursBetweenRuns: 12,
      latestAvgMdape: 0.11,
      latestAvgIntervalCoverage: 0.67,
      bestAvgMdape: 0.11,
      mdapeDeltaVsPrevious: 0.03,
      trendDirection: 'improving',
    },
    qualityTrend: [
      {
        runId: 'run-1',
        updatedAt: '2026-03-19T10:00:00Z',
        avgMdape: 0.14,
        avgIntervalCoverage: 0.62,
        verdict: 'hold',
        activeModelVersion: 'mirage-v3.10',
      },
      {
        runId: 'run-2',
        updatedAt: '2026-03-20T10:00:00Z',
        avgMdape: 0.11,
        avgIntervalCoverage: 0.67,
        verdict: 'promote',
        activeModelVersion: 'mirage-v3.11',
      },
    ],
    trainingCadence: [
      { date: '2026-03-19', runs: 1 },
      { date: '2026-03-20', runs: 1 },
    ],
    routeMetrics: [
      {
        route: 'structured_boosted',
        sampleCount: 400,
        avgMdape: 0.09,
        avgIntervalCoverage: 0.7,
        avgAbstainRate: 0.05,
        recordedAt: '2026-03-20T10:00:00Z',
      },
    ],
    datasetCoverage: {
      totalRows: 2700,
      supportedRows: 2500,
      coverageRatio: 0.925,
      baseTypeCount: 220,
      routes: [
        {
          route: 'structured_boosted',
          rows: 1500,
          share: 0.556,
        },
      ],
    },
    promotions: [
      { modelVersion: 'mirage-v3.11', promotedAt: '2026-03-20T10:15:00Z' },
    ],
    observability: {
      datasetRows: 2700,
      latestTrainingAsOf: '2026-03-20T11:57:36Z',
      promotedModels: 2,
      latestPromotionAt: '2026-03-20T12:03:00Z',
      evalRuns: 4,
      evalSampleRows: 640,
      latestEvalAt: '2026-03-20T12:02:10Z',
      evaluationAvailable: true,
    },
    ...overrides,
  };
}

function createSearchHistoryResponse(overrides: Partial<SearchHistoryResponse> = {}): SearchHistoryResponse {
  return {
    query: { text: 'Mageblood', league: 'Mirage', sort: 'item_name', order: 'asc' },
    filters: {
      leagueOptions: ['Mirage'],
      price: { min: 1, max: 100 },
      datetime: { min: null, max: null },
    },
    histograms: { price: [], datetime: [] },
    rows: [
      {
        itemName: 'Mageblood',
        league: 'Mirage',
        listedPrice: 95,
        currency: 'chaos',
        addedOn: '2026-03-15T12:00:00Z',
      },
    ],
    ...overrides,
  };
}

function createSuggestionsResponse(overrides: Partial<SearchSuggestionsResponse> = {}): SearchSuggestionsResponse {
  return {
    query: 'Mageblood',
    suggestions: [],
    ...overrides,
  };
}

function createPricingOutliersResponse(
  overrides: Partial<PricingOutliersResponse> = {}
): PricingOutliersResponse {
  return {
    query: {
      query: '',
      league: 'Mirage',
      sort: 'expected_profit',
      order: 'desc',
      minTotal: 25,
      limit: 100,
    },
    rows: [
      {
        itemName: 'Mageblood',
        affixAnalyzed: null,
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
      },
    ],
    weekly: [
      {
        weekStart: '2026-03-10T00:00:00Z',
        tooCheapCount: 2,
      },
    ],
    ...overrides,
  };
}

const DEFAULT_OUTLIERS_REQUEST = {
  sort: 'expected_profit',
  order: 'desc',
};

const OUTLIER_SORT_OPTION_VALUES = [
  'expected_profit',
  'roi',
  'underpriced_rate',
  'items_total',
  'item_name',
];

const OPPORTUNITY_HEADER_ORDER = [
  'Buy-In',
  'Fair Value',
  'Expected Profit',
  'ROI',
  'Underpriced Rate',
  'Sample Size',
  'Item Name',
  'Affix Analyzed',
];

function defer<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((nextResolve, nextReject) => {
    resolve = nextResolve;
    reject = nextReject;
  });
  return { promise, resolve, reject };
}

async function flushMicrotasks() {
  await act(async () => {
    await Promise.resolve();
  });
}

async function renderOutliersPanel() {
  render(<AnalyticsTab subtab="outliers" />);
  await act(async () => {
    vi.advanceTimersByTime(260);
  });
  await flushMicrotasks();
}

async function changeOutliersOrder(value: 'asc' | 'desc') {
  fireEvent.change(screen.getByRole('combobox', { name: /order/i }), { target: { value } });
  await act(async () => {
    vi.advanceTimersByTime(260);
  });
  await flushMicrotasks();
}

async function typeSearchQuery(value: string) {
  fireEvent.change(screen.getByTestId('search-history-input'), { target: { value } });
  await act(async () => {
    vi.advanceTimersByTime(320);
  });
  await flushMicrotasks();
}

beforeEach(() => {
  vi.useFakeTimers();
  getAnalyticsSearchSuggestionsMock.mockResolvedValue(createSuggestionsResponse());
  getAnalyticsSearchHistoryMock.mockResolvedValue(createSearchHistoryResponse());
  getAnalyticsPricingOutliersMock.mockResolvedValue(createPricingOutliersResponse());
  getMlAutomationStatusMock.mockResolvedValue(createMlAutomationStatus());
  getMlAutomationStatusMock.mockResolvedValue(createMlAutomationStatus());
  getMlAutomationHistoryMock.mockResolvedValue(createMlAutomationHistory());
});

afterEach(() => {
  vi.runOnlyPendingTimers();
  vi.useRealTimers();
  vi.clearAllMocks();
});

describe('AnalyticsTab search history panel', () => {
  test('requests search history with item-name ascending defaults and renders exact-match-first helper copy', async () => {
    render(<AnalyticsTab subtab="search" />);

    await typeSearchQuery('Mageblood');

    expect(getAnalyticsSearchHistoryMock).toHaveBeenCalledWith(expect.objectContaining({
      query: 'Mageblood',
      sort: 'item_name',
      order: 'asc',
    }));

    expect(screen.getByText(/exact item matches first/i)).toBeInTheDocument();
  });

  test('renders relevance-first suggestions from the backend payload', async () => {
    getAnalyticsSearchSuggestionsMock.mockResolvedValueOnce(createSuggestionsResponse({
      suggestions: [
        { itemName: 'Mageblood', itemKind: 'unique_name', matchCount: 5 },
        { itemName: 'Mageblood Replica', itemKind: 'unique_name', matchCount: 20 },
        { itemName: 'The Mageblood Map', itemKind: 'base_type', matchCount: 30 },
      ],
    }));

    render(<AnalyticsTab subtab="search" />);

    await typeSearchQuery('Mageblood');

    const suggestionList = screen.getByTestId('search-history-suggestions');
    const suggestionButtons = within(suggestionList).getAllByTestId('search-history-suggestion');

    expect(suggestionButtons.map(button => button.textContent)).toEqual([
      'Mageblood',
      'Mageblood Replica',
      'The Mageblood Map',
    ]);
    expect(screen.getByText(/relevance-first suggestions/i)).toBeInTheDocument();
  });

  test('clears stale results and shows the degraded state when search history fails', async () => {
    getAnalyticsSearchHistoryMock
      .mockResolvedValueOnce(createSearchHistoryResponse())
      .mockRejectedValueOnce(new Error('search history offline'));

    render(<AnalyticsTab subtab="search" />);

    await typeSearchQuery('Mageblood');

    expect(screen.getByText('Historical Results')).toBeInTheDocument();
    expect(screen.getByText('Mageblood')).toBeInTheDocument();

    await typeSearchQuery('Mageblood Replica');

    expect(screen.getByTestId('state-degraded')).toHaveTextContent('search history offline');
    expect(screen.queryByText('Historical Results')).not.toBeInTheDocument();
    expect(screen.queryByText('Mageblood')).not.toBeInTheDocument();
  });

  test('clears the degraded state when retrying after an error', async () => {
    const retryHistory = defer<SearchHistoryResponse>();
    getAnalyticsSearchHistoryMock
      .mockRejectedValueOnce(new Error('search history offline'))
      .mockImplementationOnce(() => retryHistory.promise);

    render(<AnalyticsTab subtab="search" />);

    await typeSearchQuery('Mageblood');

    expect(screen.getByTestId('state-degraded')).toHaveTextContent('search history offline');

    await typeSearchQuery('Mageblood Replica');

    expect(screen.getByTestId('state-loading')).toHaveTextContent('Querying ClickHouse…');
    expect(screen.queryByTestId('state-degraded')).not.toBeInTheDocument();
  });

  test('clears stale results while a new valid history request is loading', async () => {
    const pendingHistory = defer<SearchHistoryResponse>();
    getAnalyticsSearchHistoryMock
      .mockResolvedValueOnce(createSearchHistoryResponse())
      .mockImplementationOnce(() => pendingHistory.promise);

    render(<AnalyticsTab subtab="search" />);

    await typeSearchQuery('Mageblood');

    expect(screen.getByText('Historical Results')).toBeInTheDocument();
    expect(screen.getByText('Mageblood')).toBeInTheDocument();

    await typeSearchQuery('Mageblood Replica');

    expect(screen.getByTestId('state-loading')).toHaveTextContent('Querying ClickHouse…');
    expect(screen.queryByText('Historical Results')).not.toBeInTheDocument();
    expect(screen.queryByText('Mageblood')).not.toBeInTheDocument();
  });

  test('clears loading when a valid search is shortened below two characters', async () => {
    const pendingHistory = defer<SearchHistoryResponse>();
    getAnalyticsSearchHistoryMock.mockImplementationOnce(() => pendingHistory.promise);

    render(<AnalyticsTab subtab="search" />);

    await typeSearchQuery('Mageblood');

    expect(screen.getByTestId('state-loading')).toHaveTextContent('Querying ClickHouse…');

    fireEvent.change(screen.getByTestId('search-history-input'), { target: { value: 'M' } });

    await flushMicrotasks();
    expect(screen.queryByTestId('state-loading')).not.toBeInTheDocument();
    expect(screen.getByTestId('state-empty')).toHaveTextContent(
      'Type at least two characters to search the historical listings index.'
    );
  });

  test('shows a clear empty state when no matching historical listings are returned', async () => {
    getAnalyticsSearchHistoryMock.mockResolvedValueOnce(createSearchHistoryResponse({ rows: [] }));

    render(<AnalyticsTab subtab="search" />);

    await typeSearchQuery('Mageblood');

    expect(screen.getByText(/no matching historical listings/i)).toBeInTheDocument();
  });
});

describe('AnalyticsTab low-investment outliers panel', () => {
  test('uses expected-profit descending defaults with a 100 chaos buy-in cap', async () => {
    await renderOutliersPanel();

    expect(getAnalyticsPricingOutliersMock).toHaveBeenCalledWith(expect.objectContaining(DEFAULT_OUTLIERS_REQUEST));
  });

  test('renders low-investment opportunity title and helper copy', async () => {
    await renderOutliersPanel();

    expect(screen.getByText('Low-Investment Flip Opportunities')).toBeInTheDocument();
    expect(screen.getByText(/focus on sub-100 chaos entries with the strongest expected resale edge/i)).toBeInTheDocument();
  });

  test('renders opportunity-first columns', async () => {
    await renderOutliersPanel();

    const headers = screen.getAllByRole('columnheader').map(header => header.textContent?.trim());

    expect(headers).toEqual(OPPORTUNITY_HEADER_ORDER);
  });

  test('renders required sort options for opportunity ranking', async () => {
    await renderOutliersPanel();

    const sortSelect = screen.getByDisplayValue(/expected profit/i);
    const options = within(sortSelect).getAllByRole('option');

    expect(options.map(option => option.getAttribute('value'))).toEqual(OUTLIER_SORT_OPTION_VALUES);
  });

  test('renders opportunity row values with the expected formatting', async () => {
    await renderOutliersPanel();

    const resultsTable = screen.getByTestId('pricing-outliers-results');
    const row = within(resultsTable).getByRole('row', {
      name: /90\.00 150\.00 60\.00 66\.7% 40\.0% 40 Mageblood All item rolls item/i,
    });

    expect(within(row).getByText('90.00')).toBeInTheDocument();
    expect(within(row).getByText('150.00')).toBeInTheDocument();
    expect(within(row).getByText('60.00')).toBeInTheDocument();
    expect(within(row).getByText('66.7%')).toBeInTheDocument();
    expect(within(row).getByText('40.0%')).toBeInTheDocument();
    expect(within(row).getByText('40')).toBeInTheDocument();
    expect(within(row).getByText('Mageblood')).toBeInTheDocument();
    expect(within(row).getByText('All item rolls')).toBeInTheDocument();
    expect(within(row).getByText('item')).toBeInTheDocument();
  });

  test('renders an order control for sort direction', async () => {
    await renderOutliersPanel();

    expect(screen.getByRole('combobox', { name: /order/i })).toHaveDisplayValue(/descending/i);
  });

  test('shows affix-only weekly guidance when weekly series is empty', async () => {
    getAnalyticsPricingOutliersMock.mockResolvedValueOnce(createPricingOutliersResponse({
      rows: [
        {
          itemName: 'Watcher\'s Eye',
          affixAnalyzed: '+15% to Damage over Time Multiplier while affected by Malevolence',
          p10: 80,
          median: 130,
          p90: 200,
          itemsPerWeek: 0.8,
          itemsTotal: 22,
          analysisLevel: 'affix',
          entryPrice: 80,
          expectedProfit: 50,
          roi: 0.625,
          underpricedRate: 0.3,
        },
      ],
      weekly: [],
    }));

    await renderOutliersPanel();

    expect(screen.getByText(/weekly trend is available for item-name matches only/i)).toBeInTheDocument();
  });

  test('shows an empty state when no cheap opportunities are returned', async () => {
    getAnalyticsPricingOutliersMock.mockResolvedValueOnce(createPricingOutliersResponse({ rows: [], weekly: [] }));

    await renderOutliersPanel();

    expect(screen.getByTestId('state-empty')).toHaveTextContent(/no cheap opportunities found under the current cap/i);
  });

  test('shows a degraded state when the request fails', async () => {
    getAnalyticsPricingOutliersMock.mockRejectedValueOnce(new Error('pricing offline'));

    await renderOutliersPanel();

    expect(screen.getByTestId('state-degraded')).toHaveTextContent('pricing offline');
  });

  test('clears the degraded state when retrying through the order control', async () => {
    const retryOutliers = defer<PricingOutliersResponse>();
    getAnalyticsPricingOutliersMock
      .mockRejectedValueOnce(new Error('pricing offline'))
      .mockImplementationOnce(() => retryOutliers.promise);

    await renderOutliersPanel();

    expect(screen.getByTestId('state-degraded')).toHaveTextContent('pricing offline');

    await changeOutliersOrder('asc');

    expect(getAnalyticsPricingOutliersMock).toHaveBeenLastCalledWith(expect.objectContaining({
      ...DEFAULT_OUTLIERS_REQUEST,
      order: 'asc',
    }));
    expect(screen.getByTestId('state-loading')).toHaveTextContent('Loading low-investment opportunities…');
    expect(screen.queryByTestId('state-degraded')).not.toBeInTheDocument();
  });

  test('clears stale results while a refetch triggered by the order control is loading', async () => {
    const pendingOutliers = defer<PricingOutliersResponse>();
    getAnalyticsPricingOutliersMock
      .mockResolvedValueOnce(createPricingOutliersResponse())
      .mockImplementationOnce(() => pendingOutliers.promise);

    await renderOutliersPanel();

    expect(screen.getByTestId('pricing-outliers-results')).toBeInTheDocument();
    expect(screen.getByText('Mageblood')).toBeInTheDocument();

    await changeOutliersOrder('asc');

    expect(getAnalyticsPricingOutliersMock).toHaveBeenNthCalledWith(2, expect.objectContaining({
      ...DEFAULT_OUTLIERS_REQUEST,
      order: 'asc',
    }));
    expect(screen.getByTestId('state-loading')).toHaveTextContent('Loading low-investment opportunities…');
    expect(screen.queryByTestId('pricing-outliers-results')).not.toBeInTheDocument();
    expect(screen.queryByText('Mageblood')).not.toBeInTheDocument();
  });

  test('shows a degraded state when derived opportunity fields are missing', async () => {
    getAnalyticsPricingOutliersMock.mockResolvedValueOnce(createPricingOutliersResponse({
      rows: [
        {
          itemName: 'Mageblood',
          affixAnalyzed: null,
          p10: 90,
          median: 150,
          p90: 220,
          itemsPerWeek: 1.5,
          itemsTotal: 40,
          analysisLevel: 'item',
          entryPrice: null,
          expectedProfit: null,
          roi: null,
          underpricedRate: null,
        },
      ],
      weekly: [],
    }));

    await renderOutliersPanel();

    expect(screen.getByTestId('state-degraded')).toHaveTextContent(/missing opportunity metrics/i);
  });
});

describe('AnalyticsTab ML panel', () => {
  test('renders live automation and training data without legacy empty placeholders', async () => {
    render(<AnalyticsTab subtab="ml" />);

    await act(async () => {
      vi.advanceTimersByTime(260);
    });
    await flushMicrotasks();

    expect(getMlAutomationStatusMock).toHaveBeenCalledTimes(1);
    expect(getMlAutomationStatusMock).toHaveBeenCalledTimes(1);
    expect(getMlAutomationHistoryMock).toHaveBeenCalledTimes(1);

    expect(screen.getByText('Runs / 7d')).toBeInTheDocument();
    expect(screen.getAllByText('2').length).toBeGreaterThan(0);
    expect(screen.getByText('Latest Promotion')).toBeInTheDocument();
    expect(screen.getByText('Latest Eval')).toBeInTheDocument();
    expect(screen.getByText('Trainer Runtime')).toBeInTheDocument();
    expect(screen.getByText('Route metrics')).toBeInTheDocument();
    expect(screen.getByText('Model promotions')).toBeInTheDocument();
    expect(screen.getByText('Run History')).toBeInTheDocument();
    expect(screen.queryByText(/No ML data available/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Unknown/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/None/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/No route hotspots/i)).not.toBeInTheDocument();
  });

  test('hides empty live-only sections when the API returns sparse data', async () => {
    getMlAutomationStatusMock.mockResolvedValueOnce(createMlAutomationStatus({
      latestRun: null,
      trainerRuntime: null,
      routeHotspots: [],
    }));
    getMlAutomationHistoryMock.mockResolvedValueOnce(createMlAutomationHistory({
      history: [],
      qualityTrend: [],
      trainingCadence: [],
      routeMetrics: [],
      promotions: [],
      datasetCoverage: {
        totalRows: 0,
        supportedRows: 0,
        coverageRatio: 0,
        baseTypeCount: null,
        routes: [],
      },
    }));

    render(<AnalyticsTab subtab="ml" />);

    await act(async () => {
      vi.advanceTimersByTime(260);
    });
    await flushMicrotasks();

    expect(screen.queryByText('Latest Run')).not.toBeInTheDocument();
    expect(screen.queryByText('Trainer Runtime')).not.toBeInTheDocument();
    expect(screen.queryByText('Route metrics')).not.toBeInTheDocument();
    expect(screen.queryByText('Model promotions')).not.toBeInTheDocument();
    expect(screen.queryByText('Run History')).not.toBeInTheDocument();
    expect(screen.queryByText(/No ML data available/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Unknown/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/None/i)).not.toBeInTheDocument();
  });
});
