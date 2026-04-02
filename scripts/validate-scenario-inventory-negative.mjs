import { mkdir, writeFile } from 'node:fs/promises';

const outDir = new URL('../../.sisyphus/evidence/product/task-2-scenario-inventory/', import.meta.url);
await mkdir(outDir, { recursive: true });

const scenarios = [
  { id: 'duplicate-id' },
  { id: 'duplicate-id' },
];
const ids = scenarios.map((row) => row.id);
const uniqueIds = new Set(ids);
const duplicateDetected = uniqueIds.size !== ids.length;

await writeFile(
  new URL('inventory-negative.json', outDir),
  JSON.stringify({ status: duplicateDetected ? 'ok' : 'failed', duplicateDetected }, null, 2),
);

if (!duplicateDetected) {
  process.exit(1);
}
