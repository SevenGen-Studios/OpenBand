# Independent source review, 2 November 2026

The automated inventory covers all 816 published SK/AB/MB Nation-years at input commit `55127c8e8a66ee6170b6326cd2f2b33863c1e1c8`. It checks 12,470 revenue and 8,672 expense activity rows, plus 38 category totals without activity rows. Five original financial statements were inspected, and **80 selected rows** have recorded independent source decisions: 69 retained, 10 corrected and one confirmed extraction issue. This is not complete PDF verification. Every other row remains unresolved, even when its label and arithmetic appear plausible.

`evidence.json` records original label, category, amount, source URL, PDF page, actual column, identity/year/section/amount/duplication/context checks, source excerpts, explanations and SHA-256. Original PDFs are retained in `sources/`. The two Cowessess files were already archived in the repository's previous source-review material; the other three PDFs were downloaded from the existing ISC source URLs. No PDF was edited.

`undo.json` contains before/after activity rows and the complete original versions of all four affected Nation-years. It binds the input and output dataset bytes by SHA-256. No amount, total, source label, original reference, financial adjustment, publication status or other Nation-year changed. Matching expense-detail categories follow the corrected parent program but are never added to consolidated spending.

## Run a read-only inventory

```sh
python -m tools.audit_capital_classification --report current-classification-audit.json --markdown current-classification-audit.md
```

The committed report describes the original input and applied corrections. Re-running the old evidence manifest against corrected data deliberately fails its original-category leases: it is not a reusable authorization to change future rows. New verified corrections need fresh row-specific evidence.

## Apply a proposed evidence manifest

Run against the exact original dataset, inspect the generated proposal report, then:

```sh
python -m tools.audit_capital_classification --evidence research/classification-audit/2026-11-02/evidence.json --apply --undo new-undo.json
```

Only `verified_misclassification` decisions with all checks completed and matching PDF hashes can apply. Existing manually reviewed classifications also require an explicit `supersedesReviewedDecision` in the independent review. Automated proposals cannot change existing categories. The undo destination must be new; an older audit trail is never overwritten.

## Restore the exact original dataset to a new file

```sh
python -m tools.restore_capital_classification --undo research/classification-audit/2026-11-02/undo.json --output restored-capital-data.json
```

This refuses to run if the current dataset has changed after the audit and confirms the restored file's bytes match the original input hash. Compare the restored file before replacing any live dataset.

## Main findings and safeguards

- Broad keyword precedence confused government-owned business earnings with government transfers and trust-held equity earnings with ordinary investment returns. Chipewyan Prairie notes 6–9 distinguish modified equity net income from distributions and capital adjustments.
- Long Plain note 2 explicitly defines Tribal Council as administration/governance and Makoose C Gamik as Child and Family Services. Schedule 18 corroborates the latter expense; no schedule was added to the totals.
- Cowessess note 21 reconciles recognized health funding after recovery and deferral adjustments. Its generic contributions, mixed bingo/fundraising and trust distributions remain unresolved.
- Cowessess 2022–2023 FSIN was extracted as `2,022` from a year inside the label instead of actual `(412,859)`, explaining the $414,881 revenue-row difference. This is separately reported; this classification patch does not change the financial amount. Its annual surplus also has a $1 difference after separately reported adjustments.
- The existing `nearly_equal` uses a 1% tolerance (and $10 absolute floor). This audit uses Decimal with **zero tolerance** and reports small rounding differences separately from proven errors. The legacy normalization helper now uses its zero-relative-tolerance option, preserves existing categories, refuses missing/unreadable rows and skips manually reviewed summaries.
- 2,467 expense rows hit the unknown Operations fallback in the original-input automated pass. Operations now has an explicit review status unless an operating object or reviewed program context supports it. Unverified historic categories are preserved for review rather than silently remapped.
- Aggregation preserves row review/evidence fields. Detail enrichment inherits existing parent classifications and refuses duplicate parent labels. The recovery merge already protects reviewed summaries; its existing protection remains.
- Future ingestion uses the same conservative rules in all provinces; new rows carry automated/pending-source-review status. Government funders are distinguished from unidentified contributors; tribal councils, generic trust distributions, deferrals, financing, mixed labels and asset disposals require source context. Wrapped business-income labels retain their heading.
- The new GitHub workflow produces read-only audit artifacts on capital data/parser changes and runs regression tests. It does not rewrite or suppress disclosures. Existing website layout is preserved. The revenue explorer now honors stored categories before displaying them, including Unclassified, instead of overriding reviewed decisions with another client-side keyword classifier. Category-sensitive subcategories no longer call business earnings trust distributions.

## Limits and follow-up

The full JSON report is the row-level review queue. It includes 21,060 activity rows awaiting independent review and 41 extraction/coverage issues, including the 38 source-less category totals. There are 52 Nation-years with exact reconciliation or source-coverage exceptions and 73 without a reported annual result. A $1 exception is not automatically an error. Unclassified revenue is reported both net and absolute gross across all fiscal years; deferred movements can be negative and must not be read as positive income.

The public-facing dataset still contains unresolved classifications and the separately identified FSIN extraction error. Do not describe the website as fully source-verified. Completing original-PDF review of the backlog, resolving the extraction error in a separate source-backed change and inspecting suspicious year-to-year movements remain outstanding.
