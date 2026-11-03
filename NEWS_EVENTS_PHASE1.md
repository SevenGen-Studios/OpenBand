# News and events infrastructure — Phase 1

The pipeline remains Python + GitHub Actions + static GitHub Pages. It uses the existing community IDs and shared profile/news UI. There are no accounts, subscriptions, Follow buttons, push notifications or paid API dependencies.

## What changed and why

- Both registries now include all 180 identities: SK 69, AB 48 and MB 63. Both CLIs accept `SK`, `AB`, `MB`, `ALL`, including lowercase input. The scheduled/manual workflows include MB, preserve the existing writer concurrency group and stage regenerated Manitoba pages.
- Source candidates reuse ISC-listed contacts and the reviewed Manitoba Nation/partner identity evidence. A listed website is not marked as a working news source merely because a community exists. Sources are scanned and given explicit last-check outcomes. Shared council/partner publishers require local evidence tying each announcement to the particular Nation.
- Linked same-host RSS/Atom feeds are discovered before lower-priority page navigation. Reader comments feeds are excluded. Explicit publisher publication fields are required; feed `updated` timestamps and GDELT `seendate` do not become publication dates. GDELT candidates need publisher detail verification before publication. Facebook remains authorized-Meta-API-only, with token/page-mapping diagnostics and no login-wall bypass.
- HTML parsing ignores scripts/styles and handles void tags without leaking card context. Classifiers use the title before local summary text, with emergency, election/voter and employment specificity. Halloween/gathering/craft topics do not become Healthcare because of page menus. Term/full-time job notices are held for the separate employment system rather than mixed into news.
- Event dates, publication dates, source offsets, times and locations are independent fields. Schema.org Event and explicit iCalendar VEVENT sources are supported. All-day iCalendar DTEND is treated as exclusive. Recurrence rules without expanded occurrences are held for review. Explicit full/cross-year ranges preserve end dates. OCR/PDF candidates keep the existing free extraction path and stricter year/date checks; ambiguous yearless flyers are not published as guessed events.
- Generic homepages and card publication icons cannot become event permalinks/dates. The Fisher River meeting-card regression and calendar `EventID` news-date regression are covered explicitly. Structured cancellation/postponement withdraws an existing schedule. Old valid events can be retained in the archive; current/recent events retain runtime date filtering.
- Repeated source runs merge by community identity and permalink/explicit event UID. Existing IDs and first-discovered timestamps survive updates. Different community IDs never fall back to a similar name in the frontend. Distinct same-day events do not collapse merely because they share a category. Record fingerprints, revisions and update timestamps separate material changes from another scan.
- Review history is deduplicated by finding identity, retains originals and preserves first-seen evidence. Valid historical articles survive source outages. JSON writes are atomic. Requests have per-origin pacing, size limits, bounded page/detail/media counts, TLS verification and redirect/robots checks. Robots unavailability, actual disallow rules, TLS/DNS failures, access restrictions, JavaScript-only sites and unrelated/parked redirects are reported separately.
- Community-specific news links preserve the community ID on reload. Empty states distinguish failed/inconclusive sources and required social authorization from successful scans with no indexed result. The existing layout, provincial themes, financial data, logos, seasonal motion and other product features are retained.

## Measurements and evidence

See `community-intelligence-phase1-report.md` and `.json`. The before snapshot is retained under `research/community-intelligence/2026-11-02/before/`; source sweep reports are retained beside it. Before figures describe old stored records, including misclassified/invalid records subsequently held for review, so raw totals are not a quality target.

The live measurement selected all 180 identities and attempted 178 monitorable news-source entries, followed by targeted Fisher River/Chemawawin checks. The event measurement includes community sources plus shared indexes. Source scans were limited to three pages, two article-detail requests and no OCR media requests for this sweep. These are measured bounded scans, not claims of exhaustive site extraction. The default automation retains free media extraction and broader request limits.

All changed datasets are source-backed; unit-test synthetic fixtures are never copied into the production JSON. Data without a verifiable date/identity stays in the review queue. The old general readiness audit (`tools/audit_community_updates.py`) and its API remain intact; the Phase 1 measurements use a separate audit command.

The old Manitoba preservation regression treated whole news/jobs feeds as immutable, even though they have independent writers. It now continues to check every original financial/profile/identity/logo projection while the news feed is validated by its dedicated ingestion/integrity regressions. Jobs data was already newer than that historical snapshot on the input branch and is unchanged by this work. No financial preservation values or ingestion code were changed.

## Reproduce and maintain

```sh
python -m tools.news_discovery --province ALL --skip-search --workers 6 --timeout 8 --max-pages-per-source 3 --max-details-per-source 2 --max-media-per-source 0
python -m tools.events_discovery --province ALL --workers 6 --timeout 8 --max-pages-per-source 3 --max-media-per-source 0
# Read-only summary of the Phase 1 measurement; add --revalidate only when
# intentionally applying the strict record gates to the saved datasets.
python -m tools.audit_news_events_phase1
python tools/build_site.py
python -m unittest discover -s tests
node tests/test_community_updates_runtime.js
```

Both discovery CLIs also support `--band-id`, `--dry-run` and their existing source controls. Run dataset writers sequentially. Do not silently re-enable a blocked, unrelated or expired-domain source. Confirm identity and current public source URLs before modifying source registries. Never disable TLS validation or override robots rules to increase counts.

## Remaining limitations and Follow readiness

No authorized Meta token was present in this measurement, so Facebook posts were not fetched. Some public websites need JavaScript, have expired certificates, deny access, are unreachable, or redirect to unrelated content. Many communities still lack a current, dated source result even where a readable publisher exists. Comments, job notices, publication-only cards and ambiguous dates are held, not counted as successful coverage.

Stable identities and material-change fields are now suitable for designing a small future Follow pilot. The system is **not ready to promise comprehensive personalized updates or deliver production notifications**: source research, manual review, repeated freshness measurements and Phase 2 delivery/deduplication design are still needed. Nothing sends notifications or subscribes a user today.

## Final validation

- 512 Python tests passed with no skips.
- 13 JavaScript suites passed.
- Generated all 180 community profiles; `git diff --check` passed.
- Browser verified Manitoba news, separate publication/event dates, NCN upcoming workshops, and community selection persistence after reload.
- Financial, jobs, logo and seasonal-motion data/source files remain unchanged from the input branch.
- Work remains local on `codex/news-events-phase-1`; no commit or publication was made.
