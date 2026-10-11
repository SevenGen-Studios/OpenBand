import {buildIntelligence, IntelligenceReport, NationAnalysis, OfficialAnalysis, StoryLead} from "./intelligence";

interface D1Result<T = Record<string, unknown>> { results?: T[]; success: boolean; }
interface D1PreparedStatement {
  bind(...values: unknown[]): D1PreparedStatement;
  all<T = Record<string, unknown>>(): Promise<D1Result<T>>;
  run(): Promise<D1Result>;
}
interface D1Database {
  prepare(query: string): D1PreparedStatement;
  batch(statements: D1PreparedStatement[]): Promise<D1Result[]>;
}
interface ExecutionContext { waitUntil(promise: Promise<unknown>): void; }

interface Env {
  DB: D1Database;
  VISITOR_HASH_SALT: string;
  ANALYTICS_ADMIN_TOKEN: string;
  ALLOWED_ORIGINS: string;
  DATA_RETENTION_DAYS?: string;
  INTELLIGENCE_DATA_URL?: string;
}

interface IncomingEvent {
  timestamp?: unknown;
  page?: unknown;
  event?: unknown;
  community_id?: unknown;
  fiscal_year?: unknown;
  session_id?: unknown;
  visitor_id?: unknown;
  device_type?: unknown;
  browser?: unknown;
  referrer?: unknown;
  parameters?: unknown;
}

const EVENT_NAMES = new Set([
  "page_view", "session_end", "engagement", "citation_copied", "profile_shared", "search_performed", "search_no_results",
  "community_view", "statement_opened", "statement_downloaded",
  "community_capital_view", "revenue_chart_viewed", "expense_chart_viewed",
  "asset_chart_viewed", "comparison_started", "comparison_completed",
  "news_article_opened", "news_article_shared", "outbound_link_clicked",
  "jobs_tab_viewed", "job_search_performed", "job_filter_used",
  "job_posting_opened", "job_application_clicked",
  "pdf_failed_to_load", "parser_error"
]);
const PARAMETER_KEYS = new Set([
  "page_location", "page_referrer", "page_title", "search_term", "result_count",
  "community_name", "province", "fiscal_year", "statement_type",
  "community_count", "destination", "duration_seconds", "error_code",
  "filter", "value", "job_id", "utm_source", "utm_medium", "utm_campaign", "tracking_version"
]);
const ID_PATTERN = /^[a-zA-Z0-9-]{8,80}$/;

const json = (value: unknown, status = 200, headers: HeadersInit = {}) => new Response(
  JSON.stringify(value),
  {status, headers: {"Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store", ...headers}}
);

const allowedOrigins = (env: Env) => new Set((env.ALLOWED_ORIGINS || "https://openband.ca").split(",").map(value => value.trim()).filter(Boolean));
const corsHeaders = (request: Request, env: Env): Record<string, string> => {
  const origin = request.headers.get("Origin") || "";
  return allowedOrigins(env).has(origin)
    ? {"Access-Control-Allow-Origin": origin, "Access-Control-Allow-Methods": "GET,POST,OPTIONS", "Access-Control-Allow-Headers": "Authorization,Content-Type", "Vary": "Origin"}
    : {};
};

