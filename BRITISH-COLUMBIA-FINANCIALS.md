# British Columbia financial records

Phase 3 builds on the 204 verified Phase 2 government and administration profiles. The count spans overlapping band/village, national and administrative levels. It is not a count of mutually exclusive populations or reporting groups.

## Published and discovered

All 204 profiles were checked against supported sources. The 201 ISC identities were checked against their individual financial listings; source-listed official websites were explored where available, up to five relevant pages each. This is bounded discovery, not an exhaustive search of every official archive.

The ISC index contains **4,048 documents: 2,033 audited-statement listings and 2,015 remuneration-schedule listings**, covering 2014–15 through 2025–26. Official-site PDFs are separately recorded as candidates until their government, type and actual period are reviewed. A health authority, village, trust or shared administration is never silently assigned to its related central government.

The first bounded extraction batch processed **24 documents**. The user explicitly approved the frozen three-candidate batch in `docs/BC-PHASE3-APPROVAL.json`:

- Bonaparte First Nation, 2025–26 audited statement: revenue 19,803,109; expenses 11,975,742; annual surplus 7,827,367. Current-year operations on PDF page 8 were visually checked.
- Cheam First Nation, 2025–26 audited statement: revenue 12,484,788; expenses 15,640,335; annual deficit 3,155,547. The actual column on PDF page 7 was visually checked separately from budget and prior year.
- Aitchelitz, 2025–26 remuneration: the complete two-person schedule on PDF page 3 and practitioner review on page 2 were visually checked. Exact names, titles and remuneration/expense columns are preserved. No travel or benefits amount is invented. Combined totals are calculated and labelled accordingly; the source reports no footer total.

Only these three approved documents enter `data.json` and `capital-data.json`. Native text, proposed names and uncertain OCR output remain in ignored staging. The shared financial overview, year selector, history, remuneration and original-source views consume the existing schemas.

## Coverage and remaining work

See [the fiscal-year coverage report](bc-financial-coverage-report.md) and its JSON companion for all twelve years, field-specific coverage, source retrieval errors, government/year discovery states and every unresolved indexed document. Discovery and extraction have different denominators.

**4,024 indexed documents remain unprocessed; 21 processed documents require review.** Official-site PDF candidates form an additional, separately counted identity/period review queue in `bc-financial-index.json`. No full historical extraction or complete official-site search is claimed.

Two scanned Beecher Bay documents received free local RapidOCR retries. One recovered text but remained under review; one hit the 180-second worker timeout. Neither was published. Download hashes and resumable checkpoints are retained even after a timeout.

The two published audits are **withheld from cross-government comparisons** until a reviewer explicitly confirms currency, annual period and consolidated entity scope. The comparison gate requires a recorded compatible basis; tests cover missing values, incompatible periods, shared statements and duplicate source hashes. Existing SK/AB/MB comparison behavior remains unchanged. Modern treaty/national governments are not silently pooled with band governments. Other periods and entity frameworks require their own reviewed compatibility policy.

Absent ISC entries, inaccessible sources and unassigned official-site candidates remain distinct. They are never evidence of legal noncompliance. Treaty/self-government evidence comes from Phase 2's official sources; it does not establish a uniform FNFTA obligation.

## Refresh and extraction

Run from the repository root with the existing requirements and free OCR dependencies installed:

```powershell
python -m tools.ingest_bc --discover --refresh --audit
python -m tools.ingest_bc --parse --year 2025-2026 --limit 20 --workers 3
python -m tools.ingest_bc --parse --band 640 --year 2025-2026 --document-type audited --ocr --retry --limit 1 --workers 1
python -m tools.audit_bc --financial
python -m tools.bc_financial_report
```

`--refresh` combined with `--parse` fetches fresh selected PDF bytes and invalidates a worker result when the source hash changes, including revisions at the same URL. An existing public statement is never automatically replaced.

The scope constant `YEARS` currently covers the requested 2014–15 through 2025–26 period. Extend it for newly completed reporting years. Fiscal labels do not imply a March 31 year-end; the actual cover date is separately required.

`--band`, `--year`, `--document-type`, `--limit`, `--workers`, `--retry`, `--refresh` and `--ocr` support targeted resumable work. Discovery checks complete source pages, retaining their historical links even when extraction is year-filtered. Worker concurrency is capped at four. Native workers are bounded at 45 seconds and OCR workers at 180 seconds. A writer lock prevents competing provincial transactions.

Set `OPENBAND_OCR_ENGINE=tesseract` or `rapidocr`; provide Poppler and the selected local backend. Native text is followed by the shared coordinate-aware parser and then local OCR when requested. No paid extraction or OpenAI fallback is enabled. Low-confidence columns, scaled currency units, wrong entity/year, unreconciled totals, missing provenance and incomplete remuneration schedules remain under review.

Official-site candidates can be indexed after source review using `python -m tools.review_bc_documents --manifest PATH`. The manifest format is documented in that module. It requires a URL already found on a successfully checked official page and explicit entity/type/period evidence; it accepts no figures. Shared reporting scope is retained and withheld from automatic allocation.

## Approval and recovery

All extraction writes to `.openband-ocr/british-columbia/`:

- `results.json`: resumable per-document results and exact remaining processing state.
- `*.source` and matching metadata: original downloaded bytes and SHA-256.
- `<PDF-SHA>.text.json`: layout-preserving native text with original PDF page numbers.
- `*.task.json`, `*.result.json`, `*.ocr.json`: bounded-worker and OCR checkpoints.
- `review-batch.json`: hash-bound proposed import; no automatic publication.
- `approval-batch-first.json` / `approval-first.json`: the frozen user-approved initial batch and approval.
- `imports/`: pre-import public data backups and transaction receipts.

To import a future batch, review its exact source pages and all candidate fields. Record `approved: true`, `reviewer`, `approvedAt`, its exact `batchSha256` and an explicit list of `candidateKeys`. Then run:

```powershell
python -m tools.import_bc_financials --approval APPROVAL.json --batch FROZEN-BATCH.json
python -m tools.audit_bc --financial
python -m tools.build_site --province BC
```

The importer rechecks batch and PDF hashes, accounting validation, remuneration quality, duplicate/revised sources, government identity and the protected baseline before atomic replacement. It backs up both public datasets and rolls back either file if validation or replacement fails. Comparison reviews additionally require a supported basis and source evidence; they are not inferred from a fiscal label.

The manual `.github/workflows/bc-financial-ingestion.yml` performs discovery, bounded free extraction, validation, tests and artifact upload only. It has read-only repository permissions and contains no importer, commit, push, merge or deployment step. Download the review artifacts and approve/import separately.

## Preservation and validation

`tools/bc-source-cache/financial-baseline.json` protects non-BC financial/filing records and capital summaries, all existing SK/AB/MB profile and financial HTML pages, maps, boundaries, contacts, population, logos, elections, history, enterprises and manual overrides. Text fingerprints normalize only CRLF/LF for reproducibility across Windows and Linux; PDF hashes always cover the original bytes. Nine pre-existing untracked financial pages are separately protected in the ignored local baseline; they are not required in a clean CI checkout and were not added to the PR. The Phase 2 identity roster remains unchanged.

All 18 JavaScript suites and isolated desktop/mobile browser checks pass. The complete Python suite retains five pre-existing evidence/legacy-baseline failures (Cold Lake, Cold Lake history, Day Star/Cote, Gordon and the older Manitoba elections fingerprint), recorded before Phase 3. These failures are not concealed by rewriting source evidence. See `docs/BC-PHASE3-REVIEW.md` for the final run and exact file manifest.
