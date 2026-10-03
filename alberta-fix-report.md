# Alberta repair and verification report

Reviewed October 3, 2026. The parser recovery and refreshed data are included in the main-branch update.

## Corrections

- Reattempted all 308 remaining source documents across the Alberta roster. This pass recovered 26 more documents: 18 audited statements and eight remuneration schedules, including 15 newly publishable financial Nation-years. Complete visual transcriptions of the eight pay schedules retain all 44 printed officials, their payment components, source hashes and available footer totals. Printed-row and footer checks now prevent incomplete OCR schedules from being marked parsed.
- Restored reserve areas on all 47 profiles with individual ISC reserve lists. Areas use listed hectares, retain source links, deduplicate reserve IDs, and identify shared parcels. All 47 boundary owner names match the current ISC map layer. Whitefish Lake #128 retains its separate identity and does not inherit Saddle Lake land or totals.
- Visually verified 15 official logos: Alexander, Bearspaw, Beaver Lake, Blood, Cold Lake, Duncan's, Enoch, Ermineskin, Fort McMurray #468, Horse Lake, Kapawe'no, Louis Bull, O'Chiese, Sawridge, and Woodland Cree. The reviewed SVG hash for Enoch now matches the actual asset.
- Corrected current official links for Driftpile, Kehewin, Bearspaw, Montana, Ermineskin and Blood. Access failures remain recorded independently of website identity verification.
- Recovered Tthebatthie remuneration for 2019-2020, 2021-2022, 2022-2023 and 2023-2024. Salary and honoraria are combined as remuneration; travel and northern allowance stay separate. Every printed numeric column and the footer total must reconcile.
- Rechecked all individual ISC listings and retried 430 previously unresolved filings. No additional posted links were discovered. Cleared transient connection, disk-space and non-PDF retrieval failures.
- Preserved separate Stoney government identities and the link to shared administration 471. Shared disclosures are not copied into individual totals.

## Remaining source and extraction limitations

The collection indexes 754 documents, of which 472 passed automated validation and 282 still need extraction or accounting review. The recovery attempted all 432 previously unresolved files and validated 150 additional documents. 0 technical extraction failures remain. There are 42 verified Alberta logos. See the [parser recovery report](alberta-parser-recovery-report.md) for every attempted source and its result.

The six remaining unverified logos are Driftpile, Kehewin, Lubicon Lake, Montana, Whitefish Lake #459 and Whitefish Lake #128. Driftpile's Cityvile template mark and Whitefish Lake #128's generic maple-leaf/teepee candidate were rejected. Montana's flag is not substituted for a verified logo.

Unindexed periods below mean no corresponding posted link was found in the rechecked ISC listing. They do not prove that a filing does not exist elsewhere. Native text, geometric table extraction, Windows OCR and an isolated RapidOCR cross-check recovered additional filings. Unreconciled amounts, unidentified officials, incomplete scans and accounting ambiguities remain linked for manual review. Missing values are not inferred.

## Nation-by-Nation results

