type ChartRow = {label: string; value: number};
type GeoRow = {country: string; province: string; value: number};
type DashboardPayload = {
  generatedAt: string;
  rangeDays: number;
  today: Record<string, number>;
  period: Record<string, number>;
  charts: {
    daily: ChartRow[]; monthly: ChartRow[]; communities: ChartRow[];
    searches: ChartRow[]; fiscalYears: ChartRow[]; sources: ChartRow[];
    devices: ChartRow[]; browsers: ChartRow[]; geography: GeoRow[];
    visitors: ChartRow[];
  };
  rankings: {
    communities: ChartRow[]; searches: ChartRow[]; downloads: ChartRow[];
    landingPages: ChartRow[]; exitPages: ChartRow[];
  };
  journeys: ChartRow[];
};

declare global {
  interface Window { OPENBAND_ANALYTICS_CONFIG?: {apiEndpoint?: string}; }
}

const node = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const number = (value: unknown) => Number.isFinite(Number(value)) ? Number(value) : 0;
const whole = (value: unknown) => Math.round(number(value)).toLocaleString("en-CA");
const duration = (value: unknown) => {
  const seconds = Math.max(0, number(value));
  return seconds >= 3600 ? `${Math.floor(seconds / 3600)}h ${Math.round(seconds % 3600 / 60)}m` : `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
};
const escapeHtml = (value: unknown) => String(value ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const endpoint = () => (window.OPENBAND_ANALYTICS_CONFIG?.apiEndpoint || "").replace(/\/v1\/events\/?$/, "/v1/dashboard");

let adminToken = "";

function metricMarkup(rows: Array<[string, number | string]>): string {
  return rows.map(([label, value]) => `<div class="admin-metric"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`).join("");
}

function lineChart(rows: ChartRow[]): string {
  if (!rows.length) return '<div class="admin-empty">No data is available for this period.</div>';
  const width = 900, height = 230, left = 48, right = 18, top = 18, bottom = 35;
  const maximum = Math.max(1, ...rows.map(row => number(row.value)));
  const x = (index: number) => left + (rows.length === 1 ? (width - left - right) / 2 : index * (width - left - right) / (rows.length - 1));
  const y = (value: number) => top + (maximum - value) / maximum * (height - top - bottom);
  const path = rows.map((row, index) => `${index ? "L" : "M"}${x(index).toFixed(1)},${y(number(row.value)).toFixed(1)}`).join(" ");
  const points = rows.map((row, index) => `<circle class="point" cx="${x(index).toFixed(1)}" cy="${y(number(row.value)).toFixed(1)}" r="4"><title>${escapeHtml(row.label)}: ${whole(row.value)}</title></circle>`).join("");
  const labels = rows.filter((_row, index) => rows.length <= 12 || index % Math.ceil(rows.length / 10) === 0 || index === rows.length - 1).map((row, index, selected) => {
    const sourceIndex = rows.indexOf(row);
    return `<text x="${x(sourceIndex).toFixed(1)}" y="${height - 10}" text-anchor="${index === 0 ? "start" : index === selected.length - 1 ? "end" : "middle"}">${escapeHtml(row.label.slice(5))}</text>`;
  }).join("");
  const grid = [0, .25, .5, .75, 1].map(ratio => { const value = maximum * ratio, py = y(value); return `<line class="grid" x1="${left}" y1="${py}" x2="${width-right}" y2="${py}"></line><text x="${left-8}" y="${py+3}" text-anchor="end">${whole(value)}</text>`; }).join("");
  return `<svg class="admin-line-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="Visitor trend">${grid}<path class="line" d="${path}"></path>${points}${labels}</svg>`;
}

function barChart(rows: ChartRow[], limit = 10): string {
  const shown = rows.slice(0, limit);
  if (!shown.length) return '<div class="admin-empty">No data is available for this period.</div>';
  const maximum = Math.max(1, ...shown.map(row => number(row.value)));
  return `<div class="admin-bars">${shown.map(row => `<div class="admin-bar-row" title="${escapeHtml(row.label)}: ${whole(row.value)}"><span class="admin-bar-label">${escapeHtml(row.label)}</span><span class="admin-bar-track"><span class="admin-bar-fill" style="width:${Math.min(100, number(row.value) / maximum * 100).toFixed(1)}%"></span></span><strong class="admin-bar-value">${whole(row.value)}</strong></div>`).join("")}</div>`;
}

function rankingTable(rows: ChartRow[], firstHeading: string, secondHeading: string): string {
  if (!rows.length) return '<div class="admin-empty">No data is available for this period.</div>';
  return `<table class="admin-table"><thead><tr><th>${escapeHtml(firstHeading)}</th><th>${escapeHtml(secondHeading)}</th></tr></thead><tbody>${rows.slice(0, 15).map(row => `<tr><td>${escapeHtml(row.label)}</td><td>${whole(row.value)}</td></tr>`).join("")}</tbody></table>`;
}

function geography(rows: GeoRow[]): string {
  if (!rows.length) return '<div class="admin-empty">No geographic data is available for this period.</div>';
  return `<div class="admin-geo">${rows.map(row => `<div class="admin-geo-row"><span>${escapeHtml([row.province, row.country].filter(value => value && value !== "Unknown").join(", ") || "Unknown")}</span><strong>${whole(row.value)}</strong></div>`).join("")}</div>`;
}

