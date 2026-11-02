# Manitoba data pipeline

This checkpoint includes 63 Manitoba Nations, 488 validated documents (125 audited statements and 363 remuneration schedules), and 420 reserve display parcels. Another 692 documents remain withheld for review and two password-protected files remain blocked. None of the ingestion tools commit, push, deploy or use paid extraction APIs.

## Sources and identity

`manitoba-nations.json` contains the 63 unique band numbers returned by the official ISC First Nations search with province `MB`. ISC's provincial overview independently confirms the 63-Nation target. The roster joins the official treaty-annuity and geographic layers by band number, never by fuzzy name alone: 58 numbered-treaty memberships and five explicitly documented non-signatories. All 63 have ISC geographic points. Population, council, reserves, listed website and governance metadata come from each identity-checked ISC profile page.

Public source snapshots, request provenance and SHA-256 fingerprints are in `tools/manitoba-source-cache/`. The AMC page is retained as a secondary reference. Six AMC public-name variants are linked through unique exact website hostnames also listed on the band-number-verified ISC profiles. Their evidence is retained per alias. Other AMC/common/historical names need band-number-backed reconciliation before addition. Existing ISC and treaty/geographic spelling variants are retained as aliases. ISC-listed website links are not claims that the destination is currently accessible or that its content has been reviewed. Historic remuneration is separate from appointment/current-leadership metadata.

## Reproducible commands

Run from the repository root in an environment containing `requirements.txt`, `lxml`, `pdfplumber`, Pillow and optional free RapidOCR. Use Poppler for OCR rendering. In this workspace the isolated Python environment is `../venv/bin/python`.

```sh
python -m tools.refresh_manitoba_roster --refresh
python -m tools.ingest_manitoba --integrate-roster
python -m tools.ingest_manitoba --discover --workers 2
python -m tools.ingest_manitoba --parse --limit 40 --workers 2
# Resume all remaining never-attempted native documents:
python -m tools.ingest_manitoba --parse --workers 3
# Run a bounded recovery pass; failures stay reviewable:
OPENBAND_OCR_ENGINE=rapidocr OPENBAND_OCR_THREADS=1 python -m tools.ingest_manitoba --parse --ocr --retry --limit 10 --workers 1
python -m tools.merge_manitoba_enrichment
python -m tools.audit_manitoba
python tools/build_site.py
python -m tools.manitoba_baseline
python -m unittest discover -s tests
node tests/test_manitoba.js
node tests/test_missing_filing_years.js
```

`--refresh` on discovery refreshes source pages. Extraction can target `--band-id 266 --year 2022-2023` for a specific retry. `--document-type audited|remuneration` bounds extraction by type. `--reparse` explicitly revisits earlier results; ordinary reruns skip attempted documents. Increment the Manitoba parser revision after interpretation changes before reparsing. Do not run ingestion and enrichment/merge commands simultaneously. The ingestion CLI holds an OS writer lock; parser children save only document checkpoints.

The shared Alberta engine supplies discovery, native PDF text and table-aware extraction, document cover identity/year/type checks, remuneration completeness checks, reported-total reconciliation, free OCR and subprocess isolation. Manitoba uses its own cache, roster, parser revision and worker entry point. Alberta remains the default for the existing command. Document deadlines are 45 seconds native and 180 seconds OCR. Every ten completed documents are merged, and each subprocess result is checkpointed independently under ignored `.openband-ocr/manitoba/`; downloaded PDFs and OCR pages are cached there. Interrupted runs resume rather than start over. No successful checkpoint is treated as validated without the source checks and reconciliation gates.

## Preservation and publication

`tools/manitoba-source-cache/protected-baseline.json` records all original SK/AB IDs, record counts and normalized record fingerprints. Every Manitoba dataset write checks the protected projection before atomic replacement. Band-number collisions are rejected before mutation. Discovery refreshes preserve validated filing rows; failed extraction retries preserve a previously publishable summary. Changes to a document digest never inherit prior remuneration rows.