| Nation | Reserve area (ha) | Logo | Parsed remuneration years | Unindexed audited years | Unindexed remuneration years | Documents still needing review |
|---|---:|---|---|---|---|---:|
| Alexander | 9,587.40 | Verified | 2014-2015, 2016-2017, 2017-2018, 2019-2020, 2020-2021, 2021-2022, 2022-2023, 2023-2024, 2024-2025, 2025-2026 | None | None | 7 |
| Alexis Nakota Sioux Nation | 14,479.10 | Verified | 2019-2020, 2020-2021, 2021-2022, 2022-2023, 2023-2024, 2024-2025 | 2025-2026 | 2025-2026 | 12 |
| Athabasca Chipewyan First Nation | 34,776.00 | Verified | 2018-2019, 2019-2020, 2020-2021 | 2014-2015, 2015-2016, 2016-2017, 2017-2018, 2025-2026 | 2014-2015, 2015-2016, 2016-2017, 2017-2018, 2021-2022, 2022-2023, 2023-2024, 2024-2025, 2025-2026 | 0 |
| Bearspaw | 48,775.10 (shared included) | Verified | None | 2014-2015, 2015-2016, 2016-2017, 2017-2018, 2018-2019, 2019-2020, 2020-2021, 2021-2022, 2022-2023, 2023-2024, 2024-2025, 2025-2026 | 2014-2015, 2015-2016, 2016-2017, 2017-2018, 2018-2019, 2019-2020, 2020-2021, 2021-2022, 2022-2023, 2023-2024, 2024-2025, 2025-2026 | 0 |
| Beaver First Nation | 7,075.30 | Verified | 2015-2016 | 2017-2018, 2018-2019, 2019-2020, 2020-2021, 2021-2022, 2022-2023, 2023-2024, 2024-2025, 2025-2026 | 2017-2018, 2018-2019, 2019-2020, 2020-2021, 2021-2022, 2022-2023, 2023-2024, 2024-2025, 2025-2026 | 3 |
| Beaver Lake Cree Nation | 6,241.50 (shared included) | Verified | 2017-2018, 2018-2019, 2019-2020, 2020-2021, 2021-2022, 2022-2023, 2023-2024, 2024-2025 | 2025-2026 | 2014-2015, 2025-2026 | 7 |
| Bigstone Cree Nation | 33,765.70 | Verified | 2014-2015, 2015-2016, 2016-2017, 2017-2018, 2019-2020, 2020-2021, 2021-2022, 2022-2023, 2023-2024 | 2024-2025, 2025-2026 | 2024-2025, 2025-2026 | 11 |
| Blood | 136,264.60 | Verified | None | 2025-2026 | 2024-2025, 2025-2026 | 20 |
| Chiniki | 48,775.10 (shared included) | Verified | None | 2014-2015, 2015-2016, 2016-2017, 2017-2018, 2018-2019, 2019-2020, 2020-2021, 2021-2022, 2022-2023, 2023-2024, 2024-2025, 2025-2026 | 2014-2015, 2015-2016, 2016-2017, 2017-2018, 2018-2019, 2019-2020, 2020-2021, 2021-2022, 2022-2023, 2023-2024, 2024-2025, 2025-2026 | 0 |
| Chipewyan Prairie First Nation | 3,079.70 | Verified | 2014-2015, 2015-2016, 2016-2017, 2017-2018, 2018-2019, 2019-2020, 2020-2021, 2021-2022, 2022-2023 | 2023-2024, 2024-2025, 2025-2026 | 2023-2024, 2024-2025, 2025-2026 | 5 |
| Cold Lake First Nations | 20,853.40 (shared included) | Verified | 2016-2017, 2017-2018, 2019-2020, 2020-2021, 2021-2022, 2022-2023, 2023-2024, 2024-2025, 2025-2026 | None | None | 8 |
| Dene Tha' | 30,038.00 | Verified | 2014-2015, 2015-2016, 2018-2019, 2019-2020, 2020-2021, 2021-2022, 2022-2023, 2024-2025 | 2025-2026 | 2023-2024, 2025-2026 | 2 |
| Driftpile Cree Nation | 6,354.80 | Unverified | 2017-2018, 2019-2020, 2020-2021, 2021-2022, 2022-2023, 2023-2024, 2024-2025 | 2025-2026 | 2025-2026 | 8 |
| Duncan's First Nation | 2,426.10 | Verified | 2014-2015, 2015-2016, 2016-2017, 2017-2018, 2019-2020, 2021-2022 | 2025-2026 | 2022-2023, 2023-2024, 2024-2025, 2025-2026 | 5 |
| Enoch Cree Nation #440 | 5,308.20 | Verified | 2014-2015, 2017-2018, 2019-2020, 2020-2021, 2021-2022, 2022-2023, 2023-2024, 2024-2025, 2025-2026 | None | None | 7 |
| Ermineskin Tribe | 12,216.90 (shared included) | Verified | 2014-2015, 2015-2016, 2016-2017 | 2017-2018, 2018-2019, 2019-2020, 2020-2021, 2021-2022, 2022-2023, 2023-2024, 2024-2025, 2025-2026 | 2017-2018, 2018-2019, 2019-2020, 2020-2021, 2021-2022, 2022-2023, 2023-2024, 2024-2025, 2025-2026 | 1 |
| Fort McKay First Nation | 14,886.00 | Verified | 2019-2020 | None | None | 15 |
| Fort McMurray #468 First Nation | 3,231.70 | Verified | 2014-2015, 2015-2016, 2016-2017, 2017-2018, 2018-2019, 2019-2020, 2020-2021 | 2023-2024, 2024-2025, 2025-2026 | 2021-2022, 2022-2023, 2023-2024, 2024-2025, 2025-2026 | 3 |
| Frog Lake | 18,941.60 (shared included) | Verified | 2017-2018 | 2025-2026 | 2018-2019, 2019-2020, 2020-2021, 2021-2022, 2022-2023, 2023-2024, 2024-2025, 2025-2026 | 7 |
| Goodstoney | 48,775.10 (shared included) | Verified | None | 2014-2015, 2015-2016, 2016-2017, 2017-2018, 2018-2019, 2019-2020, 2020-2021, 2021-2022, 2022-2023, 2023-2024, 2024-2025, 2025-2026 | 2014-2015, 2015-2016, 2016-2017, 2017-2018, 2018-2019, 2019-2020, 2020-2021, 2021-2022, 2022-2023, 2023-2024, 2024-2025, 2025-2026 | 0 |
| Heart Lake | 4,600.70 (shared included) | Verified | 2014-2015 | 2020-2021, 2021-2022, 2022-2023, 2023-2024, 2024-2025, 2025-2026 | 2015-2016, 2016-2017, 2017-2018, 2018-2019, 2019-2020, 2020-2021, 2021-2022, 2022-2023, 2023-2024, 2024-2025, 2025-2026 | 6 |
| Horse Lake First Nation | 3,099.10 | Verified | 2015-2016, 2016-2017, 2017-2018, 2019-2020, 2020-2021, 2021-2022, 2022-2023, 2023-2024, 2024-2025 | 2025-2026 | 2025-2026 | 7 |
| Kapawe'no First Nation | 1,562.70 | Verified | 2014-2015, 2016-2017, 2017-2018, 2018-2019, 2019-2020, 2021-2022, 2022-2023, 2023-2024, 2024-2025 | 2025-2026 | 2020-2021, 2025-2026 | 4 |
| Kehewin Cree Nation | 8,321.20 (shared included) | Unverified | 2014-2015, 2015-2016, 2018-2019, 2019-2020, 2021-2022 | 2024-2025, 2025-2026 | 2020-2021, 2022-2023, 2023-2024, 2024-2025, 2025-2026 | 5 |
| Little Red River Cree Nation | 24,533.80 | Verified | 2014-2015, 2015-2016, 2016-2017, 2017-2018 | 2018-2019, 2019-2020, 2020-2021, 2021-2022, 2022-2023, 2023-2024, 2024-2025, 2025-2026 | 2018-2019, 2019-2020, 2020-2021, 2021-2022, 2022-2023, 2023-2024, 2024-2025, 2025-2026 | 0 |
| Loon River Cree | 21,906.30 | Verified | 2017-2018 | 2018-2019, 2019-2020, 2020-2021, 2021-2022, 2022-2023, 2023-2024, 2024-2025, 2025-2026 | 2018-2019, 2019-2020, 2020-2021, 2021-2022, 2022-2023, 2023-2024, 2024-2025, 2025-2026 | 7 |
| Louis Bull Tribe | 5,566.60 (shared included) | Verified | 2019-2020, 2020-2021, 2021-2022, 2022-2023, 2023-2024, 2024-2025 | 2025-2026 | 2025-2026 | 10 |
| Lubicon Lake Band No. 453 | 25,563.00 | Unverified | 2014-2015, 2015-2016, 2016-2017, 2017-2018, 2019-2020 | 2022-2023, 2023-2024, 2024-2025, 2025-2026 | 2018-2019, 2020-2021, 2021-2022, 2022-2023, 2023-2024, 2024-2025, 2025-2026 | 1 |
| Mikisew Cree First Nation | 5,116.10 | Verified | 2014-2015, 2015-2016, 2016-2017, 2017-2018, 2018-2019, 2019-2020, 2021-2022, 2022-2023, 2023-2024, 2024-2025 | 2025-2026 | 2020-2021, 2025-2026 | 5 |
| Montana | 4,745.90 (shared included) | Unverified | 2014-2015, 2015-2016, 2016-2017, 2017-2018, 2018-2019, 2019-2020, 2020-2021, 2021-2022, 2022-2023, 2023-2024, 2024-2025 | 2025-2026 | 2025-2026 | 3 |
| O'Chiese | 14,132.00 | Verified | 2014-2015, 2017-2018 | 2025-2026 | 2015-2016, 2016-2017, 2018-2019, 2025-2026 | 10 |
| Paul | 7,330.60 | Verified | 2016-2017, 2017-2018, 2019-2020, 2020-2021, 2021-2022, 2022-2023, 2023-2024, 2024-2025, 2025-2026 | None | None | 7 |
| Peerless Trout First Nation | 26,609.20 | Verified | 2016-2017, 2017-2018 | 2018-2019, 2019-2020, 2020-2021, 2021-2022, 2022-2023, 2023-2024, 2024-2025, 2025-2026 | 2018-2019, 2019-2020, 2020-2021, 2021-2022, 2022-2023, 2023-2024, 2024-2025, 2025-2026 | 6 |
| Piikani Nation | 45,677.80 | Verified | 2020-2021 | 2022-2023, 2023-2024, 2024-2025, 2025-2026 | 2019-2020, 2022-2023, 2023-2024, 2024-2025, 2025-2026 | 14 |
| Saddle Lake Cree Nation | 30,419.50 (shared included) | Verified | 2017-2018, 2019-2020, 2020-2021, 2021-2022, 2022-2023, 2023-2024, 2024-2025 | 2025-2026 | 2014-2015, 2015-2016, 2016-2017, 2025-2026 | 8 |
| Samson | 15,607.50 (shared included) | Verified | 2015-2016, 2018-2019, 2019-2020, 2020-2021, 2021-2022, 2023-2024, 2024-2025 | 2025-2026 | 2025-2026 | 5 |
| Sawridge First Nation | 2,143.30 | Verified | None | 2014-2015, 2015-2016, 2016-2017, 2017-2018, 2018-2019, 2019-2020, 2020-2021, 2021-2022, 2022-2023, 2023-2024, 2024-2025, 2025-2026 | 2014-2015, 2015-2016, 2016-2017, 2017-2018, 2018-2019, 2019-2020, 2020-2021, 2021-2022, 2022-2023, 2023-2024, 2024-2025, 2025-2026 | 0 |
| Siksika Nation | 71,087.50 | Verified | 2016-2017 | 2021-2022, 2022-2023, 2023-2024, 2024-2025, 2025-2026 | 2021-2022, 2022-2023, 2023-2024, 2024-2025, 2025-2026 | 11 |
| Sturgeon Lake Cree Nation | 15,664.50 | Verified | None | 2025-2026 | 2020-2021, 2025-2026 | 15 |
| Sucker Creek | 5,987.00 | Verified | 2016-2017, 2019-2020, 2020-2021, 2021-2022, 2022-2023, 2023-2024, 2024-2025, 2025-2026 | None | None | 5 |
| Sunchild First Nation | 5,218.10 | Verified | 2014-2015, 2016-2017, 2018-2019, 2019-2020 | 2024-2025, 2025-2026 | 2020-2021, 2021-2022, 2022-2023, 2023-2024, 2024-2025, 2025-2026 | 6 |
| Swan River First Nation | 4,342.70 | Verified | 2014-2015, 2015-2016, 2016-2017, 2017-2018, 2018-2019, 2019-2020, 2020-2021, 2021-2022, 2022-2023, 2023-2024, 2024-2025 | 2025-2026 | 2025-2026 | 2 |
| Tallcree Tribal Government | 8,160.30 | Verified | 2016-2017, 2017-2018, 2018-2019, 2019-2020, 2020-2021, 2021-2022, 2022-2023 | 2023-2024, 2024-2025, 2025-2026 | 2023-2024, 2024-2025, 2025-2026 | 2 |
| Tsuut'ina Nation | 29,417.40 | Verified | None | 2015-2016, 2016-2017, 2017-2018, 2018-2019, 2019-2020, 2020-2021, 2021-2022, 2022-2023, 2023-2024, 2024-2025, 2025-2026 | 2015-2016, 2016-2017, 2017-2018, 2018-2019, 2019-2020, 2020-2021, 2021-2022, 2022-2023, 2023-2024, 2024-2025, 2025-2026 | 2 |
| Tthebatthie Denesųłiné Nation | 10,049.70 | Verified | 2019-2020, 2021-2022, 2022-2023, 2023-2024 | 2024-2025, 2025-2026 | 2024-2025, 2025-2026 | 8 |
| Whitefish Lake | 8,299.70 | Unverified | 2019-2020, 2022-2023, 2023-2024, 2024-2025 | 2025-2026 | 2018-2019, 2020-2021, 2021-2022, 2025-2026 | 5 |
| Whitefish Lake First Nation #128 | Not verified | Unverified | None | 2014-2015, 2015-2016, 2016-2017, 2017-2018, 2018-2019, 2019-2020, 2020-2021, 2021-2022, 2022-2023, 2023-2024, 2024-2025, 2025-2026 | 2014-2015, 2015-2016, 2016-2017, 2017-2018, 2018-2019, 2019-2020, 2020-2021, 2021-2022, 2022-2023, 2023-2024, 2024-2025, 2025-2026 | 0 |
| Woodland Cree First Nation | 16,106.00 | Verified | 2023-2024 | 2017-2018, 2018-2019, 2024-2025, 2025-2026 | 2017-2018, 2018-2019, 2019-2020, 2020-2021, 2021-2022, 2022-2023, 2024-2025, 2025-2026 | 7 |
