# OpenBand

OpenBand makes First Nations Financial Transparency Act filings easier to search, inspect, export, and verify.

The public website focuses on Saskatchewan FNFTA Chief and Council remuneration filings. Every displayed result should stay connected to the original Indigenous Services Canada source filing so readers can verify the figures themselves.

## Website Features

- Search Saskatchewan First Nations by name.
- View Chief and Council remuneration rows by fiscal year.
- Open the original Indigenous Services Canada FNFTA filing from each result.
- Export the currently displayed table as CSV.
- Copy a ready-to-use citation for a filing.
- See current data status from `audit-results.txt` directly on the homepage.
- See whether a filing is parsed, pending, not posted, or needs extraction review.

## What Is In This Repo

- `index.html` - homepage and shared static application shell
- `assets/openband.css` / `assets/openband.js` - cacheable shared site assets
- `first-nations/*/index.html` - generated permanent community profile routes
- `browse/index.html` / `news/index.html` - permanent Browse and News pages
- `tools/build_site.py` - generates profile pages, metadata, `sitemap.xml`, and `robots.txt`
- `data.json` - generated filing and remuneration data used by the website
- `map-data.json` - ISC-sourced community locations and tribal-council relationships
- `projects-data.json` - source-linked housing and infrastructure projects shown on community profiles
- `audit-results.txt` - latest coverage and parser-health report
- `scraper.py` - restored core scraper
- `run_scraper.py` - compatibility launcher with parser fallbacks
- `run_scraper_v2.py` - v2 launcher with extra Saskatchewan coverage
- `tools/merge_previous_data.py` - preserves already parsed rows and pending statuses during incremental runs
- `tools/sanitize_data.py` - removes obvious non-person rows and repairs broken totals
- `tools/local_ocr.py` - free local Poppler/Tesseract fallback for scanned remuneration PDFs
- `tools/audit_data.py` - checks coverage and pending parser work
- `tools/capital_parser.py` - extracts validated audited-statement summaries into `capital-data.json`
- `tools/member_count_scraper.py` - updates registered population counts from official ISC First Nation Profiles
- `tools/build_map_data.py` - refreshes the interactive Browse map from official ISC map services

## Browse map data

The Browse map joins tracked OpenBand bands to ISC community locations and
tribal-council relationships by band number. Documented gaps in ISC's council
layer are supplemented from FSIN's Saskatchewan First Nations listings. Refresh
the static map dataset with:

```bash
python tools/build_map_data.py
```

The map keeps original council labels and source URLs alongside short public
display names. A missing relationship is shown neutrally; OpenBand does not
infer an affiliation.

## Community Capital data

Community Capital summaries are stored separately from remuneration data in
`capital-data.json`. The parser targets the statement of operations, statement
of financial position, and change in net assets/debt to extract:

- revenue and expense totals with category breakdowns
- annual surplus or deficit
- cash and investments
- tangible capital assets and annual capital purchases
- reported debt

Run a bounded local batch with:

```bash
python tools/capital_parser.py --year 2024-2025 --limit 10
```

The `Backfill Community Capital data` GitHub Actions workflow supports larger
batches. It tries local PDF extraction, then free Tesseract OCR. Its optional
OpenAI fallback is off by default and only runs after both free stages fail
validation. Summaries that fail reconciliation remain marked for manual review
and are not displayed as parsed data.

Each run also writes `capital-extraction-report.json`, including before/after
coverage, successful and partial records, failed records, non-applicable source
documents, unresolved filings, parser method, and extraction warnings.

## Workflows

- **Scrape FNFTA data**: manual current-year scraper run. It validates the new `data.json` before committing so a bad scrape cannot easily overwrite the working site data.
- **Backfill pending remuneration data**: manual batch parser for reducing the pending posted filing count.
- **Retry pending remuneration parsing**: retries all year groups with local parsing and OCR; its paid OpenAI fallback is an explicit, disabled-by-default option.
- **Sanitize OpenBand data**: cleans parsed rows and refreshes the audit.
- **Audit OpenBand data**: manual/PR health check for missing expected Saskatchewan First Nations and pending posted filings.
- **Update registered population counts**: monthly or manual refresh of sourced ISC registered population totals.
- **Restore working site from openband**: emergency restore from the original working repo.

## GitHub Pages

Use Settings -> Pages -> Deploy from branch -> `main` / `/root`.

After changing `data.json`, `news-data.json`, or the shared site shell, regenerate
the static routes before publishing:

```bash
python tools/build_site.py
python -m unittest tests/test_site_routes.py -v
```

Housing and infrastructure entries must keep their original source URL and
publication or verification date in `projects-data.json`. Omit unverified
costs, dates, capacities, and statuses instead of filling them with estimates.

## Authorized Facebook monitoring

`tools/news_discovery.py` can monitor registered, authorized First Nation
Facebook Pages through Meta's ordinary Graph API. It paginates Page posts,
retains the original permalink and publication date, and adds supported updates
to community news. Strong housing and infrastructure signals from an official
Page are also added to the clearly labelled unverified project feed until a
second public source corroborates the delivery details.

Configure either `META_ACCESS_TOKEN` for an approved app-wide Page access path,
or `META_PAGE_TOKENS_JSON` as a secret JSON object mapping Page IDs or handles to
their authorized Page tokens. Tokens are sent only in the Authorization header
and are never written to URLs or data files.

The ordinary API scanner deliberately does not fetch Facebook Groups, private
content, login-protected material, comments, member profiles, or access-restricted
posts. Group URLs may be retained in the source registry for transparent manual
research, but automated group scraping is prohibited by the pipeline.

The scraper workflows and **Build static OpenBand routes** workflow run this
step automatically for GitHub-hosted updates.

## Analytics

The public site includes a centralized, production-only analytics service in
`assets/analytics.ts` with the compiled browser asset in
`assets/analytics.js`. It lazy-loads GA4, tracks static-route changes, batches
internal events, retries failed submissions, respects Do Not Track, and avoids
arbitrary search text.

The optional internal API and protected aggregate dashboard are in
`analytics-worker/` and `/admin/analytics/`. The site remains fully static;
the API deploys separately to Cloudflare Workers with D1. Analytics is disabled
in the committed default configuration so an unfinished endpoint never collects
or queues data. Follow `analytics-worker/README.md` to deploy it and set the
three GitHub Actions variables that activate production tracking.

## Secrets

No API key is required for normal parser workflows. Both financial pipelines try
local PDF parsing first and free Tesseract OCR second, validate totals, and save
successful results to their JSON data files. OpenAI is a last-resort option that
must be deliberately enabled on a manual workflow run; merely storing
`OPENAI_API_KEY` does not authorize a paid request. Unresolved filings remain
pending for manual review, and successful stored results are reused rather than
parsed again.

## Verification Standard

OpenBand should be used as a transparent index and research lead. Automated extractions are labelled and linked back to source PDFs. For publication, verify exact figures against the original ISC filing linked from the result page.

The standard is not "trust the scraper." The standard is "make public records easier to find, compare, and verify."
