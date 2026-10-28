# Public community data readiness — 28 October 2026

Scope: current production checkout at ed37fd23, public news/jobs/events only.
Bandy, hosting, financial data, financial extraction, styling and navigation were
not modified. No paid API calls or server purchases were made.

## Refresh and corrections

- Refreshed all configured jobs sources across both provinces. Verified active
  listings increased from 37 to 43. Eight additional date-unavailable public
  listings remain explicitly labelled; they are not counted as confirmed active.
- Original Ochapowace PDFs confirmed Accounts Payable Clerk (November 4),
  Administrative Assistant (October 29) and Community Health Representative
  (October 30). Explicit Position headers and weekday/time-prefixed deadlines
  now parse correctly. Piikani Administrative Support and Siksika Office Clerk
  postings also gained usable closing dates. Dates are stated in the sources,
  never inferred from filenames or guessed from current-year context.
- Added free pdfplumber native-text fallback before OCR when Poppler is absent.
- Corrected held records can retain stable identifiers when a newly checked
  official document unambiguously matches the same URL and community.
  Conflicting multi-role posters remain held; manual corrections are preserved.
- Partial scans retain actual earlier verification dates for unchanged manual
  listings, without claiming that unscanned sources were checked today.
- Retried news sources for six under-covered communities and added the verified
  Saddle Lake Education Authority post-secondary source. No restrictions or
  Facebook authorization requirements were bypassed.
- Four newly discovered school-calendar notices were initially accepted by the
  old news date gate. Original source checks showed event dates, not publication
  dates. They were held rather than published as new news. The same fix held five
  older calendar-derived news entries already in production. A duplicate
  Ermineskin story was consolidated with its alternate URL retained.
  News ends at 447 records, not an inflated count of 457.
- Retried events sources for Cowessess, Ochapowace, Tsuut'ina, Cold Lake and
  Saddle Lake plus configured shared indexes. Two September 27 entries aged
  outside the recent-event window; 130 events remain. Source-backed dated
  calendar details now separate real headings/body from previous/next links and
  navigation. They require matching source dates, not a URL date alone.
- Scoped news/event coverage reports explicitly identify partial scans.

## Verification

`tools/audit_community_updates.py` produces the read-only
`community-readiness-report.json`: identifier checks, source/publication basics,
job validation/freshness, event publication gates and province-level coverage.
Review history is labelled separately from an actionable pending backlog.

438 Python tests passed with one skip, plus nine JavaScript suites. Browser
checks covered 65 page/viewport combinations at 320, 375, 430, 768 and 1440px,
with no page overflow, clipped control text or JavaScript errors. Financial tests
and source links remain intact. Real-world source availability can change.

## Remaining work, not claimed complete

Hundreds of job candidates still lack reliable detail/status; many historic news
review entries have no verifiable publication date or are not community updates.
Some sources are blocked, unavailable or have certificate problems. Facebook
coverage requires authorized platform access. Source configuration is not proof
of a successful check or that a community has no updates.

Financial data was read for context only: 691 capital records carry `parsed`,
399 `manual_review`, 12 `error`, and 20 `not_applicable`. These are existing status
labels, not independent validation counts. No pending financial record was
promoted or altered in this pass.

Before a later refresh, use the audit's as-of date and current source evidence;
do not reuse today's active-job counts after their deadlines pass.
