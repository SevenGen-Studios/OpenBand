# Community breadth expansion — November 6, 2026

Local batch based on upstream main `828781de4da77f39be04b43e10bd9466e3a945a4`, preserving the latest creator-support work and the existing overview/history layout. No Follow/accounts/notifications feature, commit, or deployment is included.

Both baseline and current inventories are evaluated on November 6, 2026. The previous November 4 release had nine complete communities at that earlier cutoff; Peguis’s respite-worker deadline was November 5, leaving eight at the start of this batch.

| Measure | Before | After |
|---|---:|---:|
| Communities with all four categories | 8 | 11 |
| Confirmed active job listings | 86 | 92 |
| Communities with upcoming/ongoing events | 18 | 20 |
| Communities with active jobs | 40 | 42 |
| Manitoba communities with verified projects | 30 | 31 |
| News records | 639 | 645 |
| Event records | 306 | 328 |
| Project records | 192 | 202 |

The newly complete communities are **Saddle Lake Cree Nation, Ahtahkakoop Cree Nation, and Onion Lake Cree Nation**. Current projects are counted as verified, source-dated project records—not necessarily active construction. There are still 169 communities without all four categories at the same time.

## Reviewed content

- **Six news records:** five newly reviewed notices from Piapot, Saddle Lake and Fort McKay, plus restoration of the previously reviewed Brokenhead AGM notice from the central enrichment manifest. Publication dates come from original metadata, not event dates or crawl time.
- **23 new event records:** Saddle Lake’s November 23 membership meeting and December 10 Seniors/AISH gathering; the Bears’ Lair Frog Lake youth camp and community celebration November 20–23 (venue still TBD); and 20 additional explicitly published Onion Lake calendar occurrences. Dates for separate hockey games, craft sessions, round dances and basketball camp days are kept separate. Existing occurrence identity is retained when titles are cleaned.
- **Ten Manitoba project records:** Bunibonibee wastewater remediation and 48-unit subdivision; Red Sucker Lake aerated lagoon; Garden Hill road upgrades; Wasagamack nursing station; York Factory child/family prevention building and drainage improvements; Shamattawa re-unification centre/accommodation and women’s transitional housing; and Tataskweyak landfill expansion. Historical assessment dates remain historical. Environmental determinations are not described as completed construction, and the Wasagamack page’s template placeholders are disclosed.
- **Six active job postings:** Ahtahkakoop Cultural Worker, Public Works Supervisor, and Exceptional Needs Worker; Onion Lake Director of Technical Services; Piapot Family Shelter Executive Director and Housing/Community Infrastructure Manager. Original employer deadlines, terms, pay where explicitly published, and application instructions are retained.
- **19 additional employer leads held for review:** eight Fort McKay and eleven Mikisew Group vacancies from the employers’ public BambooHR feeds. No deadline or open-until-filled statement was verified on their static detail pages, so these remain pending and contribute nothing to active-job or all-four counts. Generic talent-pool and expression-of-interest entries are excluded.

## Data quality and repeat collection

The Onion Lake adapter pairs each embedded JSON entry with its own rendered event card, checks identity, date order and same-employer URLs, decodes title entities, preserves per-occurrence dates and IDs, and reads time from the published structured field. It does not borrow dates, time or location from neighbouring cards. It holds a source entry when the calendar dates conflict with the explicit program-start narrative.

One previously indexed Community Safety Officer Program event was withdrawn to the review queue because the publisher’s calendar range conflicts with its program description. Its original record is preserved in `held-event-conflicts.json` and `events-review-queue.json`. The exact existing-record actions are in `reviewed-event-updates.json`.

The BambooHR adapter accepts JSON only for configured, reviewed employer feeds, restricts vacancy URLs to the same employer host, filters general applications/talent pools, and holds all date-unverified rows. The ordinary HTML fetch path retains its content-type restriction. Newly registered sources are monitored by the existing workflows; registration alone never counts as coverage. New regression tests are included in scheduled news, events, jobs and coverage checks.

There were **66 bounded research checks: 63 successful, two TLS errors and one missing page**. No unavailable source restriction was bypassed. Original gzip bodies and document/OCR transcripts are in this folder; reviewed assertions are hash-bound to those bodies through `reviewed-enrichment.json` and the central manifest. The three Ahtahkakoop job posters were also visually checked against the original images.

Expired Peguis childcare and service-navigation deadlines, Ermineskin’s expired job list, old Roseau River and Muskoday meeting notices, and old Birch Narrows camp dates were not counted as new active/upcoming records. Missing categories still do not prove that no real community activity exists.

All 30 starting manual job overrides remain unchanged as records. Two automatic duplicate job rows were consolidated by the existing collector. Financial/profile inputs, roster, elections, history data, generated history asset, map runtime, styles and map data are byte-identical to starting main. The 180-community roster remains SK 69 / AB 48 / MB 63. A stale protected-data test fingerprint was refreshed to the already-published FNFTA sanitizer’s exact upstream bytes; `upstream-preservation-baseline-update.json` records that change. No financial values were edited.

## Review artifacts

`summary.json`, `coverage-report.*` and `record-changes.json` provide exact same-cutoff comparisons. `research-priorities.csv` prioritizes communities missing one category. The gap is primarily broader event coverage and verified employer deadlines, rather than more repeated records for communities already covered.

Local preview: http://127.0.0.1:8767/first-nations/ahtahkakoop-cree-nation/?tab=jobs

Validation: 595 Python tests passed (three skipped), 16 JavaScript suites passed, and the final 77-test focused pipeline/evidence suite passed. `git diff --check` passed. Browser verification confirmed the three Ahtahkakoop job cards, their deadlines, and no remaining load-error alert.
