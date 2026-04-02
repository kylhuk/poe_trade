// @vitest-environment jsdom

import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ButtonHTMLAttributes, HTMLAttributes } from 'react';
import { afterEach, describe, expect, test, vi } from 'vitest';
import OpportunitiesTab from './OpportunitiesTab';
import type { ScannerRecommendation, ScannerRecommendationsResponse } from '../../types/api';

const { getScannerRecommendationsMock } = vi.hoisted(() => ({
  getScannerRecommendationsMock: vi.fn(),
}));

vi.mock('../ui/card', () => ({
  Card: ({ children, ...props }: HTMLAttributes<HTMLDivElement>) => <div {...props}>{children}</div>,
  CardHeader: ({ children, ...props }: HTMLAttributes<HTMLDivElement>) => <div {...props}>{children}</div>,
  CardContent: ({ children, ...props }: HTMLAttributes<HTMLDivElement>) => <div {...props}>{children}</div>,
  CardTitle: ({ children, ...props }: HTMLAttributes<HTMLHeadingElement>) => <h3 {...props}>{children}</h3>,
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

vi.mock('../../services/api', () => ({
  api: {
    getScannerRecommendations: getScannerRecommendationsMock,
  },
}));

vi.mock('../../hooks/useMouseGlow', () => ({
  useMouseGlow: () => vi.fn(),
}));

function createRecommendation(overrides: Partial<ScannerRecommendation> = {}): ScannerRecommendation {
  return {
    scannerRunId: 'scan-1',
    strategyId: 'essence_flip',
    league: 'Mirage',
    itemOrMarketKey: 'Deafening Essence of Greed',
    whyItFired: 'Spread widened after the latest scanner pass.',
    buyPlan: 'Buy under 40c',
    maxBuy: 40,
    transformPlan: 'Bulk and relist',
    exitPlan: 'Sell at 60c',
    executionVenue: 'trade',
    expectedProfitChaos: 20,
    expectedProfitPerMinuteChaos: 4,
    expectedRoi: 0.5,
    expectedHoldTime: '~5m',
    expectedHoldMinutes: 5,
    confidence: 0.92,
    recordedAt: '2026-03-15T00:00:00Z',
    ...overrides,
  };
}

function createResponse(
  recommendations: ScannerRecommendation[],
  meta: ScannerRecommendationsResponse['meta'] = { hasMore: false, nextCursor: null }
): ScannerRecommendationsResponse {
  return { recommendations, meta };
}

function defer<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((nextResolve, nextReject) => {
    resolve = nextResolve;
    reject = nextReject;
  });
  return { promise, resolve, reject };
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('OpportunitiesTab', () => {
  test('defaults to profit sorting and shows both ranking metrics in each card', async () => {
    getScannerRecommendationsMock.mockResolvedValueOnce(
      createResponse([
        createRecommendation({
          expectedProfitChaos: 64,
          expectedProfitPerMinuteChaos: 8,
        }),
      ])
    );

    render(<OpportunitiesTab />);

    await waitFor(() => {
      expect(getScannerRecommendationsMock).toHaveBeenCalledWith({ sort: 'expected_profit_per_operation_chaos', limit: 50 });
    });

    expect(await screen.findByText('64c')).toBeTruthy();
    expect(screen.getByText('8c')).toBeTruthy();
    expect(screen.getByText('Expected Profit')).toBeTruthy();
    expect(screen.getAllByText('Profit / min')).toHaveLength(2);
  });

  test('switches to per-minute sorting with a fresh request and clears prior cursor state', async () => {
    const refreshRequest = defer<ScannerRecommendationsResponse>();
    getScannerRecommendationsMock
      .mockResolvedValueOnce(
        createResponse(
          [createRecommendation({ itemOrMarketKey: 'Profit-first Result' })],
          { hasMore: true, nextCursor: 'cursor-profit-1' }
        )
      )
      .mockImplementationOnce(() => refreshRequest.promise);

    render(<OpportunitiesTab />);

    expect(await screen.findByText('Profit-first Result')).toBeTruthy();
    expect(screen.getByTestId('scanner-load-more')).toBeTruthy();

    fireEvent.click(screen.getByTestId('scanner-sort-profit-per-minute'));

    await waitFor(() => {
      expect(getScannerRecommendationsMock).toHaveBeenNthCalledWith(2, {
        sort: 'expected_profit_per_minute_chaos',
        limit: 50,
      });
    });

    expect(screen.getByTestId('state-loading')).toBeTruthy();
    expect(screen.queryByTestId('scanner-load-more')).toBeNull();

    await act(async () => {
      refreshRequest.resolve(
        createResponse([
          createRecommendation({
            itemOrMarketKey: 'Per-minute Result',
            expectedProfitChaos: 30,
            expectedProfitPerMinuteChaos: 10,
          }),
        ])
      );
    });

    expect(await screen.findByText('Per-minute Result')).toBeTruthy();
    expect(screen.queryByText('Profit-first Result')).toBeNull();
  });

  test('uses the next cursor to append another page only when more results exist', async () => {
    getScannerRecommendationsMock
      .mockResolvedValueOnce(
        createResponse(
          [createRecommendation({ itemOrMarketKey: 'Page One Result' })],
          { hasMore: true, nextCursor: 'cursor-page-2' }
        )
      )
      .mockResolvedValueOnce(
        createResponse(
          [createRecommendation({ scannerRunId: 'scan-2', itemOrMarketKey: 'Page Two Result' })],
          { hasMore: false, nextCursor: null }
        )
      );

    render(<OpportunitiesTab />);

    expect(await screen.findByText('Page One Result')).toBeTruthy();

    fireEvent.click(screen.getByTestId('scanner-load-more'));

    await waitFor(() => {
      expect(getScannerRecommendationsMock).toHaveBeenNthCalledWith(2, {
        sort: 'expected_profit_per_operation_chaos',
        cursor: 'cursor-page-2',
        limit: 50,
      });
    });

    expect(await screen.findByText('Page Two Result')).toBeTruthy();
    expect(screen.getByText('Page One Result')).toBeTruthy();
    expect(screen.queryByTestId('scanner-load-more')).toBeNull();
  });

  test('keeps the empty state when the scanner returns no recommendations', async () => {
    getScannerRecommendationsMock.mockResolvedValueOnce(createResponse([]));

    render(<OpportunitiesTab />);

    expect(await screen.findByText('No opportunities found in the latest scan.')).toBeTruthy();
  });

  test('shows the degraded state when the scanner request fails', async () => {
    getScannerRecommendationsMock.mockRejectedValueOnce(new Error('scanner offline'));

    render(<OpportunitiesTab />);

    expect(await screen.findByText('scanner offline')).toBeTruthy();
  });
});
