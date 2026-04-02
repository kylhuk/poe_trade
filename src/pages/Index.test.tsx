// @vitest-environment jsdom

import '@testing-library/jest-dom/vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { beforeEach, expect, test, vi } from 'vitest';

import Index from './Index';

const useAuthMock = vi.fn();

vi.mock('@/services/auth', () => ({
  useAuth: () => useAuthMock(),
}));

vi.mock('@/components/UserMenu', () => ({
  default: () => <div data-testid="user-menu" />,
}));

vi.mock('@/components/ApiErrorPanel', () => ({
  default: () => null,
}));

vi.mock('@/components/tabs/DashboardTab', () => ({ default: () => <div>Dashboard panel</div> }));
vi.mock('@/components/tabs/ServicesTab', () => ({ default: () => <div>Services panel</div> }));
vi.mock('@/components/tabs/AnalyticsTab', () => ({ default: () => <div>Analytics panel</div> }));
vi.mock('@/components/tabs/PriceCheckTab', () => ({ default: () => <div>Pricecheck panel</div> }));
vi.mock('@/components/tabs/StashViewerTab', () => ({ default: () => <div>Stash panel</div> }));
vi.mock('@/components/tabs/EconomyTab', () => ({ default: () => <div>Economy panel</div> }));
vi.mock('@/components/tabs/MessagesTab', () => ({ default: () => <div>Messages panel</div> }));
vi.mock('@/components/tabs/FlipFinderTab', () => ({ default: () => <div>Opportunities panel</div> }));
vi.mock('@/components/tabs/DebugTrafficTab', () => ({ default: () => <div>Traffic panel</div> }));

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}</div>;
}

beforeEach(() => {
  useAuthMock.mockReturnValue({
    userRole: 'member',
    isLoading: false,
    isAuthenticated: true,
    isApproved: true,
  });
});

test('arrow key tab navigation updates the route', async () => {
  render(
    <MemoryRouter initialEntries={['/opportunities']}>
      <Routes>
        <Route
          path="/:tab/:subtab?"
          element={
            <>
              <LocationProbe />
              <Index />
            </>
          }
        />
      </Routes>
    </MemoryRouter>,
  );

  expect(screen.getByRole('tab', { name: 'Opportunities' })).toHaveAttribute('data-state', 'active');
  const activeTab = screen.getByRole('tab', { name: 'Opportunities' });
  act(() => {
    activeTab.focus();
    fireEvent.keyDown(activeTab, { key: 'ArrowRight' });
  });

  await waitFor(() => {
    expect(screen.getByTestId('location')).toHaveTextContent('/analytics');
  });
});

test('ctrl and meta shortcuts navigate between visible tabs', async () => {
  render(
    <MemoryRouter initialEntries={['/opportunities']}>
      <Routes>
        <Route
          path="/:tab/:subtab?"
          element={
            <>
              <LocationProbe />
              <Index />
            </>
          }
        />
      </Routes>
    </MemoryRouter>,
  );

  act(() => {
    fireEvent.keyDown(window, { key: 'ArrowRight', ctrlKey: true });
  });

  await waitFor(() => {
    expect(screen.getByTestId('location')).toHaveTextContent('/analytics');
  });

  act(() => {
    fireEvent.keyDown(window, { key: 'ArrowLeft', ctrlKey: true });
  });

  await waitFor(() => {
    expect(screen.getByTestId('location')).toHaveTextContent('/opportunities');
  });

  act(() => {
    fireEvent.keyDown(window, { key: 'End', metaKey: true });
  });

  await waitFor(() => {
    expect(screen.getByTestId('location')).toHaveTextContent('/economy');
  });
});
