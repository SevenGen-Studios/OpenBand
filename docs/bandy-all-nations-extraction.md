# Bandy all-Nations financial extraction

The 2026-10-09 research run processed every posted audited statement in the
current OpenBand inventory: **1,135 documents for 117 Nations in Saskatchewan
and Alberta**. This scope does not include every First Nation in Canada.

Outputs are in `research/bandy-financial/all-nations-2026-10-09/export/`:

Large JSONL and SQLite exports are versioned as lossless `.gz` files to fit
GitHub file limits. Original uncompressed files remain available in the working
directory where extraction ran. On a fresh checkout, restore missing originals
with this Python snippet, run from the repository root:

```python
import gzip
import shutil
from pathlib import Path

root = Path("research/bandy-financial/all-nations-2026-10-09/export")
for source in root.glob("*.gz"):
    target = source.with_suffix("")
    if not target.exists():
        with gzip.open(source, "rb") as incoming, target.open("xb") as outgoing:
            shutil.copyfileobj(incoming, outgoing)
```

`archive-manifest.json` records SHA-256 checksums and byte sizes for both the
compressed files and their original content. Source checkpoints, downloaded
PDFs, and transient run logs remain local and are excluded from Git.

- 111 Nations with page-backed financial records; 37 with machine-checked records.
- 47,421 normalized records across fiscal years 2012-2013 through 2025-2026:
  9,891 machine-checked and 37,530 requiring manual verification.
- 82,230 source observations retained, including comparative versions and
  duplicate candidates; 5,891 conflicting metric/year/dimension groups flagged.
- 6,852 canonical candidates without confirmed page evidence excluded from
  financial queries and retained in `unbacked-candidates.jsonl`.
- 8,414 qualitative note disclosures and 1,697 reporting-entity disclosures.
- No failed document reads and no changes to previously recorded source hashes.

`REPORT.md` contains coverage for each Nation and each metric. `summary.json`
contains counts and validation flags. `nation-coverage.json` includes missing
filing years, unavailable metrics, and coverage by fiscal year.

Six Nations have no posted audited source in this inventory: Ochapowace,
Bearspaw, Chiniki, Goodstoney, Sawridge, and Whitefish Lake #128. No values were
invented for them. Another 121 individual historical documents yielded no
structured numerical records; see `document-report.jsonl` for limitations.

## Query the research dataset

Use `financial.sqlite`. The `checked_financial_records` view excludes all review
records. Automated checks are not independent manual verification and do not
authorize a production import.

```sql
SELECT band_id, fiscal_year, metric, value, source_document, source_page
FROM checked_financial_records
WHERE metric IN ('totalRevenue', 'totalExpenses', 'annualSurplusDeficit')
ORDER BY band_id, fiscal_year, metric;

SELECT band_name, status, record_count, checked_record_count
FROM nation_coverage
ORDER BY band_name;
```

`financial_records` includes both checked and review records. Each record's
`record_json` retains its source document SHA-256, explicit actual-year column,
raw source rows, physical PDF page, bounding boxes, extraction basis, and flags.
`observations` retains every source version, including incomplete candidates.
`observation_links` connects normalized records to their original observations.
Equal values coalesce. Disagreeing versions remain flagged; choosing a
representative review record does not resolve the disagreement. Consult
`conflicts.json` and the underlying observations before resolving one.

JSONL counterparts support loading the same data without SQLite. Notes and
entity names are qualitative disclosures, not verified ownership assertions.
Derived revenue subtotals identify disclosed components only; they do not
estimate a complete own-source or government revenue amount from a residual.

## Extraction and recovery

`tools/bandy_corpus.py` downloads and hashes public sources, processes native
statement tables, and saves resumable per-document research checkpoints.
`tools/bandy_ocr_recovery.py` recovers scanned statements using free local
Windows OCR. For this run, OCR attempted 348 documents and added 15,658
observations from 260 documents. **All OCR figures require manual review.**
Recovery examines the first 16 PDF pages; later scanned notes are unavailable.
Raw PDFs are cached locally and ignored by Git. Existing validated Community
Capital figures, `data.json`, `capital-data.json`, and website files are untouched.

For a fresh run, install the repository Python requirements and, on Windows,
the optional `winocr` bindings in `tmp/bandy-runtime`. Use a new research output
directory; completed exports refuse replacement:

```powershell
python -m pip install -r requirements.txt
python -m pip install --target tmp/bandy-runtime winocr==0.0.15
python -m tools.bandy_corpus --all-nations --workers 4 --no-finalize --output research/bandy-financial/NEW-RUN
python -m tools.bandy_ocr_recovery --root research/bandy-financial/NEW-RUN --workers 4 --merge
python -m tools.bandy_corpus --all-nations --finalize-only --output research/bandy-financial/NEW-RUN
```

The last command exports the saved native and OCR checkpoints. Do not rerun
native extraction between OCR merging and finalization, as that replaces research checkpoints.
Parser changes invalidate native checkpoints. `--retry-empty` retries empty OCR
results after layout improvements; existing nonempty OCR checkpoints are reused.

No production merge, website build, paid API, commit, or push is part of these
extraction commands.

## Validation

The run checks explicit fiscal-year/actual-column selection, source identity,
audit evidence, provenance, duplicate identifiers, conflicting source versions,
unexpected signs and magnitudes, large historical changes, revenue/expense
component sums, annual result, financial assets less liabilities, accumulated
surplus, and the balance sheet. Missing check inputs require review.

Final export verification checks SQLite integrity, exact row counts, all 117
coverage rows, source URLs/hashes/page evidence, checked-record flags, and
conflict quarantine. Regression tests include split statement/date titles,
budget-column exclusion, OCR bounding boxes, idempotent recovery merging,
cross-document conflicts, duplicate observations, and exclusion of unbacked
candidates from financial queries.
