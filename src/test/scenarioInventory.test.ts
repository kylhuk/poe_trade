import { describe, expect, test } from 'vitest';
import inventory from './scenario-inventory.json';

describe('scenario inventory contract', () => {
  test('every scenario id is unique and has deterministic artifact path', () => {
    const ids = inventory.scenarios.map((row) => row.id);
    expect(new Set(ids).size).toBe(ids.length);
    for (const row of inventory.scenarios) {
      expect(row.id).toMatch(/^[a-z0-9-]+$/);
      expect(row.artifact.startsWith('.sisyphus/evidence/product/task-2-scenario-inventory/')).toBe(true);
    }
  });

  test('classification values stay in approved set', () => {
    const allowed = new Set([
      'deterministic-qa-only',
      'live-smoke',
      'degraded-state',
    ]);
    for (const row of inventory.scenarios) {
      expect(allowed.has(row.classification)).toBe(true);
    }
  });

  test('every scenario has explicit owner, selector target, and dependency mapping', () => {
    for (const row of inventory.scenarios) {
      expect(typeof row.owner).toBe('string');
      expect(row.owner.length).toBeGreaterThan(0);
      expect(typeof row.selectorTarget).toBe('string');
      expect(row.selectorTarget.length).toBeGreaterThan(0);
      expect(Array.isArray(row.backendDependencies)).toBe(true);
      expect(row.backendDependencies.length).toBeGreaterThan(0);
      for (const dep of row.backendDependencies) {
        expect(typeof dep).toBe('string');
        expect(dep.length).toBeGreaterThan(0);
      }
      expect(Array.isArray(row.apiMethods)).toBe(true);
      for (const method of row.apiMethods) {
        expect(typeof method).toBe('string');
        expect(method).toMatch(/^[a-z][A-Za-z0-9]*$/);
      }
    }
  });

  test('auth/session only flows stay explicitly tracked', () => {
    const ids = new Set(inventory.scenarios.map((row) => row.id));
    expect(ids.has('auth-session-state-indicator')).toBe(true);
    expect(ids.has('auth-settings-save-session-refresh')).toBe(true);
    expect(ids.has('auth-settings-clear-logout')).toBe(true);
  });
});
