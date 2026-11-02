# Community Capital classification audit

This is a complete automated inventory of published SK/AB/MB breakdowns, with a limited, explicitly recorded independent PDF review. It is **not** 100% source verification.

- Published Nation-years checked: 816
- Revenue activity rows: 12470; expense activity rows: 8672
- Published category rows without underlying source rows: 38
- Independently PDF-reviewed rows: 80
- Verified correct: 69; verified corrections proposed: 10
- Ambiguous / awaiting source review: 21060; extraction issues: 41
- Nation-years with exact reconciliation differences: 52; missing surplus: 73
- Remaining published Unclassified revenue: 4736 rows, $7,048,185,305 net; $10,356,809,155 absolute gross across all years. Negative deferrals must not be interpreted as positive income.

Verified corrections applied to this checkout: 10. Original input classifications remain in the report for review; the remaining Unclassified figures above reflect the applied result when applicable.

Exact checks use decimal dollars with zero tolerance; a one-dollar source rounding difference is reported for review, not declared a proven extraction error. The existing parser tolerance is reported separately in the implementation notes. Missing evidence stays unresolved even if labels and totals agree.

| Province | Nation-years | Revenue rows | Expense rows | Verified correct | Verified corrections | Awaiting review | Extraction issues |
|---|---:|---:|---:|---:|---:|---:|---:|
| AB | 241 | 3081 | 3088 | 13 | 4 | 6150 | 2 |
| MB | 125 | 1595 | 1239 | 22 | 3 | 2809 | 0 |
| SK | 450 | 7794 | 4345 | 34 | 3 | 12101 | 39 |

## Verified category corrections