const safeText = (value: unknown, maxLength: number) => typeof value === "string" ? value.trim().slice(0, maxLength) : "";
const safePage = (value: unknown) => {
  const text = safeText(value, 300);
  if (!text.startsWith("/")) return "/";
  try {
    const url = new URL(text, "https://openband.ca");
    const safe = new URLSearchParams();
    for (const key of ["band", "year", "province"]) {
      const value = url.searchParams.get(key);
      if (value && /^[a-zA-Z0-9 _.-]{1,100}$/.test(value)) safe.set(key, value);
    }
    return `${url.pathname}${safe.size ? "?" + safe : ""}`.slice(0, 300);
  } catch {
    return "/";
  }
};
const safeReferrer = (value: unknown) => {
  const text = safeText(value, 300);
  if (["direct", "unknown", "internal"].includes(text)) return text;
  try {
    const url = new URL(text);
    return url.origin === "https://openband.ca" || url.origin === "https://www.openband.ca" ? "internal" : url.origin.slice(0, 300);
  } catch {
    return "unknown";
  }
};
const containsPersonalData = (value: string) => /\b[\w.+-]+@[\w.-]+\.[a-z]{2,}\b/i.test(value) || /(?:\+?1[-. ]?)?\(?\d{3}\)?[-. ]?\d{3}[-. ]?\d{4}/.test(value);
const safeParameters = (value: unknown) => {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  const result: Record<string, string | number | boolean | null> = {};
  for (const [key, raw] of Object.entries(value as Record<string, unknown>)) {
    if (!PARAMETER_KEYS.has(key)) continue;
    if (!["string", "number", "boolean"].includes(typeof raw) && raw !== null) continue;
    const clean = typeof raw === "string" ? raw.slice(0, 200) : raw as number | boolean | null;
    if (typeof clean === "string" && containsPersonalData(clean)) continue;
    if (key === "page_location" && typeof clean === "string") { try { result[key] = "https://openband.ca" + safePage(new URL(clean).pathname + new URL(clean).search); } catch { /* omit invalid URL */ } }
    else if (key === "page_referrer") result[key] = safeReferrer(clean);
    else result[key] = clean;
  }
  return result;
};
const validTimestamp = (value: unknown) => {
  const parsed = new Date(typeof value === "string" ? value : "");
  const now = Date.now();
  return Number.isFinite(parsed.getTime()) && Math.abs(parsed.getTime() - now) < 86400000
    ? parsed.toISOString()
    : new Date(now).toISOString();
};
const hashVisitor = async (visitorId: string, salt: string) => {
  const bytes = new TextEncoder().encode(`${salt}:${visitorId}`);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map(byte => byte.toString(16).padStart(2, "0")).join("");
};
const safeEqual = (a: string, b: string) => {
  const encoder = new TextEncoder();
  const left = encoder.encode(a), right = encoder.encode(b);
  let difference = left.length ^ right.length;
  const length = Math.max(left.length, right.length);
  for (let index = 0; index < length; index++) difference |= (left[index % Math.max(1, left.length)] || 0) ^ (right[index % Math.max(1, right.length)] || 0);
  return difference === 0;
};

async function ingest(request: Request, env: Env): Promise<Response> {
  const headers = corsHeaders(request, env);
  const origin = request.headers.get("Origin") || "";
  if (!allowedOrigins(env).has(origin)) return json({error: "origin_not_allowed"}, 403, headers);
  const length = Number(request.headers.get("Content-Length") || 0);
  if (length > 65536) return json({error: "payload_too_large"}, 413, headers);
  let body: {events?: IncomingEvent[]};
  try { const raw = await request.text(); if (new TextEncoder().encode(raw).length > 65536) return json({error: "payload_too_large"}, 413, headers); body = JSON.parse(raw) as {events?: IncomingEvent[]}; }
  catch { return json({error: "invalid_json"}, 400, headers); }
  if (!body || !Array.isArray(body.events) || !body.events.length || body.events.length > 25) return json({error: "invalid_batch"}, 400, headers);

  const cf = (request as Request & {cf?: {country?: string; region?: string}}).cf || {};
  const country = safeText(cf.country, 8) || "Unknown";
  const province = safeText(cf.region, 80) || "Unknown";
  const statements: D1PreparedStatement[] = [];
  let accepted = 0;
  for (const candidate of body.events) {
    if (!candidate || typeof candidate !== "object") continue;
    const eventName = safeText(candidate.event, 50);
    const sessionId = safeText(candidate.session_id, 80);
    const visitorId = safeText(candidate.visitor_id, 80);
    if (!EVENT_NAMES.has(eventName) || !ID_PATTERN.test(sessionId) || !ID_PATTERN.test(visitorId)) continue;
    const device = ["mobile", "tablet", "desktop"].includes(String(candidate.device_type)) ? String(candidate.device_type) : "unknown";
    const browser = ["Chrome", "Safari", "Firefox", "Edge", "Opera", "Other"].includes(String(candidate.browser)) ? String(candidate.browser) : "Other";
    const parameters = safeParameters(candidate.parameters);
    if (safePage(candidate.page).startsWith("/admin")) continue;
    const hashedVisitor = await hashVisitor(visitorId, env.VISITOR_HASH_SALT);
    statements.push(env.DB.prepare(`
      INSERT INTO analytics_events (
        occurred_at, page, event_name, community_id, fiscal_year, session_id,
        visitor_id, country, province, device_type, browser, referrer, parameters_json
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `).bind(
      validTimestamp(candidate.timestamp), safePage(candidate.page), eventName,
      safeText(candidate.community_id, 32) || null, safeText(candidate.fiscal_year, 16) || null,
      sessionId, hashedVisitor, country, province, device, browser,
      safeReferrer(candidate.referrer), JSON.stringify(parameters)
    ));
    accepted++;
  }
  if (statements.length) await env.DB.batch(statements);
  return json({accepted}, 202, headers);
}

