import type {Env} from "./index";

export interface CreatorSupportEnv {
  CREATOR_SUPPORT_ENABLED?: string;
  STRIPE_SECRET_KEY?: string;
  STRIPE_WEBHOOK_SECRET?: string;
  CREATOR_SUPPORT_RATE_LIMIT?: {limit(input: {key: string}): Promise<{success: boolean}>};
}

type Json = (value: unknown, status?: number) => Response;
const presets = new Set([500, 1000, 2500, 5000, 10000]);
const minCents = 200;
const maxCents = 99999999;
const purpose = "openband_creator_support";
const sessionPattern = /^cs_(test|live)_[a-zA-Z0-9]{1,200}$/;
const intentPattern = /^pi_[a-zA-Z0-9]+$/;
const refundPattern = /^re_[a-zA-Z0-9]+$/;
const attemptPattern = /^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/;
const validCents = (value: unknown): value is number =>
  typeof value === "number" && Number.isInteger(value) && value >= minCents && value <= maxCents;

export function donationCents(body: {presetCents?: unknown; customAmount?: unknown} | null): number | null {
  if (!body) return null;
  if (body.customAmount === undefined) {
    return typeof body.presetCents === "number" && presets.has(body.presetCents) ? body.presetCents : null;
  }
  if (body.presetCents !== undefined || typeof body.customAmount !== "string" || body.customAmount.length > 12) return null;
  const match = /^(\d{1,6})(?:[.,](\d{1,2}))?$/.exec(body.customAmount.trim());
  if (!match) return null;
  const cents = Number(match[1]) * 100 + Number((match[2] || "").padEnd(2, "0"));
  return validCents(cents) ? cents : null;
}

function stripeMode(env: Env) {
  const match = /^(?:sk|rk)_(test|live)_[a-zA-Z0-9_]+$/.exec(env.STRIPE_SECRET_KEY || "");
  return match?.[1] as "test" | "live" | undefined;
}

function acceptingDonations(env: Env) {
  return env.CREATOR_SUPPORT_ENABLED === "true" && Boolean(
    stripeMode(env) && env.STRIPE_WEBHOOK_SECRET?.startsWith("whsec_") && env.CREATOR_SUPPORT_RATE_LIMIT
  );
}

async function readBody(request: Request, maxBytes: number): Promise<Uint8Array | null> {
  if (!request.body || Number(request.headers.get("Content-Length")) > maxBytes) return null;
  const reader = request.body.getReader();
  const body = new Uint8Array(maxBytes);
  let length = 0;
  for (;;) {
    const {value, done} = await reader.read();
    if (done) return body.subarray(0, length);
    if (length + value.length > maxBytes) {
      await reader.cancel();
      return null;
    }
    body.set(value, length);
    length += value.length;
  }
}

async function verifySignature(body: Uint8Array, signature: string, secret: string) {
  if (signature.length > 2048) return false;
  const parts = signature.split(",");
  const timestamp = parts.find(part => /^t=\d+$/.test(part))?.slice(2);
  if (!timestamp || Math.abs(Date.now() / 1000 - Number(timestamp)) > 300) return false;
  const encoder = new TextEncoder();
  const prefix = encoder.encode(timestamp + ".");
  const signed = new Uint8Array(prefix.length + body.length);
  signed.set(prefix);
  signed.set(body, prefix.length);
  const key = await crypto.subtle.importKey("raw", encoder.encode(secret), {name: "HMAC", hash: "SHA-256"}, false, ["verify"]);
  for (const part of parts) {
    if (!/^v1=[a-f0-9]{64}$/.test(part)) continue;
    const bytes = Uint8Array.from(part.slice(3).match(/../g)!, hex => parseInt(hex, 16));
    if (await crypto.subtle.verify("HMAC", key, bytes, signed)) return true;
  }
  return false;
}

async function stripe<T>(env: Env, path: string, form?: URLSearchParams, attempt?: string): Promise<T> {
  const headers = new Headers({
    Authorization: `Bearer ${env.STRIPE_SECRET_KEY}`,
    "Stripe-Version": "2025-06-30.basil"
  });
  if (attempt) headers.set("Idempotency-Key", `openband-support-${attempt}`);
  const response = await fetch(`https://api.stripe.com/v1/${path}`, {
    method: form ? "POST" : "GET", headers, body: form, signal: AbortSignal.timeout(10000)
  });
  if (!response.ok) throw new Error("stripe_request_failed");
  return await response.json() as T;
}

