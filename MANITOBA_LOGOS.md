# Manitoba logos and seasonal motion

The Manitoba logo registry now includes 30 visually reviewed Nation marks out of 63. The other 33 Nations retain OpenBand placeholders. See `manitoba-logo-report.md` and `manitoba-logo-report.json` for every community's sources and remaining gaps.

## Source review and maintenance

`manual_overrides/manitoba-logo-reviews.json` records explicit visual approvals, exact source and asset URLs, original asset and source-page hashes, identity evidence, and rejected/unresolved research sources for all 63 Nations. Ranking a candidate or finding it in a header does not approve it. Shared institutional pages often contain their own council logo or other communities' emblems: those were rejected. One listed domain redirected to unrelated gambling content and was rejected.

The new `tools/manitoba_logos.py` reuses the existing collector's image optimizer and accepts only explicit named, hash-bound Manitoba approvals. Run `python -m tools.manitoba_logos --apply` to fetch and reapply approved original assets, or supply `--asset-cache PATH` containing `BAND_ID.source` originals. A changed asset fails the hash check and requires renewed image review. `python -m tools.manitoba_logos` refreshes only the coverage report. Generic logo collection preserves Manitoba's reviewed records and detailed evidence rather than automatically approving replacements. Manitoba enrichment already respects existing logo records.

Original-source hashes and optimized local-asset hashes are retained separately. All 30 local assets are WebP, contained within 512 pixels and below the existing 512 KB limit. No mark was recolored, invented, substituted with a flag/portrait, or approved solely from its filename. Existing circular image presentation and the shared search, recent-card, directory and profile renderers are retained.

The scoped baseline in `manual_overrides/manitoba-logo-baseline.json` protects all existing Saskatchewan/Alberta logo registry records, detailed reports, and local asset bytes. This work changes only the five existing Manitoba logo fields in `data.json`; all nonbranding records and financial data were compared before and after and are unchanged. No financial ingestion code was changed.

## Seasonal motion and mobile controls

Winter is the default in `assets/home-motion.js`. Add `data-hero-season="spring"` to the root `<html>` element in `index.html` and rebuild to restore the original feather artwork without changing the motion engine. Winter uses the local 32-pixel-viewBox `assets/hero-snowflake.svg`, five small, low-opacity drifting particles on desktop and three on mobile. It retains viewport, page-visibility and reduced-motion gates, with transform/opacity animations and no additional library or data request.

At widths up to 760 px, the two pause controls are visually removed from ordinary touch use. They remain keyboard-accessible and reveal on keyboard focus. Desktop controls keep their original pause/resume behavior. Touch manipulation temporarily suspends card scrolling; pointer release/cancel and completion of native scroll momentum resume it automatically after a short quiet interval. Taps do not latch keyboard focus or permanently pause the strip. Keyboard focus, hidden pages, and reduced-motion preferences still stop animation. Provincial flag-carousel files are untouched.

## Verification

- Rebuilt all 180 profile routes and provincial pages from the shared template; motion asset versions update through regeneration.
- Python: 465 tests passed with Node available, no skips.
- JavaScript: all 11 suites passed, including the new motion interaction harness.
- Runtime checks cover winter/spring artwork, touch release/cancel, tap versus keyboard focus, document visibility, reduced-motion changes and desktop pause/resume.
- Browser checks at 390 × 844 and 1365 × 900 confirm three/five snowflakes, mobile focus-reveal controls, unchanged provincial colors, desktop controls, and no mobile horizontal page overflow. Search suggestions, directory results and the Berens River profile show the authentic local emblem. Touch event sequences are verified through the runtime harness; the browser viewport check does not emulate a physical touchscreen.
- Existing SK/AB logo metadata and asset hashes match the protected baseline. All nonbranding main data and `capital-data.json` match the before/after fingerprints. Whitespace checks pass.
