const fallbackOpsPayload = {
  timestamp: new Date().toISOString(),
  services: [
    {
      id: "market_harvester",
      name: "Market Harvester",
      description: "Public stash and exchange ingestion daemon",
      status: "running",
      uptime: null,
      lastCrawl: new Date(Date.now() - 5 * 60 * 1000).toISOString(),
      rowsInDb: 123,
      containerInfo: "market_harvester",
      type: "crawler",
      allowedActions: ["start", "stop", "restart"],
    },
    {
      id: "api",
      name: "API",
      description: "Protected backend API service",
      status: "running",
      uptime: null,
      lastCrawl: null,
      rowsInDb: null,
      containerInfo: "api",
      type: "analytics",
      allowedActions: [],
    },
  ],
  deployment: {
    backendVersion: "0.1.0",
    backendSha: null,
    frontendBuildSha: null,
    recommendationContractVersion: 3,
    contractMatchState: "unknown",
  },
  summary: {
    running: 2,
    total: 2,
    errors: 0,
    criticalAlerts: 0,
  },
  topOpportunities: [
    {
      scannerRunId: "scan-1",
      strategyId: "bulk_flip",
      league: "Mirage",
      itemOrMarketKey: "Bottled Faith",
      whyItFired: "Undervalued relative to recent comparables",
      buyPlan: "Buy immediately under target",
      expectedProfitChaos: 120,
      expectedProfitPerMinuteChaos: 12,
      expectedRoi: 0.22,
      expectedHoldTime: "2h",
      confidence: 0.82,
    },
  ],
};

const elements = {
  summary: document.getElementById("summary-content"),
  deployment: document.getElementById("deployment-content"),
  services: document.getElementById("services-list"),
  opportunities: document.getElementById("opportunities-list"),
  banner: document.getElementById("status-banner"),
};

async function loadDashboard() {
  let payload = fallbackOpsPayload;
  let fallback = true;
  try {
    const response = await fetch("/api/v1/ops/dashboard", { cache: "no-cache" });
    if (response.ok) {
      payload = await response.json();
      fallback = false;
    }
  } catch (error) {
    console.warn("ops dashboard fetch failed", error);
  }
  renderDashboard(payload, fallback);
}

function renderDashboard(data, isFallback) {
  if (elements.banner) {
    elements.banner.textContent = isFallback
      ? "Live API unavailable; showing fallback dashboard snapshot until connectivity returns."
      : `Snapshot @ ${new Date(data.timestamp).toLocaleTimeString()}`;
  }
  renderSummary(data.summary);
  renderDeployment(data.deployment);
  renderServices(data.services);
  renderOpportunities(data.topOpportunities);
}

function renderSummary(summary) {
  if (!elements.summary) return;
  const data = summary || {};
  elements.summary.innerHTML = `
    <article class="rounded-2xl border border-slate-800/60 bg-slate-950/60 p-4">
      <p class="text-xs text-slate-400 uppercase tracking-[0.3em]">Running</p>
      <p class="text-3xl font-semibold text-white">${Number(data.running ?? 0)}</p>
    </article>
    <article class="rounded-2xl border border-slate-800/60 bg-slate-950/60 p-4">
      <p class="text-xs text-slate-400 uppercase tracking-[0.3em]">Total</p>
      <p class="text-3xl font-semibold text-white">${Number(data.total ?? 0)}</p>
    </article>
    <article class="rounded-2xl border border-slate-800/60 bg-slate-950/60 p-4">
      <p class="text-xs text-slate-400 uppercase tracking-[0.3em]">Errors</p>
      <p class="text-3xl font-semibold text-white">${Number(data.errors ?? 0)}</p>
    </article>
    <article class="rounded-2xl border border-slate-800/60 bg-slate-950/60 p-4">
      <p class="text-xs text-slate-400 uppercase tracking-[0.3em]">Critical alerts</p>
      <p class="text-3xl font-semibold text-white">${Number(data.criticalAlerts ?? 0)}</p>
    </article>
  `;
}

