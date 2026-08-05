type AnalyticsEventName =
  | "page_view"
  | "session_end"
  | "search_performed"
  | "search_no_results"
  | "community_view"
  | "statement_opened"
  | "statement_downloaded"
  | "community_capital_view"
  | "revenue_chart_viewed"
  | "expense_chart_viewed"
  | "asset_chart_viewed"
  | "comparison_started"
  | "comparison_completed"
  | "news_article_opened"
  | "news_article_shared"
  | "outbound_link_clicked"
  | "pdf_failed_to_load"
  | "parser_error";

type AnalyticsValue = string | number | boolean | null;
type AnalyticsParameters = Record<string, AnalyticsValue>;

interface AnalyticsConfig {
  enabled: boolean;
  gaMeasurementId: string;
  apiEndpoint: string;
  productionHosts: string[];
  debug: boolean;
}

interface QueuedAnalyticsEvent {
  timestamp: string;
  page: string;
  event: AnalyticsEventName;
  community_id: string | null;
  fiscal_year: string | null;
  session_id: string;
  visitor_id: string;
  device_type: "mobile" | "tablet" | "desktop";
  browser: string;
  referrer: string;
  parameters: AnalyticsParameters;
}

interface OpenBandAnalyticsService {
  trackPageView(page?: string): void;
  trackSearch(searchTerm: string, resultCount: number): void;
  trackCommunityView(communityName: string, province: string, fiscalYear?: string | null, communityId?: string | number | null): void;
  trackStatementOpen(statementType: string, fiscalYear?: string | null, communityId?: string | number | null): void;
  trackDownload(statementType: string, fiscalYear?: string | null, communityId?: string | number | null): void;
  trackCommunityCapitalView(communityId?: string | number | null, fiscalYear?: string | null): void;
  trackChartView(chart: "revenue" | "expense" | "asset", communityId?: string | number | null, fiscalYear?: string | null): void;
  trackComparison(completed: boolean, communityIds?: Array<string | number>): void;
  trackNewsView(articleUrl: string, communityId?: string | number | null): void;
  trackNewsShare(articleUrl: string, communityId?: string | number | null): void;
  trackOutboundLink(destination: string): void;
  trackError(errorType: "pdf_failed_to_load" | "parser_error" | "search_no_results", details?: AnalyticsParameters): void;
  flush(useBeacon?: boolean): Promise<void>;
}

declare global {
  interface Window {
    OPENBAND_ANALYTICS_CONFIG?: Partial<AnalyticsConfig>;
    OpenBandAnalytics?: OpenBandAnalyticsService;
    dataLayer?: unknown[];
    gtag?: (...args: unknown[]) => void;
    doNotTrack?: string;
    requestIdleCallback(callback: () => void, options?: {timeout: number}): number;
  }
}