async function beginCheckout(
  env: Env, body: {attempt?: unknown; presetCents?: unknown; customAmount?: unknown}, origin: string, json: Json
) {
  const cents = donationCents(body);
  if (cents === null) return json({error: "invalid_amount"}, 400);
  if (typeof body.attempt !== "string" || !attemptPattern.test(body.attempt)) return json({error: "invalid_attempt"}, 400);
  // Check the migration before creating an external Checkout Session.
  await env.DB.prepare("SELECT session_id FROM creator_donations LIMIT 1").all();
  const form = new URLSearchParams({
    mode: "payment",
    "payment_method_types[0]": "card",
    "adaptive_pricing[enabled]": "false",
    "line_items[0][price_data][currency]": "cad",
    "line_items[0][price_data][unit_amount]": String(cents),
    "line_items[0][price_data][product_data][name]": "Support the Creators of OpenBand",
    "line_items[0][quantity]": "1",
    "metadata[purpose]": purpose,
    "payment_intent_data[metadata][purpose]": purpose,
    success_url: `${origin}/support/thanks/?session_id={CHECKOUT_SESSION_ID}`,
    cancel_url: `${origin}/support/?cancelled=1`
  });
  const session = await stripe<{id: string; url: string; created: number}>(env, "checkout/sessions", form, body.attempt);
  const url = new URL(session.url);
  if (sessionPattern.exec(session.id)?.[1] !== stripeMode(env) ||
      url.origin !== "https://checkout.stripe.com" || !Number.isInteger(session.created)) {
    throw new Error("invalid_checkout_session");
  }
  await env.DB.prepare(`
    INSERT INTO creator_donations (session_id, livemode, amount_cents, created_at)
    VALUES (?, ?, ?, ?) ON CONFLICT(session_id) DO NOTHING
  `).bind(session.id, Number(stripeMode(env) === "live"), cents, session.created).run();
  return json({url: url.href});
}

interface StripeEvent {
  type: string;
  created: number;
  livemode: boolean;
  data?: {object?: {
    id: string; mode?: string; currency?: string; amount_total?: number; payment_status?: string;
    payment_intent?: string | null; metadata?: {purpose?: string};
  }};
}

async function updateDonation(env: Env, event: StripeEvent) {
  const session = event.data?.object;
  if (!session || !sessionPattern.test(session.id) || session.metadata?.purpose !== purpose ||
      session.mode !== "payment" || session.currency !== "cad" || !validCents(session.amount_total)) return;
  if (event.type === "checkout.session.completed" || event.type === "checkout.session.async_payment_succeeded") {
    if (session.payment_status !== "paid" || !session.payment_intent || !intentPattern.test(session.payment_intent)) return;
    const {results} = await env.DB.prepare(`
      UPDATE creator_donations SET status = 'paid', paid_at = COALESCE(paid_at, ?), payment_intent = ?
      WHERE session_id = ? AND livemode = ? AND amount_cents = ?
        AND (payment_intent IS NULL OR payment_intent = ?)
      RETURNING session_id
    `).bind(event.created, session.payment_intent, session.id, Number(event.livemode), session.amount_total,
      session.payment_intent).all();
    if (!results?.length) throw new Error("checkout_does_not_match_donation");
    return;
  }
  const status = event.type === "checkout.session.expired" ? "expired" : "failed";
  await env.DB.prepare(`
    UPDATE creator_donations SET status = ?, payment_intent = COALESCE(?, payment_intent)
    WHERE session_id = ? AND livemode = ? AND amount_cents = ? AND status = 'pending'
  `).bind(status, intentPattern.test(session.payment_intent || "") ? session.payment_intent : null,
    session.id, Number(event.livemode), session.amount_total).run();
}

interface StripeRefund {
  id: string;
  amount: number;
  currency: string;
  status: string;
  payment_intent: {id: string; livemode: boolean; metadata?: {purpose?: string}} | null;
}

async function updateRefund(env: Env, event: StripeEvent) {
  const id = event.data?.object?.id || "";
  if (!refundPattern.test(id)) return;
  // Read the current status since Stripe can deliver events out of order.
  const refund = await stripe<StripeRefund>(env, `refunds/${id}?expand[]=payment_intent`);
  const intent = refund.payment_intent;
  if (!intent || !intentPattern.test(intent.id) || intent.metadata?.purpose !== purpose ||
      intent.livemode !== event.livemode || refund.currency !== "cad" ||
      !Number.isInteger(refund.amount) || refund.amount <= 0 ||
      !["pending", "requires_action", "succeeded", "failed", "canceled"].includes(refund.status)) return;
  // Stripe's terminal failure or cancellation supersedes pending or succeeded snapshots.
  await env.DB.prepare(`
    INSERT INTO creator_refunds (refund_id, payment_intent, livemode, amount_cents, status)
    VALUES (?, ?, ?, ?, ?)
    ON CONFLICT(refund_id) DO UPDATE SET status = excluded.status
    WHERE creator_refunds.status IN ('pending', 'requires_action')
       OR (creator_refunds.status = 'succeeded' AND excluded.status IN ('failed', 'canceled'))
  `).bind(refund.id, intent.id, Number(event.livemode), refund.amount, refund.status).run();
}

