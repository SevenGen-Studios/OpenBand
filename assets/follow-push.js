(() => {
  'use strict';

  // Set the origin of the deployed Follow Worker when enabling the live pilot.
  const endpoint = 'https://openband-follow.kakakawaybrennan-ee1.workers.dev';
  if (!endpoint) return;

  const tokenKey = 'openband-follow-token-v1';
  let config;
  let lastVersion = 0;

  function prepare() {
    config ||= fetch(endpoint + '/v1/config', { cache: 'no-store' })
      .then(response => {
        if (!response.ok) throw Error('Push setup unavailable');
        return response.json();
      })
      .then(({ publicKey }) => {
        if (!/^[\w-]{87}$/.test(publicKey)) throw Error('Invalid push key');
        const base64 = publicKey.replace(/-/g, '+').replace(/_/g, '/');
        return Uint8Array.from(atob(base64 + '='), character => character.charCodeAt(0));
      })
      .catch(error => { config = null; throw error; });
    return config;
  }

  async function save(subscription, follows, token) {
    const version = Math.max(Date.now(), lastVersion + 1);
    lastVersion = version;
    const response = await fetch(endpoint + '/v1/subscription', {
      method: 'PUT',
      headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' },
      body: JSON.stringify({ subscription, follows, version }),
    });
    if (!response.ok) throw Error('Push preferences unavailable');
  }

  window.OpenBandPush = {
    prepare,
    feedURL: id => endpoint + '/v1/feed/' + id,
    async testAlert() {
      const token = localStorage.getItem(tokenKey);
      if (!token) throw Error('Push subscription missing');
      const response = await fetch(endpoint + '/v1/test-alert', {
        method: 'POST', headers: { Authorization: 'Bearer ' + token },
      });
      if (!response.ok) throw Error('Push test unavailable');
    },
    async enable(registration, follows) {
      const applicationServerKey = await prepare();
      let token = localStorage.getItem(tokenKey);
      let subscription = await registration.pushManager.getSubscription();
      if (!token && subscription) {
        await subscription.unsubscribe();
        subscription = null;
      }
      if (!token) {
        token = Array.from(crypto.getRandomValues(new Uint8Array(32)),
          byte => byte.toString(16).padStart(2, '0')).join('');
        localStorage.setItem(tokenKey, token);
      }
      const created = !subscription;
      subscription ||= await registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey });
      try {
        await save(subscription, follows, token);
      } catch (error) {
        if (created) await subscription.unsubscribe();
        throw error;
      }
    },
    async sync(registration, follows) {
      const subscription = await registration.pushManager.getSubscription();
      const token = localStorage.getItem(tokenKey);
      if (!subscription || !token) throw Error('Push subscription missing');
      await save(subscription, follows, token);
    },
    async disable(registration) {
      const subscription = await registration.pushManager.getSubscription();
      const token = localStorage.getItem(tokenKey);
      if (subscription) await subscription.unsubscribe();
      if (token) {
        try {
          const response = await fetch(endpoint + '/v1/subscription', {
            method: 'DELETE', headers: { Authorization: 'Bearer ' + token },
          });
          if (response.ok) localStorage.removeItem(tokenKey);
        } catch { /* The device has already unsubscribed. */ }
      }
    },
  };
})();
