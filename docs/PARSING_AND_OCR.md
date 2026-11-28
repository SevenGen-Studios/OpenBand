# Financial parsing and OCR runbook

Read AGENTS.md and README.md first. This document explains the financial extraction process. Source code and workflow definitions remain authoritative when behavior changes.

## End-to-end process

1. Discover the official filing for the correct Nation, document type and fiscal year. A roster entry, a posted PDF and usable extracted amounts are three different facts.
2. Preserve its source URL, document identity and digest where recorded. Reuse an existing validated result rather than replacing it with a weaker extraction.
3. Try native PDF text/table extraction. Select the actual current-year column. Budget, comparative-year, consolidated and entity-only columns must not be mixed.
4. If native extraction does not validate, try free local OCR. OCR reads page images into text and positioned cells; the financial parser must still interpret rows, headings, roles and columns.
5. Where configured, try the optional Docling structured-document adapter. Its output also requires financial validation.
6. Paid OpenAI extraction is an explicit last resort. An available API key alone does not authorize paid usage.
7. Reconcile results against the document. Hold ambiguous or incomplete records for review rather than presenting them as parsed.
8. Review the diff and evidence, apply through the relevant pipeline, run tests/audits, regenerate routes where required, then verify the public record after an authorized deployment.

## Two financial pipelines

### Remuneration

data.json contains Nation filing entries and people/payment rows. run_scraper.py supplies compatibility parsing and fallback logic; run_scraper_v2.py adds discovery/coverage behavior. tools/merge_previous_data.py preserves prior parsed data and tools/sanitize_data.py removes invalid rows and repairs supported issues.

Check official names, Chief/Councillor roles, months served and each printed payment component. Preserve separate remuneration, travel, expenses, credit-card and other-payment columns. Do not double-count repeated columns, omit continuation pages, substitute organization totals for individual people, or infer missing amounts as zero. Retain source warnings and distinguish reported totals from sums derived from components.

A visually reviewed row can use `sourceNullFields` to identify source blanks or dashes (for example, `["travel", "otherPayments"]`). The normalizer retains those explicitly reviewed absences as null canonical values; this marker does not change unmarked legacy records or authorize treating absent amounts as zero. Keep the original source cells in `reportedComponents`.

Complete, hash-bound manual source reviews can retain omitted names (`sourceNameOmitted`), omitted roles (`sourceRoleOmitted` with `Not specified`), or an all-dash payment row (`sourceAllAmountsUnreported`). These require distinct source-row numbers and matching per-row source hashes. Generic parsing still rejects missing names, missing Chief rows and absent totals. Display labels for anonymous source rows are not personal identities, and all-dash totals remain null. Explicit exchanged ISC listing labels are replayed by source URL/year/hash before applying reviewed rows.

Inspect parse_status, parse_confidence, manual_review_required, warnings and parse_stages when present. Do not assume every pipeline uses identical status strings; consult the producer and frontend status handling.

### Audited Community Capital

tools/capital_parser.py writes capital-data.json separately from remuneration. Its parse_pdf_with_fallbacks function tries native extraction, local OCR, optional Docling output and explicitly enabled OpenAI. It can stop after a publishable result or a not_applicable document. A remuneration-only schedule is not an audited financial statement.

Validate statements of operations, financial position, and applicable changes in net assets/debt. Select the correct actual year and financial scope; reconcile revenue, expenses, surplus/deficit and applicable adjustments. Keep original labels and source references. A numeric extraction or high OCR confidence alone does not establish publishability.

Inspect parseStatus, publishable, warnings, parser and extraction stage records. Unreconciled summaries remain manual-review/partial/error records and must not be relabelled parsed to increase coverage.

## Local OCR engines

tools/local_ocr.py is the shared adapter. Availability depends on the host and installed optional dependencies. Supported paths include Poppler/Tesseract, RapidOCR, Windows OCR bindings, and macOS Apple Vision. Inspect availability() and ocr_pdf_bytes() before configuring an engine.

- The scheduled Linux retry workflow installs poppler-utils and tesseract-ocr.
- OPENBAND_OCR_ENGINE selects an available local engine. Do not assume a macOS engine exists on Linux.
- OPENBAND_TESSERACT_BIN and OPENBAND_VISION_OCR_BIN support explicit binary locations.
- tools/vision_ocr.py is the optional PyObjC Apple Vision adapter. It performs on-device OCR and preserves coordinates.
- requirements-macos-ocr.txt, requirements-windows-ocr.txt and requirements-docling.txt describe optional environments; requirements.txt is the shared baseline.

Missing binaries, page limits, timeouts and engine errors are diagnostic outcomes. They are not permission to fabricate text or mark a filing complete. Fix the environment or keep the filing pending.

## Independent verification workflow

tools/parse_discovered_filings.py is a stricter evidence-driven path, distinct from the generic fallback parser. It uses native PDF geometry with independent OCR checkpoints and checks source digests and actual-year source cells. It can use additional scanned-page cross-check evidence. OCR is evidence, not an approval override.

This command requires a prepared work directory; do not point it at an arbitrary PDF folder and assume it discovers everything:

```sh
python tools/parse_discovered_filings.py --help
python tools/parse_discovered_filings.py --work-dir /absolute/path/to/prepared-work --report /absolute/path/to/report.json
```

The default is a report/proposal run. --apply mutates the target data and capital files. Inspect prepared inputs, proposals, source evidence and conflicts first. Existing validated remuneration rows that conflict with proposed values need review, not silent replacement. Keep private PDF/OCR working caches outside the public repository.

## Bounded execution and review

A bounded Community Capital run supported by the current CLI is:

```sh
python tools/capital_parser.py --help
python tools/capital_parser.py --year 2024-2025 --limit 10
```

This writes outputs: use an isolated checkout and review its data diff and capital-extraction-report.json. --band, --province, --year and --limit bound the work. Do not use --force as a routine default. --use-openai explicitly enables the optional paid stage and requires user authorization for that usage.

For remuneration, inspect the current CLI and .github/workflows/retry-pending.yml before starting. The workflow's use_openai input defaults to disabled and is mapped to OPENBAND_ALLOW_OPENAI. Other entry points have their own explicit options; do not assume one environment variable controls every parser.

Useful audit and verification entry points include tools/manual_review_report.py, tools/audit_data.py, tests/test_tiered_pdf_pipeline.py, tests/test_structured_capital.py, tests/test_parser_quality.py and the current site workflow. Read CLI help before running tools with mutation options.

## When extraction fails

- Wrong Nation/year/type: repair identity or discovery evidence before parsing again.
- Native text missing/garbled: inspect the original PDF and try an available local OCR path.
- Column or continuation ambiguity: inspect all relevant pages; retain review status.
- Totals fail reconciliation: check actual versus budget/prior-year columns, adjustments, funding splits, missing rows and accounting scope. Never change source values simply to force equality.
- OCR disagreement: compare the original page/cells and digests; document the disagreement.
- OpenAI unavailable/quota failure: preserve the best safe result and report the failure. Do not loop paid requests or substitute an unrelated model without authorization.
- Existing good data would be replaced: stop that replacement and isolate the conflicting proposal for review.

## Publication checklist

Preserve original source links, fiscal year, warnings and verification evidence. Test both extraction and publication eligibility. Compare before/after coverage and ensure existing reliable records remain intact. Use the current build/audit workflows and shared data-writer concurrency rules. After authorized publication, verify the live fiscal year, amounts/status and original document link.

Do not claim all historical filings are complete, that OCR is infallible, or that a newly posted year already has validated amounts. Filing-year notifications announce availability; they do not certify extracted financial numbers.
