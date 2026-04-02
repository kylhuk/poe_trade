// @vitest-environment jsdom

import '@testing-library/jest-dom/vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import PriceCheckTab from './PriceCheckTab';

const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    priceCheck: vi.fn(),
    mlPredictOne: vi.fn(),
  },
}));

vi.mock('@/services/api', () => ({
  api: apiMock,
}));

vi.mock('@/components/ui/card', () => ({
  Card: ({ children, ...props }: React.HTMLAttributes<HTMLDivElement>) => <div {...props}>{children}</div>,
  CardContent: ({ children, ...props }: React.HTMLAttributes<HTMLDivElement>) => <div {...props}>{children}</div>,
  CardHeader: ({ children, ...props }: React.HTMLAttributes<HTMLDivElement>) => <div {...props}>{children}</div>,
  CardTitle: ({ children, ...props }: React.HTMLAttributes<HTMLHeadingElement>) => <h2 {...props}>{children}</h2>,
}));

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button>,
}));

vi.mock('@/components/ui/textarea', () => ({
  Textarea: ({ ...props }: React.TextareaHTMLAttributes<HTMLTextAreaElement>) => <textarea {...props} />,
}));

vi.mock('@/components/ui/table', () => ({
  Table: ({ children }: { children: React.ReactNode }) => <table>{children}</table>,
  TableBody: ({ children }: { children: React.ReactNode }) => <tbody>{children}</tbody>,
  TableCell: ({ children }: { children: React.ReactNode }) => <td>{children}</td>,
  TableHead: ({ children }: { children: React.ReactNode }) => <th>{children}</th>,
  TableHeader: ({ children }: { children: React.ReactNode }) => <thead>{children}</thead>,
  TableRow: ({ children }: { children: React.ReactNode }) => <tr>{children}</tr>,
}));

vi.mock('@/components/ui/badge', () => ({
  Badge: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
}));

vi.mock('@/components/shared/StatusIndicators', () => ({
  ConfidenceBadge: ({ value }: { value: number | null | undefined }) => <span>{value}</span>,
}));

vi.mock('@/components/shared/RenderState', () => ({
  RenderState: ({ message }: { message?: string }) => <div>{message}</div>,
}));

vi.mock('@/hooks/useMouseGlow', () => ({
  useMouseGlow: () => vi.fn(),
}));

describe('PriceCheckTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders prediction value and comparables from unified response', async () => {
    apiMock.priceCheck.mockResolvedValue({
      predictedValue: 100,
      currency: 'chaos',
      confidence: 0.61,
      comparables: [],
      interval: { p10: 90, p90: 120 },
    });

    render(<PriceCheckTab />);
    fireEvent.change(screen.getByTestId('pricecheck-input'), { target: { value: 'Rarity: Rare' } });
    fireEvent.click(screen.getByTestId('pricecheck-submit'));

    expect(await screen.findByText(/100/)).toBeInTheDocument();
    expect(screen.getByText(/chaos/i)).toBeInTheDocument();
  });

  it('uses unified price-check response without calling mlPredictOne', async () => {
    apiMock.priceCheck.mockResolvedValue({
      predictedValue: 100,
      currency: 'chaos',
      confidence: 0.7,
      comparables: [],
      interval: { p10: 90, p90: 120 },
    });

    const spy = vi.spyOn(apiMock, 'mlPredictOne');
    render(<PriceCheckTab />);
    fireEvent.change(screen.getByTestId('pricecheck-input'), { target: { value: 'Rarity: Rare' } });
    fireEvent.click(screen.getByTestId('pricecheck-submit'));

    await waitFor(() => expect(apiMock.priceCheck).toHaveBeenCalledTimes(1));
    expect(spy).not.toHaveBeenCalled();
  });
});