async function webhook(request: Request, env: Env, json: Json) {
  const secret = env.STRIPE_WEBHOOK_SECRET;
  const mode = stripeMode(env);
  if (!secret?.startsWith("whsec_") || !mode) return json({error: "unavailable"}, 503);
  const body = await readBody(request, 262144);
  if (!body) return json({error: "invalid_payload"}, 400);
  if (!await verifySignature(body, request.headers.get("Stripe-Signature") || "", secret)) {
    return json({error: "invalid_signature"}, 400);
  }
  let event: StripeEvent;
  try { event = JSON.parse(new TextDecoder().decode(body)); }
  catch { return json({error: "invalid_payload"}, 400); }
  if (!event || event.livemode !== (mode === "live") || !Number.isInteger(event.created)) {
    return json({error: "invalid_event"}, 400);
  }
  switch (event.type) {
    case "checkout.session.completed":
    case "checkout.session.async_payment_succeeded":
    case "checkout.session.async_payment_failed":
    case "checkout.session.expired":
      await updateDonation(env, event);
      break;
    case "refund.created":
    case "refund.updated":
    case "refund.failed":
      await updateRefund(env, event);
      break;
  }
  return json({received: true});
}

async function report(env: Env, json: Json) {
  const mode = stripeMode(env);
  if (!mode) return json({error: "unavailable"}, 503);
  const results = await env.DB.batch([
    env.DB.prepare(`
      SELECT COUNT(*) AS successfulCount, COALESCE(SUM(amount_cents - refunded_cents), 0) AS netCents
      FROM creator_donation_totals WHERE livemode = ? AND status = 'paid'
    `).bind(Number(mode === "live")),
    env.DB.prepare(`
      SELECT COALESCE(paid_at, created_at) AS date, amount_cents AS amountCents, status,
        COALESCE(payment_intent, session_id) AS reference, refunded_cents AS refundedCents,
        refund_pending AS refundPending, refund_failed AS refundFailed
      FROM creator_donation_totals WHERE livemode = ?
      ORDER BY COALESCE(paid_at, created_at) DESC, session_id DESC LIMIT 25
    `).bind(Number(mode === "live"))
  ]);
  return json({mode, summary: results[0].results?.[0], transactions: results[1].results});
}

export async function handleCreatorSupport(request: Request, env: Env, path: string, allowedOrigin: string, authorized: boolean, json: Json) {
  try {
    if (path === "/webhook" && request.method === "POST") return await webhook(request, env, json);
    if (path === "/admin" && request.method === "GET") {
      if (!authorized) return json({error: "unauthorized"}, 401);
      return await report(env, json);
    }
    if (path === "/config" && request.method === "GET") {
      return json({enabled: acceptingDonations(env), testMode: stripeMode(env) === "test"});
    }
    if (request.method !== "POST" || !["/checkout", "/confirmation"].includes(path)) return json({error: "not_found"}, 404);
    if (!allowedOrigin) return json({error: "origin_not_allowed"}, 403);
    if (path === "/checkout" && !acceptingDonations(env)) return json({error: "unavailable"}, 503);
    if (!request.headers.get("Content-Type")?.toLowerCase().startsWith("application/json")) return json({error: "invalid_content_type"}, 415);
    const limiter = env.CREATOR_SUPPORT_RATE_LIMIT;
    const ip = request.headers.get("CF-Connecting-IP") || "unknown";
    if (!limiter) return json({error: "unavailable"}, 503);
    // Confirmation can poll for webhook delivery. Keep its allowance separate from session creation.
    const bucket = path === "/confirmation" ? "confirmation" : "checkout";
    if (!(await limiter.limit({key: `${bucket}:${ip}`})).success) return json({error: "rate_limited"}, 429);
    const raw = await readBody(request, 1024);
    if (!raw) return json({error: "invalid_payload"}, 400);
    let body;
    try { body = JSON.parse(new TextDecoder().decode(raw)); }
    catch { return json({error: "invalid_payload"}, 400); }
    if (!body || typeof body !== "object" || Array.isArray(body)) return json({error: "invalid_payload"}, 400);
    if (path === "/checkout") return await beginCheckout(env, body, allowedOrigin, json);
    const mode = stripeMode(env);
    if (!mode) return json({error: "unavailable"}, 503);
    if (typeof body.sessionId !== "string" || sessionPattern.exec(body.sessionId)?.[1] !== mode) {
      return json({error: "invalid_session"}, 400);
    }
    const {results} = await env.DB.prepare(`
      SELECT status FROM creator_donations WHERE session_id = ? AND livemode = ?
    `).bind(body.sessionId, Number(mode === "live")).all<{status: string}>();
    return results?.[0] ? json({status: results[0].status}) : json({error: "unknown_session"}, 404);
  } catch {
    // Do not expose or log Stripe response bodies or donor data.
    return json({error: "unavailable"}, 503);
  }
}
