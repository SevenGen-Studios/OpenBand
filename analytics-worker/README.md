# OpenBand Analytics Worker

This Cloudflare Worker is the optional internal analytics API for the static
OpenBand site and the API for Creator Support. Analytics ingestion stores
coarse, anonymous usage records in D1. It never reads or stores request IP
addresses, raw user-agent strings, names, emails, or other personal information.

## Deploy

1. Create a GA4 web data stream for `https://openband.ca` and keep its public
   measurement ID (`G-...`).
2. Create a D1 database:

   ```bash
   npx wrangler d1 create openband-analytics
   ```

3. Copy `wrangler.toml.example` to `wrangler.toml` and add the returned D1 ID.
   Keep `wrangler.toml` private if it contains account-specific routing data.
4. Apply the schema:

   ```bash
   npx wrangler d1 execute openband-analytics --remote --file schema.sql
   ```

5. Add separate high-entropy secrets. The hash salt must remain stable or
   returning-visitor counts will reset.

   ```bash
   npx wrangler secret put VISITOR_HASH_SALT
   npx wrangler secret put ANALYTICS_ADMIN_TOKEN
   ```

6. Deploy the Worker and attach a custom domain such as
   `analytics.openband.ca`:

   ```bash
   npx wrangler deploy
   ```

7. In the GitHub repository, add Actions variables:

   - `OPENBAND_GA4_ID`: the GA4 measurement ID
   - `OPENBAND_ANALYTICS_ENDPOINT`: for example,
     `https://analytics.openband.ca/v1/events`
   - `OPENBAND_ANALYTICS_ENABLED`: `true`

8. Run **Build static OpenBand routes**. The workflow writes the public IDs to
   `assets/analytics-config.js`. Neither value is a secret.

The dashboards at `/admin/analytics/` and `/admin/intelligence/` ask for
`ANALYTICS_ADMIN_TOKEN` and keep it in memory only. For an additional gate,
protect `/admin/*` with Cloudflare Access. Never put the administrator token in
GitHub variables, frontend code, URLs, or browser storage.

## OpenBand Intelligence

`GET /v1/intelligence` is protected by the same bearer token as the traffic
dashboard. The Worker fetches OpenBand's existing `data.json`, builds the
normalized metrics and research signals server-side, and caches the derived
report in Worker memory for five minutes. No intelligence report is committed
to the public Pages repository and the browser never computes signals from the
public dataset.

The optional `INTELLIGENCE_DATA_URL` variable defaults to
`https://openband.ca/data.json`. Supported authenticated sections are:

- `section=overview`
- `section=leads`, with Nation, official, year, type, and strength filters
- `section=officials`, with Nation, official, and year filters
- `section=nations`, with Nation and year filters
- `section=quality`

Every lead includes a source-filing URL or filing-level provenance where the
source data provides it. Missing values remain null, reported totals are not
synthesized, and travel, expenses, credit-card amounts, and other payments stay
distinct. The dashboard repeatedly states that signals require manual source
verification and are not findings of wrongdoing.

## Privacy and retention

- Browser tracking runs only on the configured production host.
- Do Not Track disables both GA4 and the internal endpoint.
- Search text is reduced to a matched community name or `unmatched_query`.
- Visitor IDs are random, rotate on the client, and are SHA-256 hashed again at
  the Worker with a private salt.
- Country and province come from Cloudflare's coarse edge metadata.
- The scheduled task deletes events after `DATA_RETENTION_DAYS` (760 by
  default).
- The API exposes aggregates only; there is no raw-event reporting route.

## Operations

Check `GET /health` after deployment. The event endpoint accepts batches at
`POST /v1/events`. The protected dashboard endpoint is
`GET /v1/dashboard?days=30` with an `Authorization: Bearer ...` header.
The protected financial-intelligence endpoint is
`GET /v1/intelligence?section=overview` with the same authorization header.

## Growth reporting and operations (tracking version 2)

The admin home now reads the published news, jobs, and events coverage reports,
shows their generation times, review queues, source failures, and freshness,
and checks the analytics health endpoint. A healthy HTTP response alone does
not prove event ingestion; inspect the dashboard's last receipt and version-2
session count. Reports older than 48 hours need a freshness review.

The authenticated dashboard adds equal-length previous-period comparisons,
useful outcome sessions, visible-page engagement, search failures, event errors,
first-page campaign attribution, refresh, JSON export, and sign-out. “Today” and
daily date labels use Saskatchewan time; period comparisons use rolling 7/30/90/365
day windows. The current day is partial. Outcome events count distinct sessions
and can overlap; this is not an ordered funnel. Source clicks and application
clicks are intent signals, not proof of successful loading or application.

