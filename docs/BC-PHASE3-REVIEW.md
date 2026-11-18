# Phase 3 review

Branch: `codex/british-columbia-phase3`.

The pull request is based on `codex/british-columbia-phase2` (`6e30dfd4`, including the sanitizer follow-up to `ad13f351`), so its diff contains Phase 3 only. The Phase 2 base includes Phase 1 and is a separate prerequisite; production is not changed or deployed. Its automatic sanitizer refreshed seven older job prerenders after the initial push. The Phase 3 merge explicitly restores those seven profiles to the captured original baseline, and limits automatic sanitizer runs to main; manual dispatch remains available.

## Result

- 204 verified government/administration profiles checked; 189 have documents in the checked ISC listings.
- 4,048 indexed ISC source links: 2,033 audited statements and 2,015 remuneration schedules.
- 381 unique official-site PDF candidates remain separate from verified entity/year documents. Bounded official searches and 28 source-access failures are disclosed in the reports.
- 24 downloads and processing attempts; 21 documents yielded native/OCR text. Two audits and one remuneration schedule passed the applicable source review and were explicitly approved by the user.
- 4,024 indexed documents remain unprocessed; 21 processed documents require review. Five have identity/year warnings. One of two free OCR retries recovered text; the other timed out. No OCR result was published.
- Original revenue rows remain cited. Ambiguous inferred own-source/business aggregates were withheld: gaming receipts alone do not establish an owned business or an accounting definition of own-source revenue.
- Comparison logic preserves missing values, contributors and duplicate-source protection. Both new audit summaries remain excluded pending a documented compatible currency/period/entity review. Other frameworks require separate policies.

The user-approved source hashes and batch receipt are in [BC-PHASE3-APPROVAL.json](BC-PHASE3-APPROVAL.json). This approval authorizes only the initial three source documents, and does not authorize future extraction batches or deployment.

## Implementation and operation

The driver reuses `ingest_alberta` bounded workers, `capital_parser`, the existing remuneration parser and local OCR. It replaces their province configuration and public-data writer with BC-only staging. Original native pages, coordinates/provenance from shared parsers, hashes and failures remain available for review. Source URLs are restricted to checked official hosts, including redirect validation; downloads are retried, size bounded and hash checked.

The importer has a separate explicit approval interface. It validates selected candidate keys and the frozen batch hash, source digests, accounting and remuneration quality, duplicates and revisions before an atomic transaction with backups. Both public data files roll back if a replacement or post-write check fails. It cannot change non-BC records.

BC profiles retain the existing tabs and layout. Original document links are available in static and interactive profiles; approved figures use the existing capital and remuneration schemas. BC remuneration views and CSV exports retain exact reported titles and separate missing travel, expenses, benefits and other payments. Calculated combined payments are labelled separately from reported amounts. Returning to another province restores its original table headings.

The manual workflow has read-only repository permissions. It discovers, stages, audits, tests and uploads review artifacts, including original source bytes. It contains no public-data importer, push, merge or deployment.

See [the operating guide](../BRITISH-COLUMBIA-FINANCIALS.md), [fiscal-year coverage](../bc-financial-coverage-report.md) and [the exact changed-file manifest](BC-PHASE3-FILES.txt).

## Validation

- Complete Python run: 582 tests, 577 passed, five existing failures. The same five failures occurred before Phase 3: Cold Lake recovery manifest, Cold Lake historical recovery checkpoint, Day Star/Cote recovery checkpoint, Gordon recovery manifest and the older Manitoba elections fingerprint. No evidence files were rewritten to conceal these failures.
- All 18 JavaScript suites pass, including BC compatibility, period/framework exclusions, missing values and duplicate-source checks.
- 17 focused BC financial pipeline tests pass (including subsequent revision-cache and unavailable-refresh retention tests): verified identity and year scope, official/private URL rejection, cache hashes, approval requirements, invalid candidates, shared documents, preserved baselines, workflow constraints, column/page provenance, financial position, units, OCR timeout state, source rendering and conservative revenue definitions.
- Isolated headless Chrome tests pass for Bonaparte's capital figures, exact Aitchelitz remuneration, 390px mobile overflow, navigation back to Saskatchewan and no runtime console exceptions. Source PDF operations/schedule pages were rendered and visually reviewed.
- The full regression suite rebuilds time-dependent non-BC job prerenders as a side effect. Those seven generated profile changes were restored to the captured baseline before staging; the final preservation audit verifies the original content.
- Protected non-BC data/capital records, 1,831 versioned profile/financial HTML pages plus nine existing untracked pages protected by a separate local baseline, maps, geometry, contacts, population, logos, elections, history, enterprise data and manual overrides remain unchanged. Text fingerprints normalize only CRLF/LF across operating systems.

## Limits requiring review

This PR provides a working staged ingestion and approved-publication path; it does not complete historical extraction. Missing ISC records are not legal noncompliance findings. Bounded government-site exploration can miss archives or differently named documents. Official-site candidates need entity/type/period review; related health authorities, national governments and villages are not automatically interchangeable. Non-March periods, currency definitions, modern treaty frameworks and shared statements remain explicitly excluded from automatic band-government comparison totals until a supported policy exists.

Exact document URLs, source failures, year states and review queues are recorded in the JSON reports. The local OCR/results checkpoint is `.openband-ocr/british-columbia/results.json`; refresh workflow artifacts and its cache preserve subsequent runs. No paid extraction was used.
