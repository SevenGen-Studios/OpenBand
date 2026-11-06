#!/bin/sh
set -eu

staging_origin=https://openband.kakakawaybrennan-ee1.workers.dev

# The staging Worker may only open Stripe test sessions.
sed -i 's/env.CREATOR_SUPPORT_ENABLED === "true"/env.CREATOR_SUPPORT_ENABLED === "true" \&\& stripeMode(env) === "test"/' src/creator-support.ts

# Expose only a fixed diagnostic code while testing Checkout in the sandbox.
sed -i 's/  const url = new URL(session.url);/  if (!session.url) throw new Error("stripe_missing_checkout_url");\n  const url = new URL(session.url);\n  if (url.origin !== "https:\/\/checkout.stripe.com") throw new Error("stripe_checkout_host_" + url.hostname);/' src/creator-support.ts
sed -i 's/^  } catch {$/  } catch (caught) {/' src/creator-support.ts
sed -i '/Do not expose or log Stripe response bodies or donor data./a\
    const code = caught instanceof Error ? caught.message : "";\n    if (code.includes("D1_ERROR")) return json({error: "staging_database_error", detail: code.replace(/(?:cs|pi|re)_[a-zA-Z0-9_]+/g, "[reference]").replace(/[a-f0-9-]{24,}/ig, "[id]").slice(0, 200)}, 503);\n    if (code === "stripe_request_failed") return json({error: code}, 503);\n    if (code === "stripe_missing_checkout_url" || code === "invalid_checkout_session" || /^stripe_checkout_host_[a-z0-9.-]+$/.test(code)) return json({error: code}, 503);\n    if (caught instanceof Error) return json({error: "staging_" + caught.name, kind: /fetch|timeout|JSON|URL|bind|body|abort/i.exec(code)?.[0]?.toLowerCase() || null}, 503);
' src/creator-support.ts

mkdir -p staging-site/assets
cp -R ../support staging-site/
cp ../assets/favicon.svg ../assets/openband.css ../assets/creator-support.css ../assets/creator-support.js staging-site/assets/
sed -i 's/content="no-referrer"/content="strict-origin"/' staging-site/support/thanks/index.html
sed -i 's|href="/"|href="https://openband.ca/"|g' staging-site/support/index.html staging-site/support/thanks/index.html

printf '%s\n' 'window.OPENBAND_ANALYTICS_CONFIG = {apiEndpoint: location.origin + "/v1/events"};' > staging-site/assets/analytics-config.js
printf '%s\n' '/*' '  X-Robots-Tag: noindex, nofollow' > staging-site/_headers

cat > wrangler.toml <<EOF
name = "openband"
main = "src/index.ts"
compatibility_date = "2026-08-01"
workers_dev = true

[assets]
directory = "./staging-site"
html_handling = "force-trailing-slash"

[[d1_databases]]
binding = "DB"
database_name = "openband-analytics-staging"
database_id = "adfa2b89-3517-4209-9ae4-7c1e073bd23d"

[vars]
ALLOWED_ORIGINS = "$staging_origin"
CREATOR_SUPPORT_ENABLED = "true"

[[ratelimits]]
name = "CREATOR_SUPPORT_RATE_LIMIT"
namespace_id = "1002"
  [ratelimits.simple]
  limit = 10
  period = 60
EOF
