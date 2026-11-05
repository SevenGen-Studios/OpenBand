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
