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

The `alberta-ingestion.yml` manual GitHub workflow performs discovery, parsing, validation, generation, and tests, and uploads a review artifact. It does not commit or publish changes. Review the resulting coverage report and original PDFs before accepting updates. Increment the ingestion parser revision when interpretation changes so old checkpoints cannot bypass new checks.

## Interpretation and review

Source URLs, listing pages, document titles, retrieval dates, PDF hashes, parser status, and identity/year checks travel with each indexed filing. Source labels, selected fiscal-year columns, and page references accompany financial values. A known revised PDF cannot inherit remuneration rows from a different URL or hash.

Financial-position and cash-flow fields are extracted only from explicit statement labels. Missing values remain null. Net financial assets are distinct from total assets. Assets versus liabilities plus accumulated surplus is checked when all three are reported; legitimate alternative presentations remain reviewable at the source. Unexplained differences block publication.

The shared parser stops expense rows at an excess/deficiency result, recognizes final operating surplus, and excludes an other-items subtotal when its components are already counted. Source-derived Alexander and Alexis regression fixtures test these cases against the actual reported current-year figures.

Own-source revenue includes only confidently identified lines or an explicit subtotal. Non-ISC revenue is never automatically classified as own-source revenue. Federal revenue includes ISC; own-source subtotals overlap their components and must not be added together. Same-year provincial subtotals count reporting Nations separately for each field, exclude unpublishable/shared summaries, and suppress duplicate source hashes.

Current leadership uses ISC appointment and expiry dates. Appointment dates are not labelled election dates. Historic remuneration is retained separately and follows the shared remuneration parser's column and reconciliation checks. Benefits, travel, and salary are not inferred when headers are unclear.

Official-site discovery evidence is stored in `alberta-enrichment.json`. Business ownership evidence is in `alberta-businesses.json` and merged into `community-enterprise.json`; ownership percentages remain unknown unless explicitly sourced. No business financial metrics are inferred from ownership. To refresh candidate research, run `python -m tools.enrich_alberta`; review its output before merging.

Logos require a visual review and exact local-asset hash in `manual_overrides/alberta-logo-reviews.json`. Generic website discovery cannot overwrite reviewed Alberta marks. Driftpile's municipal-template false positive is rejected. Unverified logos use the existing OpenBand placeholder.

## Coverage and limitations

`alberta-coverage-report.json` is the detailed document and review ledger; `.md` and `.html` provide readable summaries. It lists every Nation, audited and remuneration years, missing periods, source failures, verified businesses/logos, and documents needing review. Roster completion does not imply complete financial coverage.

Bearspaw, Chiniki, Goodstoney, Sawridge, and Whitefish Lake #128 have no individually indexed ISC disclosures in this collection. Shared administration links are provided where available. Official-site candidate reports and alternate versions remain separately labelled until document equivalence and extraction are verified. Website access failures, sparse business research, unverified logos, and scanned or unreconciled financial records remain in the review queue.

The Saskatchewan news, project, jobs, and election-result source collections are not represented as completed Alberta research. Alberta pages show explicit empty states when those records are unavailable. Whitefish Lake #128 has no separately verified map point; Alberta reserve areas are not copied from unrelated or shared records.
