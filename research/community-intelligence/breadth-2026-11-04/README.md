# Community breadth expansion — November 4, 2026

Local working copy based on GitHub main `59a96ea8`. The parked map work remains in the original OpenBand checkout. Nothing in this batch has been committed or deployed.

Coverage is evaluated on the same November 4 cutoff for both the frozen baseline and current inventory:

| Measure | Before | After |
|---|---:|---:|
| Communities with all four categories | 3 | 9 |
| Communities with upcoming events | 14 | 18 |
| Communities with active jobs | 39 | 43 |
| Manitoba communities with verified projects | 26 | 30 |
| Confirmed active job listings | 82 | 93 |
| News records | 591 | 594 |
| Event records | 234 | 241 |
| Project records | 188 | 192 |
| Job records (including pending/closed) | 820 | 831 |

The six newly complete profiles are Athabasca Chipewyan, Blood/Kainai, Fisher River, Peguis, Lac La Ronge and Whitecap Dakota. An announced future opening remains an announced opening, not proof that the facility is operating. Coverage is still incomplete for 171 communities.

## Reviewed additions

- Seven event records: Fisher River audit/program meetings on November 24 and 25 (separate published occurrences), November 16–20 security training; Peguis meetings on November 24 and 25 at their respective venues; Lac La Ronge’s November 19 sobriety recognition gala; and Whitecap’s announced December 4 public spa opening.
- Eleven job listings: Peguis CFS respite worker; ACFN special education/ECE posting covering two positions; two Blood Tribe Administration roles; five Lac La Ronge roles with explicit “until suitable candidate is found” deadlines; and Pasqua’s Red Eagle Lodge executive director and Jordan’s Principle coordinator. One posting advertising multiple positions remains one listing.
- Four projects: Whitecap’s Dakota Dunes Thermal Spa, Cross Lake Women’s Shelter, Fisher River’s Ka Pa Pak transitional housing shelter, and the provincial Project 6 road proposal benefiting Manto Sipi, Bunibonibee and God’s Lake. The completed road environmental assessment is not described as completed road construction. Shelter program funding is not presented as total project cost.
- Three source-publication-dated notices. The existing Fisher River meeting news and Pasqua educational assistants posting retain their original IDs rather than acquiring duplicates.

## Evidence and ongoing collection

`source-checks.json` records 67 bounded primary-source checks: 58 successful, five unavailable robots checks, two TLS failures, one missing page and one timeout. Restrictions were not bypassed. The gzip evidence files are hash-bound to reviewed assertions in `reviewed-enrichment.json` and the central enrichment manifest. `poster-transcripts.json` contains OCR text for five visually reviewed posters, bound to their image hashes; the original images remain the evidence of record.

New official boards and project sources are registered in `community-research-sources.json` and the existing collectors. Registration alone never counts as content. Dynamic BambooHR content, missing deadlines, stale Ermineskin closing dates, and the inconsistent Pasqua custodian deadline were not promoted to new active records. The latter was already correctly closed in the inventory. The Peguis career fair poster is October 14 and was not counted as upcoming. The George Gordon book club has an unbounded recurrence; no future occurrences were invented. CDN content whose robots check failed was held.

Pipeline fixes preserve separate dated occurrences of the same event, recognize explicit employer deadline variants, permit dated audit community meetings while still rejecting audit reports, and use the already pinned RapidOCR dependency for image research when Tesseract is absent. These changes retain manual review and source/identity/date gates.

All 19 job overrides present on current main remain byte-for-byte equivalent as records. Roster, financial inputs, elections, history data and generated history content are unchanged. The 180-Nation roster remains SK 69 / AB 48 / MB 63.

## Overview layout

Elections and Brief History share a row at desktop widths of 1100px and above. Cards stack below that width; existing history expansion, citations, election content, and event/news presentation remain available. Both prerendered and hydrated profiles use the grouping. Browser checks at 1280px and 390px confirmed desktop alignment, mobile stacking and no horizontal overflow. Cache versions were updated for the edited assets.

## Validation

572 Python tests passed (three skipped), plus all 15 JavaScript suites. The final focused data/history/routes rerun passed after preserving the existing Pasqua educational-assistant ID. `git diff --check` passed. The evidence validator checks the manifest at its reviewed date, while fixed-date negative fixtures continue testing rejection of future or incorrect dates.

`summary.json`, `record-changes.json` and `coverage-report.*` contain the exact comparisons. `research-priorities.csv` orders remaining gaps with communities needing one category first. No Follow, account or notification feature was introduced.
