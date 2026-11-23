# OpenBand agent guide

## Purpose and scope

OpenBand (https://openband.ca) makes source-linked First Nations public records easier to find and understand. It includes remuneration filings, audited Community Capital summaries, community news, jobs, events, projects, and related community information.

Read this guide and README.md before editing. Follow any more specific AGENTS.md in the directory you change. This file provides project context; it does not grant account access, credentials, or permission to publish. Confirm the current user's instructions and available access.

For the detailed financial extraction and OCR process, read [docs/PARSING_AND_OCR.md](docs/PARSING_AND_OCR.md).

## Start here

1. Fetch the latest main and inspect git status, recent commits, and open pull requests. Use an isolated branch or worktree. Preserve concurrent code, data, and generated-route changes.
2. Read README.md and the relevant provincial or feature documentation. Old reports and local checkouts may describe earlier coverage.
3. Derive the current roster and category coverage from the current datasets. Do not reuse community counts from chat history. Application IDs and ISC band numbers are distinct; some application IDs are synthetic.
4. Identify a bounded change, verify its sources, run the relevant checks, and describe what is ready versus what is deployed.

## Repository map

- index.html and assets/: shared frontend. assets/openband.js renders community profiles and news; assets/provinces.js handles shared name matching; assets/nation-name.js handles Nation identity display.
- tools/build_site.py: generates permanent profiles, provincial landings, browse/news routes, metadata, robots.txt, and sitemap.xml. Edit source templates or generators instead of hand-editing hundreds of generated pages.
- data.json: community identities, filing links, remuneration rows, and extraction status.
- capital-data.json: audited financial summaries. Keep it separate from remuneration.
- news-data.json, jobs-data.json, events-data.json, projects-data.json: public community update datasets.
- news-sources.json, jobs-sources.json, jobs-source-registry.json, events-sources.json: source discovery and monitoring configuration.
- jobs-overrides.json: reviewed job records and corrections retained by collection. Publishing an override alone may not immediately update jobs-data.json.
- tools/news_discovery.py, tools/jobs_collector.py, tools/events_discovery.py: collection and validation.
- tools/build_follow_updates.py, follow-updates.json, follow-data/: shared notification/inbox feed and generated per-community data.
- follow-worker/: Web Push service and delivery tests. analytics-worker/ and admin/: analytics collection and administration.
- manual_overrides/ and research/: reviewed corrections and evidence. Inspect existing conventions before adding records.
- .github/workflows/: scheduled collection, ingestion, audit, route generation, and publication. Read the actual workflow before dispatching it.

## Data and editorial rules

- Preserve provenance: original source URL, publisher, published/event/fiscal dates, community association, and verification status. Prefer the Nation, employer, project owner, government source, or organizer's own publication.
- Never invent dates, amounts, ownership, community affiliation, project completion, job availability, or missing financial values. A missing amount is not zero.
- Posted document availability is different from validated extraction. Keep pending/manual-review status when financial rows do not reconcile. Never copy another Nation's records to fill a gap.
- A grant agreement confirms funding and the named recipient; it does not alone establish construction, completion, or Nation ownership. Distinguish a benefiting community from the recipient/provider.
- Keep historical project evidence clearly dated. Do not present an old announcement as a current development.
- For jobs, verify the employer, direct posting, application route, and closing date. Do not revive expired vacancies. Use reviewed overrides where appropriate and verify the final public dataset.
- For events, verify the actual event date and community/organizer. Calendar navigation dates, an organizer directory entry, and a speaker's Nation identity alone do not establish a community event.
- Coverage across news/jobs/events/projects must use consistent community associations. Report whether counts include historical records, regional jobs, current jobs, or upcoming events.
- News previews should be concise and factual. The frontend currently uses conciseNewsSummary to prefer a complete sentence and cap long excerpts around 240 characters. Preserve original sources and avoid rewriting claims beyond the evidence.

## Validation

Read .github/workflows/build-site.yml and feature workflows for current required checks. Typical commands:

```sh
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python tools/build_site.py
node tests/test_provinces.js
node tests/test_follow_inbox.js
```

For Follow Worker changes, run npm ci and npm test inside follow-worker/. Node 22 is used by the site workflow. Run the relevant browser logic suites listed in that workflow for frontend changes.

For coverage batches, check unique IDs and URLs, valid community IDs/names, schema/category/status conventions, date correctness, preserved prior records, and source links. Parser success is not enough: test that an extracted record passes publication filters and reaches the public dataset.

Some tests deliberately fingerprint public assets. For an intentional UI change, inspect the guard, update only the expected fingerprint for the changed asset, and keep unrelated preservation checks intact. Do not disable guards to make CI pass.

## Automation and notifications

- Shared data writers use workflow concurrency. Preserve their serialization and safely reconcile concurrent commits; do not force-push main or discard data updates.
- Inspect the latest run and its logs before retrying. Re-running an old workflow can use old code; use a fresh dispatch on the intended branch when appropriate.
- Preserve existing D1 bindings, VAPID key pair, subscriptions, delivery records, and environment configuration when updating Follow. Setup examples in follow-worker/README.md are not instructions to recreate production resources.
- Filing-year alerts cover posted audited statements and remuneration schedules. The permanent filingYears baseline prevents historical alerts and duplicate alerts for the second document in the same Nation/year. Preserve it.
- Device delivery requires an actual subscribed device. Never claim a phone received a notification from a unit test or provider acceptance alone. Verify current platform support in the code before promising it.
- Do not fabricate public records to test notifications or broadcast test alerts to unrelated subscribers.
- Private GA4 extracts, subscription credentials, secrets, and private analytics belong outside the public repository. Do not commit them. Use authorized connected accounts and never scrape credentials.

## Publishing and handoff

Pushes, pull requests, merges, and deployments are separate actions. Follow the user's current authorization and applicable approval controls. A previous deployment approval is not a blanket grant for unrelated changes.

Before publishing, inspect required CI and relevant failures. An unrelated failing integration check does not prove the site is broken, and a successful build does not prove deployment. Inspect each result and verify the actual production change.

After an authorized rollout, check deployment status and the live asset/data/profile affected. State precisely what shipped, which checks passed, and what remains unverified.

For a future agent or account, leave a PR description with the problem, sources, changed files, validation, and remaining work. This repository is the durable project record; do not depend on private chat memory. Never store tokens, passwords, private account details, or transient access instructions in this guide.
