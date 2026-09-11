# OpenBand Analytics Worker

This Cloudflare Worker is the optional internal analytics API for the static
OpenBand site. It stores only coarse, anonymous usage records in D1. It never
reads or stores request IP addresses, raw user-agent strings, names, emails, or
other personal information.

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