function journeys(rows: ChartRow[]): string {
  if (!rows.length) return '<div class="admin-empty">Journey data will appear after multi-page sessions are recorded.</div>';
  return `<div class="admin-journeys">${rows.map(row => `<div class="admin-journey"><div class="admin-journey-path">${String(row.label).split(" → ").map((page, index) => `${index ? '<span class="admin-journey-arrow">→</span>' : ""}<span class="admin-journey-page">${escapeHtml(page)}</span>`).join("")}</div><strong>${whole(row.value)} sessions</strong></div>`).join("")}</div>`;
}

function sourceRows(rows: ChartRow[]): ChartRow[] {
  return rows.map(row => {
    if (["direct", "unknown"].includes(row.label)) return row;
    try { return {...row, label: new URL(row.label).hostname}; }
    catch { return row; }
  }).reduce<ChartRow[]>((combined, row) => {
    const existing = combined.find(item => item.label === row.label);
    if (existing) existing.value += number(row.value); else combined.push({...row, value: number(row.value)});
    return combined;
  }, []).sort((a, b) => b.value - a.value);
}

function renderDashboard(data: DashboardPayload): void {
  node("analyticsGenerated").textContent = `Updated ${new Date(data.generatedAt).toLocaleString("en-CA")} · ${data.rangeDays}-day reporting range`;
  node("todayMetrics").innerHTML = metricMarkup([
    ["Active Users", whole(data.today.activeUsers)], ["Total Visits", whole(data.today.totalVisits)],
    ["Page Views", whole(data.today.pageViews)], ["Average Session Duration", duration(data.today.averageSessionDuration)],
    ["Bounce Rate", `${number(data.today.bounceRate).toFixed(1)}%`]
  ]);
  node("periodMetrics").innerHTML = metricMarkup([
    ["Unique Visitors", whole(data.period.uniqueVisitors)], ["Returning Visitors", whole(data.period.returningVisitors)],
    ["Total Searches", whole(data.period.totalSearches)], ["Community Views", whole(data.period.totalCommunityViews)],
    ["PDF Opens", whole(data.period.totalPdfOpens)], ["Downloads", whole(data.period.totalDownloads)]
  ]);
  node("dailyVisitors").innerHTML = lineChart(data.charts.daily);
  node("monthlyVisitors").innerHTML = lineChart(data.charts.monthly);
  node("visitorTypes").innerHTML = barChart(data.charts.visitors);
  node("communityChart").innerHTML = barChart(data.charts.communities);
  node("searchChart").innerHTML = barChart(data.charts.searches);
  node("fiscalYearChart").innerHTML = barChart(data.charts.fiscalYears);
  node("downloadChart").innerHTML = barChart(data.rankings.downloads);
  node("trafficSources").innerHTML = barChart(sourceRows(data.charts.sources), 12);
  node("deviceBreakdown").innerHTML = barChart(data.charts.devices);
  node("browserBreakdown").innerHTML = barChart(data.charts.browsers);
  node("geography").innerHTML = geography(data.charts.geography);
  node("topCommunities").innerHTML = rankingTable(data.rankings.communities, "Community", "Views");
  node("topSearches").innerHTML = rankingTable(data.rankings.searches, "Search term", "Count");
  node("topDownloads").innerHTML = rankingTable(data.rankings.downloads, "Statement", "Downloads");
  node("landingPages").innerHTML = rankingTable(data.rankings.landingPages, "Landing page", "Visits");
  node("exitPages").innerHTML = rankingTable(data.rankings.exitPages, "Exit page", "Exits");
  node("userJourneys").innerHTML = journeys(data.journeys);
}

async function loadDashboard(): Promise<void> {
  const error = node<HTMLParagraphElement>("analyticsDashboardError");
  error.hidden = true;
  const api = endpoint();
  if (!api) { error.textContent = "The analytics API endpoint is not configured."; error.hidden = false; return; }
  try {
    const days = node<HTMLSelectElement>("analyticsRange").value;
    const response = await fetch(`${api}?days=${encodeURIComponent(days)}`, {headers: {Authorization: `Bearer ${adminToken}`}, credentials: "omit", cache: "no-store"});
    if (response.status === 401) throw new Error("Authentication failed.");
    if (!response.ok) throw new Error(`Analytics API returned ${response.status}.`);
    renderDashboard(await response.json() as DashboardPayload);
  } catch (caught) {
    error.textContent = caught instanceof Error ? caught.message : "The dashboard could not be loaded.";
    error.hidden = false;
  }
}

node<HTMLFormElement>("analyticsLoginForm").addEventListener("submit", event => {
  event.preventDefault();
  const api = endpoint(), loginError = node<HTMLParagraphElement>("analyticsLoginError");
  if (!api) { loginError.textContent = "Set the analytics API endpoint before opening the dashboard."; loginError.hidden = false; return; }
  adminToken = node<HTMLInputElement>("analyticsToken").value;
  node<HTMLInputElement>("analyticsToken").value = "";
  node("analyticsLogin").hidden = true;
  node("analyticsDashboard").hidden = false;
  void loadDashboard();
});
node<HTMLSelectElement>("analyticsRange").addEventListener("change", () => void loadDashboard());
document.querySelectorAll<HTMLButtonElement>("[data-admin-tab]").forEach(button => button.addEventListener("click", () => {
  document.querySelectorAll<HTMLButtonElement>("[data-admin-tab]").forEach(item => { const active = item === button; item.classList.toggle("active", active); item.setAttribute("aria-selected", String(active)); });
  document.querySelectorAll<HTMLElement>("[data-admin-panel]").forEach(panel => panel.classList.toggle("active", panel.dataset.adminPanel === button.dataset.adminTab));
}));
document.querySelectorAll<HTMLElement>("[data-current-year]").forEach(element => { element.textContent = String(new Date().getFullYear()); });

export {};
