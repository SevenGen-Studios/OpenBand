#!/bin/sh
set -eu

staging_origin=https://openband.kakakawaybrennan-ee1.workers.dev

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
