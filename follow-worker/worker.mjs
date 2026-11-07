import { generateRequestDetails } from 'web-push';

const isCommunityId = id => typeof id === 'string' && id.length <= 48 &&
  id !== 'communities' && /^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(id);
const kinds = { news: 'News', events: 'Event', jobs: 'Job', projects: 'Project' };
const windowMs = 48 * 60 * 60 * 1000;
const minute = 60000;
const fetchFromInternet = (url, options) => fetch(url, options);

export function validSubscription(value) {
  if (!value || typeof value.endpoint !== 'string' || value.endpoint.length > 2048 ||
      !/^[\w-]{87}=?$/.test(value.keys?.p256dh || '') || !/^[\w-]{22}={0,2}$/.test(value.keys?.auth || '')) return false;
  try {
    const url = new URL(value.endpoint);
    return url.protocol === 'https:' && !url.port && !url.username && !url.password && !url.hash &&
      (url.hostname === 'fcm.googleapis.com' || url.hostname === 'updates.push.services.mozilla.com' ||
       url.hostname.endsWith('.push.apple.com') || url.hostname.endsWith('.notify.windows.com') ||
       url.hostname.endsWith('.wns.windows.com'));
  } catch {
    return false;
  }
}

async function readRequest(request) {
  const reader = request.body?.getReader();
  if (!reader) throw Error('Missing body');
  const decoder = new TextDecoder();
  let size = 0;
  let text = '';
  for (;;) {
    const { done, value } = await reader.read();
    if (done) return JSON.parse(text + decoder.decode());
    size += value.byteLength;
    if (size > 8192) {
      await reader.cancel();
      throw Error('Request too large');
    }
    text += decoder.decode(value, { stream: true });
  }
}

async function subscriptionId(request) {
  const token = /^Bearer ([a-f0-9]{64})$/.exec(request.headers.get('Authorization') || '')?.[1];
  if (!token) return '';
  const hash = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(token));
  return Array.from(new Uint8Array(hash), byte => byte.toString(16).padStart(2, '0')).join('');
}

