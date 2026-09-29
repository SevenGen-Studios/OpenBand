# Optional local Docling fallback

Docling runs after standard PDF extraction and free OCR, before the explicitly
enabled OpenAI fallback. It is disabled by default. Remote Docling services are
disabled; initial model downloads still require network access.

Enable `use_docling` in the Community Capital backfill workflow. Start with a
small Alberta batch (5 filings, one fiscal year), `unresolved_only=true`, and
`use_openai=false`. Verified publishable summaries retain the existing skip
behavior. Remuneration also supports the adapter through the environment flag.

Local setup:

```sh
pip install -r requirements-docling.txt --extra-index-url https://download.pytorch.org/whl/cpu
OPENBAND_ENABLE_DOCLING=true python tools/capital_parser.py --help
```

`OPENBAND_DOCLING_TIMEOUT` defaults to 300 seconds per document and
`OPENBAND_DOCLING_MAX_PAGES` defaults to 100. Conversion runs in a separate
process so timeouts terminate inference. Results are validated using the
existing financial checks before publication. Capital extraction stages record
Docling attempts; remuneration results attach the table source page.

Benchmark against original PDFs before broad activation: use clean documents,
scans, multi-line headers, current/prior-year columns, and multi-page tables.
Measure validated recoveries, incorrect recoveries, time per file, and source
reference accuracy. Tests currently cover adapter failure handling and the
validation gate; they do not demonstrate real Docling extraction accuracy.

Read-only trial (results go to a temporary directory, never public data):

```sh
OPENBAND_ENABLE_DOCLING=true python -m tools.benchmark_docling --bands 467,464,442
```

The report compares baseline and Docling results and retains full extraction
output for inspecting page and table alignment. `verifiedAgainstPdf` starts
false: reconciliation alone is not proof that the correct source column was
selected. Check the original statements before manually accepting a recovery.
