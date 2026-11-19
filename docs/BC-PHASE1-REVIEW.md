# British Columbia expansion — Phase 1 review

Branch: `codex/british-columbia-phase1`

Phase 1 adds BC to the existing OpenBand interface. No Phase 2 roster, profiles, locations, boundaries, leadership, or research were created. No Phase 3 financial collection, extraction, comparisons, or monitoring were implemented.

## Changes

- Added British Columbia to the homepage carousel, hero links, and shared desktop/mobile provincial navigation. The carousel uses the BC provincial flag in the same Wikimedia SVG format as the existing flags. Its four-item controls retain keyboard arrows, wraparound, animations, and swipe handling. Inactive flag links are excluded from keyboard focus and cannot intercept pointer input.
- Added the permanent `/british-columbia/` landing page using the existing template, with BC metadata, canonical URL, search, Browse links, coverage, recently updated section, supporting content, and expansion notice.
- Added `/browse/?province=BC` integration using the existing province-scoped records and Leaflet map. Existing BC bounds, responsive camera movement, zoom controls, soft pan limits, layers, and legend remain in use. No markers or reserve boundaries are fabricated.
- Added honest “Not yet indexed” coverage and financial states, the requested directory empty message, and a recently updated placeholder. Comparison controls remain absent when no validated fiscal-year data exists. The existing datasets drive the interface as records become available.
- Centralized multiword province slugs in the Python generator and fixed generated provincial directory links. Added BC to the sitemap. Existing Nation routes and legacy redirects remain intact.
- Fixed route detection so stale BC bootstrap context cannot override the homepage or Browse path during history navigation. Added wrapping to the existing hero province links for narrow screens; the visual design is otherwise retained.
- Regenerated shared navigation in existing provincial, Browse, News, and 180 profile pages. Preserved existing profile prerender contents, including seven time-dependent jobs snapshots that the build would otherwise refresh.

## Files

[BC-PHASE1-FILES.txt](BC-PHASE1-FILES.txt) lists every modified/new file for this change, including all generated pages.

Main implementation files: `index.html`, `assets/provinces.js`, `assets/province-ui.js`, `assets/province-carousel.js`, `assets/province-carousel.css`, `assets/openband.js`, `assets/openband.css`, `tools/build_site.py`, and `tools/seo_records.py`.

New page: `british-columbia/index.html`. Tests: `tests/test_provinces.js`, `tests/test_manitoba.js`, `tests/test_site_routes.py`, and new `tests/test_british_columbia_routes.py`.

## Validation

- JavaScript: all 16 existing suites passed, including BC route/filter/empty-state tests, four-province carousel controls, existing SK/AB/MB coverage, and map viewport tests at desktop and phone widths.
- Python full suite: 557 tests ran; 552 passed and 5 failed. All route, SEO, BC, Manitoba landing, and map assertions passed after updating stale carousel/map expectations to the existing runtime values.
- Site generation completed successfully for the 180 existing profiles, provincial pages, Browse, News, legacy redirects, robots, and sitemap. BC canonical paths and generated internal links are covered by route/SEO checks.
- JavaScript syntax and Git whitespace checks passed.
- Git comparison confirms no tracked community datasets, financial data, source records, boundaries, financial-year pages, or legacy redirects changed. Existing untracked Nation/financial files and `tmp/` content were excluded from the change.

The five unrelated Python failures are:

1. `test_data_accuracy_cold_lake.ColdLakeSourceTests.test_recovery_manifest`
2. `test_data_accuracy_cold_lake_history.ColdLakeHistoricalTests.test_recovery_checkpoint`
3. `test_data_accuracy_daystar_cote.DayStarCoteSourceTests.test_recovery_checkpoint_hashes_and_queue`
4. `test_data_accuracy_gordon.FurtherSourceReviewTests.test_recovery_manifest_and_remaining_queue`
5. `test_manitoba_pipeline.ManitobaPipelineTests.test_protected_financial_and_profile_records_unchanged`

The first four concern existing evidence hash/byte-count mismatches in unchanged files. The fifth concerns the existing `elections-data.json` preservation baseline mismatch; the current elections file was not modified. These fixtures were left intact.

## Remaining limitations

- The browser preview could not connect to the local server, including a second loopback-only server attempt. Real-browser screenshots, live console inspection, and visual desktop/mobile QA remain unverified. Carousel, empty-state, history routing, and responsive map behaviours were exercised through the repository runtime tests.
- BC intentionally contains no indexed communities, financial records, markers, or reserve parcels. “No indexed records” describes OpenBand coverage, not whether Nations have published statements.
- Flag images, map tiles, fonts, and Leaflet retain the existing external-network dependencies.
- Changes are prepared locally for review; no deployment was performed.

## Requirements before Phase 2

- Establish a source-linked, verified BC First Nations roster and reconcile ISC identifiers, aliases, and cross-border cases.
- Define identity/source verification and review rules before merging records into existing datasets.
- Verify community coordinates, reserve associations, governance, treaty/council information, and any logos against authoritative sources.
- Add ingestion/preservation checks so BC additions cannot overwrite SK, AB, or MB records. Financial document collection remains Phase 3.
