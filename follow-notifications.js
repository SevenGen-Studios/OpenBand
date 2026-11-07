/* global self, caches, clients */
'use strict';

// This worker only delivers alerts. Page requests stay with the normal browser cache.
const deliveryCache = 'openband-follow-delivered-v1';
const deliveryLog = '/.openband/follow-delivered';
let queue = Promise.resolve();

self.addEventListener('install', event => event.waitUntil(self.skipWaiting()));
self.addEventListener('activate', event => event.waitUntil(clients.claim()));

self.addEventListener('message', event => {
  if (event.data?.type !== 'openband-new-items' || !Array.isArray(event.data.items)) return;
  event.waitUntil(scheduleDelivery(event.data.items));
});

self.addEventListener('push', event => {
  if (!event.data) return;
  try { event.waitUntil(scheduleDelivery([event.data.json()])); }
  catch { /* Ignore malformed payloads. */ }
});

function scheduleDelivery(items) {
  queue = queue.catch(() => {}).then(() => deliver(items));
  return queue;
}

async function deliver(items) {
  const cache = await caches.open(deliveryCache);
  const log = await cache.match(deliveryLog);
  const sent = new Set(log ? await log.json() : []);
  for (const item of items) {
    if (!item || !/^[a-f0-9]{24}$/.test(item.id) || sent.has(item.id) ||
        !/^\/first-nations\/[a-z0-9-]+\/$/.test(item.path) ||
        typeof item.title !== 'string' || typeof item.community !== 'string') continue;
    await self.registration.showNotification(item.community, {
      body: `${item.category} · ${item.title}`,
      icon: '/assets/favicon.svg',
      tag: 'openband-' + item.id,
      data: { path: item.path },
    });
    sent.add(item.id);
    await cache.put(deliveryLog, new Response(JSON.stringify([...sent].slice(-256))));
  }
}

self.addEventListener('notificationclick', event => {
  const path = event.notification.data?.path;
  event.notification.close();
  if (!/^\/first-nations\/[a-z0-9-]+\/$/.test(path)) return;
  const target = new URL(path + '?updates=1', self.location.origin).href;
  event.waitUntil((async () => {
    const windows = await clients.matchAll({ type: 'window', includeUncontrolled: true });
    const existing = windows.find(window => window.url === target);
    if (existing) await existing.focus();
    else await clients.openWindow(target);
  })());
});
