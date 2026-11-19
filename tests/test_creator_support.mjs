import assert from "node:assert/strict";
import {createHmac, randomUUID} from "node:crypto";
import {readFileSync} from "node:fs";
import {DatabaseSync} from "node:sqlite";
import {test} from "node:test";
import {donationCents, handleCreatorSupport} from "../analytics-worker/src/creator-support.ts";

const origin = "https://openband.ca";
const api = "https://worker.example/v1/creator-support";
const purpose = "openband_creator_support";
const signingSecret = "whsec_fixture";
const sessionDate = 1750000000;
const json = (data, status = 200) => Response.json(data, {status});

function fixture(t) {
  const db = new DatabaseSync(":memory:");
  t.after(() => db.close());
  db.exec(readFileSync(new URL("../analytics-worker/creator-support.sql", import.meta.url), "utf8"));
  const env = {
    CREATOR_SUPPORT_ENABLED: "true",
    STRIPE_SECRET_KEY: "sk_test_fixture",
    STRIPE_WEBHOOK_SECRET: signingSecret,
    CREATOR_SUPPORT_RATE_LIMIT: {limit: async () => ({success: true})},
    DB: {
      prepare(sql) {
        const all = async (...values) => ({results: db.prepare(sql).all(...values)});
        return {all, bind(...values) {
          return {
            all: () => all(...values),
            run: async () => db.prepare(sql).run(...values)
          };
        }};
      },
      batch: statements => Promise.all(statements.map(statement => statement.all()))
    }
  };
  const checkouts = new Map();
  const refunds = new Map();
  t.mock.method(globalThis, "fetch", async (url, options) => {
    const path = new URL(url).pathname;
    assert.equal(options.headers.get("Authorization"), "Bearer sk_test_fixture");
    if (path === "/v1/checkout/sessions") {
      assert.equal(options.body.get("mode"), "payment");
      assert.equal(options.body.get("line_items[0][price_data][currency]"), "cad");
      assert.equal(options.body.get("adaptive_pricing[enabled]"), "false");
      assert.equal(options.body.get("success_url"), origin + "/support/thanks/?session_id={CHECKOUT_SESSION_ID}");
      assert.equal(options.body.get("cancel_url"), origin + "/support/?cancelled=1");
      assert.equal(options.body.get("metadata[purpose]"), purpose);
      assert.equal(options.body.get("payment_intent_data[metadata][purpose]"), purpose);
      const key = options.headers.get("Idempotency-Key");
      assert.match(key, /^openband-support-/);
      const id = checkouts.get(key)?.id || "cs_test_session" + (checkouts.size + 1);
      checkouts.set(key, {id, cents: Number(options.body.get("line_items[0][price_data][unit_amount]"))});
      return Response.json({id, created: sessionDate, url: "https://checkout.stripe.com/pay/" + id});
    }
    const refund = refunds.get(path.split("/").at(-1));
    assert.ok(refund);
    return Response.json(refund);
  });

  function request(path, payload, {authorized = false, allowedOrigin = origin, headers = {}} = {}) {
    const method = payload === undefined ? "GET" : "POST";
    const body = typeof payload === "string" ? payload : JSON.stringify(payload);
    const req = new Request(api + path, {method, body, headers: {"Content-Type": "application/json", ...headers}});
    return handleCreatorSupport(req, env, path, allowedOrigin, authorized, json);
  }

  async function sendEvent(type, object, options = {}) {
    const {secret = signingSecret, secondsAgo = 0, livemode = false} = options;
    const body = JSON.stringify({type, livemode, created: sessionDate + 120, data: {object}});
    const timestamp = Math.floor(Date.now() / 1000) - secondsAgo;
    const signature = createHmac("sha256", secret).update(timestamp + "." + body).digest("hex");
    return request("/webhook", body, {headers: {"Stripe-Signature": `t=${timestamp},v1=${signature}`}});
  }
  const report = async () => (await request("/admin", undefined, {authorized: true})).json();
  const confirm = async sessionId => (await request("/confirmation", {sessionId})).json();
  return {env, request, sendEvent, report, confirm, refunds, checkouts};
}

test("validates presets and CAD custom amounts as integer cents", () => {
  for (const presetCents of [500, 1000, 2500, 5000, 10000]) {
    assert.equal(donationCents({presetCents}), presetCents);
  }
  for (const [customAmount, cents] of [["2", 200], ["2.01", 201], ["23,5", 2350], ["999999.99", 99999999]]) {
    assert.equal(donationCents({customAmount}), cents);
  }
  for (const customAmount of ["1.99", "", "-5", "2.001", "1e3", "1,000", "1000000", "$10", 2, {}, "Infinity"]) {
    assert.equal(donationCents({customAmount}), null);
  }
  assert.equal(donationCents({presetCents: 100}), null);
  assert.equal(donationCents({presetCents: 1000, customAmount: "5"}), null);
});