function renderDeployment(deployment) {
  if (!elements.deployment) return;
  const data = deployment || {};
  elements.deployment.innerHTML = `
    <div class="rounded-2xl border border-slate-800/60 bg-slate-950/60 p-4 space-y-2 text-sm">
      <div class="flex items-center justify-between gap-3">
        <span class="text-slate-400">Backend version</span>
        <span class="text-white font-medium">${String(data.backendVersion ?? "n/a")}</span>
      </div>
      <div class="flex items-center justify-between gap-3">
        <span class="text-slate-400">Contract version</span>
        <span class="text-white font-medium">${String(data.recommendationContractVersion ?? "n/a")}</span>
      </div>
      <div class="flex items-center justify-between gap-3">
        <span class="text-slate-400">Build SHA</span>
        <span class="text-white font-medium">${String(data.frontendBuildSha ?? "n/a")}</span>
      </div>
      <div class="flex items-center justify-between gap-3">
        <span class="text-slate-400">Match state</span>
        <span class="text-white font-medium">${String(data.contractMatchState ?? "unknown")}</span>
      </div>
    </div>
  `;
}

function renderServices(services) {
  if (!elements.services) return;
  if (!services || !services.length) {
    elements.services.innerHTML = `<p class="text-sm text-slate-500">No services reported.</p>`;
    return;
  }
  elements.services.innerHTML = services
    .map((service) => `
      <article class="rounded-2xl border border-slate-800/60 bg-slate-950/60 p-4">
        <div class="flex items-center justify-between gap-3">
          <div>
            <p class="text-sm font-semibold text-white">${escapeHtml(service.name || service.id || "Service")}</p>
            <p class="text-xs text-slate-400">${escapeHtml(service.description || "")}</p>
          </div>
          <span class="text-xs uppercase tracking-[0.3em] ${service.status === "running" ? "text-emerald-300" : service.status === "error" ? "text-rose-300" : "text-slate-300"}">
            ${escapeHtml(service.status || "unknown")}
          </span>
        </div>
        <div class="mt-3 grid gap-2 text-xs text-slate-400 sm:grid-cols-2">
          <div>Type: <span class="text-slate-200">${escapeHtml(service.type || "n/a")}</span></div>
          <div>Rows: <span class="text-slate-200">${service.rowsInDb ?? "n/a"}</span></div>
          <div>Last crawl: <span class="text-slate-200">${service.lastCrawl ? formatTime(service.lastCrawl) : "n/a"}</span></div>
          <div>Actions: <span class="text-slate-200">${Array.isArray(service.allowedActions) ? service.allowedActions.join(", ") : "n/a"}</span></div>
        </div>
      </article>
    `)
    .join("\n");
}

function renderOpportunities(opportunities) {
  if (!elements.opportunities) return;
  if (!opportunities || !opportunities.length) {
    elements.opportunities.innerHTML = `<p class="text-sm text-slate-500">No opportunities returned.</p>`;
    return;
  }
  elements.opportunities.innerHTML = opportunities
    .map((opp) => `
      <article class="rounded-2xl border border-amber-500/40 bg-slate-950/60 p-4">
        <div class="flex items-center justify-between gap-3">
          <p class="text-sm font-semibold text-white">${escapeHtml(opp.itemOrMarketKey || opp.strategyId || opp.scannerRunId || "Opportunity")}</p>
          <span class="text-xs uppercase tracking-[0.3em] text-amber-200">${escapeHtml(opp.strategyId || "n/a")}</span>
        </div>
        <p class="mt-2 text-sm text-slate-300">${escapeHtml(opp.whyItFired || "No explanation provided.")}</p>
        <div class="mt-3 grid gap-2 text-xs text-slate-400 sm:grid-cols-2">
          <div>League: <span class="text-slate-200">${escapeHtml(opp.league || "n/a")}</span></div>
          <div>Scanner run: <span class="text-slate-200">${escapeHtml(opp.scannerRunId || "n/a")}</span></div>
          <div>Profit: <span class="text-slate-200">${opp.expectedProfitChaos ?? "n/a"}</span></div>
          <div>Confidence: <span class="text-slate-200">${opp.confidence != null ? Number(opp.confidence).toFixed(2) : "n/a"}</span></div>
        </div>
      </article>
    `)
    .join("\n");
}

function formatTime(value) {
  return new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

document.addEventListener("DOMContentLoaded", () => {
  loadDashboard();
  setInterval(loadDashboard, 45 * 1000);
});
