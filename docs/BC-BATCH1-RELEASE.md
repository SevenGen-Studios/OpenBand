# BC first financial extraction release

Adds 15 explicitly user-approved source documents: 13 audited statements and two remuneration schedules. Published BC coverage becomes 18 documents (15 audits and three remuneration schedules).

The latest-available pass processed 378 filings across the 189 profiles with indexed documents. Local RapidOCR and on-device Apple Vision recovered text from 71 scanned or timed-out PDFs. The remaining 360 processed documents stay under review; 3,670 indexed historical documents remain unprocessed.

## Source verification

Actual-year operations, financial-position, net-financial-assets and cash-flow pages were visually checked before import. Cook's Ferry and Douglas remuneration schedules retain exact names, positions, months and separate remuneration/expense columns. Combined totals are calculated; unreported travel and benefits remain missing.

Two optional-field errors were corrected before publication:

- Osoyoos 2024–25: replace prior-year restatement-note balances from PDF page 28 with actual 2025 statement-of-financial-position values on PDF page 7. Cash is 40,302,008; restricted cash 18,372,632; receivables 3,682,833; investments 988,225. Related position fields retain page-level current-year provenance.
- Tlatlasikwala 2017–18: withhold interest income 2,363 because that amount belongs to the 2017 comparison column; the 2018 source column is a dash.

N'Quatqua's source prints capital additions of 102,770 in the changes-in-net-financial-assets statement and cash purchases of 102,769 in the cash-flow statement. Both source-reported amounts and their respective page references are retained.

## Approval and preservation

The user authorized publication in chat: “ok commit live and move on to second”. The dated approval and source hashes are recorded in `BC-BATCH1-APPROVAL.json` and `BC-BATCH1-SOURCES.json`. The frozen publication batch includes the source-page corrections and a new batch hash; the original extraction hash is retained in the approval receipt.

Other provinces' financial records and protected files remain unchanged. No appearance assets changed. Comparison eligibility remains withheld pending the existing separate currency/period/entity review. No paid extraction was used.