const authorize = (request: Request, env: Env) => {
  const token = request.headers.get("Authorization")?.replace(/^Bearer\s+/i, "") || "";
  return Boolean(env.ANALYTICS_ADMIN_TOKEN && safeEqual(token, env.ANALYTICS_ADMIN_TOKEN));
};
let intelligenceCache: {sourceUrl: string; expiresAt: number; report: IntelligenceReport} | null = null;
const normalizedFilter = (value: string | null) => (value || "").normalize("NFKC").toLocaleLowerCase("en-CA").trim();
const includesFilter = (value: unknown, filter: string) => !filter || String(value || "").normalize("NFKC").toLocaleLowerCase("en-CA").includes(filter);
const boundedPage = (url: URL) => ({
  limit: Math.min(500, Math.max(1, Number(url.searchParams.get("limit")) || 100)),
  offset: Math.max(0, Number(url.searchParams.get("offset")) || 0)
});

async function loadIntelligence(env: Env, refresh: boolean): Promise<IntelligenceReport> {
  const sourceUrl = env.INTELLIGENCE_DATA_URL || "https://openband.ca/data.json";
  if (!refresh && intelligenceCache && intelligenceCache.sourceUrl === sourceUrl && intelligenceCache.expiresAt > Date.now()) return intelligenceCache.report;
  const response = await fetch(sourceUrl, {headers: {Accept: "application/json"}, cf: {cacheEverything: true, cacheTtl: 300}} as RequestInit);
  if (!response.ok) throw new Error(`OpenBand data source returned ${response.status}`);
  const report = buildIntelligence(await response.json() as Record<string, unknown>);
  intelligenceCache = {sourceUrl, expiresAt: Date.now() + 300000, report};
  return report;
}

