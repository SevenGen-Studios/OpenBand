# Bandy financial infrastructure: milestone 1

Implemented on October 9, 2026. Research outputs are isolated under
`research/bandy-financial/milestone-1`. No website files or production data were
changed, and no production import or automatic promotion is included.

## Existing functionality retained

`tools/capital_parser.py` already parses audited statements into
`capital-data.json` (`bands[bandId].years[fiscalYear]`). It extracts total revenue,
expenses, annual surplus/deficit, revenue and expense categories and source rows,
expense schedules, capital spending/assets, cash/investments and debt. Its newer
fields already cover receivables, deferred revenue, accumulated surplus, net
financial assets/debt, several government and own-source revenue components,
and some cash-flow labels.

The existing pipeline supports native PDF text, coordinate reconstruction,
local OCR and optional Docling. Publication checks include fiscal-year selection,
category reconciliation and annual-result reconciliation; the audit and recovery
merge tools protect existing usable and manually verified summaries.

A read-only inventory of the current Saskatchewan production snapshot found
450 publishable year summaries with revenue and expense totals, 418 with annual
results, 385 with combined cash/investments, 346 with capital assets and 425 with
debt. Individually named extended fields are less widely populated: 16 summaries
contain `cash`, 20 contain receivables, 20 contain long-term debt and 21 contain
accumulated surplus. These counts describe stored coverage, not independent
verification of every figure. The extension reuses the working parser rather
than rebuilding these capabilities.

## Implemented changes

- Expanded explicit balance-sheet labels in the existing parser: accounts
  payable **and accruals**, total **financial** liabilities, portfolio investments,
  GICs, business and joint-venture investments, non-financial asset totals,
  current debt, refinancing loans, claim loans, bank indebtedness, lease
  obligations, retirement obligations and contaminated-site liabilities.
- Fixed numbers in labels such as `Treaty 4` and `1907 Specific Claim` being
  treated as monetary values, including wrapped lines without an amount.
- Added `tools/bandy_financial.py`. It uses native word coordinates to isolate
  explicit actual columns, then feeds current and comparative columns into the
  existing Community Capital parser. Budget cells are excluded; blank actual
  cells stay missing; printed dashes retain their original evidence and mean zero.
- Preserved nested government funding context, including ISC funding categories
  and deferred funding movements. Exported government and own-source subtotals
  include only explicitly identified components. They are not exhaustive totals
  or residual estimates.
- Added source-backed note text and reporting-entity disclosures in separate
  collections. Qualitative entity names are never encoded as dollar amounts.
- Added normalized JSON, checked-only JSONL, an indexed SQLite database and a
  JSON Schema. Each numeric record retains band ID, fiscal year, metric, value,
  original URL, PDF hash, one-based PDF page, original label/text/cell, coordinates,
  selected year, extraction basis and validation status.
- Added strict accounting checks with a maximum $2 absolute rounding difference,
  duplicate/conflict checks, missing-input and provenance flags, negative/magnitude
  checks and large adjacent-year change flags. Checks do not correct source values.

## Real audited sample and results

The sample is three Saskatchewan statements for the year ended March 31, 2025,
including their March 31, 2024 comparatives. Source URLs, retrieval date, PDF
SHA-256 hashes and reproducible native text/coordinate fixtures are recorded in
`tests/fixtures/bandy-sk/manifest.json`. The downloadable PDFs were checked against
their hashes and key statement pages were rendered and visually inspected.

| First Nation | Band ID | Numeric records across both years | Additional metric types recovered |
| --- | --- | ---: | ---: |
| Kahkewistahaw First Nation | 362 | 139 | 9 |
| George Gordon First Nation | 391 | 136 | 8 |
| Kinistin Saulteaux Nation | 377 | 107 | 7 |

**382 numeric records**, including **377 machine-checked** observations and
**5 requiring manual review**, plus **37 relevant note-page disclosures** and
**20 reporting-entity/investee disclosures**. All note and entity disclosures
remain marked for manual interpretation. All **36 accounting checks** pass:
six checks for each of six nation/year combinations. Machine-checked extraction
is an automated result, not an independent audit or production approval.

Fourteen additional metric types were successfully extracted in this sample:
portfolio investments, GICs, business investments, joint-venture investments,
non-financial assets, current long-term debt, loans subject to refinancing,
claim loans, bank indebtedness, capital leases, current capital leases, asset
retirement obligations, contaminated-site liabilities and program-expense totals.
Several previously supported fields were also recovered using the additional
explicit label variants.

Examples from 2024-2025:

