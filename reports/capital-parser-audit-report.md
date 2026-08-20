# Community Capital parser audit

Date: 2026-07-31

## Source finding

Carry the Kettle Nakoda Nation FY 2024-2025 was checked against the official ISC audited financial statement. The $78,308,074 amount is a reported Land Claims program expense on the Consolidated Statement of Operations (PDF page 8, printed page 6), not settlement revenue or a wrong-column extraction.

Schedule 7 (PDF page 43, printed page 41) reconciles that expense to:

- Transfer to trust: $36,875,382
- Per Capita Distribution: $30,660,000
- Professional fees: $9,473,926
- Insurance: $1,169,853
- Interest and bank charges: $128,913

The same schedule reports $81,525,381 of Settlement Distribution as revenue. The auditor qualified the classification of changes in settlement-claim loan balances recorded as professional fees, so OpenBand retains a source-verification warning.

## Dataset audit

- Stored community/year summaries audited: 700
- Safely normalized records: 101
- Newly suppressed publishable records: 0
- Major year-over-year changes flagged: 30
- Existing records remaining in manual review: 295

The normalization pass changed category labels only where source rows reconciled to the reported total. It did not change reported source amounts. Land Claims rows are now distinct from Operations, and settlement distributions/proceeds are distinct revenue.

## Validation added

- Revenue and expense section context is retained for extracted rows.
- PDF page, statement/table, section, fiscal year, and selected-column metadata is attached to new extractions.
- Settlement distributions, settlement proceeds, trust revenue, grants, funding, and other revenue labels are rejected from expense rows.
- Current-year column selection must match the filing fiscal year.
- Revenue and expense category totals must reconcile to reported totals.
- Revenue minus expenses, including separately reported adjustments, must reconcile to surplus or deficit.
- Negative expenses, revenue values inside expense categories, wrong-section rows, and wrong-year rows require manual review.
- Extreme categories and major year-over-year changes are flagged for source verification.
- Failed validation sets `publishable: false`; the existing UI displays the manual-review unavailable state.

Machine-readable details are in `capital-validation-report.json`.