test("protects Checkout creation and sends each amount to Stripe in CAD", async t => {
  const {env, request, report, checkouts} = fixture(t);
  assert.equal((await request("/admin")).status, 401);
  assert.equal((await request("/checkout", {presetCents: 1000}, {allowedOrigin: ""})).status, 403);
  env.CREATOR_SUPPORT_ENABLED = "false";
  assert.equal((await (await request("/config")).json()).enabled, false);
  assert.equal((await request("/checkout", {presetCents: 1000})).status, 503);
  env.CREATOR_SUPPORT_ENABLED = "true";
  assert.equal((await (await request("/config")).json()).enabled, true);
  env.CREATOR_SUPPORT_RATE_LIMIT.limit = async () => ({success: false});
  assert.equal((await request("/checkout", {presetCents: 1000})).status, 429);
  env.CREATOR_SUPPORT_RATE_LIMIT.limit = async () => ({success: true});
  assert.equal((await request("/checkout", {customAmount: "-2", attempt: randomUUID()})).status, 400);
  for (const presetCents of [500, 1000, 2500, 5000, 10000]) {
    assert.equal((await request("/checkout", {presetCents, attempt: randomUUID()})).status, 200);
  }
  const attempt = randomUUID();
  for (let retry = 0; retry < 2; retry++) {
    assert.equal((await request("/checkout", {customAmount: "2.09", attempt})).status, 200);
  }
  assert.deepEqual([...checkouts.values()].map(item => item.cents), [500, 1000, 2500, 5000, 10000, 209]);
  const data = await report();
  assert.equal(data.transactions.length, 6);
  assert.deepEqual(data.summary, {successfulCount: 0, netCents: 0});
});

test("only signed and matching paid events confirm a donation and retries preserve totals", async t => {
  const {request, sendEvent, report, confirm} = fixture(t);
  for (const presetCents of [2500, 1000, 500]) await request("/checkout", {presetCents, attempt: randomUUID()});
  const session = {id: "cs_test_session1", mode: "payment", currency: "cad", amount_total: 2500,
    payment_intent: "pi_1", payment_status: "paid", metadata: {purpose}};
  assert.equal((await sendEvent("checkout.session.completed", session, {secret: "other_secret"})).status, 400);
  assert.equal((await sendEvent("checkout.session.completed", session, {secondsAgo: 400})).status, 400);
  assert.equal((await sendEvent("checkout.session.completed", session, {livemode: true})).status, 400);
  await sendEvent("checkout.session.completed", {...session, payment_status: "unpaid"});
  await sendEvent("checkout.session.completed", {...session, currency: "usd"});
  assert.equal((await sendEvent("checkout.session.completed", {...session, amount_total: 2400})).status, 503);
  assert.deepEqual(await confirm(session.id), {status: "pending"});
  for (let retry = 0; retry < 2; retry++) {
    assert.equal((await sendEvent("checkout.session.completed", session)).status, 200);
  }
  await sendEvent("checkout.session.expired", session);
  await sendEvent("checkout.session.expired", {...session, id: "cs_test_session2", amount_total: 1000, payment_intent: null});
  await sendEvent("checkout.session.async_payment_failed", {...session, id: "cs_test_session3", amount_total: 500, payment_intent: "pi_3"});
  assert.deepEqual(await confirm(session.id), {status: "paid"});
  assert.deepEqual(await confirm("cs_test_session2"), {status: "expired"});
  assert.deepEqual(await confirm("cs_test_session3"), {status: "failed"});
  const data = await report();
  assert.deepEqual(data.summary, {successfulCount: 1, netCents: 2500});
  assert.equal(data.transactions[0].reference, "pi_1");
});

test("refunds reconcile across duplicate and out-of-order webhook deliveries", async t => {
  const {request, sendEvent, report, refunds} = fixture(t);
  await request("/checkout", {presetCents: 2500, attempt: randomUUID()});
  const intent = {id: "pi_1", livemode: false, metadata: {purpose}};
  const refund = {id: "re_a", currency: "cad", amount: 1000, status: "succeeded", payment_intent: intent};
  refunds.set(refund.id, refund);
  await sendEvent("refund.updated", {id: refund.id});
  await sendEvent("refund.created", {id: refund.id});
  await sendEvent("checkout.session.completed", {id: "cs_test_session1", mode: "payment", currency: "cad",
    amount_total: 2500, payment_intent: "pi_1", payment_status: "paid", metadata: {purpose}});
  assert.deepEqual((await report()).summary, {successfulCount: 1, netCents: 1500});
  const remainder = {...refund, id: "re_b", amount: 1500, status: "pending"};
  refunds.set(remainder.id, remainder);
  await sendEvent("refund.created", {id: remainder.id});
  assert.equal((await report()).transactions[0].refundPending, 1);
  remainder.status = "succeeded";
  await sendEvent("refund.updated", {id: remainder.id});
  assert.deepEqual((await report()).summary, {successfulCount: 1, netCents: 0});
  remainder.status = "failed";
  await sendEvent("refund.failed", {id: remainder.id});
  const data = await report();
  assert.deepEqual(data.summary, {successfulCount: 1, netCents: 1500});
  assert.equal(data.transactions[0].refundFailed, 1);
});
