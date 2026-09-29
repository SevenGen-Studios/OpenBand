# Docling local benchmark

Date: 2026-09-29. Docling 2.131.0, isolated Python 3.12 environment.
No OpenAI calls were made. No public financial datasets were overwritten.
Docling remains optional and disabled by default.

Three FY2024-2025 official ISC PDFs were downloaded through the source URLs
already attached to capital-data.json. Statement pages were rendered and
visually compared with extraction output. This was a capital benchmark, not
a remuneration benchmark or a full-document verification of every field.

| Community / ISC band | PDF page | Verified revenue | Verified expenses | Final surplus / deficit | Docling result |
| --- | --- | ---: | ---: | ---: | --- |
| Fort McKay / 467 | 6 | 111,781,540 | 72,291,197 | 7,308,429 | Revenue overstated by 682,399; expenses and final surplus matched; blocked |
| Cold Lake / 464 | 7 | 49,967,693 | 45,328,903 | 14,587,510 | Selected budget amounts rather than actual amounts; blocked |
| Montana / 442 | 7 | 22,219,050 | 16,371,157 | -442,969 | Revenue and deficit matched; expenses understated by 1,216,900; blocked |

Elapsed per document: 253.47, 153.51 and 112.24 seconds respectively.
The first run included model initialization/download overhead. Local model
storage was approximately 506 MB. Results are not a performance guarantee.

## Issues exposed

- Fort McKay: a missing dash in a current-year revenue cell shifted a budget
  amount into actual revenue. Flattened table text does not preserve empty
  monetary positions reliably.
- Cold Lake: actual precedes budget, unlike the other two documents.
  The existing baseline also returned incorrect revenue and budget expenses
  while marking the candidate publishable because final surplus was missing.
  This record needs manual review; it must not be treated as verified.
- Montana: the Special Projects expense of 1,216,900 was omitted by the
  Docling/text path. The baseline extracted the three headline values correctly.
- All three statements contain separately reported adjustments after operating
  surplus. Fort McKay reports 32,181,914 in other items; Cold Lake reports
  9,948,720 in other income; Montana reports -6,290,862 in other revenue/
  expenditures. These explain the final surplus and must be extracted explicitly,
  rather than forcing a simple revenue-minus-expenses identity.

## Decision

### Structured-cell follow-up

The new capital_docling_structured_v1 path selects the current non-budget
column from individual table headers and keeps monetary cells separate.
Cached extraction was rechecked without API calls or additional conversion.
Cold Lake now matches all three verified headline values and reconciles its
9,948,720 adjustment subtotal. Fort McKay matches headline totals but remains
blocked for missing actual-cell dashes. Montana remains blocked for merged
Social Services / Special Projects cells and unreconciled adjustments.
Validated candidate coverage is now 1/3, not a complete capital-data recovery.
Ancillary financial metrics are deliberately unavailable in this path until
their own tables are verified. Public datasets have not been modified.

Regression coverage includes actual-first columns, blank cells, merged rows,
wrong years, multiple candidate tables, and separately reported adjustments.
Full suite: 253 tests passed, one skipped.

```sh
python -m tools.benchmark_docling --reuse-extraction
```

Do not enable a blanket Docling backfill based on this trial. Validated new
publication coverage in the original text-only trial was 0/3. Improved text recovery is not equivalent to
correct financial extraction. Keep the adapter experimental and opt-in.

Next work should preserve structured table cells, resolve actual/budget/prior
columns from their coordinates and headers, retain blank positions, capture
separate surplus adjustments, and tighten acceptance when headline totals are
missing. Add source-backed fixtures for these cases before broad activation.

## Reproduction

Install requirements-docling.txt into an isolated environment, then run:

```sh
OPENBAND_ENABLE_DOCLING=true python -m tools.benchmark_docling --bands 467,464,442
```

The benchmark writes downloaded PDFs, extracted tables and candidate summaries
to its separate output directory, not capital-data.json. Inspect original PDFs
before accepting any candidate. The report's verifiedAgainstPdf field remains
false because the full output has not been verified; the headline checks above
are deliberately narrower.

Verification: full suite passed 243 tests (one skipped); focused adapter tests
passed after diagnostic changes. No production UI changes were made.
