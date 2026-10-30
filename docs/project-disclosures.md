# Audited project disclosure coverage

The project extractor scans publicly posted audited financial statements for Alberta and Saskatchewan. A successful Community Capital summary is not required: posted audits can still contain readable project notes when the financial-summary extraction failed. Documents classified as non-statements remain excluded.

```bash
python tools/project_disclosure_extractor.py --province ALL
python tools/project_disclosure_extractor.py --province ALL --all-years
python tools/build_audit_partnerships.py
python tools/build_site.py
python -m unittest tests.test_project_disclosure_extractor tests.test_projects_integrity tests.test_site_routes
```

The weekly **Update audited project disclosures** workflow defaults to both provinces and all available audit years. Manual runs can select AB or SK. Optional `--cache-dir /path/outside/repo` reuses downloaded PDFs for local research; omit it for fresh downloads. Do not commit the cache.

## What is extracted

- Existing explicitly labelled ISC capital-project and restricted-cash rows.
- Named physical infrastructure and project activities in deferred revenue, contribution, or funding notes, including continued notes.
- Project labels with source prefixes and individual AT/CT identifiers; repeated identifiers within an audit share one disclosure with the original evidence rows retained. Shared funding-program Q-codes do not establish project identity.

Generic programs, operating and maintenance costs, accounting totals, and ambiguous truncated labels are excluded. Names and their original PDF page references are retained. A disclosure is evidence that an audit names an activity; it does not establish construction status, approval, completion, or total cost.

New deferred-funding layouts retain their original row text but leave monetary fields empty. Column order and sign conventions vary, so a row's figures are not automatically labelled as expenditure or total project cost. Restricted cash uses the selected fiscal year's column, including reversed comparative columns.

## Coverage and unresolved sources

`project-disclosure-report.json` records attempted documents, failures, and per-province extraction counts. Records count annual disclosures, not distinct projects across all years. `needs_ocr` means the PDF has insufficient machine-readable text; it does not mean the Nation has no projects. Existing disclosures and research leads are preserved for failed downloads and PDFs requiring OCR.

Financial disclosures remain separate from independently corroborated project announcements. Accounting entities and business interests remain non-public research leads until corroborated. No paid extraction is enabled by this tool.
