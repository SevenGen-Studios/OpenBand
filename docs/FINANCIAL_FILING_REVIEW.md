# Financial Filing Review

This adds `/admin/financial-filings/` to the existing admin portal. The public
site and existing parsers are unchanged. The Python companion service owns
private SQLite review state and original PDFs. It reuses `bandy_financial` and
`capital_parser` for actual-column selection and page-level financial evidence,
and `local_ocr` for RapidOCR model loading and coordinate grouping.

## Run locally

Use Python 3.12, the existing `requirements.txt`, and Tesseract 5 for an additional
independent engine. PDF rendering uses pdfplumber/PDFium. No API-based financial
extraction is used. Install these dependencies into a dedicated virtualenv;
do not install unreviewed repositories into the service environment.

```sh
python -m pip install -r requirements.txt
python -m tools.filing_review scan
python -m tools.filing_review discover --limit 25
python -m tools.filing_review process --limit 25
python -m tools.filing_review report --output /private/path/coverage.json
python -m tools.filing_review serve
```

Before `serve`, supply the existing `ANALYTICS_ADMIN_TOKEN` through the process
secret environment (at least 24 characters). Never commit a secret or pass one
in a URL. Open `http://127.0.0.1:8765/admin/financial-filings/`, then sign in with
the admin token. The browser retains the token in memory only. The API base is
editable; the same-origin `/v1/filing-review` is the default. Set
`FILING_REVIEW_ALLOWED_ORIGINS` to the exact admin frontend origins when needed.
Only explicit static assets are served: the private state directory, database,
PDFs, and repository data files are never exposed by the static server.

`--years 2021-2022 2022-2023 2023-2024 2024-2025 2025-2026` is the default.
`--state` selects private persistent storage and `--root` selects the working
copy to inspect/import. All provinces and all profiles in `data.json` are
included without a province allowlist. `iscBandNumber` is never inferred from a
profile ID; shared or missing ISC identities require review.

## Source discovery

Government disclosure listings are searched for each slot. Additional official
Nation pages and verified repositories are registered through the admin source
form, including ownership evidence and confirmation of terms/permissions.
Known Nation website addresses appear in slot metadata as research leads; they
are not automatically treated as verified document hosts. Register official
transparency pages and additional PDF/CDN hostnames before crawling them.
Robots, host permissions and public IP addresses are checked before downloads
and every redirect. DNS is pinned for the TLS connection. Authentication,
CAPTCHAs, 401/403 responses and unavailable robots rules are logged and deferred.
Downloads are limited to HTTPS, 40 MB, five redirects and a 30-second socket
timeout. HTML traversal is bounded to one financial-page link level and ten
additional pages per slot. Documents are verified after downloading, regardless
of filenames and link titles.

For search beyond source pages, configure `BRAVE_SEARCH_API_KEY` as a service
secret. The provider returns public URLs using Nation names, roster aliases,
band number, fiscal range, year-end year and financial-report terms. Search
responses are retained in the private search log; unknown hosts require source
registration. No key is needed for government listings or registered pages.
If the provider or any source is unavailable, the search remains incomplete.
“Search Pending” is an operational state, outside the four verification
categories. A blocked/incomplete search never establishes “Not Publicly Located”.
That category requires a completed accessible-source search, no qualifying
candidate and no queued/failed candidate awaiting validation. It always refers
to the search scope, not to whether an audit was prepared or submitted.

Use “Retry search” on a slot after registering sources or resolving access
failures. Previous search attempts are retained. Candidate URLs can also be
submitted manually, but both PDF and source must be on approved public hosts.
Do not register a third-party host without checking original-document provenance.

## Extraction and financial correctness

1. Native PDF text and word boxes come first. Low-text pages use OCR at 300 DPI.
2. Tesseract TSV boxes or RapidOCR boxes are converted to PDF point coordinates.
   The existing parser selects explicit actual-year columns, excludes budgets,
   retains signs/raw cells, and flags ambiguous cells, scaled units and missing
   columns. It does not silently repair O/0, I/1 or decimal punctuation.
3. Native statement pages are cross-checked with an available OCR engine.
   Scanned statement pages need a second, different engine. With one engine,
   they remain review-required. Engines are optional; unavailable engines do not
   silently become successful verification.