export async function handle(request, env, fetcher = fetchFromInternet, defer) {
  const origin = request.headers.get('Origin');
  const allowed = (env.ALLOWED_ORIGINS || '').split(',').map(value => value.trim());
  if (!origin || !allowed.includes(origin)) return new Response(null, { status: 403 });
  const headers = {
    'Access-Control-Allow-Origin': origin, 'Vary': 'Origin', 'Cache-Control': 'no-store',
    'Access-Control-Allow-Methods': 'GET, PUT, POST, DELETE, OPTIONS',
    'Access-Control-Allow-Headers': 'Authorization, Content-Type',
  };
  const path = new URL(request.url).pathname;
  const feedId = /^\/v1\/feed\/([^/]+)$/.exec(path)?.[1];
  const feed = feedId === 'communities' || isCommunityId(feedId) ? feedId : null;
  const empty = status => new Response(null, { status, headers });
  if (!feed && !['/v1/config', '/v1/subscription', '/v1/test-alert'].includes(path)) return empty(404);
  if (request.method === 'OPTIONS') return empty(204);
  if (!env.VAPID_PUBLIC_KEY || !env.VAPID_PRIVATE_KEY || !env.VAPID_SUBJECT) return empty(503);
  if (feed && request.method === 'GET') {
    try {
      const url = new URL(`follow-data/${feed}.json`, env.FEED_URL);
      const response = await fetcher(url.href, { redirect: 'manual', signal: AbortSignal.timeout(8000) });
      if (!response.ok) return empty(response.status === 404 ? 404 : 502);
      return new Response(response.body, { headers: {
        ...headers, 'Content-Type': 'application/json', 'X-Content-Type-Options': 'nosniff',
        'Cache-Control': 'public, max-age=45',
      } });
    } catch (error) {
      console.warn('OpenBand feed request failed:', error.name);
      return empty(502);
    }
  }
  if (path === '/v1/config' && request.method === 'GET') {
    return Response.json({ publicKey: env.VAPID_PUBLIC_KEY }, { headers });
  }
  const test = path === '/v1/test-alert' && request.method === 'POST';
  if (!test && (path !== '/v1/subscription' || !['PUT', 'DELETE'].includes(request.method))) return empty(405);
  const id = await subscriptionId(request);
  if (!id) return empty(401);
  const limit = await env.SUBSCRIPTION_LIMIT.limit({ key: request.headers.get('CF-Connecting-IP') || id });
  if (!limit.success) return empty(429);
  if (test) {
    if (!defer) return empty(503);
    const row = await env.DB.prepare(
      'SELECT subscription, community_id FROM follow_subscriptions WHERE id = ?',
    ).bind(id).first();
    if (!row || !isCommunityId(row.community_id)) return empty(404);
    defer(sendTest(env, fetcher, id, row));
    return empty(202);
  }
  if (request.method === 'DELETE') {
    await env.DB.prepare('DELETE FROM follow_subscriptions WHERE id = ?').bind(id).run();
    return empty(204);
  }
  let data;
  try { data = await readRequest(request); }
  catch { return empty(400); }
  if (!data || !validSubscription(data.subscription) || !data.follows || Array.isArray(data.follows) ||
      typeof data.follows !== 'object') return empty(400);

  const now = Date.now();
  const choices = Object.entries(data.follows);
  if (choices.length > 1) return empty(400);
  const [community, date] = choices[0] || [];
  const followedAt = Date.parse(date);
  if (choices.length && (!isCommunityId(community) || !Number.isFinite(followedAt))) return empty(400);
  if (!Number.isSafeInteger(data.version) || data.version < 0 || data.version > now + minute) return empty(400);
  const { endpoint, keys } = data.subscription;
  const record = JSON.stringify({ endpoint, keys: { auth: keys.auth, p256dh: keys.p256dh } });
  try {
    const result = await env.DB.prepare(`
      INSERT INTO follow_subscriptions (id, endpoint, subscription, community_id, followed_at, version, created_at)
      VALUES (?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT(id) DO UPDATE SET
        endpoint = excluded.endpoint, subscription = excluded.subscription,
        community_id = excluded.community_id, followed_at = excluded.followed_at, version = excluded.version
      WHERE excluded.version > follow_subscriptions.version
    `).bind(id, endpoint, record, community || null, community ? Math.min(now, followedAt) : null, data.version, now).run();
    if (result.meta.changes === 0) return empty(409);
  } catch (error) {
    if (String(error).includes('UNIQUE constraint failed')) return empty(409);
    throw error;
  }
  return empty(204);
}

async function sendTest(env, fetcher, id, row) {
  await new Promise(resolve => setTimeout(resolve, 8000));
  try {
    const stillFollowing = await env.DB.prepare(
      'SELECT id FROM follow_subscriptions WHERE id = ? AND community_id = ? AND subscription = ?',
    ).bind(id, row.community_id, row.subscription).first();
    if (!stillFollowing) return;
    const response = await fetcher(new URL(`follow-data/${row.community_id}.json`, env.FEED_URL).href,
      { redirect: 'manual', signal: AbortSignal.timeout(5000) });
    if (!response.ok) return;
    const community = (await response.json()).communities?.[row.community_id];
    if (!/^\/first-nations\/[a-z0-9-]+\/$/.test(community?.path)) return;
    await send(JSON.parse(row.subscription), {
      id: crypto.randomUUID().replaceAll('-', '').slice(0, 24), category: 'Test',
      community: 'OpenBand test alert', title: 'Device alerts are working.', path: community.path,
    }, env, fetcher);
  } catch {
    console.warn('OpenBand test alert could not be sent.');
  }
}

function freshItems(feed, now) {
  if (feed.schemaVersion !== 1 || !feed.communities || !Array.isArray(feed.updates)) throw Error('Invalid Follow feed');
  return feed.updates.flatMap(item => {
    const firstSeen = Date.parse(item.firstSeenAt);
    const community = feed.communities[item.communityId];
    if (!isCommunityId(item.communityId) || !Object.hasOwn(kinds, item.kind) ||
        !/^[a-f0-9]{24}$/.test(item.id) || firstSeen < now - windowMs || firstSeen > now ||
        !Number.isFinite(firstSeen) || !/^\/first-nations\/[a-z0-9-]+\/$/.test(community?.path) ||
        typeof community.name !== 'string' || typeof item.title !== 'string') return [];
    return [{
      id: item.id, communityId: item.communityId, firstSeen, title: item.title.slice(0, 240),
      category: kinds[item.kind], community: community.name.slice(0, 100), path: community.path,
    }];
  });
}