const Analytics = (() : OpenBandAnalyticsService => {
  const defaults: AnalyticsConfig = {
    enabled: false,
    gaMeasurementId: "",
    apiEndpoint: "",
    productionHosts: ["openband.ca", "www.openband.ca"],
    debug: false
  };
  const config: AnalyticsConfig = {...defaults, ...(window.OPENBAND_ANALYTICS_CONFIG || {})};
  const production = config.productionHosts.includes(location.hostname);
  const permitted = config.enabled && production && navigator.doNotTrack !== "1" && window.doNotTrack !== "1";
  const queue: QueuedAnalyticsEvent[] = [];
  const viewed = new Set<string>();
  let flushTimer = 0;
  let retryDelay = 2000;
  let gaLoaded = false;
  let gaPrepared = false;
  let lastPage = "";

  const log = (...values: unknown[]) => {
    if (config.debug || !production) console.debug("[OpenBand analytics]", ...values);
  };

  const randomId = () => crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  const sessionId = permitted ? (() => {
    const existing = sessionStorage.getItem("openband_session_id");
    if (existing) return existing;
    const next = randomId();
    sessionStorage.setItem("openband_session_id", next);
    return next;
  })() : "";
  const visitorId = permitted ? (() => {
    const key = "openband_visitor_v1";
    try {
      const stored = JSON.parse(localStorage.getItem(key) || "null") as {id?: string; created?: number} | null;
      if (stored?.id && stored.created && Date.now() - stored.created < 15552000000) return stored.id;
      const next = {id: randomId(), created: Date.now()};
      localStorage.setItem(key, JSON.stringify(next));
      return next.id;
    } catch {
      return randomId();
    }
  })() : "";

  const pagePath = () => `${location.pathname}${location.search}`.slice(0, 300);
  const cleanReferrer = () => {
    if (!document.referrer) return "direct";
    try {
      const url = new URL(document.referrer);
      return `${url.origin}${url.pathname}`.slice(0, 300);
    } catch {
      return "unknown";
    }
  };
  const cleanDestination = (value: string) => {
    try {
      const url = new URL(value, location.origin);
      return `${url.origin}${url.pathname}`.slice(0, 300);
    } catch {
      return "unknown";
    }
  };
  const deviceType = (): "mobile" | "tablet" | "desktop" => {
    if (/ipad|tablet/i.test(navigator.userAgent)) return "tablet";
    if (/mobile|iphone|android/i.test(navigator.userAgent)) return "mobile";
    return "desktop";
  };
  const browserName = () => {
    const ua = navigator.userAgent;
    if (/Edg\//.test(ua)) return "Edge";
    if (/OPR\//.test(ua)) return "Opera";
    if (/Firefox\//.test(ua)) return "Firefox";
    if (/Chrome\//.test(ua)) return "Chrome";
    if (/Safari\//.test(ua)) return "Safari";
    return "Other";
  };

  const prepareGa = () => {
    if (!permitted || gaPrepared || !/^G-[A-Z0-9]+$/.test(config.gaMeasurementId)) return;
    gaPrepared = true;
    window.dataLayer = window.dataLayer || [];
    window.gtag = (...args: unknown[]) => { window.dataLayer?.push(args); };
    window.gtag("js", new Date());
    window.gtag("config", config.gaMeasurementId, {send_page_view: false, anonymize_ip: true});
  };

  const loadGa = () => {
    prepareGa();
    if (!gaPrepared || gaLoaded) return;
    gaLoaded = true;
    const script = document.createElement("script");
    script.async = true;
    script.src = `https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(config.gaMeasurementId)}`;
    document.head.appendChild(script);
  };

  const scheduleGa = () => {
    if ("requestIdleCallback" in window) window.requestIdleCallback(loadGa, {timeout: 2500});
    else window.setTimeout(loadGa, 1200);
  };

  const sanitizeParameters = (parameters: AnalyticsParameters = {}) => Object.fromEntries(
    Object.entries(parameters)
      .slice(0, 20)
      .map(([key, value]) => [key.slice(0, 40), typeof value === "string" ? value.slice(0, 200) : value])
  );

  const persistQueue = () => {
    try { localStorage.setItem("openband_analytics_queue", JSON.stringify(queue.slice(-100))); } catch { /* best effort */ }
  };

  const enqueue = (
    event: AnalyticsEventName,
    parameters: AnalyticsParameters = {},
    communityId: string | number | null = null,
    fiscalYear: string | null = null
  ) => {
    if (!permitted) { log(event, parameters); return; }
    prepareGa();
    scheduleGa();
    const clean = sanitizeParameters(parameters);
    window.gtag?.("event", event, clean);
    if (!config.apiEndpoint) return;
    queue.push({
      timestamp: new Date().toISOString(),
      page: pagePath(),
      event,
      community_id: communityId == null ? null : String(communityId).slice(0, 32),
      fiscal_year: fiscalYear ? String(fiscalYear).slice(0, 16) : null,
      session_id: sessionId,
      visitor_id: visitorId,
      device_type: deviceType(),
      browser: browserName(),
      referrer: cleanReferrer(),
      parameters: clean
    });
    persistQueue();
    if (queue.length >= 10) void flush();
    else if (!flushTimer) flushTimer = window.setTimeout(() => void flush(), 5000);
  };

  const flush = async (useBeacon = false) => {
    if (!permitted || !config.apiEndpoint || !queue.length) return;
    if (flushTimer) window.clearTimeout(flushTimer);
    flushTimer = 0;
    const batch = queue.splice(0, 25);
    const body = JSON.stringify({events: batch});
    try {
      if (useBeacon && navigator.sendBeacon) {
        const sent = navigator.sendBeacon(config.apiEndpoint, new Blob([body], {type: "text/plain;charset=UTF-8"}));
        if (!sent) throw new Error("Beacon queue full");
      } else {
        const response = await fetch(config.apiEndpoint, {method: "POST", headers: {"Content-Type": "application/json"}, body, keepalive: true, credentials: "omit"});
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
      }
      retryDelay = 2000;
      persistQueue();
      if (queue.length) flushTimer = window.setTimeout(() => void flush(), 250);
    } catch (error) {
      queue.unshift(...batch);
      persistQueue();
      log("submission failed", error);
      flushTimer = window.setTimeout(() => void flush(), retryDelay);
      retryDelay = Math.min(retryDelay * 2, 60000);
    }
  };

  const once = (key: string, callback: () => void) => {
    if (viewed.has(key)) return;
    viewed.add(key);
    callback();
  };

  const service: OpenBandAnalyticsService = {
    trackPageView(page = pagePath()) {
      if (page === lastPage) return;
      lastPage = page;
      enqueue("page_view", {page_location: `${location.origin}${page}`, page_title: document.title});
    },
    trackSearch(searchTerm, resultCount) {
      const safeTerm = resultCount > 0 ? searchTerm.slice(0, 100) : "unmatched_query";
      enqueue("search_performed", {search_term: safeTerm, result_count: resultCount});
      if (!resultCount) enqueue("search_no_results", {result_count: 0});
    },
    trackCommunityView(communityName, province, fiscalYear = null, communityId = null) {
      once(`community:${communityId}:${fiscalYear}`, () => enqueue("community_view", {community_name: communityName, province, fiscal_year: fiscalYear}, communityId, fiscalYear));
    },
    trackStatementOpen(statementType, fiscalYear = null, communityId = null) {
      enqueue("statement_opened", {statement_type: statementType, fiscal_year: fiscalYear}, communityId, fiscalYear);
    },
    trackDownload(statementType, fiscalYear = null, communityId = null) {
      enqueue("statement_downloaded", {statement_type: statementType, fiscal_year: fiscalYear}, communityId, fiscalYear);
    },
    trackCommunityCapitalView(communityId = null, fiscalYear = null) {
      once(`capital:${communityId}:${fiscalYear}`, () => enqueue("community_capital_view", {}, communityId, fiscalYear));
    },
    trackChartView(chart, communityId = null, fiscalYear = null) {
      once(`chart:${chart}:${communityId}:${fiscalYear}`, () => enqueue(`${chart}_chart_viewed` as AnalyticsEventName, {}, communityId, fiscalYear));
    },
    trackComparison(completed, communityIds = []) {
      enqueue(completed ? "comparison_completed" : "comparison_started", {community_count: communityIds.length});
    },
    trackNewsView(articleUrl, communityId = null) {
      enqueue("news_article_opened", {destination: cleanDestination(articleUrl)}, communityId);
    },
    trackNewsShare(articleUrl, communityId = null) {
      enqueue("news_article_shared", {destination: cleanDestination(articleUrl)}, communityId);
    },
    trackOutboundLink(destination) {
      enqueue("outbound_link_clicked", {destination: cleanDestination(destination)});
    },
    trackError(errorType, details = {}) {
      enqueue(errorType, details);
    },
    flush
  };

  const restorePending = () => {
    if (!permitted) return;
    try {
      const pending = JSON.parse(localStorage.getItem("openband_analytics_queue") || "[]") as QueuedAnalyticsEvent[];
      queue.push(...pending.slice(-100));
    } catch { /* ignore invalid local data */ }
  };

  const observeCharts = () => {
    if (!("IntersectionObserver" in window)) return;
    const observer = new IntersectionObserver(entries => entries.forEach(entry => {
      if (!entry.isIntersecting) return;
      const node = entry.target as HTMLElement;
      const bandId = document.getElementById("results")?.dataset.bandId || null;
      const year = new URLSearchParams(location.search).get("year");
      const chart = node.dataset.analyticsChart as "revenue" | "expense" | "asset";
      service.trackChartView(chart, bandId, year);
      observer.unobserve(node);
    }), {threshold: 0.35});
    document.querySelectorAll<HTMLElement>("[data-analytics-chart]").forEach(node => observer.observe(node));
  };

  const bindGlobalInteractions = () => {
    document.addEventListener("click", event => {
      const link = (event.target as Element | null)?.closest<HTMLAnchorElement>("a[href]");
      if (!link) return;
      const destination = link.href;
      const bandId = document.getElementById("results")?.dataset.bandId || null;
      const fiscalYear = new URLSearchParams(location.search).get("year");
      if (link.matches(".news-card a,.profile-news-item")) service.trackNewsView(destination, bandId);
      if (/DisplayBinaryData\.aspx/i.test(destination)) {
        const statementType = /audited/i.test(destination) ? "audited_financial_statement" : "remuneration_schedule";
        service.trackStatementOpen(statementType, fiscalYear, bandId);
        if (link.hasAttribute("download") || link.dataset.analyticsDownload === "true") service.trackDownload(statementType, fiscalYear, bandId);
      }
      if (destination.startsWith("http") && new URL(destination).origin !== location.origin) service.trackOutboundLink(destination);
    }, {capture: true});
    document.addEventListener("openband:charts-rendered", observeCharts);
  };

  const bindRoutes = () => {
    const notify = () => queueMicrotask(() => service.trackPageView());
    for (const method of ["pushState", "replaceState"] as const) {
      const original = history[method].bind(history);
      history[method] = ((...args: Parameters<History[typeof method]>) => {
        const result = original(...args);
        notify();
        return result;
      }) as History[typeof method];
    }
    addEventListener("popstate", notify);
  };

  if (permitted) {
    restorePending();
    bindRoutes();
    bindGlobalInteractions();
    prepareGa();
    scheduleGa();
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", () => service.trackPageView(), {once: true});
    else service.trackPageView();
    addEventListener("pagehide", () => {
      enqueue("session_end", {duration_seconds: Math.round(performance.now() / 1000)});
      void flush(true);
    });
  } else {
    log("disabled", {production, enabled: config.enabled, doNotTrack: navigator.doNotTrack});
  }

  return service;
})();

window.OpenBandAnalytics = Analytics;

export {};