The coverage audit rechecks preservation. Existing SK/AB financial figures and original source links must remain unchanged. Supporting datasets may add MB rows; their existing SK/AB rows remain fingerprint-protected. Shared parser changes require the existing Alberta and Saskatchewan regression suites.

The roster itself is not a claim of complete financial coverage. The report distinguishes checked listings, genuinely posted source links, retrieved PDFs, validated extractions, manual-review documents, technical failures and not-posted fiscal-year/type slots. Source errors cannot become not-posted records. Missing public documents are not findings of noncompliance. Missing financial values are not zero; partial comparisons are not provincial totals.

`manitoba-coverage-report.json` retains Nation-by-Nation fiscal-year and document detail; `manitoba-coverage-report.md` is its readable summary. Only validated source-backed figures enter public financial displays. Password-protected, malformed, ambiguous or unreconciled documents remain withheld with the original citations. Logos remain unverified placeholders until source and visual review. No projects, businesses, jobs, news or election results are inferred from missing records.

The optional `manitoba-ingestion.yml` workflow is manual only, uses read-only repository permissions, and uploads review artifacts. It never commits or deploys. Review batch limits and OCR selection before running it.

## Remaining review

See the current generated coverage report for actual counts; extraction and OCR are deliberately checkpointed and can remain incomplete. Review unresolved identity/year/type flags, duplicates, password/retrieval errors, scanned documents and unreconciled tables against original PDFs. Reconcile additional current Nation names and aliases by verified band number, verify logo assets and community activity sources separately, then review all changes before any commit or deployment.

## Recovery additions

The optional macOS-only Vision helper supplies an independent, local OCR engine. Language correction is disabled; coordinate rows and the same strict source/year, row, footer and financial-column checks still apply. Build it once with Apple's installed Swift SDK:

```sh
mkdir -p .openband-ocr/bin .openband-ocr/swift-module-cache
swiftc -module-cache-path .openband-ocr/swift-module-cache tools/macos_ocr.swift -o .openband-ocr/bin/vision-ocr
OPENBAND_OCR_ENGINE=vision OPENBAND_OCR_THREADS=1 python -m tools.ingest_manitoba --parse --ocr --retry --scans-only --unattempted-ocr --limit 20 --workers 2
```

The macOS OCR service must be accessible to the process; a restricted execution sandbox can prevent it from running. The backend is optional; Linux/Windows and existing default OCR behavior are unchanged. `--unattempted-ocr` is backend-specific, so trying a different engine does not reuse an earlier failed engine's result. `--native-timeout 90 --timeouts-only` permits a deliberate bounded native retry.

Complete visual transcriptions are keyed to the original source hash, band number, year, URL and a digest of the entire review, including transcribed names. Both printed column totals and individual rows are checked. Practitioner qualifications remain visible next to the source link. A scan whose expenses overlap remuneration is withheld rather than added twice.

Two official Dakota Tipi responses are DOCX containers mislabeled by the server as PDF. `tools/manitoba_source_formats.py` recognizes the original format without executing it. Original Word files are retained byte-for-byte under `public/disclosure-sources/`, with their source URL and hash, and are downloadable through the profile's source note. The 2017–2018 embedded table has blank financial columns and lacks an independent Nation/year heading; it remains withheld, not zero. The 2019–2020 table has an accompanying qualified practitioner report; the qualification is retained alongside the transcribed figures.

`python -m tools.revalidate_manitoba_headers` uses the shared strict financial parser on cached native statements whose explicit year headings were previously unreadable. Only header digits are normalized, never monetary rows. `--timeouts-only` evaluates cached native text without repeating expensive table reconstruction. Failed revalidation never overwrites a publishable alternate source.

`python -m tools.build_manitoba_boundaries --refresh` appends Manitoba-only official display geometry and joins by ISC reserve numbers with exact administrative-owner fallback. The original SK/AB feature fingerprints are checked before and after; no protected geometry is rebuilt. All 420 Manitoba parcels passed the existing topology rules and all 63 Manitoba communities have source-backed parcel associations. The display layer is not a legal survey.
