# Alberta data and maintenance

OpenBand uses the existing `data.json`, `capital-data.json`, profile generator, map/contact/member/logo sidecars, enterprise schema, and shared financial and remuneration parsers for both provinces. The original 69 Saskatchewan profiles remain in place. Alberta adds 48 government profiles.

Source-level regression testing also identified an existing expense-row defect in Muskeg Lake statements: the annual excess was being counted as an expense. Seven summaries were corrected after rechecking the original ISC PDFs. The 2018-2019 summary remains withheld because re-extraction does not reconcile. `manual_overrides/muskeg-lake-parser-review.json` preserves every previous summary and the new extraction for review. All other Saskatchewan financial summaries and datasets are unchanged.

## Identity reconciliation

[Alberta](https://www.alberta.ca/first-nations-relations) recognizes 48 First Nations. The reviewed roster in `alberta-nations.json` contains 47 distinct ISC band numbers plus the separately administered Whitefish Lake First Nation #128 government, which shares ISC 462 with Saddle Lake. Its stable application ID is `ab-whitefish-lake-128`; `iscBandNumber` remains 462. Its population, leadership, location, and financial totals are not copied from Saddle Lake.

Stoney Tribal Administration (471) is an umbrella for Bearspaw (473), Chiniki (433), and Goodstoney (475). It is linked as a shared disclosure source, not indexed as a fourth Nation or allocated to three sets of financial totals. Onion Lake (344) keeps its existing Saskatchewan profile; the Alberta directory links that cross-border community without adding it to Alberta's 48-government count.

Treaty membership is sourced from ISC's treaty-annuity list and the cited Alberta source for Whitefish Lake #128, rather than inferred from coordinates. Corrected names and historic aliases are retained across roster refreshes. The source snapshots used to reproduce the roster are in `tools/alberta-source-cache/`.

## Updating public disclosures

Install `requirements.txt`, `lxml`, and `Pillow`. PDFium comes with pdfplumber. Free OCR requires Poppler plus Tesseract or RapidOCR; no OpenAI or paid extraction is enabled by this pipeline.

```sh
python -m tools.ingest_alberta --refresh-roster --discover --refresh
python -m tools.ingest_alberta --parse --workers 3
python -m tools.merge_alberta_enrichment
python -m tools.audit_alberta
python tools/manual_review_report.py
python tools/build_site.py
python -m unittest discover -s tests
node tests/test_provinces.js
```

The discovery stage checks every supported ISC page and retains only actual posted links for 2014-2015 through 2025-2026. Unavailable pages remain errors rather than becoming claims that no filing exists. PDF download caches and per-document parser checkpoints live in ignored `.openband-ocr/alberta/`. Do not run two ingestion/merge processes against the shared JSON files simultaneously.

```sh
# Retry a bounded set of unresolved scans using free local OCR.
python -m tools.ingest_alberta --parse --ocr --retry --limit 20 --workers 2
# Revalidate existing documents after parser changes.
python -m tools.ingest_alberta --parse --reparse
# Revalidate only audited statements after an accounting-parser change.
python -m tools.ingest_alberta --parse --reparse --document-type audited
```

The `alberta-ingestion.yml` manually triggered GitHub workflow performs discovery, parsing, validation, generation, and tests, uploads a review artifact, and commits and pushes the validated refresh to main. Review the resulting coverage report and original PDFs. Increment the ingestion parser revision when interpretation changes so old checkpoints cannot bypass new checks.

OCR preserves original page numbers, processes selected cover and statement pages,
and caches successfully recognized text. On machines with limited memory, use
`--workers 1` or `--workers 2`; `OPENBAND_OCR_THREADS` defaults to one per worker.
Downloads reserve disk space for rendering, and the queue checkpoints every ten
documents. Failed recognition remains reviewable and is retried on the next run.
Financial retries reuse extracted text and rebuild geometric tables on statement
pages while retaining the notes and original page positions. Image-only
remuneration PDFs use OCR without repeating native table extraction; a complete
OCR schedule with a reconciled printed footer can validate before geometric
extraction.
For memory-related OCR failures, `python -m tools.retry_alberta_ocr` caches each
recognition result before loading the large financial dataset for merging. It
retries unresolved extraction/OCR errors and contradictory validation flags on
quarantined records. Successful pages survive a later
page failure, while numerically ambiguous pages remain withheld if their
independent cross-check fails.

Windows can also use its installed English OCR language engine through the optional
[WinOCR bindings](https://pypi.org/project/winocr/). With Python 3.12, install
`requirements-windows-ocr.txt` and set `OPENBAND_OCR_ENGINE=windows` before running
the same retry command. Word coordinates preserve financial rows. Pages containing
ambiguous three-digit decimal separators are cross-checked with RapidOCR instead
of guessing whether the source printed a comma. That cross-check runs in a
separate process because loading ONNX alongside the Windows OCR runtime can
crash on some machines. The backend is recorded on the
filing, and its cache is separate from the default OCR cache. A reconciled
operations statement allows OCR to stop after two additional selected pages;
unresolved statements continue through the bounded page selection.

## Interpretation and review

Source URLs, listing pages, document titles, retrieval dates, PDF hashes, parser status, and identity/year checks travel with each indexed filing. Source labels, selected fiscal-year columns, and page references accompany financial values. A known revised PDF cannot inherit remuneration rows from a different URL or hash.

When an explicit PDF cover shows that ISC interchanged its remuneration and
financial-statement labels, the parser uses the document's actual type and retains
`listedDocType`, `listedDocumentTitle`, and the original URL. Alternative table
extraction strategies are validated separately. Numeric names, plural footer
totals, merged columns, implausible amounts, and unreconciled rows cannot qualify
as newly recovered remuneration. Missing names or own-source pay figures are not
filled with guesses. The remuneration review report includes Alberta's
`manual_review` status as well as the legacy `pending_manual_review` status.

Samson's split-funding tables use the printed remuneration and expense subtotals,
without adding federal/own-source funding splits twice. Every expense component,
funding split and footer column must reconcile. The printed `Chief/Councillor`
role is preserved. Pre-extracted native text can validate these tables even when
PDF geometry reconstruction fails. Quarantined records are excluded from validated
coverage counts.

Financial-position and cash-flow fields are extracted only from explicit statement labels. Missing values remain null. Net financial assets are distinct from total assets. Assets versus liabilities plus accumulated surplus is checked when all three are reported; legitimate alternative presentations remain reviewable at the source. Unexplained differences block publication.

The shared parser stops expense rows at an excess/deficiency result, recognizes final operating surplus, and excludes an other-items subtotal when its components are already counted. Source-derived Alexander and Alexis regression fixtures test these cases against the actual reported current-year figures.

Own-source revenue includes only confidently identified lines or an explicit subtotal. Non-ISC revenue is never automatically classified as own-source revenue. Federal revenue includes ISC; own-source subtotals overlap their components and must not be added together. Same-year provincial subtotals count reporting Nations separately for each field, exclude unpublishable/shared summaries, and suppress duplicate source hashes.

Current leadership uses ISC appointment and expiry dates. Appointment dates are not labelled election dates. Historic remuneration is retained separately and follows the shared remuneration parser's column and reconciliation checks. Benefits, travel, and salary are not inferred when headers are unclear.

Official-site discovery evidence is stored in `alberta-enrichment.json`. Business ownership evidence is in `alberta-businesses.json` and merged into `community-enterprise.json`; ownership percentages remain unknown unless explicitly sourced. No business financial metrics are inferred from ownership. To refresh candidate research, run `python -m tools.enrich_alberta`; review its output before merging.

Logos require a visual review and exact local-asset hash in `manual_overrides/alberta-logo-reviews.json`. Generic website discovery cannot overwrite reviewed Alberta marks. Driftpile's municipal-template false positive is rejected. Unverified logos use the existing OpenBand placeholder.

## Coverage and limitations

The October 2, 2026 repair pass is documented in `alberta-fix-report.md`.
The subsequent parser recovery is detailed in `alberta-parser-recovery-report.md`
and its JSON companion, including each originally unresolved source document.
It rechecked all individual ISC disclosure listings, restored ISC-listed reserve
areas for 47 profiles, verified 15 additional logos, corrected official website
links, and recovered four Tthebatthie remuneration years. Missing disclosure
links and failed extraction checks remain explicitly documented rather than
being filled with inferred records. `tools/review_alberta_sources.py` refreshes
website and logo candidates without approving them or changing shared datasets.
Visual decisions and exact asset hashes remain in the logo review overrides.

`alberta-coverage-report.json` is the detailed document and review ledger; `.md` and `.html` provide readable summaries. It lists every Nation, audited and remuneration years, missing periods, source failures, verified businesses/logos, and documents needing review. Roster completion does not imply complete financial coverage.

Bearspaw, Chiniki, Goodstoney, Sawridge, and Whitefish Lake #128 have no individually indexed ISC disclosures in this collection. Shared administration links are provided where available. Official-site candidate reports and alternate versions remain separately labelled until document equivalence and extraction are verified. Website access failures, sparse business research, unverified logos, and scanned or unreconciled financial records remain in the review queue.

The Saskatchewan news, project, jobs, and election-result source collections are not represented as completed Alberta research. Alberta pages show explicit empty states when those records are unavailable. Whitefish Lake #128 has no separately verified map point; Alberta reserve areas are not copied from unrelated or shared records.