async function intelligence(request: Request, env: Env): Promise<Response> {
  const headers = corsHeaders(request, env);
  if (!authorize(request, env)) return json({error: "unauthorized"}, 401, {...headers, "WWW-Authenticate": "Bearer"});
  const url = new URL(request.url), section = url.searchParams.get("section") || "overview";
  const nation = normalizedFilter(url.searchParams.get("nation")), official = normalizedFilter(url.searchParams.get("official"));
  const year = url.searchParams.get("year") || "", type = url.searchParams.get("type") || "", strengthFilter = url.searchParams.get("strength") || "";
  const {limit, offset} = boundedPage(url);
  try {
    const report = await loadIntelligence(env, url.searchParams.get("refresh") === "1");
    if (section === "overview") return json({generatedAt: report.generatedAt, sourceGeneratedAt: report.sourceGeneratedAt, overview: report.overview, dataQuality: report.dataQuality, priorityStoryLeads: report.storyLeads.filter(lead => lead.scope !== "filing").slice(0, 25)}, 200, headers);
    if (section === "leads") {
      const matches = (lead: StoryLead) => includesFilter(lead.nation, nation) && includesFilter(lead.official, official) && (!year || lead.fiscalYear === year) && (!type || (lead.signalTypes || [lead.type]).includes(type)) && (!strengthFilter || lead.signalStrength === strengthFilter);
      const filtered = report.storyLeads.filter(matches);
      return json({generatedAt: report.generatedAt, total: filtered.length, offset, limit, results: filtered.slice(offset, offset + limit)}, 200, headers);
    }
    if (section === "officials") {
      const matches = (item: OfficialAnalysis) => includesFilter(item.provenance.nation, nation) && includesFilter(item.official, official) && (!year || item.provenance.fiscalYear === year);
      const filtered = report.officialAnalysis.filter(matches).sort((left, right) => right.provenance.fiscalYear.localeCompare(left.provenance.fiscalYear) || left.provenance.nation.localeCompare(right.provenance.nation) || left.official.localeCompare(right.official));
      return json({generatedAt: report.generatedAt, total: filtered.length, offset, limit, results: filtered.slice(offset, offset + limit)}, 200, headers);
    }
    if (section === "nations") {
      const matches = (item: NationAnalysis) => includesFilter(item.nation, nation) && (!year || item.fiscalYear === year);
      const filtered = report.nationAnalysis.filter(matches).sort((left, right) => right.fiscalYear.localeCompare(left.fiscalYear) || left.nation.localeCompare(right.nation));
      return json({generatedAt: report.generatedAt, total: filtered.length, offset, limit, results: filtered.slice(offset, offset + limit)}, 200, headers);
    }
    if (section === "quality") return json({generatedAt: report.generatedAt, dataQuality: report.dataQuality, pendingFilings: report.storyLeads.filter(lead => lead.scope === "filing").slice(offset, offset + limit)}, 200, headers);
    return json({error: "invalid_section"}, 400, headers);
  } catch (caught) {
    return json({error: "intelligence_unavailable", message: caught instanceof Error ? caught.message : "The intelligence report could not be generated."}, 503, headers);
  }
}
const rows = async <T = Record<string, unknown>>(env: Env, sql: string, ...bindings: unknown[]) =>
  (await env.DB.prepare(sql).bind(...bindings).all<T>()).results || [];
const first = async <T = Record<string, unknown>>(env: Env, sql: string, ...bindings: unknown[]) =>
  (await rows<T>(env, sql, ...bindings))[0] || {} as T;

