const SLO_RUNBOOK_LINK = "docs/ops-runbook.md#slo-penalty-tiles";

const fallbackOpsPayload = {
  timestamp: new Date().toISOString(),
  ingest_rate: {
    window_minutes: 15,
    public_stash_records_per_minute: 110.5,
    currency_records_per_minute: 32.2,
    public_stash_last_seen: new Date(Date.now() - 5 * 60 * 1000).toISOString(),
    currency_last_seen: new Date(Date.now() - 38 * 60 * 1000).toISOString(),
  },
  checkpoint_health: [
    {
      cursor_name: "stash_cursor",
      last_checkpoint: new Date(Date.now() - 12 * 60 * 1000).toISOString(),
      expected_interval_minutes: 10,
      drift_minutes: 12.0,
      alert: true,
    },
  ],
  request_rate: {
    requests_per_minute: 42.7,
    error_rate_percent: 1.8,
    throttled_percent: 0.4,
  },
  slo_status: [
    {
      stream_name: "public_stash",
      target_minutes: 10,
      observed_minutes: 6.2,
      within_slo: true,
      note: null,
    },
    {
      stream_name: "currency_snapshot",
      target_minutes: 65,
      observed_minutes: 54.8,
      within_slo: true,
      note: null,
    },
  ],
  rate_limit_alerts: [
    {
      status_code: 429,
      occurrences: 7,
      window_minutes: 30,
      severity: "critical",
      alert: true,
    },
    {
      status_code: 404,
      occurrences: 9,
      window_minutes: 30,
      severity: "warning",
      alert: true,
    },
  ],
  slo_penalties: [
    {
      metric_name: "ingest_latency_seconds",
      target_seconds: 60,
      observed_seconds: 45,
      penalty_seconds: 0,
      within_target: true,
      runbook_link: SLO_RUNBOOK_LINK,
    },
    {
      metric_name: "alert_latency_seconds",
      target_seconds: 30,
      observed_seconds: 35,
      penalty_seconds: 5,
      within_target: false,
      runbook_link: SLO_RUNBOOK_LINK,
    },
  ],
};

const elements = {
  ingest: document.getElementById("ingest-content"),
  request: document.getElementById("request-content"),
  checkpoint: document.getElementById("checkpoint-list"),
  slo: document.getElementById("slo-list"),
  alerts: document.getElementById("alerts-list"),
  penalties: document.getElementById("penalty-list"),
  penaltyRunbook: document.getElementById("penalty-runbook-link"),
  banner: document.getElementById("status-banner"),
};