| Nation / band | Province / year | Source label | Original → proposed | Amount | PDF page | Explanation |
|---|---|---|---|---:|---:|---|
| Long Plain / 287 | MB / 2024-2025 | Tribal Council | Operations → Administration | $23,195,696 | [8](https://services.sac-isc.gc.ca/fnp/main/Search/DisplayBinaryData.aspx?BAND_NUMBER_FF=287&FY=2024-2025&DOC=Audited consolidated financial statements&lang=eng) | Note 2 Segments (PDF p15, printed p11) explicitly defines Long Plain First Nation Tribal Council as administration and governance activities. The 23,195,696 consolidated program expense is included once, not added again from Schedule 4. |
| Long Plain / 287 | MB / 2024-2025 | Makoose C Gamick | Operations → Social programs | $4,558,123 | [8](https://services.sac-isc.gc.ca/fnp/main/Search/DisplayBinaryData.aspx?BAND_NUMBER_FF=287&FY=2024-2025&DOC=Audited consolidated financial statements&lang=eng) | Note 2 Segments (PDF p15) identifies Makoose C Gamik as Child and Family Services. Schedule 18 (PDF p51) confirms Makoose C Gamick actual expenses 4,558,123; this is the same consolidated row, not additional spending. |
| Chipewyan Prairie First Nation / 470 | AB / 2022-2023 | Trust | Investment income → Business and enterprise revenue | $3,381,415 | [8](https://services.sac-isc.gc.ca/fnp/main/Search/DisplayBinaryData.aspx?BAND_NUMBER_FF=470&FY=2022-2023&DOC=Audited consolidated financial statements&lang=eng) | The stored one-word label lost its preceding lines. Statement p8 identifies NOHA Trust business enterprise income; Note 8 (PDF p25) distinguishes net income 3,381,415 from distribution 3,672,679. Retain the amount and original label with full label in review evidence. |
| Chipewyan Prairie First Nation / 470 | AB / 2022-2023 | Chipewyan Prairie Business Trust | Investment income → Business and enterprise revenue | $2,355,016 | [8](https://services.sac-isc.gc.ca/fnp/main/Search/DisplayBinaryData.aspx?BAND_NUMBER_FF=470&FY=2022-2023&DOC=Audited consolidated financial statements&lang=eng) | Full statement label identifies income from government business enterprises. Note 7 (PDF p22) reports net income of 2,355,016 separately from distributions of 2,551,135; modified equity accounting, not portfolio investment income. |
| Cowessess First Nation / 361 | SK / 2022-2023 | Other | Unclassified → Other revenue | $1,577,606 | [8](https://fnp-ppn.aadnc-aandc.gc.ca/fnp/Main/Search/DisplayBinaryData.aspx?BAND_NUMBER_FF=361&FY=2022-2023&DOC=Audited consolidated financial statements&lang=eng) | The consolidated revenue section explicitly reports Other at 1,577,606 actual. The separate FSIN extraction issue is not balanced or changed. |
| Cowessess First Nation / 361 | SK / 2019-2020 | First Nation and Inuit Health Branch | Unclassified → Government funding and transfers | $1,370,567 | [8](https://fnp-ppn.aadnc-aandc.gc.ca/fnp/Main/Search/DisplayBinaryData.aspx?BAND_NUMBER_FF=361&FY=2019-2020&DOC=Audited consolidated financial statements&lang=eng) | Note 21 (PDF p27) reconciles First Nation and Inuit Health Branch funding confirmation, recoveries and opening/closing deferrals to the recognized 1,370,567. Use the recognized statement amount, not cash received. |
| Cowessess First Nation / 361 | SK / 2019-2020 | Other | Unclassified → Other revenue | $968,030 | [8](https://fnp-ppn.aadnc-aandc.gc.ca/fnp/Main/Search/DisplayBinaryData.aspx?BAND_NUMBER_FF=361&FY=2019-2020&DOC=Audited consolidated financial statements&lang=eng) | The consolidated revenue section explicitly reports Other at 968,030 actual. This maps the reported Other line, not an invented balancing residual. |
| Chipewyan Prairie First Nation / 470 | AB / 2022-2023 | Chipewyan Prairie First Nation Business Trust | Investment income → Business and enterprise revenue | $758,442 | [8](https://services.sac-isc.gc.ca/fnp/main/Search/DisplayBinaryData.aspx?BAND_NUMBER_FF=470&FY=2022-2023&DOC=Audited consolidated financial statements&lang=eng) | Full statement label and Note 6 (PDF pp20-21) identify modified equity business earnings of 758,442, not an ordinary trust investment return. |
| Chipewyan Prairie First Nation / 470 | AB / 2022-2023 | Income from government business enterprises - other | Government funding and transfers → Business and enterprise revenue | $162,530 | [8](https://services.sac-isc.gc.ca/fnp/main/Search/DisplayBinaryData.aspx?BAND_NUMBER_FF=470&FY=2022-2023&DOC=Audited consolidated financial statements&lang=eng) | Government describes ownership of business enterprises, not the funding source. Note 9 (PDF p26) reports 162,530 net income under modified equity accounting, separate from the opening net asset adjustment. |
| Long Plain / 287 | MB / 2024-2025 | Daycare fees | Unclassified → Program and service revenue | $11,175 | [7](https://services.sac-isc.gc.ca/fnp/main/Search/DisplayBinaryData.aspx?BAND_NUMBER_FF=287&FY=2024-2025&DOC=Audited consolidated financial statements&lang=eng) | Daycare fees are explicitly reported service fees, 11,175 actual on the operations statement and Schedule 11 (PDF p44). Gross fees and separate deferred contribution adjustments are preserved. |

## Reconciliation exceptions

| Nation / band | Year | Revenue differences | Expense differences | Surplus difference |
|---|---|---|---|---:|
| Sioux Valley Dakota Nation / 290 | 2018-2019 | {} | {} | 1 |
| Lucky Man Cree Nation / 341 | 2021-2022 | {} | {} | 7846 |
| Red Pheasant Cree Nation / 346 | 2020-2021 | {"sourceDifference": 6, "categoryDifference": 6} | {} | 0 |
| Red Pheasant Cree Nation / 346 | 2024-2025 | {} | {} | 75852 |
| Sweetgrass First Nation / 348 | 2023-2024 | {} | {} | 99092 |
| Sweetgrass First Nation / 348 | 2024-2025 | {} | {} | -6 |
| Hatchet Lake Denesuline / 352 | 2016-2017 | {} | {} | 42856 |
| Hatchet Lake Denesuline / 352 | 2024-2025 | {} | {} | -2 |
| Cowessess First Nation / 361 | 2022-2023 | {"sourceDifference": 414881, "categoryDifference": 414881} | {} | 1 |
| Kahkewistahaw First Nation / 362 | 2023-2024 | {} | {} | -1907 |
| Kahkewistahaw First Nation / 362 | 2024-2025 | {} | {} | -1907 |
| Cote First Nation / 366 | 2014-2015 | {} | {} | -8164 |
| The Key First Nation / 368 | 2021-2022 | {} | {} | 1 |
| James Smith Cree Nation / 370 | 2014-2015 | {} | {} | -9411 |
| One Arrow First Nation / 373 | 2021-2022 | {"sourceRowsMissing": true, "sourceDifference": -24608619, "sourceCategoryDifferences": {"Financing proceeds": -529730, "Own-source and business revenue": -1290025, "Trust income": -7418, "Other revenue": -1114307, "Government transfers": -21667139}} | {"sourceRowsMissing": true, "sourceDifference": -22048556, "sourceCategoryDifferences": {"Social programs": -3193834, "Economic development": -411759, "Education": -5164095, "Infrastructure / public works": -4898551, "Health": -6081064, "Lands, culture and trusts": -723878, "Administration": -1575375}} | 0 |
| One Arrow First Nation / 373 | 2022-2023 | {"sourceRowsMissing": true, "sourceDifference": -30421981, "sourceCategoryDifferences": {"Financing proceeds": -196908, "Own-source and business revenue": -2706185, "Trust income": -39211, "Other revenue": -1292459, "Government transfers": -26187218}} | {"sourceRowsMissing": true, "sourceDifference": -30386076, "sourceCategoryDifferences": {"Social programs": -4933131, "Economic development": -623876, "Education": -6701279, "Infrastructure / public works": -5777421, "Health": -8396883, "Lands, culture and trusts": -1090884, "Administration": -2862602}} | 0 |
| One Arrow First Nation / 373 | 2023-2024 | {"sourceRowsMissing": true, "sourceDifference": -31966908, "sourceCategoryDifferences": {"Own-source and business revenue": -3701625, "Trust income": -117954, "Other revenue": -485778, "Government transfers": -27661551}} | {"sourceRowsMissing": true, "sourceDifference": -28363385, "sourceCategoryDifferences": {"Economic development": -344548, "Infrastructure / public works": -5098922, "Health": -2904546, "Child and family services": -3053212, "Culture and recreation": -267151, "Social development": -3640001, "Education": -8906201, "Housing": -1999944, "Land management": -1709052, "Administration": -439808}} | 0 |
| Little Black Bear First Nation / 379 | 2021-2022 | {} | {} | -1 |
| Muscowpetung First Nation / 381 | 2013-2014 | {} | {} | -14950 |
| Piapot First Nation / 385 | 2019-2020 | {} | {} | -3740 |
| Ahtahkakoop Cree Nation / 406 | 2016-2017 | {} | {} | 2100 |
| O'Chiese / 431 | 2022-2023 | {} | {} | 6 |
| O'Chiese / 431 | 2023-2024 | {} | {} | 2 |
| O'Chiese / 431 | 2024-2025 | {} | {} | -1 |
| Alexander / 438 | 2025-2026 | {} | {} | 4 |
| Enoch Cree Nation #440 / 440 | 2025-2026 | {} | {} | -2 |
| Paul / 441 | 2017-2018 | {} | {} | -2 |
| Paul / 441 | 2025-2026 | {} | {} | 11 |
| Samson / 444 | 2017-2018 | {} | {} | -11092 |
| Samson / 444 | 2019-2020 | {"sourceDifference": -371943, "categoryDifference": -371943} | {} | 0 |
| Tallcree Tribal Government / 446 | 2021-2022 | {"sourceDifference": 8, "categoryDifference": 8} | {} | 0 |
| Dene Tha' / 448 | 2014-2015 | {} | {} | 9152 |
| Horse Lake First Nation / 449 | 2021-2022 | {} | {} | -1 |
| Horse Lake First Nation / 449 | 2024-2025 | {} | {} | 1 |
| Driftpile Cree Nation / 450 | 2023-2024 | {} | {} | 19938 |
| Driftpile Cree Nation / 450 | 2024-2025 | {} | {} | -1 |
| Duncan's First Nation / 451 | 2017-2018 | {} | {} | 18 |
| Duncan's First Nation / 451 | 2022-2023 | {} | {} | 1 |
| Duncan's First Nation / 451 | 2023-2024 | {} | {} | -1 |
| Duncan's First Nation / 451 | 2024-2025 | {} | {} | -1 |
| Kapawe'no First Nation / 452 | 2016-2017 | {} | {} | -231 |
| Kapawe'no First Nation / 452 | 2021-2022 | {} | {} | -1 |
| Kapawe'no First Nation / 452 | 2022-2023 | {} | {} | -3 |
| Kapawe'no First Nation / 452 | 2023-2024 | {} | {} | 2 |
| Kapawe'no First Nation / 452 | 2024-2025 | {} | {} | -1 |
| Sturgeon Lake Cree Nation / 455 | 2023-2024 | {} | {} | 3942 |
| Frog Lake / 465 | 2022-2023 | {} | {} | 2 |
| Frog Lake / 465 | 2023-2024 | {} | {} | -2 |
| Kehewin Cree Nation / 466 | 2019-2020 | {} | {} | -286408 |
| Fort McMurray #468 First Nation / 468 | 2017-2018 | {} | {"sourceDifference": 100882, "categoryDifference": 100882} | 0 |
| Fort McMurray #468 First Nation / 468 | 2022-2023 | {} | {} | 4 |
| Woodland Cree First Nation / 474 | 2022-2023 | {} | {} | 3 |

## Evidence and remaining work

The JSON report contains every activity row and every source-coverage gap, its original category and amount, proposed category (if any), URL/page, confidence, explanation, evidence level, issues and manual-review requirement. All unreviewed rows remain Ambiguous, including plausible labels; this count is a source-verification backlog, not a count of proven mistakes.

Category corrections do not change totals, amounts, labels, URLs, publication status, deferred revenue, surplus adjustments or asset balances. The undo file stores complete prior affected summaries and individual before/after rows. Schedules are corroborating evidence, never additional revenue or expense activity rows.

Prior manual reviews are preserved and distinguished from PDF review performed for this audit. Ambiguous trust distributions, intermediaries, combined programs, deferred contribution movements, financing, asset sales and internal transfers require statements, schedules and notes before classification. No residual is assigned to government, Other revenue or Operations.

## Implementation and regression results

96 Python capital tests passed, including 18 new classification/audit regressions. The frontend capital-spending regression passed all 1,708 stored Nation-year mappings. All activity amounts, financial totals, source labels/references and publication flags were compared to the original dataset; only the 10 verified category decisions and associated review/detail metadata changed. Exact rollback reproduced the original SHA-256.

See `research/classification-audit/2026-11-02/README.md` for the rule changes, evidence limitations, commands and remaining source-review work. The existing 1% parser reconciliation tolerance was not used to declare classifications verified; this report uses exact decimal-dollar comparisons.

The seven existing data-accuracy repair tests also passed. The new frontend classification regression passed all 12,484 published revenue mappings (including aggregate categories lacking source rows). The revenue explorer previously reran label keywords before checking stored categories, which would have hidden the verified corrections. It now honors stored categories, including Unclassified, before display; unsupported labels are not classified by the browser. This display-precedence correction preserves the existing layout and is separate from the ten source-verified dataset changes.
