import { mkdir, writeFile } from 'node:fs/promises';
import { dirname } from 'node:path';
import type { Page } from '@playwright/test';

export async function writeEvidence(page: Page, basePath: string): Promise<void> {
  await mkdir(dirname(basePath), { recursive: true });
  const html = await page.content();
  await writeFile(`${basePath}.html`, html, 'utf-8');
  await page.screenshot({ path: `${basePath}.png`, fullPage: true });
}

export async function writeScenarioArtifact(page: Page, artifactPath: string, payload?: unknown): Promise<void> {
  await mkdir(dirname(artifactPath), { recursive: true });
  if (artifactPath.endsWith('.png')) {
    await page.screenshot({ path: artifactPath, fullPage: true });
    return;
  }
  if (artifactPath.endsWith('.html')) {
    const html = await page.content();
    await writeFile(artifactPath, html, 'utf-8');
    if (payload !== undefined) {
      const jsonPath = artifactPath.replace(/\.html$/, '.json');
      await writeFile(jsonPath, JSON.stringify(payload, null, 2), 'utf-8');
    }
    return;
  }
  if (artifactPath.endsWith('.json')) {
    await writeFile(artifactPath, JSON.stringify(payload ?? {}, null, 2), 'utf-8');
    return;
  }
  const html = await page.content();
  await writeFile(artifactPath, html, 'utf-8');
}
