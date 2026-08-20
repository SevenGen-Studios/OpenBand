# Repository Layout

This repository is both the OpenBand source repository and the GitHub Pages deployment root. Some top-level files therefore remain at the repository root intentionally because the public site or GitHub Actions reference them directly.

## Keep at the root

These files are part of the deployed site or core automation and should not be moved casually:

- `index.html` — GitHub Pages entry point.
- `CNAME` — custom domain configuration.
- `.nojekyll` — GitHub Pages behavior.
- `robots.txt` and `sitemap.xml` — public search-engine files.
- `requirements.txt` — Python workflow dependencies.
- `data.json` — primary FNFTA/remuneration dataset consumed by the site.
- `capital-data.json` — Community Capital dataset.
- `map-data.json` — Browse map data.
- `contacts-data.json` — Band Office contact data.
- `member-counts.json` — registered population data.
- `first-nation-logos.json` — logo registry.
- `projects-data.json` — housing/infrastructure project data.
- `jobs-data.json`, `news-data.json`, `events-data.json`, `elections-data.json`, `community-enterprise.json` — public feature datasets.
- `audit-results.txt` — parser/coverage status displayed by the site and used by workflows.
- `scraper.py`, `run_scraper.py`, `run_scraper_v2.py` — current scraper/launcher chain used by automation.

Moving any of the above requires updating every frontend, test, tool, and workflow reference in the same change.

## Directories

- `.github/` — GitHub Actions workflows.
- `admin/` — internal static admin pages.
- `analytics-worker/` — optional Cloudflare analytics service.
- `assets/` — shared browser CSS, JavaScript, analytics code, images, and icons.
- `browse/` — Browse page.
- `first-nations/` — generated permanent First Nation profile routes.
- `news/` — News page.
- `public/` — public static assets generated or served by OpenBand.
- `tests/` — automated tests.
- `tools/` — data collection, parsing, validation, build, and maintenance utilities.
- `capital_overrides/` and `manual_overrides/` — reviewed manual corrections/overrides. These names are currently referenced by tooling, so rename only with a coordinated path migration.
- `reports/` — human-facing audit/debug reports that are not direct runtime dependencies.
- `docs/` — project documentation and historical notes.

## Cleanup rules

1. Do not place temporary notes or one-off audit text files in the repository root.
2. Put human-readable audit/debug output in `reports/` unless a workflow or the public site consumes that exact path.
3. Put temporary project notes in `docs/notes/`.
4. Put reusable maintenance scripts in `tools/` rather than the root.
5. Before moving a generated JSON file, search the repository for its filename and update all consumers/producers in the same commit.
6. Keep cleanup changes separate from product-feature changes so deployment regressions are easy to identify.
7. Never delete an apparently old scraper/parser until GitHub Actions, tests, and the README have been checked for references.
