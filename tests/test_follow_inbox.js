'use strict';
const assert = require('node:assert/strict');
const { isUnread, oneCommunity } = require('../assets/follow.js');

const item = { communityId: '362', updatedAt: '2026-11-07T11:10:00+00:00' };
assert.equal(isUnread(item, {}), false);
assert.equal(isUnread(item, { '430': '2026-11-07T11:00:00Z' }), false);
assert.equal(isUnread(item, { '362': '2026-11-07T11:00:00Z' }), true);
assert.equal(isUnread(item, { '362': '2026-11-07T11:10:00.000Z' }), false);
assert.equal(isUnread(item, { '362': '2026-11-07T11:15:00Z' }), false);
assert.deepEqual(oneCommunity({
  '362': '2026-11-07T11:15:00Z', '269': '2026-11-07T11:20:00Z', '../unknown': '2026-11-07T12:00:00Z',
}), { '269': '2026-11-07T11:20:00Z' });
assert.deepEqual(oneCommunity({ 'ab-whitefish-lake-128': '2026-11-07T11:20:00Z' }),
  { 'ab-whitefish-lake-128': '2026-11-07T11:20:00Z' });
console.log('Follow inbox unread state handles community filtering, existing history, and marking as read.');

const { isNewForDevice } = require('../assets/follow.js');
const following = { '362': '2026-11-07T11:05:00Z' };
const added = { ...item, firstSeenAt: '2026-11-07T11:09:00Z' };
assert.equal(isNewForDevice(added, following, '2026-11-07T11:08:00Z'), true);
assert.equal(isNewForDevice(added, following, '2026-11-07T11:10:00Z'), false);
assert.equal(isNewForDevice({ ...added, firstSeenAt: '2026-11-07T11:00:00Z' }, following, '2026-11-07T11:08:00Z'), false);

async function verifyDelivery() {
  const fs = require('node:fs');
  const vm = require('node:vm');
  const handlers = {};
  const shown = [];
  let log;
  const cache = {
    async match() { return log?.clone(); },
    async put(key, response) { log = response; },
  };
  const self = {
    addEventListener(name, handler) { handlers[name] = handler; },
    registration: { async showNotification(title, options) { shown.push({ title, ...options }); } },
  };
  vm.runInNewContext(fs.readFileSync(require.resolve('../follow-notifications.js'), 'utf8'), {
    self, caches: { async open() { return cache; } }, Response,
  });
  const update = { id: '123456789012345678901234', title: 'Community workshop',
    category: 'Event', community: 'Kahkewistahaw First Nation', path: '/first-nations/kahkewistahaw-first-nation/' };
  function dispatch(items) {
    return new Promise(resolve => handlers.message({
      data: { type: 'openband-new-items', items },
      waitUntil: resolve,
    }));
  }
  await Promise.all([dispatch([update]), dispatch([update])]);
  assert.equal(shown.length, 1);
  assert.equal(shown[0].body, 'Event · Community workshop');
  const pushed = { ...update, id: '999999999999999999999999', title: 'New verified update' };
  await new Promise(resolve => handlers.push({ data: { json: () => pushed }, waitUntil: resolve }));
  assert.equal(shown.length, 2);
  assert.equal(shown[1].body, 'Event · New verified update');
  console.log('Device alerts use opt-in cutoffs and deduplicate concurrent refreshes.');
}
verifyDelivery().catch(error => { console.error(error); process.exitCode = 1; });