| Metric | Kahkewistahaw | George Gordon | Kinistin |
| --- | ---: | ---: | ---: |
| Business investments | $2,010,276 | $11,030,811 | Unavailable |
| Portfolio investments | $965 | Unavailable | Unavailable under this label |
| Guaranteed investment certificates | Unavailable | Unavailable | $3,172,664 |
| Current portion of long-term debt | $15,715,196 (review) | $1,094,579 | $496,000 |
| Accounts payable and accruals | $10,084,241 | $2,829,899 | $1,701,694 |
| Total liabilities | $107,728,606 | $27,478,375 | $20,300,347 |
| Claim loan | Unavailable under this label | Unavailable under this label | $667,455 |

Unavailable means no supported, explicit source observation was extracted;
it does not mean zero or prove the item does not exist. Kinistin separately
reports `investments` of $66,010; this is retained under the existing metric.

## Unavailable and manual-review information

The machine-readable `review-report.json` lists extracted, additional and
unavailable metrics separately for every nation and year, with each accounting
check and every flagged financial observation.

- Separate **administrative expenses** were not explicitly reported in the
  primary program statements. `Band Government` remains an expense-program row;
  it is not relabelled as administration.
- No explicit Saskatchewan-government revenue row was identified. Transfers
  via tribal councils and other organizations remain their original revenue
  components; government provenance is not inferred.
- Own-source and government revenue exports use
  `extractionBasis=identified_components_only`; complete totals require more
  classification evidence. Business revenue is also an identified subtotal,
  retaining the reported sign of business losses.
- Individual investment-holding note tables, loan-by-loan maturity schedules,
  contingencies, ownership percentages and business-level financial statements
  remain in source-backed notes for manual interpretation. These are not mixed
  into the Nation's consolidated totals. Some business entities have December
  year-ends and some note headers use different years.
- Five Kahkewistahaw 2024-2025 observations stay in review: annual surplus
  $132,134,851; financial assets $184,737,261; current long-term debt
  $15,715,196; accumulated surplus $197,675,254; and derived total assets
  $305,403,860. Four trigger large year-over-year changes; total assets inherits
  its component's review flag. The statement separately reports a $133,698,067
  agricultural-benefits settlement in other items. Passing reconciliation does
  not clear these flags.

## Querying and rerunning

Run from the repository root with Python and the existing `requirements.txt`:

```sh
# Deterministic offline extraction from source-hashed native fixtures.
python -m tools.bandy_financial --output research/bandy-financial/new-offline-run

# Re-read the actual PDFs, download if absent, and verify manifest hashes.
python -m tools.bandy_financial --download \
  --output research/bandy-financial/new-pdf-run

python -m unittest discover -s tests
```

The CLI defaults to a three-document limit and refuses manifests larger than
ten documents. Native coordinate extraction is the milestone's supported path.
Scanned PDFs, missing/ambiguous year headers, scaled units and unsupported currency
are quarantined rather than guessed. The existing OCR pipeline remains available
separately, but its output is not automatically promoted into this export.

Output paths must stay under `research/bandy-financial`. Existing exports are
never overwritten; use a fresh directory for another run. The CLI has no paid
AI fallback and no option to update `capital-data.json` or the public website.

The SQLite `financial_records` table contains all observations. Use
`checked_financial_records` for the 377 records that passed automated checks:

```sql
SELECT band_id, fiscal_year, metric, value, source_document, source_page
FROM checked_financial_records
WHERE metric IN ('businessInvestments', 'guaranteedInvestmentCertificates',
                 'loansPayable', 'accountsPayable')
ORDER BY band_id, fiscal_year, metric;
```

`record_json` retains full provenance and flags in SQLite. The JSON export also
contains document metadata, note disclosures and entity disclosures. JSONL
contains only checked numeric observations. Dimensions identify individual
revenue components, expense programs and annual-result adjustments. Do not sum
totals together with their components or add identified subtotals to total revenue.
`totalAssets` is explicitly marked as derived where financial and non-financial
assets were added. Comparative records retain the newer source document's fiscal
year in `sourceFiscalYear`; cross-document duplicates and restatement conflicts
are retained and flagged rather than silently selected.

## Validation completed

- Full Python suite: **358 tests passed**, including **18 new financial tests**.
- All **four JavaScript regression runners passed**; public-facing files remain
  unchanged.
- Tests cover actual/current/prior figures, direct source evidence, budget
  exclusion, blank-versus-zero cells, wrong/ambiguous years, scaled units,
  label numbers, nested ISC context, duplicates/conflicts, missing fields,
  accounting inconsistencies, suspicious figures, identity mismatch, review
  flags, queryable exports and production-file immutability.
- The downloaded-source run produced the milestone dataset; the offline fixture
  run is covered by tests. Each source PDF's hash was verified before parsing.
- `capital-data.json` remains unchanged; no public-facing files are in the diff.
