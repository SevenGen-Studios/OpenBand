# Alberta implementation report

Audit generated: 2026-09-11T11:48:11+00:00

## Result

Alberta is supported through the shared OpenBand application and data schemas. All 48 recognized Alberta governments have profiles; financial, logo, business, leadership, and map coverage remain explicitly partial. The existing 69 Saskatchewan profiles and their filing/remuneration data remain intact.

| Coverage | Result |
|---|---:|
| Alberta governments | 48 of 48 |
| Distinct ISC identifiers | 47, with the documented shared 462 exception |
| Treaty 6 / 7 / 8 | 17 / 7 / 24 |
| Indexed financial PDFs | 754 |
| Audited / remuneration PDFs | 400 / 354 |
| Successfully validated documents | 256 (121 audited, 135 remuneration) |
| Documents requiring review | 498 |
| Technical retrieval/parser errors remaining | 0 |
| Nations with audited and remuneration filings | 43 |
| Visually verified logos | 28 |
| Source-listed official websites | 47; some are inaccessible or unverified at present |
| Verified businesses / owning Nations | 8 / 11 |
| Separately verified map points | 47 |

The PDF count covers 754 distinct ISC-indexed disclosures that were downloaded and hashed. A separate Tallcree official-site version has a visually verified cover and is linked for equivalence review. A Fort McKay annual community report is also linked; it is not counted as an audited statement.

The roster reconciles 48 governments with 47 distinct ISC band numbers: Whitefish Lake #128 shares ISC 462 with Saddle Lake. Stoney Tribal Administration (471) is linked as shared administration rather than duplicated as a fourth Stoney Nation. Onion Lake retains its original Saskatchewan profile and is linked for cross-border discovery.

## Fiscal-year coverage

| Fiscal year | Actual posted documents |
|---|---:|
| 2014-2015 | 84 |
| 2015-2016 | 80 |
| 2016-2017 | 80 |
| 2017-2018 | 75 |
| 2018-2019 | 67 |
| 2019-2020 | 71 |
| 2020-2021 | 63 |
| 2021-2022 | 63 |
| 2022-2023 | 59 |
| 2023-2024 | 54 |
| 2024-2025 | 46 |
| 2025-2026 | 12 |

## Missing and uncertain data

No individual disclosures are indexed for Bearspaw, Chiniki, Goodstoney, Sawridge, or Whitefish Lake #128. Shared Stoney disclosures are linked without attributing shared totals to individual Nations. Missing fiscal years are not manufactured.

The 498 unresolved documents comprise 495 manual-review records and 3 links containing the wrong document type. Reasons include scans, uncertain cover identity/year, ambiguous columns, incomplete statement sections, and failed reconciliation. These values are excluded from public financial summaries and comparisons. All 754 PDF URLs returned PDF content during retrieval; 10 profile/official-site source-access or identity issues remain separately recorded. Twenty logos remain unverified.

The audit also flags 5 missing financial-position sections and 3 balance-sheet discrepancies. Business coverage is limited to sourced ownership evidence; no business revenue, profits, or ownership percentages were inferred. Registered population is distinct from on-own-reserve population. Current term-verified leadership is separate from historical remuneration; appointment dates are not called election dates.

## Shared parser correction and Saskatchewan preservation

Source-level tests found that an “Excess of revenue over expenses” row could enter the expense breakdown, inflating expenses. The shared parser now stops before the annual result, recognizes final operating surplus and excess/deficiency labels, and avoids counting both other-income components and their subtotal. All 400 Alberta audited disclosures were reprocessed with the corrected parser.

The same defect affected eight existing Muskeg Lake summaries. Seven were corrected after rechecking their original ISC PDFs. The 2018-2019 summary is withheld because its re-extraction does not reconcile. Previous summaries and new source extractions are preserved in [the review record](manual_overrides/muskeg-lake-parser-review.json).

A Git comparison confirmed that all 69 original Saskatchewan profile/filing records, contacts, members, map entries, logos, news, projects, jobs, elections, enterprise records, and all other Saskatchewan financial summaries are unchanged. No existing profile route was removed.

## Files and scripts

- Shared datasets: `data.json`, `capital-data.json`, `community-enterprise.json`, `contacts-data.json`, `member-counts.json`, `map-data.json`, `first-nation-logos.json`, and `first-nation-logo-report.json`.
- Source registries and review records: `alberta-nations.json`, `alberta-enrichment.json`, `alberta-businesses.json`, `manual_overrides/alberta-logo-reviews.json`, `manual_overrides/muskeg-lake-parser-review.json`, and the two official snapshots in `tools/alberta-source-cache/`.
- New ingestion/research/audit scripts: `tools/refresh_alberta_roster.py`, `tools/ingest_alberta.py`, `tools/enrich_alberta.py`, `tools/merge_alberta_enrichment.py`, and `tools/audit_alberta.py`.
- Shared scripts updated: `tools/capital_parser.py`, `tools/build_site.py`, `tools/build_map_data.py`, `tools/collect_first_nation_logos.py`, `tools/contact_scraper.py`, `tools/member_count_scraper.py`, `tools/jobs_collector.py`, and `tools/merge_previous_data.py`.
- UI: `index.html`, `assets/openband.js`, `assets/openband.css`, new `assets/provinces.js` and `assets/province-ui.js`; regenerated Browse, News, 117 profile pages and their legacy redirects, and `sitemap.xml`.
- Assets: 28 visually verified official logos under `public/first-nation-logos/`; no generated logos.
- Automation: `.github/workflows/alberta-ingestion.yml` produces a review artifact without automatic publication.
- Tests: `tests/test_alberta.py`, `tests/test_provinces.js`, two real statement fixtures, and updated route/jobs/project coverage assertions that preserve original Saskatchewan checks.
- Documentation: `README.md`, `ALBERTA.md`, this report, and `alberta-coverage-report.json`, `.md`, and `.html`.

## Verification performed

- All 187 Python tests pass: `python -m unittest discover -s tests`.
- JavaScript province, treaty, alias/ISC search, same-year comparison, null-value, and duplicate-source aggregation tests pass: `node tests/test_provinces.js`.
- JavaScript syntax checks and `git diff --check` pass.
- All 117 generated profile routes returned HTTP 200 on the local server. Existing profile and legacy redirect routes are covered by the route suite.
- Browser checks verified Alberta 48, Saskatchewan 69, Treaty 7 counts, Goodfish alias search, province-specific treaty options, compatible-year comparison figures, capital history charts, remuneration, source PDF links, rendered official logos, population, current leadership, and business ownership content.
- Original PDF spot checks produced permanent Alexander and Alexis regression fixtures; all 400 Alberta audited statements were then revalidated.
- Coverage audit reconciles the roster and reports no duplicate Nation IDs, unexpected shared ISC identities, duplicate document URLs/hashes, or incorrect URL fiscal-year matches.

## Continuing maintenance

See [ALBERTA.md](ALBERTA.md) for discovery, parsing, OCR retry, review, generation, and workflow commands. Detailed per-document statuses, warnings, hashes, source URLs, and Nation-level missing periods are in [the coverage ledger](alberta-coverage-report.json). The local PDF/OCR cache is ignored by Git and supports resumable research.

The work is implemented locally. No deployment or public publication was performed.

## Integration with current main

Before pushing, the Alberta changes were merged with 74 newer upstream commits. The merge preserves the Waterhen 3D map, updated homepage and revenue explorer, and newer Saskatchewan data. All 223 tests in the combined suite pass, as do the province JavaScript checks and Alberta coverage audit. The eight documented Muskeg Lake corrections remain in place.