4. Figure comparisons require metric, dimension, page and amount agreement,
   with clean source evidence. Derived figures keep their component references;
   identified government components never imply complete government transfers.
5. Revenue/expenses/result, assets/liabilities/accumulated surplus and financial
   assets/liabilities/net debt checks are applied when inputs exist. Separately
   recognized surplus adjustments are considered. A failure requires a source-
   based presentation review, not automatic number changes. Missing inputs
   remain “not applicable or missing inputs”.
6. Unlocated observations without a raw source cell or PDF page are quarantined
   outside importable figures, and approval refuses unlocated values. Every figure retains source/checksum, actual fiscal year, page, title, raw
   cells, normalized value, currency, unit, method, comparison observations,
   confidence and verification status. Comparative-year observations never
   create another verified filing.

The title/cover must identify the Nation, year end and audited statements, and
an independent auditor report must be present. Explicit source band/FY
mismatches block acceptance. Corporation-only title pages are quarantined.
Auditor/opinion detection is conservative and retains report pages. The current
heuristic recognizes selected common auditor names; unidentified names remain
unconfirmed. Non-consolidated audits are labeled explicitly.

The parser runs in a subprocess with a 660-second wall timeout, a CPU limit,
a 300-page ceiling and, on Linux, a 4 GiB address-space limit. Use an unprivileged
container with read-only code, restricted egress and writable private state for
production PDF processing. This is defense in depth, not a malware scanner.

## Review, approval and import

- **Verified:** an administrator has approved the correct document and financial
  presentation; every outstanding issue has a source-page resolution.
- **Review Required:** extraction produced figures requiring adjudication, or
  an indexed audit still needs independent document verification.
- **Document Found — Extraction Pending:** a qualifying audit was located but
  no successful financial extraction is available.
- **Not Publicly Located:** the recorded accessible-source search completed
  without a qualifying audit; this makes no assertion about audit preparation.

Scores are evidence rules, not probabilities: 0 when nothing is extracted,
35 with incomplete evidence, 85 for independently matched, clean figure evidence,
and 95 after documented administrator approval. A numeric confidence score
never grants publication. All unresolved issues require their own page number
and specific written explanation. Approval also requires source/entity/year/
column/unit/presentation confirmation. Incorrect-identity documents cannot be
approved; reject them and submit a correct candidate instead.

Original and proposed values are shown in evidence. The source-checked figure form
can correct an extracted key metric or add a previously unextracted metric; it
requires the exact printed amount, units, actual-year page, statement title and
explanation. It preserves the previous observation in immutable history and
requires subsequent approval. Existing data is never
automatically replaced. Import requires an approved candidate; any existing
summary requires a second explicit replacement action showing the differences.
Previous summaries, source pages, approval evidence and complete before-file
snapshots are kept permanently. History rows cannot be edited or deleted through
SQLite/API operations. Retain and back up the private state directory to retain
this history. The current shared admin bearer token identifies the administrator
role; per-person attribution requires the deployment's authenticated identity
proxy rather than treating an arbitrary browser-provided name as identity.

Import adds an audit filing to `data.json` and source-backed current-year scalar
metrics to the matching `capital-data.json` record. It never guesses mappings
such as cash -> cash plus investments or total liabilities -> interest-bearing
debt. Existing unrelated fields are retained. `sourceReferences` identifies
exactly which metrics were reviewed; retained fields keep their prior provenance
in the immutable before image and are not independently re-extracted by this
import. Review any old breakdowns alongside changed totals before publication.
A source-backed field review map is included with imported records.

Only the private service exposes approve/import routes. CLI discovery/extraction
cannot approve or publish. Imports update a local working copy; the existing
build/release process publishes it after normal repository review. No deployment
or production values are changed by the initial scan.

## Resume, recovery and production integration

SQLite uses WAL and unique slot/candidate keys. Completed discovery slots and
completed extraction candidates are skipped. Failed extractions retry at most
three times with exponential backoff. Expired processing leases are recoverable;
a successful candidate is never reset merely by rescanning. The admin retry
button explicitly resets a failed candidate's attempts. Jobs expose progress,
state and structured errors. Rejected candidates remain rejected.

