import assert from 'node:assert/strict';
import { createECDH, randomBytes } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { DatabaseSync } from 'node:sqlite';
import test from 'node:test';
import { generateVAPIDKeys } from 'web-push';
import { handle, refresh, validSubscription } from './worker.mjs';

const origin = 'https://openband.ca';
const api = 'https://follow.openband.ca/v1/subscription';

function setup() {
  const sqlite = new DatabaseSync(':memory:');
  sqlite.exec(readFileSync(new URL('schema.sql', import.meta.url), 'utf8'));
  const db = {
    prepare(sql) {
      const statement = sqlite.prepare(sql);
      return {
        bind(...args) {
          return {
            async run() { return { meta: statement.run(...args) }; },
            async first() { return statement.get(...args); },
            async all() { return { results: statement.all(...args) }; },
          };
        },
      };
    },
  };
  const { publicKey, privateKey } = generateVAPIDKeys();
  const env = {
    DB: db, ALLOWED_ORIGINS: origin, FEED_URL: origin + '/follow-updates.json',
    SUBSCRIPTION_LIMIT: { async limit() { return { success: true }; } },
    VAPID_SUBJECT: 'mailto:test@example.org', VAPID_PUBLIC_KEY: publicKey, VAPID_PRIVATE_KEY: privateKey,
  };
  const clientKey = createECDH('prime256v1');
  const subscription = {
    endpoint: 'https://fcm.googleapis.com/fcm/send/test-token',
    keys: { p256dh: clientKey.generateKeys().toString('base64url'), auth: randomBytes(16).toString('base64url') },
  };
  const token = randomBytes(32).toString('hex');
  const now = Date.now();
  const request = (method, body, overrides) => new Request(api, {
    method, body: body ? JSON.stringify(body) : undefined,
    headers: { Origin: origin, Authorization: 'Bearer ' + token, 'Content-Type': 'application/json', ...overrides },
  });
  const record = { subscription, version: now, follows: { '362': new Date(now - 1000).toISOString() } };
  const feed = {
    schemaVersion: 1,
    communities: { '362': { name: 'Kahkewistahaw First Nation', path: '/first-nations/kahkewistahaw-first-nation/' } },
    updates: [
      { id: '123456789012345678901234', communityId: '362', kind: 'news', title: 'A new verified story',
        firstSeenAt: new Date(now + 2000).toISOString() },
      { id: '987654321098765432109876', communityId: '362', kind: 'jobs', title: 'Earlier vacancy',
        firstSeenAt: new Date(now - 10000).toISOString() },
    ],
  };
  return { env, sqlite, subscription, now, request, record, feed };
}

test('subscription endpoints accept one community, a supported push endpoint and a private token', async () => {
  const { env, sqlite, subscription, request, record } = setup();
  assert.equal(validSubscription(subscription), true);
  assert.equal(validSubscription({ ...subscription, endpoint: 'https://fcm.googleapis.com.evil.org/' }), false);
  assert.equal(validSubscription({ ...subscription, endpoint: 'http://fcm.googleapis.com/' }), false);
  assert.equal((await handle(request('PUT', record, { Origin: 'https://elsewhere.example' }), env)).status, 403);
  assert.equal((await handle(request('PUT', record, { Authorization: '' }), env)).status, 401);
  assert.equal((await handle(request('PUT', { ...record, follows: { '../bad': new Date().toISOString() } }), env)).status, 400);
  assert.equal((await handle(request('PUT', { ...record, follows: { ...record.follows, '430': new Date().toISOString() } }), env)).status, 400);
  assert.equal((await handle(request('PUT', record), env)).status, 204);
  assert.equal((await handle(request('PUT', { ...record, follows: {}, version: record.version + 1 }), env)).status, 204);
  assert.equal((await handle(request('PUT', record), env)).status, 409);
  assert.equal(sqlite.prepare('SELECT community_id FROM follow_subscriptions').get().community_id, null);
  assert.equal((await handle(request('DELETE'), env)).status, 204);
  assert.equal(sqlite.prepare('SELECT count(*) n FROM follow_subscriptions').get().n, 0);
});

test('Apple and Edge subscriptions receive standard encrypted Web Push', async () => {
  const providers = [
    'https://web.push.apple.com/test-token',
    'https://wns2-db5p.notify.windows.com/test-token',
    'https://edge.wns.windows.com/test-token',
  ];
  for (const endpoint of providers) {
    const { env, now, request, record, feed } = setup();
    const subscription = { ...record.subscription, endpoint };
    assert.equal((await handle(request('PUT', { ...record, subscription }), env)).status, 204);
    let sends = 0;
    await refresh(env, now + 3000, async (url, options) => {
      if (url === env.FEED_URL) return Response.json(feed);
      assert.equal(url, endpoint);
      assert.equal(options.redirect, 'manual');
      assert.equal(options.headers['Content-Encoding'], 'aes128gcm');
      assert.match(options.headers.Authorization, /^vapid /);
      assert.ok(Number(options.headers.TTL) > 0);
      sends++;
      return new Response(null, { status: 201 });
    });
    assert.equal(sends, 1, endpoint);
  }
  const { subscription } = setup();
  assert.equal(validSubscription({ ...subscription, endpoint: 'https://wns2.notify.windows.com.example.org/' }), false);
});