Browser session IDs rotate after 30 minutes without recorded activity. Visible
engagement is recorded in incremental blocks, and anonymous IDs remain estimates:
blocked storage, tab separation, browser restrictions, and retries affect counts.
Admin routes and Do Not Track are excluded. Query strings allow only band/year/
province; acquisition keeps validated utm_source/utm_medium/utm_campaign values.
Job searches keep a matched/unmatched flag rather than typed search text.
Retries are at least once; this release does not introduce event deduplication.

### Release order

1. Deploy `analytics-worker/src/index.ts` with the **existing** D1 binding, hash
   salt, and administrator token. No database migration is required. Keep the
   salt stable. Verify `/health` and authenticated `/v1/dashboard?days=7`;
   the response must contain `growth`. Health now supports the allowed origins.
2. Publish the frontend via the repository's normal Pages build. Verify the
   tracking asset uses version `20261011a` and the admin home loads its reports.
3. In GA4's web stream, review Enhanced Measurement history-based page views:
   manual route pageviews are already sent by OpenBand, so disable the overlapping
   history change collection to avoid double counting. `send_page_view:false`
   alone does not disable Enhanced Measurement history tracking. See
   https://developers.google.com/analytics/devguides/collection/ga4/views.
4. Confirm source open, CSV download, successful citation copy, profile share,
   and job application click in GA4 DebugView and the internal action report.
   Test an unmatched search; inspect the failed-search count. Verify recent event
   receipts, then compare the next complete 7-day period to its predecessor.

New engagement and campaign fields are prospective. Historical data is not
backfilled; averages use version-2 sessions only. If the frontend ships first,
the dashboard explicitly reports that the Worker needs the growth update while
existing reporting remains available. Production verification requires an
administrator sign-in and Cloudflare deployment access.

Run `node tests/test_analytics_runtime.js` from the repository root, and
`python -m unittest discover -s tests -p 'test_analytics*.py'`. Reporting tests
execute the dashboard SQL against SQLite, including equal-length boundaries,
distinct outcome sessions, and ISO timestamp handling.

## Creator Support

The donation page and admin report use this Worker through the existing
`OPENBAND_ANALYTICS_ENDPOINT` public configuration. Checkout starts disabled.
The admin report uses the existing `ANALYTICS_ADMIN_TOKEN`. D1 holds Checkout
and PaymentIntent references, amounts, timestamps, and statuses. Donor names,
email addresses, and card details stay with Stripe. Refunds are managed in Stripe.

### Configure and test

1. Use a staging Worker and D1 database with a staging site in
   `ALLOWED_ORIGINS`. Keep the production configuration disabled during testing.
   Apply the donation migration to the bound D1 database and add the
   `CREATOR_SUPPORT_RATE_LIMIT` binding from the example Wrangler configuration
   with a unique namespace ID. Use Wrangler 4.36 or newer.

   ```bash
   npx wrangler d1 execute openband-analytics --remote --file creator-support.sql
   ```

2. In your Stripe sandbox, set up a snapshot webhook for events from your own
   account at `https://YOUR-WORKER-HOST/v1/creator-support/webhook`. Select
   `checkout.session.completed`, `checkout.session.async_payment_succeeded`,
   `checkout.session.async_payment_failed`, `checkout.session.expired`,
   `refund.created`, `refund.updated`, and `refund.failed`. Use API version
   `2025-06-30.basil` for the endpoint. Checkout uses Stripe's standard hosted
   domain, one-time card payments in CAD, and server-created prices.

3. Store the Stripe API key and the webhook endpoint's signing secret as
   Cloudflare Worker secrets. Use a test key with the test endpoint.

   ```bash
   npx wrangler secret put STRIPE_SECRET_KEY
   npx wrangler secret put STRIPE_WEBHOOK_SECRET
   ```

   For a restricted key, allow Checkout Session writes and read access to
   refunds and PaymentIntents. Set `CREATOR_SUPPORT_ENABLED = "true"` under
   `[vars]` and deploy to staging. The Worker derives test or live mode from
   the Stripe key, rejects webhooks from the other mode, and separates the
   records in the admin report.

4. Verify each preset and a custom amount, including $2.00 and invalid
   values. Complete, cancel, and decline a Checkout in the sandbox. Resend
   the completed webhook, then issue partial and full refunds. Check that
   the thank-you page only appears after a verified payment and that
   `/admin/creator-support/` reports one successful payment for each paid
   session. Amounts are net of successful refunds, before Stripe fees.
   The count measures payments completed, including payments refunded later.

### Enable live donations

Activate the Stripe account, configure payouts, and create a separate
live-mode webhook with the same event selection. Apply the migration and
configure the rate limit on the production Worker, add the live API key and
live webhook signing secret, and set `CREATOR_SUPPORT_ENABLED = "true"` in
production. Verify the first live payment and its webhook delivery in Stripe
and Creator Support. To pause new checkouts, set the flag to `"false"` and keep
the production webhook and secrets active for existing payments and refunds.
