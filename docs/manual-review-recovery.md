# Retrying filings marked for review

`tools/recover_review_filings.py` selects posted source documents across every
OpenBand province. Its queue includes both the filing-level review flags and
the separate Community Capital review status. It does not retry unposted
documents or replace an already usable financial summary.

The native and cached OCR passes use the same parsing and validation gates as
normal ingestion. A remuneration recovery also needs a reconciled printed
footer or a complete visual transcription tied to the exact original PDF
hash. An audited statement needs the reported revenue, expense and annual
result, with the correct fiscal-year column and reconciled components. A
changed source hash stays in review until the new version is checked.

Example from an isolated checkout, using the repository Python dependencies:

```powershell
python tools/recover_review_filings.py --mode native --workers 4 --output .openband-ocr/native-review
python tools/recover_review_filings.py --mode cached --workers 4 --output .openband-ocr/cached-review
```

For scanned documents on Windows, install the pinned `winocr` dependency and
PDFium in the local runtime. The coordinate OCR pass renders pages in memory,
retains their original page numbers and checks that financial amounts align
with the printed year columns. Pages with ambiguous numeric separators are
withheld. This avoids substituting a guessed digit or amount.

```powershell
$env:OPENBAND_OCR_ENGINE = 'windows-coordinate'
python tools/recover_review_filings.py --mode ocr --scanned-only `
  --recheck-from .openband-ocr/native-review --workers 3 `
  --output .openband-ocr/scanned-review
```

`--cache-source` can point to another local OpenBand checkout with original
PDF and OCR caches. Workers use bounded timeouts and save per-document results;
the trial reports identify unresolved causes. Run with `--recheck-only` and
`--recheck-from` to validate stored trials again without downloading or running
OCR. Add `--merge` to apply accepted results. The tool uses free local
extraction and does not enable paid API calls.

The [release report](../manual-review-recovery-report.json) lists accepted
documents, source hashes and remaining review counts. It covers this recovery
batch. The preservation fingerprints were refreshed after verifying that all
previously usable financial summaries and all other filings were unchanged.

## Discovered-document batch verification

The November 7 batch includes the 33 daily-scan recoveries and both Canoe Lake
2023–2024 documents. All 35 PDFs were downloaded, SHA-256 checked, and read with
native extraction and independent on-device Apple Vision OCR. Scanned Lac La
Ronge pages also received RapidOCR extraction. Engine agreement does not
override failed fiscal-year, completeness, column, or reconciliation checks.

`filing-extraction-report.json` retains every outcome, previous record, proposed
extraction, source URL, digest, raw OCR page text, and unresolved reason. The
administration operations page links the report and its processed, verified,
and review counts. Proposals for unsuccessful extractions are kept in this
report rather than substituted into published financial values.

`tools/parse_discovered_filings.py` rechecks downloaded recovery checkpoints:

```sh
python tools/parse_discovered_filings.py \
  --work-dir .openband-ocr/parse-discovered \
  --report filing-extraction-report.json --apply
```

Omit `--apply` to produce a report without updating financial data. Use
`--data` and `--capital` to verify against isolated copies before publication.
The work directory's `selection.json` contains `{band, filing}` entries from
the database. Each `<band>-<year>-audit` or `-pay` key has the original `.pdf`,
the existing recovery worker's `.native.json` checkpoint, and a `.vision.json`
checkpoint containing `sha256` and `pages` with page numbers, raw text, and
word boxes in PDF points. Missing or mismatched evidence fails closed.
The original PDFs and engine caches remain under ignored `.openband-ocr/`.

Native and optical amounts must occupy the same source page, row, and actual
fiscal-year column. Negative signs and decimal points must agree. Complete
remuneration schedules use the existing hash-bound source-review mechanism,
with every row inspected and available printed column totals checked. Salary,
contracts, travel, reimbursements, and other payments keep their source labels
and components. Signature lines are excluded. No printed total is invented
when the source does not contain one.

Apple Vision is optional. On macOS, `requirements-macos-ocr.txt` pins PyObjC's
Vision bindings; `tools/vision_ocr.py` exposes word boxes without uploading the
document. Set `OPENBAND_VISION_PYOBJC=1` to select the Python bindings. The
existing Swift executable remains the default.
The bindings are maintained in [PyObjC](https://github.com/ronaldoussoren/pyobjc)
under its MIT license and call Apple's system Vision framework. No macOS
dependency is added to Linux ingestion. OCR model/resource access requires a
normal local host process; an unavailable engine leaves the document in review.
