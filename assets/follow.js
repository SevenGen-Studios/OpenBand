(() => {
  'use strict';

  const storageKey = 'openband-follow-pilot-v1';
  const categories = { news: 'News', events: 'Event', jobs: 'Job', projects: 'Project' };
  const isUnread = (item, following) => Date.parse(item.updatedAt) > Date.parse(following[item.communityId]);
  const isNewForDevice = (item, following, enabledAt) => Date.parse(item.firstSeenAt) >
    Math.max(Date.parse(following[item.communityId]), Date.parse(enabledAt));
  const oneCommunity = data => Object.fromEntries(Object.entries(data || {}).filter(([id, date]) =>
    id.length <= 48 && /^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(id) &&
    id !== 'communities' && typeof date === 'string' && Number.isFinite(Date.parse(date)))
    .sort((a, b) => Date.parse(b[1]) - Date.parse(a[1])).slice(0, 1));
  if (typeof module === 'object' && module.exports) {
    module.exports = { isUnread, isNewForDevice, oneCommunity };
    return;
  }

  const push = window.OpenBandPush;
  const deviceKey = push ? 'openband-follow-web-push-v1' : 'openband-follow-device-v1';
  // A configured sender enables the pilot on the published site.
  if (!push && !['localhost', '127.0.0.1', '[::1]'].includes(location.hostname)) return;

  let following = readFollowing();
  let profile = null;
  let roster = null;
  let rosterRequest = null;
  let choosing = false;
  let managing = false;
  let visibleLimit = 4;
  let feed = null;
  let pending = null;
  let lastLoaded = 0;
  let persistenceUnavailable = false;
  let deviceSince = readDeviceSince();
  let deviceWorker = null;
  const nav = document.querySelector('nav[aria-label="Primary navigation"], nav[aria-label="OpenBand navigation"]');
  if (!nav) return;
  nav.classList.add('follow-nav');

  function make(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  }

  function readFollowing() {
    try {
      const data = JSON.parse(localStorage.getItem(storageKey) || '{}');
      return oneCommunity(data);
    } catch {
      return {};
    }
  }

  function save() {
    try {
      localStorage.setItem(storageKey, JSON.stringify(following));
    } catch {
      persistenceUnavailable = true;
    }
  }

  function readDeviceSince() {
    try { return localStorage.getItem(deviceKey) || ''; }
    catch { return ''; }
  }

  function items() {
    return (feed?.updates || []).filter(item => following[item.communityId]);
  }

  function selectedId() {
    return Object.keys(following)[0] || '';
  }

  const bell = make('button', 'follow-bell');
  bell.type = 'button';
  bell.setAttribute('aria-haspopup', 'dialog');
  bell.setAttribute('aria-controls', 'followInbox');
  bell.innerHTML = '<svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/></svg>';
  const badge = make('span', 'follow-badge');
  badge.setAttribute('aria-hidden', 'true');
  bell.append(badge);
  nav.append(bell);

  const dialog = make('dialog', 'follow-inbox');
  dialog.id = 'followInbox';
  dialog.setAttribute('aria-labelledby', 'followInboxTitle');
  const supportsPopover = typeof dialog.showPopover === 'function';
  if (supportsPopover) dialog.setAttribute('popover', 'auto');
  const panelOpen = () => supportsPopover ? dialog.matches(':popover-open') : dialog.open;
  const top = make('div', 'follow-inbox-top');
  const heading = make('h2', '', 'Updates');
  heading.id = 'followInboxTitle';
  const manage = make('button', 'follow-text-button', 'Manage');
  manage.type = 'button';
  manage.addEventListener('click', () => {
    managing = !managing;
    choosing = managing && !selectedId();
    paint();
    if (choosing) void ensureRoster();
    if (managing && push && supportsDevice) {
      void push.prepare().catch(() => {});
      void getDeviceWorker().catch(() => {});
    }
  });
  const close = make('button', 'follow-close', '×');
  close.type = 'button';
  close.setAttribute('aria-label', 'Close community updates');
  close.addEventListener('click', () => {
    if (supportsPopover) dialog.hidePopover();
    else dialog.close();
    bell.focus();
  });
  top.append(heading, manage, close);
  const currentName = make('p', 'follow-current-name');
  const identity = make('div', 'follow-identity');
  const identityIcon = make('span', 'follow-identity-icon');
  identityIcon.setAttribute('aria-hidden', 'true');
  const identityText = make('div', 'follow-identity-text');
  const communityLink = make('a', 'follow-identity-name');
  const summary = make('p', 'follow-summary');
  identityText.append(communityLink, summary);
  const change = make('button', 'follow-read', 'Change');
  change.type = 'button';
  change.addEventListener('click', () => {
    choosing = !choosing;
    paint();
    if (choosing) {
      search.focus();
      void ensureRoster();
    }
  });
  identity.append(identityIcon, identityText, change);
  const picker = make('section', 'follow-picker');
  const search = make('input', 'follow-search');
  search.type = 'search';
  search.placeholder = 'Search First Nations';
  search.setAttribute('aria-label', 'Find your community');
  search.addEventListener('input', paintChoices);
  const choices = make('div', 'follow-choices');
  const pickerStatus = make('p', 'follow-device-status');
  pickerStatus.setAttribute('role', 'status');
  picker.append(search, choices, pickerStatus);
  const toolbar = make('div', 'follow-toolbar');
  const more = make('button', 'follow-text-button', 'More updates');
  more.type = 'button';
  more.addEventListener('click', () => { visibleLimit += 8; paint(); });
  const read = make('button', 'follow-text-button', 'Mark all as read');
  read.type = 'button';
  read.addEventListener('click', () => {
    for (const item of items()) {
      if (isUnread(item, following)) following[item.communityId] = item.updatedAt;
    }
    save();
    paint();
  });
  toolbar.append(more, read);
  const body = make('div', 'follow-inbox-body');
  body.setAttribute('aria-live', 'polite');
  const deviceRow = make('div', 'follow-device');
  const deviceButton = make('button', 'follow-read');
  deviceButton.type = 'button';
  const testAlert = make('button', 'follow-read', 'Send test alert');
  testAlert.type = 'button';
  testAlert.hidden = true;
  const deviceStatus = make('span', 'follow-device-status');
  deviceStatus.setAttribute('role', 'status');
  deviceRow.append(deviceButton, testAlert, deviceStatus);
  const stream = make('div', 'follow-stream');
  stream.append(body);
  dialog.append(top, currentName, identity, picker, deviceRow, stream, toolbar);
  document.body.append(dialog);
  const updateExpanded = () => bell.setAttribute('aria-expanded', String(panelOpen()));
  dialog.addEventListener(supportsPopover ? 'toggle' : 'close', updateExpanded);
  updateExpanded();

  const supportsDevice = 'Notification' in window && 'serviceWorker' in navigator && (!push || 'PushManager' in window);
  function paintDevice() {
    deviceRow.hidden = !managing || (!selectedId() && !deviceSince) || choosing;
    deviceButton.hidden = !supportsDevice;
    if (!supportsDevice) {
      testAlert.hidden = true;
      deviceStatus.textContent = push
        ? 'Device alerts need a supported browser. On iPhone or iPad, open OpenBand from your Home Screen.'
        : 'Device alerts are unavailable in this browser.';
      return;
    }
    deviceButton.textContent = deviceSince ? 'Turn off device alerts' : 'Enable device alerts';
    testAlert.hidden = !deviceSince;
    deviceStatus.textContent = push ? 'Get alerts even when OpenBand is closed.' : 'Alerts work while OpenBand is open.';
  }

  deviceButton.addEventListener('click', async () => {
    deviceButton.disabled = true;
    try {
      if (deviceSince) {
        if (push) await push.disable(await getDeviceWorker());
        localStorage.removeItem(deviceKey);
        deviceSince = '';
      } else {
        if (!push && await Notification.requestPermission() !== 'granted') {
          deviceStatus.textContent = 'Allow notifications in your browser to receive device alerts.';
          return;
        }
        const registration = await getDeviceWorker();
        if (push) await push.enable(registration, following);
        const enabledAt = new Date().toISOString();
        localStorage.setItem(deviceKey, enabledAt);
        deviceSince = enabledAt;
      }
      paintDevice();
    } catch {
      deviceStatus.textContent = 'Device alerts could not be set up on this browser.';
    } finally {
      deviceButton.disabled = false;
    }
  });

  function getDeviceWorker() {
    deviceWorker ||= navigator.serviceWorker.register('/follow-notifications.js')
      .then(() => navigator.serviceWorker.ready)
      .catch(error => { deviceWorker = null; throw error; });
    return deviceWorker;
  }

  testAlert.addEventListener('click', async () => {
    try {
      if (push) {
        await push.testAlert();
        deviceStatus.textContent = 'Test alert queued. You can close this tab now.';
        return;
      }
      const registration = await getDeviceWorker();
      await registration.showNotification('OpenBand test alert', {
        body: 'New updates from communities you follow will appear here.',
        icon: '/assets/favicon.svg',
        tag: 'openband-follow-test',
        data: { path: roster?.[selectedId()]?.path || feed?.communities[selectedId()]?.path },
      });
    } catch {
      deviceStatus.textContent = 'The browser could not show a device alert.';
    }
  });

  async function sendDeviceAlerts() {
    if (push || !deviceSince || !supportsDevice || Notification.permission !== 'granted') return;
    const incoming = items().filter(item => isNewForDevice(item, following, deviceSince));
    if (!incoming.length) return;
    try {
      const registration = await getDeviceWorker();
      // Follows or consent can change while a worker is starting.
      registration.active?.postMessage({ type: 'openband-new-items', items: incoming
        .filter(item => deviceSince && isNewForDevice(item, following, deviceSince))
        .map(item => ({
          id: item.id, title: item.title, category: categories[item.kind],
          community: feed.communities[item.communityId].name, path: feed.communities[item.communityId].path,
        })) });
    } catch {
      deviceStatus.textContent = 'Device alerts are temporarily unavailable.';
    }
  }

  function dateLabel(value) {
    if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return '';
    return new Date(value + 'T12:00:00Z').toLocaleDateString(undefined, { month: 'short', day: 'numeric', timeZone: 'UTC' });
  }

  function metadata(item) {
    if (item.kind === 'events') return dateLabel(item.startDate);
    if (item.kind === 'jobs') return item.closingDate ? `Apply by ${dateLabel(item.closingDate)}` : 'See employer posting';
    return dateLabel(item.date);
  }

  function paint(error = false) {
    const rows = items();
    const unread = rows.filter(item => isUnread(item, following)).length;
    badge.hidden = unread === 0;
    badge.textContent = unread > 99 ? '99+' : String(unread);
    bell.setAttribute('aria-label', unread ? `Community updates, ${unread} unread` : 'Community updates');
    if (!panelOpen()) return;
    const id = selectedId();
    const community = roster?.[id] || feed?.communities[id] || (profile?.id === id ? profile : null);
    currentName.hidden = managing || !id;
    currentName.textContent = community?.name || 'My community';
    manage.textContent = managing ? 'Done' : id ? 'Manage' : 'Choose community';
    manage.setAttribute('aria-expanded', String(managing));
    identity.hidden = !managing || !id;
    communityLink.textContent = community?.name || 'Your community';
    if (community?.path) communityLink.href = community.path;
    else communityLink.removeAttribute('href');
    identityIcon.textContent = (community?.name || 'My community').split(/\s+/).slice(0, 2).map(word => word[0]).join('').toUpperCase();
    summary.textContent = persistenceUnavailable ? 'Saved for this tab' : 'Your community on this browser';
    change.textContent = choosing ? 'Done' : 'Change';
    change.setAttribute('aria-expanded', String(choosing));
    picker.hidden = !managing || (!!id && !choosing);
    deviceRow.hidden = !managing || (!id && !deviceSince) || choosing;
    more.hidden = rows.length <= visibleLimit;
    read.hidden = unread === 0;
    toolbar.hidden = managing || (more.hidden && read.hidden);
    stream.hidden = managing;
    if (!picker.hidden) paintChoices();
    body.replaceChildren();
    if (stream.hidden) return;
    if (!id) {
      body.append(make('p', 'follow-empty', 'Choose a community to see its latest updates.'));
      return;
    }
    if (!feed?.communities[id]) {
      body.append(make('p', 'follow-empty', error ? 'Updates are temporarily unavailable. Try reopening the inbox.' : 'Loading updates…'));
      return;
    }
    if (error) body.append(make('p', 'follow-empty', 'Showing the last available updates. Reopen the inbox to retry.'));
    const visible = rows.slice(0, visibleLimit);
    if (!visible.length) body.append(make('p', 'follow-empty', 'Verified updates for your community will appear here.'));
    for (const item of visible) {
      const card = make('article', 'follow-update');
      const meta = make('div', 'follow-update-meta', [categories[item.kind], metadata(item)].filter(Boolean).join(' · '));
      if (isUnread(item, following)) meta.append(make('span', 'follow-new', 'New'));
      const link = make('a', 'follow-update-title', item.title);
      link.href = item.sourceUrl;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      card.append(meta, link);
      body.append(card);
    }
  }

  function ensureRoster() {
    if (roster) return Promise.resolve(roster);
    rosterRequest ||= fetch(feedURL('communities'))
      .then(response => {
        if (!response.ok) throw Error('Community list unavailable');
        return response.json();
      })
      .then(data => { roster = data; paint(); return roster; })
      .catch(() => { pickerStatus.textContent = 'Could not load communities. Reopen the inbox to retry.'; })
      .finally(() => { rosterRequest = null; });
    return rosterRequest;
  }

  function paintChoices() {
    choices.replaceChildren();
    const query = search.value.trim().toLocaleLowerCase();
    if (!roster) {
      pickerStatus.textContent = 'Loading communities…';
      return;
    }
    if (!query) {
      pickerStatus.textContent = 'Choose one community to see its updates here.';
      return;
    }
    const matches = Object.entries(roster).filter(([id, community]) =>
      id.includes(query) || community.name.toLocaleLowerCase().includes(query));
    pickerStatus.textContent = matches.length ? '' : 'No communities match that search.';
    for (const [id, community] of matches.slice(0, 8)) {
      const button = make('button', 'follow-choice');
      button.type = 'button';
      button.disabled = id === selectedId();
      button.append(make('span', '', community.name), make('small', '', community.province));
      button.addEventListener('click', async () => {
        button.disabled = true;
        if (await setCommunity(id)) {
          choosing = false;
          search.value = '';
          paint();
          change.focus();
        } else {
          pickerStatus.textContent = 'Could not change your community. Try again.';
          button.disabled = false;
        }
      });
      choices.append(button);
    }
  }

  function ensureFeed(force = false) {
    const id = selectedId();
    if (!id) return Promise.resolve(null);
    if (pending?.id === id) return pending.promise;
    if (!force && feed?.communities[id] && Date.now() - lastLoaded < 45000) return Promise.resolve(feed);
    const request = { id };
    request.promise = fetch(feedURL(id), { cache: 'no-cache' })
      .then(response => {
        if (!response.ok) throw Error('Follow feed unavailable');
        return response.json();
      })
      .then(data => {
        if (data.schemaVersion !== 1 || !data.communities?.[id] || !Array.isArray(data.updates)) throw Error('Invalid follow feed');
        if (selectedId() !== id) return null;
        data.updates = data.updates.filter(item => categories[item.kind] && item.communityId === id &&
          typeof item.updatedAt === 'string' && /^https:\/\//.test(item.sourceUrl));
        feed = data;
        lastLoaded = Date.now();
        paint();
        paintButton();
        void sendDeviceAlerts();
        return data;
      })
      .catch(() => { if (selectedId() === id) paint(true); return null; })
      .finally(() => { if (pending === request) pending = null; });
    pending = request;
    return request.promise;
  }

  function feedURL(id) {
    return push ? push.feedURL(id) : `/follow-data/${id}.json`;
  }

  const follow = make('button', 'follow-button');
  follow.type = 'button';
  follow.hidden = true;
  const followStatus = make('span', 'follow-device-status');
  followStatus.setAttribute('role', 'status');
  follow.addEventListener('click', async () => {
    if (!profile) return;
    follow.disabled = true;
    followStatus.textContent = '';
    if (!await setCommunity(selectedId() === profile.id ? '' : profile.id)) {
      followStatus.textContent = 'Could not update device alerts. Try again.';
    }
    follow.disabled = false;
  });

  let changingCommunity = false;
  async function setCommunity(id) {
    if (changingCommunity) return false;
    const next = id ? { [id]: new Date().toISOString() } : {};
    changingCommunity = true;
    try {
      if (push && deviceSince) await push.sync(await getDeviceWorker(), next);
      following = next;
      feed = null;
      save();
      paintButton();
      paint();
      void ensureFeed();
      return true;
    } catch {
      return false;
    } finally {
      changingCommunity = false;
    }
  }

  function paintButton() {
    follow.hidden = !profile;
    if (!profile) return;
    const pressed = selectedId() === profile.id;
    follow.textContent = pressed ? '✓ Following' : selectedId() ? 'Switch' : 'Follow';
    follow.setAttribute('aria-label', pressed ? `Unfollow ${profile.name}`
      : selectedId() ? `Switch my community to ${profile.name}` : `Follow ${profile.name}`);
    follow.setAttribute('aria-pressed', String(pressed));
    const actions = document.querySelector('#results .ch .tool-actions');
    if (actions && follow.parentElement !== actions) actions.prepend(follow, followStatus);
  }

  window.OpenBandFollow = {
    renderProfile(band) {
      profile = { id: String(band.id), name: band.name };
      paintButton();
    },
  };
  bell.addEventListener('click', () => {
    if (panelOpen()) {
      if (supportsPopover) dialog.hidePopover();
      else dialog.close();
      return;
    }
    managing = false;
    choosing = false;
    visibleLimit = 4;
    if (supportsPopover) dialog.showPopover({ source: bell });
    else dialog.showModal();
    updateExpanded();
    paint();
    if (selectedId()) void ensureFeed(true);
  });
  window.addEventListener('storage', event => {
    if (![storageKey, deviceKey, null].includes(event.key)) return;
    following = readFollowing();
    deviceSince = readDeviceSince();
    paint();
    paintButton();
    paintDevice();
    void ensureFeed();
  });
  function refreshFollowing() {
    if ((!document.hidden || deviceSince) && Object.keys(following).length) void ensureFeed();
  }
  window.addEventListener('focus', refreshFollowing);
  window.setInterval(refreshFollowing, 60000);
  paintDevice();
  paint();
  refreshFollowing();
  if (new URLSearchParams(location.search).get('updates') === '1') bell.click();
})();
