import { mkdir, readFile, writeFile } from 'node:fs/promises';

const inputPath = new URL('../src/test/scenario-inventory.json', import.meta.url);
const apiTypesPath = new URL('../src/types/api.ts', import.meta.url);
const outPath = new URL('../../.sisyphus/evidence/product/task-2-scenario-inventory/inventory-validation.json', import.meta.url);

const raw = await readFile(inputPath, 'utf-8');
const inventory = JSON.parse(raw);
const scenarios = Array.isArray(inventory.scenarios) ? inventory.scenarios : [];

const apiTypesSource = await readFile(apiTypesPath, 'utf-8');
const apiServiceBlockMatch = apiTypesSource.match(/export interface ApiService\s*\{([\s\S]*?)\n\}/);
const apiServiceBlock = apiServiceBlockMatch?.[1] ?? '';
const expectedApiMethods = Array.from(apiServiceBlock.matchAll(/^\s*([a-z][A-Za-z0-9]*)\s*\(/gm)).map((match) => match[1]);
const expectedApiMethodSet = new Set(expectedApiMethods);

const ids = scenarios.map((row) => row.id);
const uniqueIds = new Set(ids);
const allowedClassifications = new Set(['deterministic-qa-only', 'live-smoke', 'degraded-state']);
const requiredAuthScenarios = [
  'auth-session-state-indicator',
  'auth-settings-save-session-refresh',
  'auth-settings-clear-logout',
];

const rowShapeIssues = [];
for (const row of scenarios) {
  const rowId = typeof row?.id === 'string' ? row.id : '<missing-id>';
  if (typeof row?.id !== 'string' || row.id.length === 0) {
    rowShapeIssues.push(`${rowId}: missing id`);
  }
  if (typeof row?.owner !== 'string' || row.owner.length === 0) {
    rowShapeIssues.push(`${rowId}: missing owner`);
  }
  if (!allowedClassifications.has(row?.classification)) {
    rowShapeIssues.push(`${rowId}: invalid classification ${String(row?.classification)}`);
  }
  if (typeof row?.selectorTarget !== 'string' || row.selectorTarget.length === 0) {
    rowShapeIssues.push(`${rowId}: missing selectorTarget`);
  }
  if (typeof row?.artifact !== 'string' || !row.artifact.startsWith('.sisyphus/evidence/product/task-2-scenario-inventory/')) {
    rowShapeIssues.push(`${rowId}: invalid artifact path`);
  }
  if (!Array.isArray(row?.backendDependencies) || row.backendDependencies.length === 0) {
    rowShapeIssues.push(`${rowId}: missing backendDependencies`);
  }
  if (!Array.isArray(row?.apiMethods)) {
    rowShapeIssues.push(`${rowId}: apiMethods must be an array`);
  }
}

const authScenarioSet = new Set(scenarios.map((row) => row.id));
const missingAuthScenarios = requiredAuthScenarios.filter((id) => !authScenarioSet.has(id));

const coveredApiMethods = new Set();
const unknownApiMethods = [];
for (const row of scenarios) {
  for (const method of Array.isArray(row.apiMethods) ? row.apiMethods : []) {
    if (typeof method !== 'string') {
      continue;
    }
    if (!expectedApiMethodSet.has(method)) {
      unknownApiMethods.push({ scenarioId: row.id, method });
      continue;
    }
    coveredApiMethods.add(method);
  }
}
const missingApiMethods = expectedApiMethods.filter((method) => !coveredApiMethods.has(method));

const valid =
  ids.length > 0 &&
  uniqueIds.size === ids.length &&
  rowShapeIssues.length === 0 &&
  missingApiMethods.length === 0 &&
  unknownApiMethods.length === 0 &&
  missingAuthScenarios.length === 0;

await mkdir(new URL('../../.sisyphus/evidence/product/task-2-scenario-inventory/', import.meta.url), { recursive: true });
await writeFile(
  outPath,
  JSON.stringify(
    {
      status: valid ? 'ok' : 'failed',
      total: ids.length,
      unique: uniqueIds.size,
      expectedApiMethods,
      coveredApiMethods: Array.from(coveredApiMethods).sort(),
      missingApiMethods,
      unknownApiMethods,
      missingAuthScenarios,
      rowShapeIssues,
    },
    null,
    2,
  ),
);

if (!valid) {
  process.exit(1);
}
