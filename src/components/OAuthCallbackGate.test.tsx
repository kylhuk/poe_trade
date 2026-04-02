// @vitest-environment jsdom

import '@testing-library/jest-dom/vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { expect, test } from 'vitest';

import OAuthCallbackGate from './OAuthCallbackGate';

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}{location.search}</div>;
}

test('redirects oauth error callbacks to the auth callback route', async () => {
  render(
    <MemoryRouter initialEntries={['/inventory?error=access_denied&error_description=user%20cancelled']}>
      <OAuthCallbackGate>
        <Routes>
          <Route path="*" element={<LocationProbe />} />
        </Routes>
      </OAuthCallbackGate>
    </MemoryRouter>,
  );

  await waitFor(() => {
    expect(screen.getByTestId('location')).toHaveTextContent(
      '/auth/callback?error=access_denied&error_description=user%20cancelled',
    );
  });
});
