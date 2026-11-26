# Financial recovery — November 26, 2026

This batch restores Blood Tribe consolidated Community Capital summaries for 2023–2024 and 2024–2025, and the complete 13-official remuneration schedule for 2017–2018. It does not claim all historical years are recovered.

## Evidence and validation

Official ISC source URLs, complete-PDF SHA-256 digests, source years and page references are in source-manifest.json. Selected rendered source pages are retained here for visual review. The OCR snapshots are supporting evidence, not authoritative replacements for source images. Financial figures were independently checked against the actual-year columns; budget and comparative columns were excluded.

Capital operations span PDF pages 7–8. The final annual results include separately reported Other income of $8,433,748 (2024) and $9,793,598 (2025). These are explicit source rows, not balancing residuals. Complete reported revenue/expense activity, source labels and references are retained in the override. Every source row and category total reconciles exactly. The 2024 and 2025 annual results reconcile exactly after the explicit adjustments. Financial asset/liability/net-asset checks also reconcile. Cash/investments combines reported cash equivalents and temporary investments, excluding separately reported restricted cash, trust funds and business investments. Capital spending is the magnitude of reported tangible-asset additions on PDF page 9; debt is reported long-term debt on PDF page 6.

Remuneration is PDF page 9 of the 2018 schedule. All 13 row totals reconcile; salary totals $1,359,876 and the source's combined Travel and other column totals $378,627, producing the printed $1,738,503 total. The combined column includes board travel/honoraria. Both original component columns are retained so the combined value is not double-counted. Other unreported payment fields stay null. The reviewed override is replayable and protects the complete source schedule.

## Parser improvements

Known joined OCR statement headings are restored without changing figures or names. Final labels such as Surplus (deficit) for the year terminate the adjustment section rather than being counted as another adjustment. Continuation-page year captions are excluded from adjustment values. Regression tests use both real Blood OCR snapshots, retain reconciliation holds for unreviewed wrapped rows, and reject a one-dollar alteration in independently reviewed source activity.

Explicitly named Nation department statements are held for financial-scope review, even if their arithmetic reconciles. This applies to native and structured paths. Blood's 2022–2023 linked PDF is titled BLOOD TRIBE ECONOMIC DEVELOPMENT and covers that department, not the consolidated Nation. Its existing unpublishable summary is marked with the scope concern; no departmental totals are presented as whole-Nation finances.

## Remaining work

The 2016 and 2020 pay schedules contain apparent inconsistencies among printed component/combined/total columns. They remain held rather than being forced to reconcile. Other Blood capital years remain in their existing review states. No reliable prior records, source files or unrelated communities are replaced.

The reusable inventory command is:

    python3 -m tools.audit_financial_coverage --output research/financial-recovery/2026-11-26-blood

financial-coverage.json and .md inventory all 180 communities and separate posted-but-unextracted files, review holds, and records not indexed as posted. They are not a fresh HTTP check of every filing. Publication readiness is distinct from source availability. This provides a reproducible queue for further source discovery and recovery across both financial categories and all provinces.
