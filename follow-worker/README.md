# OpenBand Follow background notifications

The local preview offers device alerts while a tab is open. The optional Follow Worker delivers Web Push when the tab is closed. It reads the same verified inbox feed, sends only items first seen after a device opted in and followed the community, and keeps a delivery record so scheduled runs and retries do not normally send the same alert twice. Changes to existing records stay in the inbox.

The service uses its own D1 database. It stores browser push subscriptions, one selected community per browser, and recent delivery results. It uses a hashed device credential to manage each subscription and has no email or account sign-in requirement.

## Enable on an OpenBand test hostname first

1. In this directory, run `npm ci` and `npm test` with Node 22 or later.
2. Create a dedicated D1 database with `npx wrangler d1 create openband-follow`. Copy `wrangler.toml.example` to `wrangler.toml`, set the new database ID, and apply the schema with `npx wrangler d1 execute openband-follow --remote --file schema.sql`.
3. Generate a VAPID key pair with `npx web-push generate-vapid-keys`. Put the public key and an OpenBand contact address in the Worker configuration. Store the private key with `npx wrangler secret put VAPID_PRIVATE_KEY`. Preserve the key pair so existing device subscriptions remain usable.
4. Set the allowed site origins and the trusted publishing feed URL. The example reads the feed from the public GitHub publishing branch so inbox refreshes and notifications can pick up automated data commits independently of Pages builds. Deploy the Worker and attach an HTTPS hostname. Check `GET /v1/config` and `GET /v1/feed/communities` with an allowed origin.
5. Set the deployed Worker origin in `assets/follow-push.js` and bump that asset's version in the site templates. After previewing the build on the test hostname, pick a community, enable device alerts, and close the tab. On iPhone and iPad, add OpenBand to the Home Screen and open it there before enabling alerts.
6. Publish a verified test update to the test feed. Wait for the scheduled sender to process it, check the device notification, and open it. Run the schedule again and verify the device receives one alert. Unfollow and repeat with a later update to verify that the subscription preferences are respected.

The scheduled sender checks the published feed every two minutes and retries transient failures for up to 48 hours. On a published site, delivery also depends on the browser's permission and its device notification settings. With no Worker origin configured, the published pilot stays disabled and the local preview remains available.