async function send(subscription, payload, env, fetcher) {
  if (!validSubscription(subscription)) return 410;
  const details = generateRequestDetails(subscription, JSON.stringify(payload), {
    TTL: 3600,
    topic: payload.id,
    vapidDetails: { subject: env.VAPID_SUBJECT, publicKey: env.VAPID_PUBLIC_KEY, privateKey: env.VAPID_PRIVATE_KEY },
  });
  const result = await fetcher(details.endpoint, {
    method: details.method, headers: details.headers, body: details.body,
    redirect: 'manual', signal: AbortSignal.timeout(8000),
  });
  return result.status;
}

export async function refresh(env, now = Date.now(), fetcher = fetchFromInternet) {
  const response = await fetcher(env.FEED_URL, { redirect: 'manual', signal: AbortSignal.timeout(8000) });
  if (!response.ok) throw Error('Follow feed fetch failed');
  const items = freshItems(await response.json(), now);
  const db = env.DB;
  await db.prepare(`
    INSERT OR IGNORE INTO follow_deliveries (subscription_id, item_id, first_seen, payload)
    SELECT s.id, json_extract(item.value, '$.id'), json_extract(item.value, '$.firstSeen'), item.value
    FROM json_each(?) item
    JOIN follow_subscriptions s ON s.community_id = json_extract(item.value, '$.communityId')
      AND s.followed_at < json_extract(item.value, '$.firstSeen')
      AND s.created_at < json_extract(item.value, '$.firstSeen')
  `).bind(JSON.stringify(items)).run();
  await db.prepare('DELETE FROM follow_deliveries WHERE first_seen < ?').bind(now - windowMs).run();
  const due = await db.prepare(`
    SELECT d.subscription_id, d.item_id
    FROM follow_deliveries d JOIN follow_subscriptions s ON s.id = d.subscription_id
    WHERE d.delivered_at IS NULL AND d.lease_until <= ?
      AND d.item_id IN (SELECT value FROM json_each(?))
      AND s.community_id = json_extract(d.payload, '$.communityId') AND s.followed_at < d.first_seen
    ORDER BY d.lease_until, d.first_seen LIMIT 12
  `).bind(now, JSON.stringify(items.map(item => item.id))).all();

  for (const row of due.results) {
    const claim = await db.prepare(`
      UPDATE follow_deliveries SET lease_until = ?, attempts = attempts + 1
      WHERE subscription_id = ? AND item_id = ? AND delivered_at IS NULL AND lease_until <= ?
        AND EXISTS (SELECT 1 FROM follow_subscriptions s WHERE s.id = follow_deliveries.subscription_id
          AND s.community_id = json_extract(follow_deliveries.payload, '$.communityId')
          AND s.followed_at < follow_deliveries.first_seen)
      RETURNING payload, attempts, (SELECT subscription FROM follow_subscriptions s WHERE s.id = subscription_id) AS subscription
    `).bind(now + 2 * minute, row.subscription_id, row.item_id, now).first();
    if (!claim?.subscription) continue;
    let status;
    try { status = await send(JSON.parse(claim.subscription), JSON.parse(claim.payload), env, fetcher); }
    catch { status = 503; }
    if (status === 404 || status === 410) {
      await db.prepare('DELETE FROM follow_subscriptions WHERE id = ? AND subscription = ?')
        .bind(row.subscription_id, claim.subscription).run();
    } else if (status >= 200 && status < 300) {
      await db.prepare('UPDATE follow_deliveries SET delivered_at = ? WHERE subscription_id = ? AND item_id = ?')
        .bind(now, row.subscription_id, row.item_id).run();
    } else {
      const retry = now + Math.min(60, 2 ** Math.min(claim.attempts, 6)) * minute;
      await db.prepare('UPDATE follow_deliveries SET lease_until = ? WHERE subscription_id = ? AND item_id = ?')
        .bind(retry, row.subscription_id, row.item_id).run();
    }
  }
}

export default {
  fetch(request, env, ctx) { return handle(request, env, fetchFromInternet, work => ctx.waitUntil(work)); },
  scheduled(_controller, env, ctx) { ctx.waitUntil(refresh(env)); },
};