Use one batch worker per private state directory so host rate limiting remains
serial. The companion server serializes background jobs. On process restart,
old job rows are historical; queued candidates and expired leases are resumed
by the next processing batch. Back up the SQLite database consistently with
SQLite's backup API and retain the matching PDFs and `.backup.json` snapshots.

For production, deploy the Python service as a private loopback/upstream service
behind HTTPS and route `/v1/filing-review/*` to it. Keep the existing static admin
assets on Pages. The analytics Cloudflare Worker stays unchanged: CPU-heavy OCR
and local repository writes do not belong in that Worker. Configure the proxy
and CORS to the actual admin origin, provision the existing admin secret, and
mount a persistent private volume **outside the static document root** plus a
controlled repository checkout. Do not expose Python's development server
straight to the internet. No hosting resources are provisioned by this change.

Pause legacy data-writing jobs during imports: they do not honor the new advisory
lock. The review importer locks concurrent review imports, checkpoints before
images, fsyncs temporary JSON and atomically replaces each file. A crash between
the two replacements is recoverable by rerunning the same approved import;
the candidate ID prevents duplicate filings and repeat replacement prompts.
Run the existing site builder only after both files have been recovered. This
is not a multi-file filesystem transaction.

Tests:

```sh
python -m unittest tests.test_filing_review tests.test_bandy_financial
node --check assets/filing-review.js
```

## OCR repository assessment (2026-11-07)

No new OCR repository is installed as an application dependency.