async function dashboard(request: Request, env: Env): Promise<Response> {
  const headers = corsHeaders(request, env);
  if (!authorize(request, env)) return json({error: "unauthorized"}, 401, {...headers, "WWW-Authenticate": "Bearer"});
  const url = new URL(request.url);
  const rangeDays = [7,30,90,365].includes(Number(url.searchParams.get("days"))) ? Number(url.searchParams.get("days")) : 30;
  const start = `-${rangeDays} days`;

  const [today, sessions, period, returning, daily, monthly, communities, searches, fiscalYears, sources, devices, browsers, geography, downloads, landingPages, exitPages, journeys] = await Promise.all([
    first(env, `SELECT COUNT(DISTINCT visitor_id) activeUsers, COUNT(DISTINCT session_id) totalVisits, SUM(event_name='page_view') pageViews FROM analytics_events WHERE occurred_at >= strftime('%Y-%m-%dT%H:%M:%fZ','now','-6 hours','start of day','+6 hours')`),
    first(env, `WITH s AS (SELECT session_id, SUM(event_name='page_view') pages, MAX(CASE WHEN event_name='session_end' THEN CAST(json_extract(parameters_json,'$.duration_seconds') AS REAL) END) duration, (julianday(MAX(occurred_at))-julianday(MIN(occurred_at)))*86400 span FROM analytics_events WHERE occurred_at >= strftime('%Y-%m-%dT%H:%M:%fZ','now','-6 hours','start of day','+6 hours') GROUP BY session_id) SELECT ROUND(AVG(COALESCE(duration,span)),1) averageSessionDuration, ROUND(100.0*SUM(pages<=1)/NULLIF(COUNT(*),0),1) bounceRate FROM s`),
    first(env, `SELECT COUNT(DISTINCT visitor_id) uniqueVisitors, SUM(event_name='search_performed') totalSearches, SUM(event_name='community_view') totalCommunityViews, SUM(event_name='statement_opened') totalPdfOpens, SUM(event_name='statement_downloaded') totalDownloads FROM analytics_events WHERE occurred_at >= strftime('%Y-%m-%dT%H:%M:%fZ','now', ?)` , start),
    first(env, `WITH first_seen AS (SELECT visitor_id, MIN(occurred_at) firstAt FROM analytics_events GROUP BY visitor_id), active AS (SELECT DISTINCT visitor_id FROM analytics_events WHERE occurred_at >= strftime('%Y-%m-%dT%H:%M:%fZ','now', ?)) SELECT SUM(firstAt < strftime('%Y-%m-%dT%H:%M:%fZ','now', ?)) returningVisitors, SUM(firstAt >= strftime('%Y-%m-%dT%H:%M:%fZ','now', ?)) newVisitors FROM first_seen JOIN active USING(visitor_id)`, start, start, start),
    rows(env, `SELECT date(occurred_at,'-6 hours') label, COUNT(DISTINCT visitor_id) value FROM analytics_events WHERE occurred_at >= strftime('%Y-%m-%dT%H:%M:%fZ','now', ?) GROUP BY label ORDER BY label`, start),
    rows(env, `SELECT strftime('%Y-%m',occurred_at) label, COUNT(DISTINCT visitor_id) value FROM analytics_events WHERE occurred_at >= strftime('%Y-%m-%dT%H:%M:%fZ','now','-12 months') GROUP BY label ORDER BY label`),
    rows(env, `SELECT COALESCE(json_extract(parameters_json,'$.community_name'),community_id,'Unknown') label, COUNT(*) value FROM analytics_events WHERE event_name='community_view' AND occurred_at >= strftime('%Y-%m-%dT%H:%M:%fZ','now', ?) GROUP BY label ORDER BY value DESC LIMIT 15`, start),
    rows(env, `SELECT json_extract(parameters_json,'$.search_term') label, COUNT(*) value FROM analytics_events WHERE event_name='search_performed' AND json_extract(parameters_json,'$.search_term')!='unmatched_query' AND occurred_at >= strftime('%Y-%m-%dT%H:%M:%fZ','now', ?) GROUP BY label ORDER BY value DESC LIMIT 15`, start),
    rows(env, `SELECT COALESCE(fiscal_year,'Unknown') label, COUNT(*) value FROM analytics_events WHERE fiscal_year IS NOT NULL AND occurred_at >= strftime('%Y-%m-%dT%H:%M:%fZ','now', ?) GROUP BY label ORDER BY value DESC LIMIT 15`, start),
    rows(env, `WITH entries AS (SELECT referrer,session_id,ROW_NUMBER() OVER(PARTITION BY session_id ORDER BY occurred_at,id) n FROM analytics_events WHERE event_name='page_view' AND occurred_at>=strftime('%Y-%m-%dT%H:%M:%fZ','now',?)) SELECT referrer label,COUNT(*) value FROM entries WHERE n=1 GROUP BY label ORDER BY value DESC LIMIT 12`, start),
    rows(env, `SELECT device_type label, COUNT(DISTINCT session_id) value FROM analytics_events WHERE occurred_at >= strftime('%Y-%m-%dT%H:%M:%fZ','now', ?) GROUP BY label ORDER BY value DESC`, start),
    rows(env, `SELECT browser label, COUNT(DISTINCT session_id) value FROM analytics_events WHERE occurred_at >= strftime('%Y-%m-%dT%H:%M:%fZ','now', ?) GROUP BY label ORDER BY value DESC`, start),
    rows(env, `SELECT country, province, COUNT(DISTINCT visitor_id) value FROM analytics_events WHERE occurred_at >= strftime('%Y-%m-%dT%H:%M:%fZ','now', ?) GROUP BY country,province ORDER BY value DESC LIMIT 30`, start),
    rows(env, `SELECT COALESCE(json_extract(parameters_json,'$.statement_type'),'Unknown') label, COUNT(*) value FROM analytics_events WHERE event_name='statement_downloaded' AND occurred_at >= strftime('%Y-%m-%dT%H:%M:%fZ','now', ?) GROUP BY label ORDER BY value DESC LIMIT 15`, start),
    rows(env, `WITH ranked AS (SELECT page,session_id,ROW_NUMBER() OVER(PARTITION BY session_id ORDER BY occurred_at) rank FROM analytics_events WHERE event_name='page_view' AND occurred_at >= strftime('%Y-%m-%dT%H:%M:%fZ','now', ?)) SELECT page label,COUNT(*) value FROM ranked WHERE rank=1 GROUP BY page ORDER BY value DESC LIMIT 15`, start),
    rows(env, `WITH ranked AS (SELECT page,session_id,ROW_NUMBER() OVER(PARTITION BY session_id ORDER BY occurred_at DESC) rank FROM analytics_events WHERE event_name='page_view' AND occurred_at >= strftime('%Y-%m-%dT%H:%M:%fZ','now', ?)) SELECT page label,COUNT(*) value FROM ranked WHERE rank=1 GROUP BY page ORDER BY value DESC LIMIT 15`, start),
    rows(env, `SELECT path label,COUNT(*) value FROM (SELECT session_id,GROUP_CONCAT(page,' → ') path FROM (SELECT session_id,page,occurred_at FROM analytics_events WHERE event_name='page_view' AND occurred_at >= strftime('%Y-%m-%dT%H:%M:%fZ','now', ?) ORDER BY session_id,occurred_at) GROUP BY session_id) GROUP BY path ORDER BY value DESC LIMIT 12`, start)
  ]);

  const previousStart = `-${rangeDays * 2} days`;
  const summarySql = `SELECT COUNT(DISTINCT visitor_id) visitors, COUNT(DISTINCT session_id) sessions,
    COALESCE(SUM(event_name='page_view'),0) pageViews,
    COUNT(DISTINCT CASE WHEN event_name IN ('statement_opened','statement_downloaded','citation_copied','profile_shared','job_application_clicked') THEN session_id END) outcomeSessions,
    COALESCE(SUM(event_name='search_no_results'),0) failedSearches,
    COALESCE(SUM(event_name='search_performed'),0) searches
    FROM analytics_events WHERE occurred_at >= strftime('%Y-%m-%dT%H:%M:%fZ','now',?) AND occurred_at < strftime('%Y-%m-%dT%H:%M:%fZ','now',?)`;
  const [current, previous, outcomes, errors, collection, campaigns, engagement, searchPages] = await Promise.all([
    first(env, summarySql, start, '0 days'), first(env, summarySql, previousStart, start),
    rows(env, `SELECT event_name label,COUNT(DISTINCT session_id) value FROM analytics_events WHERE event_name IN ('search_performed','community_view','statement_opened','statement_downloaded','citation_copied','profile_shared','job_application_clicked') AND occurred_at>=strftime('%Y-%m-%dT%H:%M:%fZ','now',?) GROUP BY event_name ORDER BY value DESC`,start),
    rows(env, `SELECT event_name label, COUNT(*) value FROM analytics_events WHERE event_name IN ('search_no_results','pdf_failed_to_load','parser_error') AND occurred_at>=strftime('%Y-%m-%dT%H:%M:%fZ','now',?) GROUP BY event_name ORDER BY value DESC`,start),
    first(env, `SELECT MAX(received_at) lastReceivedAt,MIN(occurred_at) firstEventAt,COUNT(*) eventsLast24Hours,COUNT(DISTINCT CASE WHEN json_extract(parameters_json,'$.tracking_version')=2 THEN session_id END) version2Sessions FROM analytics_events WHERE occurred_at>=strftime('%Y-%m-%dT%H:%M:%fZ','now','-1 day')`),
    rows(env, `WITH entries AS (SELECT session_id,parameters_json,referrer,ROW_NUMBER() OVER(PARTITION BY session_id ORDER BY occurred_at,id) n FROM analytics_events WHERE event_name='page_view' AND occurred_at>=strftime('%Y-%m-%dT%H:%M:%fZ','now',?)) SELECT COALESCE(json_extract(parameters_json,'$.utm_source'),referrer) source,COALESCE(json_extract(parameters_json,'$.utm_medium'),'unattributed') medium,COALESCE(json_extract(parameters_json,'$.utm_campaign'),'none') campaign,COUNT(*) sessions FROM entries WHERE n=1 GROUP BY source,medium,campaign ORDER BY sessions DESC LIMIT 30`,start),
    first(env, `WITH s AS (SELECT session_id,SUM(event_name='page_view') pages,SUM(CASE WHEN event_name='engagement' THEN MIN(60,MAX(0,CAST(json_extract(parameters_json,'$.duration_seconds') AS REAL))) ELSE 0 END) activeSeconds,MAX(event_name IN ('statement_opened','statement_downloaded','citation_copied','profile_shared','job_application_clicked')) outcome FROM analytics_events WHERE occurred_at>=strftime('%Y-%m-%dT%H:%M:%fZ','now',?) AND json_extract(parameters_json,'$.tracking_version')=2 GROUP BY session_id) SELECT COUNT(*) measuredSessions,SUM(activeSeconds>=10 OR pages>=2 OR outcome=1) engagedSessions,ROUND(AVG(activeSeconds),1) averageActiveSeconds FROM s`,start),
    rows(env, `SELECT page, SUM(event_name='search_performed') searches, SUM(event_name='search_no_results') failures FROM analytics_events WHERE event_name IN ('search_performed','search_no_results') AND occurred_at>=strftime('%Y-%m-%dT%H:%M:%fZ','now',?) GROUP BY page ORDER BY failures DESC LIMIT 20`,start)
  ]);
  const growth = {current,previous,outcomes,errors,collection,campaigns,engagement,searchPages};
  return json({generatedAt: new Date().toISOString(), rangeDays, timezone: "America/Regina", growth, today: {...today, ...sessions}, period: {...period, ...returning}, charts: {daily, monthly, communities, searches, fiscalYears, sources, devices, browsers, geography, visitors: [{label: "Returning", value: Number((returning as Record<string, unknown>).returningVisitors || 0)}, {label: "New", value: Number((returning as Record<string, unknown>).newVisitors || 0)}]}, rankings: {communities, searches, downloads, landingPages, exitPages}, journeys}, 200, headers);
}

async function handle(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  if (request.method === "OPTIONS") return new Response(null, {status: 204, headers: corsHeaders(request, env)});
  if (url.pathname === "/v1/events" && request.method === "POST") return ingest(request, env);
  if (url.pathname === "/v1/dashboard" && request.method === "GET") return dashboard(request, env);
  if (url.pathname === "/v1/intelligence" && request.method === "GET") return intelligence(request, env);
  if (url.pathname === "/health") return json({status: "ok"}, 200, corsHeaders(request, env));
  return json({error: "not_found"}, 404);
}

export default {
  fetch: handle,
  async scheduled(_controller: unknown, env: Env, context: ExecutionContext) {
    const retention = Math.min(1095, Math.max(30, Number(env.DATA_RETENTION_DAYS) || 760));
    context.waitUntil(env.DB.prepare(`DELETE FROM analytics_events WHERE occurred_at < strftime('%Y-%m-%dT%H:%M:%fZ','now', ?)`).bind(`-${retention} days`).run());
  }
};
