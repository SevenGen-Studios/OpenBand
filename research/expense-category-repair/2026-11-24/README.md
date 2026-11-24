# Expense category repair — 2026-11-24

Samson's 2024–2025 expense ring showed only Operations and Social programs. Stored source rows contained stale catch-all classifications and a wrapped program name reduced to `Segment`. Similar stale Operations mappings occur elsewhere.

This pass inventories **all 1,722 stored Nation-years**, including 840 published years and 13,901 expense source rows. It repairs 246 rows across 40 Nations / 209 years. The published subset is **143 rows, 30 Nations / 119 years**. Samson has 26 corrections across its ten published years. No amounts, original labels, source references, revenue data, publication flags, surplus adjustments or balance-sheet fields change.

## Samson source checks

Official ISC audited statements for Samson (ISC 444) were downloaded for all ten published years. Native text was inspected where available. The 2014–2015 and 2024–2025 operations pages were rendered and visually checked for source wording and actual/current-year columns. `evidence.json` records PDF digests, URLs, page numbers and exact amounts for the four individually recovered labels:

- 2014–2015: OCR `Govemance`, actual 11,969,531 → Governance / Administration (PDF page 8).
- 2017–2018: `6`, actual 12,349,155 → Community Wellness & Family Support Segment / Social programs (page 8).
- 2019–2020: `6`, actual 16,972,573 → the same named segment / Social programs (page 9).
- 2024–2025: `Segment`, actual 19,316,478 → Community Capital Planning and Residential Development Segment / Infrastructure / public works (page 10). This combined segment is not split into invented housing and infrastructure amounts.

Samson 2024–2025 now shows Economic development 35,327,461; Social programs 32,017,245; Administration 25,965,071; Infrastructure / public works 19,316,478; Operations 18,167,592. Total remains **130,793,847**. Treaty Protectorate, Nation Projects, Celebrations and Other Programs remain in Operations pending defensible mapping to the established categories.

## Shared repair and remaining limits

Explicit governance, chief/council, medical, education, lands-management and business-program labels previously stranded in Operations use the conservative shared classifier. Added rules recognize Admin Services, Nation administration, Nation Businesses, Business Enterprises and Business Development. Investment in Business Enterprises remains review-required because it could represent an asset transaction. Reviewed row and summary decisions are preserved. These label-based corrections are recorded as automated proposals/explicit source labels, separately from independent PDF evidence; they are not represented as independently PDF-verified.

The report retains **4,317 unresolved Operations source rows**, including 2,453 published rows, and three published years without underlying expense source rows. These are a review queue, not 4,317 proven mistakes. This is a complete automated inventory, **not a claim that every historical classification has been source-verified**. Broader source review remains necessary for generic programs, trusts, combined activities and accounting adjustments. The older classification audit remains a historical snapshot.

The parser now preserves a wrapped label before an explicit `Segment` continuation, including a schedule number. Expense detail/schedule categories are updated alongside their parent source row. The Manitoba preservation baseline changes only its capital-data fingerprint, following the intentional financial-category correction.

## Reproduce

From the repository root, with the project's requirements installed:

```sh
python -m tools.repair_expense_categories
# Review the proposal report before applying:
python -m tools.repair_expense_categories --apply
python -m unittest tests.test_expense_category_repair tests.test_capital_classification tests.test_capital_parser -v
```

`audit.json` is the original before/after change inventory from main at 99da44c7. Running the tool after applying is idempotent and produces zero additional corrections; use a different `--report` path to retain the original inventory. Source PDFs and render caches are working files outside the repository; public reproducible evidence contains their URLs and digests.

Validation includes full-dataset before/after checks for exact financial amounts, unchanged original labels/source references, unchanged non-expense fields, unchanged aggregate sums, reproducibility from the baseline, and idempotence. Browser expense, capital-spending and classification tests exercise all stored/public mappings.

Prepared as a pull request; not merged or deployed by this task.
