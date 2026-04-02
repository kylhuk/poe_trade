import { Navigate, useLocation } from 'react-router-dom';

/**
 * Detects OAuth callback params (code & state) on any route
 * and redirects to /auth/callback to handle the relay.
 */
const OAuthCallbackGate: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const location = useLocation();
  const params = new URLSearchParams(location.search);

  const hasOAuthResponse = params.has('error') || (params.has('code') && params.has('state'));

  if (hasOAuthResponse && location.pathname !== '/auth/callback') {
    return <Navigate to={`/auth/callback${location.search}`} replace />;
  }

  return <>{children}</>;
};

export default OAuthCallbackGate;
