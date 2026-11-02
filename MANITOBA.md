# Manitoba: Phase 1

Manitoba uses the shared province landing template, search, directory, map, finance comparisons and profile generation. Province code: `MB`; route: `/manitoba/`; directory: `/browse/?province=MB`.

The homepage carousel uses the authentic Manitoba flag from Wikimedia Commons, following the existing SK/AB external SVG asset approach. The red theme uses the same CSS variables as Alberta. The province total is deliberately unset until its scope and source are verified. Indexed counts describe OpenBand records only; absent financial summaries remain unavailable, never zero.

No Manitoba identities, locations or financial records have been fabricated or copied. Add verified communities to `data.json` using the existing band identity, province, aliases, treaty and filing schema, and associate auxiliary datasets by the existing band ID. Map locations belong in `map-data.json`; financial summaries in `capital-data.json`; related source-backed community content belongs in the existing shared datasets. Run `python tools/build_site.py` after ingestion to generate profiles and metadata.

Phase 2: verify the Manitoba ISC roster and band numbers, aliases and treaty affiliations; verify coordinates and reserve associations; establish sourced provincial coverage scope; ingest and validate original financial/remuneration records; verify capital, projects, businesses, jobs and news. Do not infer financial values or the absence of community activity from missing records.

Validation: Python unittest discovery, existing JavaScript suites plus `tests/test_manitoba.js`, and regeneration. A desktop/mobile visual browser review remains recommended before merge; this environment did not supply Playwright.
