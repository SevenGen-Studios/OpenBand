# Community Capital audit, 25 November 2026

Follow-up: [One Arrow source-row restoration](one-arrow-2024/README.md) reduces missing source-category rows from 38 to 24, adds 23 original-statement rows and records 20 supported category decisions plus three unresolved classifications. The figures below are the preserved initial audit snapshot.

Audited current `main` at `e08cb277` on isolated branch `audit/community-capital-20261125`. This is a complete automated inventory of current published records plus a bounded original-PDF review, not a claim that every financial statement has been independently verified. No production changes or merges are authorized by this review.

## Coverage verified from current datasets

| Province | Published Nation-years | Revenue activity rows | Expense activity rows |
|---|---:|---:|---:|
| Saskatchewan | 461 | 7,990 | 4,448 |
| Alberta | 244 | 3,105 | 3,113 |
| Manitoba | 135 | 1,767 | 1,349 |
| Total | 840 | 12,862 | 8,910 |

The 180-Nation roster has 1,906 indexed audited filing entries across 1,894 unique Nation-years. There are 12 duplicate indexed Nation-years; coverage now counts each once. These are duplicate index entries, not proven double-counted financial totals. There are 1,749 unique posted Nation-years: 840 published summaries, 880 awaiting review/extraction, and 29 without a stored summary. Another 145 indexed Nation-years have no posted document or usable link. These counts describe the stored index, not a new live ISC availability survey or proof of non-submission. Unindexed years are not inferred missing disclosures.

All 1,722 stored summaries were revalidated read-only: 840 parsed, 850 manual_review, 20 not_applicable and 12 error. The normalization audit proposes changes to 1,082 summaries (including metadata and category aggregation); none of those bulk proposals were applied. No new suppression was proposed. Historical manually reviewed decisions remain intact.

## Source-confirmed correction

Cowessess First Nation, application/ISC ID 361, 2022-2023: the FSIN revenue row was **2,022**, a comparative year embedded in its label. PDF page 8 (printed page 3) shows actual **(412,859)**, with budget dash and comparative 604,046. Correcting it reduces the Unclassified revenue subtotal by **414,881** and makes both activity rows and category totals equal reported revenue **44,440,344** exactly. Reported totals, expenses, surplus, existing categories, original short label and original PDF URL stay unchanged. The full source label is now retained alongside the original label.

`correction-evidence.json` preserves the original complete summary, before/after dataset digests, PDF digest, URL, page, actual-column checks and explanation. The original unmodified PDF is already archived at `../2026-11-02/sources/cowessess-financial-2022-2023.pdf`. `capital_overrides/2026_11_25_cowessess_fsin.json` preserves the narrow correction for existing override ingestion. It does not declare the whole summary independently verified. The funding/deferral category remains Unclassified pending note attribution.

The source was read as text and visually inspected on PDF pages 8-10. The 2023 column was checked against budget and 2022. The correction fixes the discrepancy identified by the earlier November audit; that historical audit and its evidence remain unchanged.

## Operating expenses and capital acquisition

Cowessess's operations statement reports a program called Capital at **2,255,511**, within total expenses of **32,671,475**. PDF page 9 separately reports tangible-capital-asset purchases of **6,276,524**; page 10 reports cash purchases of **5,841,774**. These measures are not interchangeable and are never added together as expenses. The 434,750 difference between acquisition and cash-purchase measures needs note reconciliation before interpreting it as an error. The stored acquisition amount is retained.

The final annual surplus is **15,268,997**. Revenue less expenses plus separately reported adjustments differs by **1**; preserve the source values. A fresh parser run still holds this statement because the Other expense heading causes ambiguous signs for positive gains/TLE contributions. The new source-derived regression explicitly checks that this run remains unpublished rather than weakening reconciliation. Existing reviewed adjustments are preserved in the stored record.

## Ingestion, normalized data, sources and display

- `data.json`: Nation identities, ISC numbers and indexed audited filing URLs/statuses. Synthetic application IDs are distinct from ISC numbers.
- `tools/capital_parser.py`: native PDF extraction and OCR/optional fallback stages, row classification, aggregation and publication validation; `tools/local_ocr.py` provides local OCR. `capital-backfill.yml` orchestrates ingestion. Paid extraction was not used.
- `capital-data.json`: normalized summaries, activity rows, breakdowns, source references, accounting adjustments and publication state. Reviewed exceptions live in `capital_overrides/` and `research/`.
- Original statements: per-summary `sourceUrl` and per-row source references; this reviewed PDF is archived with a SHA-256 digest.
- `assets/openband.js`: `getCapitalParsedYears`, `getRevenueHistory`, `renderCommunityCapital` and expense drill-downs. Display requires parsed status and publishable not false; categories use stored decisions. `tools/build_site.py` generates profile routes. No UI source or production asset was changed.

## Validation improvements

Numeric prose within balanced parenthetical disclosures (including nested years and amounts) remains part of the label; bare parenthesized negative money remains a value. This prevents recurrence of the FSIN extraction error. Column validation now checks expense rows, revenue rows and reported totals symmetrically: explicit budget/prior columns, conflicting selected years and conflicting fiscal-year references cannot pass solely because totals reconcile. Missing metadata is not invented.

The classification audit compares source URL band numbers against `iscBandNumber`, avoiding false wrong-Nation alarms for synthetic application IDs. Disclosure coverage distinguishes posted-but-unparsed from unavailable documents and deduplicates indexed Nation-years. These checks do not silently recategorize historic data. Only the affected capital-data preservation fingerprint was refreshed; its before/after values are recorded and every other protected fingerprint is retained.

## Unresolved review queue

There are **46** Nation-years with exact arithmetic/source-coverage exceptions, **38** category rows without underlying source activity rows (One Arrow 2021-2024), and **71** summaries without an annual result. Cowessess remains among the 46 because its separate $1 annual-result discrepancy remains. A rounding difference is a review flag, not proof of a parser mistake.

There are **4,983** published Unclassified revenue rows and **2,517** expense rows using unresolved Operations fallback. There are **3,328** automated category differences; none was accepted as independent source evidence. Current net Unclassified revenue across all years is 6,396,533,719; absolute gross is 11,668,180,005. Negative deferrals and cross-year totals must not be presented as new positive community income.

`automated-review-queue.json.gz` retains every activity row, category-only gap, source URL/reference, automated proposal and reconciliation result. `reconciliation-exceptions.csv` lists all 46 exceptions. Prior stored reviews are distinguished from new independent verification. This pass independently confirms one corrected amount, and does not newly verify any complete set of category decisions. The automated report correctly records zero newly verified category rows.

## Checks and review state

102 capital Python tests pass, including six new source/column/coverage tests. Capital-classification, capital-spending and expense-chart browser tests pass. The full Python suite ran 701 tests and reported 17 errors, all in existing community-coverage image evidence checks because this local runtime lacks RapidOCR. No financial regression failure occurred. CI installs the declared OCR dependencies; its result must be inspected separately. The capital audit workflow now installs the PDF dependency required by the original-source regression.

The full suite regenerated profile pages as a side effect; those unrelated generated diffs were discarded. Production was not changed or verified as corrected. Review and merge remain separate from this branch/PR.

Reproduce: `python -m tools.audit_capital_classification --report current.json --markdown current.md`, `python -m tools.audit_capital_data --report validation.json` (both read-only), then `python -m unittest discover -s tests -p 'test_*capital*.py'` with PDF dependencies installed.