test('scheduled publishing sends encrypted push once across concurrent runs and skips older content', async () => {
  const { env, sqlite, now, request, record, feed, subscription } = setup();
  await handle(request('PUT', record), env);
  let sends = 0;
  const mock = async (url, options) => {
    if (url === env.FEED_URL) return Response.json(feed);
    assert.equal(url, subscription.endpoint);
    assert.equal(options.redirect, 'manual');
    assert.equal(options.headers['Content-Encoding'], 'aes128gcm');
    assert.match(options.headers.Authorization, /^vapid /);
    assert.ok(Buffer.isBuffer(options.body));
    assert.equal(options.body.includes(Buffer.from('A new verified story')), false);
    sends++;
    return new Response(null, { status: 201 });
  };
  await Promise.all([refresh(env, now + 3000, mock), refresh(env, now + 3000, mock)]);
  await refresh(env, now + 60000, mock);
  assert.equal(sends, 1);
  assert.equal(sqlite.prepare('SELECT count(*) n FROM follow_deliveries WHERE delivered_at IS NOT NULL').get().n, 1);
});

test('scheduled retries back off, respect unfollow and delete expired device subscriptions', async () => {
  const { env, sqlite, now, request, record, feed } = setup();
  await handle(request('PUT', record), env);
  let sends = 0;
  const mock = async url => {
    if (url === env.FEED_URL) return Response.json(feed);
    sends++;
    return new Response(null, { status: sends === 1 ? 503 : 410 });
  };
  await refresh(env, now + 3000, mock);
  await refresh(env, now + 60000, mock);
  assert.equal(sends, 1);
  await handle(request('PUT', { ...record, follows: {}, version: now + 1 }), env);
  await refresh(env, now + 180000, mock);
  assert.equal(sends, 1);
  await handle(request('PUT', { ...record, version: now + 2 }), env);
  await refresh(env, now + 180000, mock);
  assert.equal(sends, 2);
  assert.equal(sqlite.prepare('SELECT count(*) n FROM follow_subscriptions').get().n, 0);
  assert.equal(sqlite.prepare('SELECT count(*) n FROM follow_deliveries').get().n, 0);
});

test('switching communities replaces the delivery target and feed reads use the publishing source', async () => {
  const { env, now, request, record, feed } = setup();
  await handle(request('PUT', record), env);
  const switched = { ...record, version: now + 1, follows: { '269': new Date(now + 1000).toISOString() } };
  assert.equal((await handle(request('PUT', switched), env)).status, 204);
  feed.communities['269'] = { name: 'Peguis', path: '/first-nations/peguis/' };
  feed.updates.push({ ...feed.updates[0], id: '101010101010101010101010', communityId: '269' });
  const delivery = [];
  await refresh(env, now + 3000, async (url, options) => {
    if (url === env.FEED_URL) return Response.json(feed);
    delivery.push(options.headers.Topic);
    return new Response(null, { status: 201 });
  });
  assert.deepEqual(delivery, ['101010101010101010101010']);
  const endpoint = new Request('https://follow.openband.ca/v1/feed/269', { headers: { Origin: origin } });
  const result = await handle(endpoint, env, async url => {
    assert.equal(url, origin + '/follow-data/269.json');
    return Response.json({ updates: [] });
  });
  assert.equal(result.status, 200);
  assert.deepEqual(await result.json(), { updates: [] });
  const whitefish = new Request('https://follow.openband.ca/v1/feed/ab-whitefish-lake-128', { headers: { Origin: origin } });
  assert.equal((await handle(whitefish, env, async url => {
    assert.equal(url, origin + '/follow-data/ab-whitefish-lake-128.json');
    return Response.json({ updates: [] });
  })).status, 200);
});

test('the delayed test alert uses only the requesting device', async t => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const { env, request, record, feed, subscription } = setup();
  await handle(request('PUT', record), env);
  const alert = new Request('https://follow.openband.ca/v1/test-alert', {
    method: 'POST', headers: request('DELETE').headers,
  });
  let scheduled;
  let sends = 0;
  const response = await handle(alert, env, async url => {
    if (url === env.FEED_URL.replace('follow-updates.json', 'follow-data/362.json')) return Response.json(feed);
    assert.equal(url, subscription.endpoint);
    sends++;
    return new Response(null, { status: 201 });
  }, work => { scheduled = work; });
  assert.equal(response.status, 202);
  assert.equal(sends, 0);
  t.mock.timers.tick(8000);
  await scheduled;
  assert.equal(sends, 1);
});