| Project | Findings | Decision |
| --- | --- | --- |
| [Sheekee search](https://github.com/search?q=Sheekee+OCR&type=repositories) | No verifiable OCR/financial-validation repository located by the name in public searches. License, maintainers and security posture could not be established. | No invented dependency. A concrete repository would need a separate review. |
| [pdf-ocr-financial-documents](https://github.com/morandi-lucas/pdf-ocr-financial-documents) | [MIT license](https://github.com/morandi-lucas/pdf-ocr-financial-documents/blob/main/LICENSE). Described as a portfolio demonstration: Tesseract/PyMuPDF, configurable AI extraction and spreadsheet matching. Python, image memory and optional API resources; introduces another PDF stack and external AI path. Reviewed README/license; dependency file fetch was unavailable. No production maintenance/security guarantees established. | Reuse the existing OpenBand parser instead. No source copied or installed. |
| [FinCriticalED](https://github.com/The-FinAI/FinCriticalED) | MIT code, separately licensed datasets/models. Financial fact evaluation benchmark with entity, time, concept, number and unit checks. Local models or external APIs require additional resources. Repository documents CPU/GPU/platform differences. Not a filing identity/ingestion system; dependency security was not audited. | Adopt fact-level validation principles; keep benchmark optional and do not transmit PDFs to model APIs. |
| [Tesseract](https://github.com/tesseract-ocr/tesseract) | Apache-2.0, established active engine with a security policy; CPU local processing and TSV coordinates. System binary and language data must be maintained by deployment operators. | Supported independent engine. No change to application requirements. |
| [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) | Apache-2.0, active project. Paddle inference/runtime and model assets add platform/resource considerations; table models need separate assessment. Code and model dependencies must be checked for the chosen version. | Defer direct integration; current RapidOCR/Tesseract paths fit the existing pipeline. |
| RapidOCR | Already declared as `rapidocr-onnxruntime==1.4.4` in OpenBand requirements and used by `local_ocr.py`. Local ONNX inference avoids an external financial-data API. Transitive versions are not fully locked by existing requirements. | Reuse existing adapter; pin and vulnerability-scan the production environment before deployment. |

The public repository pages did not establish exact last-release/commit dates
for every project. No claim of a complete security or maintenance audit is made.

## Initial run in this workspace

The November 7, 2026 inventory reviewed all 180 database profiles and 900 default
fiscal-year slots. It found 512 posted/indexed filing slots and 370 summaries
meeting existing parser-valid criteria. Another 136 audit entries were
placeholders without posted document links; these are excluded from the indexed
count. There are 388 slots without an indexed audit and 142 indexed slots
without a parser-valid financial summary. These are coverage gaps, not findings
about whether an audit exists or was submitted.

A rate-limited government-source discovery pass completed for all 900 slots.
Search beyond those listings remains incomplete without a configured search
provider and registered Nation/archive pages. Twelve PDF candidates completed
processing in bounded live validation batches: seven qualifying documents are
awaiting review, including six for previously missing/incomplete records. One
qualifying document produced no financial figures and is counted as an
extraction failure. No document was approved or imported. Wrong-fiscal-year
candidates were flagged; this is why URL discoveries are not counted as filings.

The private `.openband-ocr/filing-review/coverage.json` report, SQLite queue,
search attempts, original PDFs and immutable triage history retain the actual
results. The latest report is regenerated by `report`; counts will change as
batches and reviews proceed. Zero “Not Publicly Located” records in this run
means no comprehensive accessible-source search was completed, not that every
filing was found.

## Automatic whole-database ISC availability scan

`Refresh all First Nation filing availability` runs every day at 10:17 UTC
(**4:17 a.m. Saskatchewan time**) and can also be started from GitHub Actions.
It loads every profile from `data.json`, including any future provinces. It
checks the latest five fiscal years ended March 31, and both the audited
consolidated statements and remuneration schedules. No province or Nation
allowlist restricts the scan. The legacy `review_disclosures` command also now
selects all profiles by default.

```sh
python -m tools.disclosure_scan
python -m tools.disclosure_scan --write \
  --baseline tools/manitoba-source-cache/protected-baseline.json \
  --history disclosure-scan-history.jsonl
```

The first command is read-only for the dataset. Repeat `--year 2023-2024` to
choose a custom range. `--resume` reuses successful checks from the last 24 hours,
retries blocked sources, and invalidates checkpoints when the profile identity
or year range changes. Failed jobs retain their checkpoints as Actions artifacts.
Download the checkpoint into the scan state directory before a manual resume.

Source checks use one shared rate-limited client, honor robots.txt, validate the
ISC band identity and each linked fiscal year/document type, and retry transient
failures at most three times. A missing ISC number or shared ISC identity is
reported for human review; a profile ID is never used as a band-number fallback.
All database profiles still appear in the coverage report. A source outage,
access denial or table-layout failure never turns an existing record into
“Not posted”. A changed source URL or posting date is retained as a revision
warning; previously indexed documents and financial values remain intact.

The scan automatically promotes empty not-posted placeholders or adds absent
source-listed documents. Newly indexed documents are marked posted and pending
financial verification. **It does not publish extracted financial values.**
Existing audited values and remuneration rows cannot be changed by this path.

Before publication the scanner reconstructs and validates the entire proposed
transition against the original dataset and successful source evidence. The
preservation baseline must match the input first. Only then can its `data.json`
fingerprint advance to the metadata-only result. Every update is appended to
`disclosure-scan-history.jsonl` with before/after hashes and source URLs. A
checkpointed publication journal safely recovers an interrupted data/baseline/
history write, and refuses to overwrite newer unrelated changes. History is
versioned in Git; private before/after staging files stay in ignored state.

The workflow uses the existing shared data-writer concurrency group, runs the
full regression suite, rebuilds routes, and pushes without force or automatic
rebasing of generated data. An intervening human edit causes publication to fail
safely and the next run starts from the newer dataset. Unavailable source checks
make the workflow visibly fail **after** safely checked metadata/report updates
are published; unresolved identities remain clearly flagged without inventing
filing ownership.

`disclosure-scan-report.json` records expected/reviewed profiles, successful source
checks, recovery counts, missing document slots, identity issues, source errors,
and retained-record warnings. The existing admin operations overview shows this
scan's freshness and failure counts. The scan is limited to official ISC
availability; the private review pipeline still supports broader Nation/archive
research and PDF/OCR verification.

The initial whole-database scan on November 7, 2026 reviewed all 180 profiles
(69 SK, 48 AB, 63 MB). It checked 179 ISC identities successfully, recovered
33 document links across 17 Saskatchewan Nations, and had no source failures.
Whitefish Lake First Nation #128 remained flagged for shared-identity review.
These recoveries publish document availability, while figures remain subject
to the review process above. See the versioned scan report and change history.
