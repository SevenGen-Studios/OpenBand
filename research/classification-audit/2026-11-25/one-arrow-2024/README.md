# One Arrow 2023-2024: restore source rows and separate uncertain funding

Follow-up to PR #115's initial audit. The existing source-backed totals were published with no underlying activity rows: four revenue category totals and ten expense category totals could not be traced through the drill-down. This review restores **13 revenue rows and 10 expense rows** from original PDF page 8 (printed page 6), selecting 2024 actual rather than budget or 2023 comparative. Both sides reconcile exactly, and revenue less expenses equals the existing reported annual surplus.

## Evidence and scope

The unmodified original statement is archived as `source.pdf`, obtained from the already cached official filing for One Arrow First Nation, ISC 373, 2023-2024. The original source URL remains on every row and the summary. `evidence.json` binds every label, actual amount, page, category decision and explanation to the PDF SHA-256. It also stores the complete prior summary and before/after dataset hashes. PDF pages 8, 12 and 19 were independently read as text and visually inspected. Page 12 describes modified equity accounting and STC's separate organizational scope; page 19 distinguishes portfolio holdings from controlled business enterprises.

All 23 actual amounts are verified against the operations statement; **20 category decisions are supported and three remain unresolved**. The evidence manifest passes the existing independent review gate without errors or unused evidence. Newly restored rows have no prior row category; `originalCategory` in this current-state verification manifest is the resulting stored category. The actual historical aggregate categories are preserved in `beforeSummary` for comparison. No category-only total has been relabelled as an independently transcribed row.

## What changes for people using OpenBand

The existing revenue and expense drill-downs now show the statement's actual labels, amounts and page references for this year. The previous government total 27,661,551 included 5,073,635 attributed only to Saskatoon Tribal Council. The statement identifies STC as the immediate contributor; the reviewed notes do not establish ultimate funding composition. Direct ISC and CMHC funding remains government funding at **22,587,916**, while the STC row stays **Unclassified**.

First Nations Trust gaming income **1,021,436** and Dakota Dunes Community Development Corporation **560,991** also stay Unclassified until distribution/funding context supports attribution. These three explicit rows total **6,656,062**; they are not a balancing residual. The record displays a review warning. More Unclassified revenue here reflects clearer evidence boundaries, not newly discovered revenue.

The statement's business-enterprise earnings **924,872** are recorded separately from portfolio interest and investment income. Lease/rental income **770,136** is separate from business earnings. Interest and investment income totals **542,144**, including explicitly labelled Treaty Land Entitlement interest **117,954**; that row is an interest return rather than trust principal. Other remains the explicitly reported **485,778**.

All ten existing expense category decisions are retained, now supported by their program rows. The original custom labels for Land management, Culture and recreation, Child and family services and Social development remain intact. No schedule is added to the consolidated totals. Reported revenue **31,966,908**, expenses **28,363,385**, surplus **3,603,523**, cash, debt, asset balances and capital purchases are unchanged. This review does not newly verify the balance-sheet or capital metrics.

The original `capital_overrides/one_arrow_2021_2024.json` producer now retains these rows, categories and warnings so an override import does not erase the improvement. Other years are unchanged. The only refreshed preservation fingerprint is capital-data; its old/new values are recorded in `protected-baseline-update.json`.

## Safeguard and remaining work

Publication validation now checks supplied source activity rows separately from category totals. Complete independently reviewed source-row sets must reconcile to the cent, so even a $1 mutation is held; older unreviewed records retain the established tolerance. Missing/unreadable amounts and activity totals outside the established reconciliation tolerance prevent a newly extracted summary from passing even if its category totals match. Regression tests cover a missing row, unreadable value and duplicated total on both revenue and expense sides. Legacy records without activity rows remain explicit review gaps; their rows are never fabricated from category totals.

The current follow-up inventory still has **840 published Nation-years**, now **12,875 revenue rows and 8,920 expense rows**. Missing source-category rows fall **38 -> 24**, and Nation-years with exact reconciliation/source-coverage exceptions fall **46 -> 45**. The remaining missing activity rows are One Arrow 2021-2022 and 2022-2023; those original statements use different accounting presentation and must not be silently replaced with later comparative columns. The 2024 statement's 2023 comparative amounts differ from the older as-issued statement; reconciling that presentation change remains outstanding.

`review-queue.json.gz` is the complete current inventory with this manifest applied read-only: 23 independently reviewed rows, 20 verified correct classifications, three ambiguous reviewed classifications, and all other records preserved as unreviewed by this pass. `coverage.json` contains current counts. Earlier reports and their evidence remain historical snapshots.

Tests: the capital suite now includes six restoration/evidence/publication regressions. The capital-classification, capital-spending and expense-chart browser suites pass. Manitoba preservation checks pass. CI results and the exact review state are recorded in PR #115. No merge or production change is included.

A separate apparent URL-type mismatch for Kapawe'no was investigated and left unchanged: the existing filing metadata explicitly records swapped ISC listing labels, so a URL query's DOC label alone is insufficient evidence that the actual PDF is wrong. This is why provenance checks must inspect document contents rather than blindly rewrite links.
