import React, { createContext, useContext, useState, useCallback } from 'react';

const STORAGE_KEY = 'poe-selected-league';
const DEFAULT_LEAGUE = 'Mirage';

const KNOWN_LEAGUES = ['Mirage', 'Standard', 'Hardcore', 'Hardcore Mirage'] as const;

interface LeagueContextValue {
  league: string;
  setLeague: (league: string) => void;
  knownLeagues: readonly string[];
}

const LeagueContext = createContext<LeagueContextValue>({
  league: DEFAULT_LEAGUE,
  setLeague: () => {},
  knownLeagues: KNOWN_LEAGUES,
});

export const useLeague = () => useContext(LeagueContext);

export const LeagueProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [league, setLeagueState] = useState<string>(() => {
    try {
      return localStorage.getItem(STORAGE_KEY) || DEFAULT_LEAGUE;
    } catch {
      return DEFAULT_LEAGUE;
    }
  });

  const setLeague = useCallback((l: string) => {
    setLeagueState(l);
    try { localStorage.setItem(STORAGE_KEY, l); } catch {}
  }, []);

  return (
    <LeagueContext.Provider value={{ league, setLeague, knownLeagues: KNOWN_LEAGUES }}>
      {children}
    </LeagueContext.Provider>
  );
};

// Imperative getter for use in api.ts (outside React tree)
let _getLeague: () => string = () => {
  try { return localStorage.getItem(STORAGE_KEY) || DEFAULT_LEAGUE; } catch { return DEFAULT_LEAGUE; }
};

export function getSelectedLeague(): string {
  return _getLeague();
}