async function loadDashboard() {
  let payload = fallbackOpsPayload;
  let fallback = true;
  try {
    const response = await fetch("/v1/ops/dashboard", { cache: "no-cache" });
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
  elements.banner.textContent = isFallback
    ? "Live API unavailable; showing fallback telemetry until connectivity returns."
    : `Snapshot @ ${new Date(data.timestamp).toLocaleTimeString()}`;
  renderIngest(data.ingest_rate);
  renderRequest(data.request_rate);
  renderCheckpoint(data.checkpoint_health);
  renderSLOs(data.slo_status);
  renderPenalties(data.slo_penalties);
  renderAlerts(data.rate_limit_alerts);
}

function renderIngest(rate) {
  if (!elements.ingest) return;
  elements.ingest.innerHTML = `
    <div class="rounded-xl bg-slate-900/70 p-4 space-y-3">
      <p class="text-sm uppercase tracking-[0.3em] text-slate-400">Window: ${rate.window_minutes}m</p>
      <div class="grid gap-4 sm:grid-cols-2">
        <article class="rounded-2xl border border-slate-800/60 bg-slate-950/60 p-4">
          <p class="text-xs text-slate-400">Public stash</p>
          <p class="text-3xl font-semibold text-white">${Number(rate.public_stash_records_per_minute).toFixed(1)} rpm</p>
          <p class="text-xs text-slate-500">Last seen ${formatTime(rate.public_stash_last_seen)}</p>
        </article>
        <article class="rounded-2xl border border-slate-800/60 bg-slate-950/60 p-4">
          <p class="text-xs text-slate-400">Currency snapshot</p>
          <p class="text-3xl font-semibold text-white">${Number(rate.currency_records_per_minute).toFixed(1)} rpm</p>
          <p class="text-xs text-slate-500">Last seen ${formatTime(rate.currency_last_seen)}</p>
        </article>
      </div>
    </div>
  `;
}

function renderRequest(rate) {
  if (!elements.request) return;
  elements.request.innerHTML = `
    <div class="rounded-xl bg-slate-900/70 p-4 space-y-4">
      <div class="flex items-center justify-between">
        <p class="text-sm text-slate-400">Req/min</p>
        <p class="text-sm text-slate-400">Errors %</p>
      </div>
      <div class="flex items-end gap-6">
        <p class="text-4xl font-semibold text-white">${Number(rate.requests_per_minute).toFixed(1)}</p>
        <p class="text-lg font-medium text-slate-200">${Number(rate.error_rate_percent).toFixed(1)}%</p>
      </div>
      <p class="text-xs text-slate-500">Throttled ${Number(rate.throttled_percent).toFixed(1)}%</p>
    </div>
  `;
}

function renderCheckpoint(items) {
  if (!elements.checkpoint) return;
  if (!items.length) {
    elements.checkpoint.innerHTML = `<p class="text-sm text-slate-500">No checkpoints reported.</p>`;
    return;
  }
  elements.checkpoint.innerHTML = items
    .map((item) => `
      <article class="rounded-2xl border border-slate-800/60 bg-slate-950/60 p-4">
        <div class="flex items-center justify-between">
          <p class="text-xs font-semibold uppercase tracking-[0.3em] text-slate-400">${item.cursor_name}</p>
          <span class="text-xs ${item.alert ? 'text-amber-300' : 'text-emerald-300'}">
            ${item.alert ? 'Alert' : 'Healthy'}
          </span>
        </div>
        <p class="mt-2 text-sm text-slate-400">Drift: ${Number(item.drift_minutes).toFixed(1)}m / expected ${item.expected_interval_minutes}m</p>
        <p class="text-xs text-slate-500">Last checkpoint ${formatTime(item.last_checkpoint)}</p>
      </article>
    `)
    .join("\n");
}

function renderSLOs(slos) {
  if (!elements.slo) return;
  if (!slos.length) {
    elements.slo.innerHTML = `<p class="text-sm text-amber-50">No SLO data.</p>`;
    return;
  }
  elements.slo.innerHTML = slos
    .map((slo) => `
      <article class="flex items-center justify-between rounded-2xl border border-amber-500/40 bg-amber-500/10 p-4">
        <div>
          <p class="text-sm font-semibold uppercase tracking-[0.3em] text-amber-200">${slo.stream_name}</p>
          <p class="text-sm text-amber-100">Lag ${Number(slo.observed_minutes).toFixed(1)}m / target ${slo.target_minutes}m</p>
          ${slo.note ? `<p class="text-xs text-amber-100/80">${slo.note}</p>` : ""}
        </div>
        <span class="text-sm font-semibold ${slo.within_slo ? 'text-emerald-300' : 'text-rose-300'}">
          ${slo.within_slo ? 'Within SLO' : 'Missed'}
        </span>
      </article>
    `)
    .join("\n");
}

function renderPenalties(penalties) {
  if (!elements.penalties) return;
  const linkTarget = penalties?.[0]?.runbook_link || SLO_RUNBOOK_LINK;
  if (elements.penaltyRunbook) {
    elements.penaltyRunbook.href = linkTarget;
  }
  if (!penalties || !penalties.length) {
    elements.penalties.innerHTML = `<p class="text-sm text-slate-500">No SLO penalty data.</p>`;
    return;
  }
  elements.penalties.innerHTML = penalties
    .map((penalty) => {
      const status = penalty.within_target ? "Within target" : "Penalty";
      const badgeColor = penalty.within_target ? "text-emerald-300" : "text-rose-300";
      return `
        <article class="rounded-2xl border border-slate-800/60 bg-slate-950/60 p-4">
          <div class="flex items-center justify-between">
            <p class="text-xs font-semibold uppercase tracking-[0.3em] text-slate-400">${penalty.metric_name}</p>
            <span class="text-sm font-semibold ${badgeColor}">${status}</span>
          </div>
          <p class="mt-2 text-sm text-slate-400">
            Observed ${Number(penalty.observed_seconds).toFixed(1)}s / target ${Number(penalty.target_seconds).toFixed(1)}s
          </p>
          <p class="text-xs text-slate-500">
            Penalty ${Number(penalty.penalty_seconds).toFixed(1)}s
          </p>
        </article>
      `;
    })
    .join("\n");
}

function renderAlerts(alerts) {
  if (!elements.alerts) return;
  if (!alerts.length) {
    elements.alerts.innerHTML = `<p class="text-sm text-slate-500">No alerts in the last window.</p>`;
    return;
  }
  elements.alerts.innerHTML = alerts
    .map((alert) => `
      <article class="flex items-center justify-between rounded-2xl border border-slate-800/60 bg-slate-950/60 p-4">
        <div>
          <p class="text-sm font-semibold text-slate-100">${alert.status_code}</p>
          <p class="text-xs text-slate-400">${alert.occurrences} hits / ${alert.window_minutes}m · severity ${alert.severity}</p>
        </div>
        <span class="text-sm font-semibold ${alert.alert ? 'text-rose-400' : 'text-emerald-300'}">
          ${alert.alert ? 'Triaged' : 'Watching'}
        </span>
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

document.addEventListener("DOMContentLoaded", () => {
  loadDashboard();
  setInterval(loadDashboard, 45 * 1000);
});
