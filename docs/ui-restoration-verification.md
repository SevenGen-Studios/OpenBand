# UI restoration verification — October 11, 2026

The restoration targets SEO commit `0d438a83` and compares the existing application UI against its immediate predecessor, `7a19cd34cca9668784d49583c27fb91c837dfbe6`. It starts from current main (`dd13c18e`), preserving the financial-record publishing work and all subsequent generated pages.

## Changes

- Removed `records.css` from the existing application shell. Its global body, heading, paragraph, section, and table rules were overriding the original application styles and introducing spacing and typography changes. Dedicated record pages continue to use it.
- Restored the original primary navigation, Browse label, hero copy, and footer structure. Added only the small footer row: First Nations · Financial Records · Sources & Methodology.
- Removed the injected provincial directories and profile archive cards from the application layout, including their view-switching hooks. The First Nations directory remains at `/first-nations/`.
- Moved each Nation's fiscal-year archive to `/first-nations/<slug>/financials/`, reached through its footer link. Annual records retain their existing URLs, content, schemas, and original PDF links. The new archive routes are included in the sitemap.
- Preserved titles, descriptions, canonical URLs, social metadata, JSON-LD, robots.txt, profile prerendering, and existing sitemap entries. Updated application asset versions so browsers load the restored UI.
- No changes to financial datasets, remuneration, Community Capital calculations, projects, jobs, news, or Bandy source/research files.

## Verification

Headless Microsoft Edge / Playwright compared the current UI with pages and application assets served directly from the pre-SEO Git revision, using the same local data. At widths 320, 390, 768, and 1440 pixels, the visible navigation, hero, statistics, main content, coverage, recent updates, profile, directory, and news container positions and sizes matched the original on all six sampled routes:

`/`, `/saskatchewan/`, `/alberta/`, `/browse/?province=SK`, `/news/`, and `/first-nations/waterhen-lake-first-nation/`.

The original footer starts at the same position. The compact links add 18 pixels of footer height at widths 390 and above, and 37 pixels at 320 where they wrap. No horizontal overflow, visible element after the footer, or extra trailing document space was found.

Mobile interaction checks passed for the hamburger menu, provincial Browse link, autocomplete search, all six profile tabs, contextual financial archive link, and an annual record page. No browser JavaScript errors were observed.

Automated checks passed:

- 23 existing site-route tests.
- 9 SEO tests, including every public internal link target, unique canonicals and titles, valid JSON-LD, sitemap coverage, archive discovery, source eligibility, and safe regeneration.
- 8 existing home-motion tests and 4 existing Community Capital UI tests.
- All four existing Node regression suites: provinces, missing filing years, directory map, and data loading.
- Git whitespace checks and a diff confirming protected data and Bandy files are unchanged.

## Mobile artifact limitation

The separate reported black-and-white rectangle could not be reproduced in either the local or live website in mobile Edge emulation. Live pages contained no iframe or visible element after the footer. The proven stylesheet collision and injected panels were corrected at their source; no CSS mask was added. Confirmation on the affected phone/browser is still needed. Device, browser, and exact route were requested to reproduce any remaining artifact. These checks do not establish physical iPhone/Safari behavior.

This is a local restoration branch; production has not been deployed by this task.
