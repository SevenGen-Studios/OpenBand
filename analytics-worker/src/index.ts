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
  "page_view", "session_end", "search_performed", "search_no_results",
  "community_view", "statement_opened", "statement_downloaded",
  "community_capital_view", "revenue_chart_viewed", "expense_chart_viewed",
  "asset_chart_viewed", "comparison_started", "comparison_completed",
  "news_article_opened", "news_article_shared", "outbound_link_clicked",
  "jobs_tab_viewed", "job_search_performed", "job_filter_used",
  "job_posting_opened", "job_application_clicked",
  "pdf_failed_to_load", "parser_error"
]);
const PARAMETER_KEYS = new Set([
  "page_location", "page_title", "search_term", "result_count",
  "community_name", "province", "fiscal_year", "statement_type",
  "community_count", "destination", "duration_seconds", "error_code",
  "filter", "value", "job_id"
]);
const ID_PATTERN = /^[a-zA-Z0-9-]{8,80}$/;

const json = (value: unknown, status = 200, headers: HeadersInit = {}) => new Response(
  JSON.stringify(value),
  {status, headers: {"Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store", ...headers}}
);

const allowedOrigins = (env: Env) => new Set((env.ALLOWED_ORIGINS || "https://openband.ca").split(",").map(value => value.trim()).filter(Boolean));
const corsHeaders = (request: Request, env: Env) => {
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
    return `${url.pathname}${url.search}`.slice(0, 300);
  } catch {
    return "/";
  }
};
const safeReferrer = (value: unknown) => {
  const text = safeText(value, 300);
  if (["direct", "unknown"].includes(text)) return text;
  try {
    const url = new URL(text);
    return `${url.origin}${url.pathname}`.slice(0, 300);
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
    result[key] = clean;
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
  try { body = await request.json() as {events?: IncomingEvent[]}; }
  catch { return json({error: "invalid_json"}, 400, headers); }
  if (!Array.isArray(body.events) || !body.events.length || body.events.length > 25) return json({error: "invalid_batch"}, 400, headers);

  const cf = (request as Request & {cf?: {country?: string; region?: string}}).cf || {};
  const country = safeText(cf.country, 8) || "Unknown";
  const province = safeText(cf.region, 80) || "Unknown";
  const statements: D1PreparedStatement[] = [];
  let accepted = 0;
  for (const candidate of body.events) {
    const eventName = safeText(candidate.event, 50);
    const sessionId = safeText(candidate.session_id, 80);
    const visitorId = safeText(candidate.visitor_id, 80);
    if (!EVENT_NAMES.has(eventName) || !ID_PATTERN.test(sessionId) || !ID_PATTERN.test(visitorId)) continue;
    const device = ["mobile", "tablet", "desktop"].includes(String(candidate.device_type)) ? String(candidate.device_type) : "unknown";
    const browser = ["Chrome", "Safari", "Firefox", "Edge", "Opera", "Other"].includes(String(candidate.browser)) ? String(candidate.browser) : "Other";
    const parameters = safeParameters(candidate.parameters);
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
const rows = async <T = Record<string, unknown>>(env: Env, sql: string, ...bindings: unknown[]) =>
  (await env.DB.prepare(sql).bind(...bindings).all<T>()).results || [];
const first = async <T = Record<string, unknown>>(env: Env, sql: string, ...bindings: unknown[]) =>
  (await rows<T>(env, sql, ...bindings))[0] || {} as T;

async function dashboard(request: Request, env: Env): Promise<Response> {
  const headers = corsHeaders(request, env);
  if (!authorize(request, env)) return json({error: "unauthorized"}, 401, {...headers, "WWW-Authenticate": "Bearer"});
  const url = new URL(request.url);
  const rangeDays = Math.min(365, Math.max(7, Number(url.searchParams.get("days")) || 30));
  const start = `-${rangeDays} days`;

  const [today, sessions, period, returning, daily, monthly, communities, searches, fiscalYears, sources, devices, browsers, geography, downloads, landingPages, exitPages, journeys] = await Promise.all([
    first(env, `SELECT COUNT(DISTINCT visitor_id) activeUsers, COUNT(DISTINCT session_id) totalVisits, SUM(event_name='page_view') pageViews FROM analytics_events WHERE occurred_at >= date('now')`),
    first(env, `WITH s AS (SELECT session_id, SUM(event_name='page_view') pages, MAX(CASE WHEN event_name='session_end' THEN CAST(json_extract(parameters_json,'$.duration_seconds') AS REAL) END) duration, (julianday(MAX(occurred_at))-julianday(MIN(occurred_at)))*86400 span FROM analytics_events WHERE occurred_at >= date('now') GROUP BY session_id) SELECT ROUND(AVG(COALESCE(duration,span)),1) averageSessionDuration, ROUND(100.0*SUM(pages<=1)/NULLIF(COUNT(*),0),1) bounceRate FROM s`),
    first(env, `SELECT COUNT(DISTINCT visitor_id) uniqueVisitors, SUM(event_name='search_performed') totalSearches, SUM(event_name='community_view') totalCommunityViews, SUM(event_name='statement_opened') totalPdfOpens, SUM(event_name='statement_downloaded') totalDownloads FROM analytics_events WHERE occurred_at >= datetime('now', ?)` , start),
    first(env, `WITH first_seen AS (SELECT visitor_id, MIN(occurred_at) firstAt FROM analytics_events GROUP BY visitor_id), active AS (SELECT DISTINCT visitor_id FROM analytics_events WHERE occurred_at >= datetime('now', ?)) SELECT SUM(firstAt < datetime('now', ?)) returningVisitors, SUM(firstAt >= datetime('now', ?)) newVisitors FROM first_seen JOIN active USING(visitor_id)`, start, start, start),
    rows(env, `SELECT date(occurred_at) label, COUNT(DISTINCT visitor_id) value FROM analytics_events WHERE occurred_at >= datetime('now', ?) GROUP BY label ORDER BY label`, start),
    rows(env, `SELECT strftime('%Y-%m',occurred_at) label, COUNT(DISTINCT visitor_id) value FROM analytics_events WHERE occurred_at >= datetime('now','-12 months') GROUP BY label ORDER BY label`),
    rows(env, `SELECT COALESCE(json_extract(parameters_json,'$.community_name'),community_id,'Unknown') label, COUNT(*) value FROM analytics_events WHERE event_name='community_view' AND occurred_at >= datetime('now', ?) GROUP BY label ORDER BY value DESC LIMIT 15`, start),
    rows(env, `SELECT json_extract(parameters_json,'$.search_term') label, COUNT(*) value FROM analytics_events WHERE event_name='search_performed' AND json_extract(parameters_json,'$.search_term')!='unmatched_query' AND occurred_at >= datetime('now', ?) GROUP BY label ORDER BY value DESC LIMIT 15`, start),
    rows(env, `SELECT COALESCE(fiscal_year,'Unknown') label, COUNT(*) value FROM analytics_events WHERE fiscal_year IS NOT NULL AND occurred_at >= datetime('now', ?) GROUP BY label ORDER BY value DESC LIMIT 15`, start),
    rows(env, `SELECT referrer label, COUNT(DISTINCT session_id) value FROM analytics_events WHERE event_name='page_view' AND occurred_at >= datetime('now', ?) GROUP BY label ORDER BY value DESC LIMIT 12`, start),
    rows(env, `SELECT device_type label, COUNT(DISTINCT session_id) value FROM analytics_events WHERE occurred_at >= datetime('now', ?) GROUP BY label ORDER BY value DESC`, start),
    rows(env, `SELECT browser label, COUNT(DISTINCT session_id) value FROM analytics_events WHERE occurred_at >= datetime('now', ?) GROUP BY label ORDER BY value DESC`, start),
    rows(env, `SELECT country, province, COUNT(DISTINCT visitor_id) value FROM analytics_events WHERE occurred_at >= datetime('now', ?) GROUP BY country,province ORDER BY value DESC LIMIT 30`, start),
    rows(env, `SELECT COALESCE(json_extract(parameters_json,'$.statement_type'),'Unknown') label, COUNT(*) value FROM analytics_events WHERE event_name='statement_downloaded' AND occurred_at >= datetime('now', ?) GROUP BY label ORDER BY value DESC LIMIT 15`, start),
    rows(env, `WITH ranked AS (SELECT page,session_id,ROW_NUMBER() OVER(PARTITION BY session_id ORDER BY occurred_at) rank FROM analytics_events WHERE event_name='page_view' AND occurred_at >= datetime('now', ?)) SELECT page label,COUNT(*) value FROM ranked WHERE rank=1 GROUP BY page ORDER BY value DESC LIMIT 15`, start),
    rows(env, `WITH ranked AS (SELECT page,session_id,ROW_NUMBER() OVER(PARTITION BY session_id ORDER BY occurred_at DESC) rank FROM analytics_events WHERE event_name='page_view' AND occurred_at >= datetime('now', ?)) SELECT page label,COUNT(*) value FROM ranked WHERE rank=1 GROUP BY page ORDER BY value DESC LIMIT 15`, start),
    rows(env, `SELECT path label,COUNT(*) value FROM (SELECT session_id,GROUP_CONCAT(page,' → ') path FROM (SELECT session_id,page,occurred_at FROM analytics_events WHERE event_name='page_view' AND occurred_at >= datetime('now', ?) ORDER BY session_id,occurred_at) GROUP BY session_id) GROUP BY path ORDER BY value DESC LIMIT 12`, start)
  ]);

  return json({generatedAt: new Date().toISOString(), rangeDays, today: {...today, ...sessions}, period: {...period, ...returning}, charts: {daily, monthly, communities, searches, fiscalYears, sources, devices, browsers, geography, visitors: [{label: "Returning", value: Number((returning as Record<string, unknown>).returningVisitors || 0)}, {label: "New", value: Number((returning as Record<string, unknown>).newVisitors || 0)}]}, rankings: {communities, searches, downloads, landingPages, exitPages}, journeys}, 200, headers);
}

async function handle(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  if (request.method === "OPTIONS") return new Response(null, {status: 204, headers: corsHeaders(request, env)});
  if (url.pathname === "/v1/events" && request.method === "POST") return ingest(request, env);
  if (url.pathname === "/v1/dashboard" && request.method === "GET") return dashboard(request, env);
  if (url.pathname === "/health") return json({status: "ok"});
  return json({error: "not_found"}, 404);
}

export default {
  fetch: handle,
  async scheduled(_controller: unknown, env: Env, context: ExecutionContext) {
    const retention = Math.min(1095, Math.max(30, Number(env.DATA_RETENTION_DAYS) || 760));
    context.waitUntil(env.DB.prepare(`DELETE FROM analytics_events WHERE occurred_at < datetime('now', ?)`).bind(`-${retention} days`).run());
  }
};
