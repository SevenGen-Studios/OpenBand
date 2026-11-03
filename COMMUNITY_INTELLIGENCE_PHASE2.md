# OpenBand Phase 2 — Community Intelligence & Coverage Expansion

Phase 2 release prepared on `codex/community-intelligence-phase-2`. Measurements below use the frozen Phase 1 commit `65086324b82633793ef073e8f390f2ba7f4e51d2` and evaluate both inventories as of **November 3, 2026**. No Follow, account or notification feature was added.

## Original gaps and measured result

All 180 communities were present in the Phase 1 registries, but Manitoba had no verified project records or confirmed active jobs. Recent news and upcoming events were concentrated in a small number of communities. Sources could exist without readable, dated information, and an empty result could also reflect TLS, robots, JavaScript or authorization failures.

This pass adds **42 news records, 17 event records and 24 verified project records**. Confirmed active job listings increased from **42 to 73** at the same measurement date: **31 net additional active listings**, rather than treating every scraped candidate as a vacancy.

As of 2026-11-03. Counts are Nations with verified records; activity is not inferred from registered sources.

| Province | Tracked | News ≤90 days | Upcoming events | Projects/partnerships | Active jobs | All four | No verified information |
|---|---:|---:|---:|---:|---:|---:|---:|
| SK | 69 | 13 → 21 | 2 → 4 | 67 → 69 | 23 → 24 | 0 → 0 | 1 → 0 |
| AB | 48 | 15 → 17 | 5 → 5 | 47 → 47 | 4 → 5 | 0 → 0 | 1 → 1 |
| MB | 63 | 6 → 11 | 2 → 4 | 0 → 20 | 0 → 10 | 0 → 1 | 48 → 27 |

- An empty inventory is not proof that no public information exists.
- Regional employment source coverage does not imply a job in every member Nation.
- Projects describe source-dated evidence, not necessarily current construction status. Audited disclosures alone are excluded from verified project counts.
- Date-unavailable jobs are excluded from confirmed active coverage.

Complete community-level inventory, source checks, and record changes: `community-coverage-report.json` and `.csv`.

## Record changes

| Category | Added records | Materially updated | Check metadata only | Removed/merged |
|---|---:|---:|---:|---:|
| news | 42 | 17 | 512 | 0 |
| events | 17 | 4 | 180 | 0 |
| projects | 24 | 0 | 0 | 0 |
| jobs | 62 | 1 | 0 | 10 |

Added job candidates include held and closed postings; only confirmed active jobs contribute to coverage above. Shared projects are counted once as records and separately as community associations.

## What was integrated

- **News:** official community notices, Hatchet Lake treaty land entitlement, the seven explicitly named participants in the Saskatoon Tribal Council child and family services agreement, Peepeekisis economic development, Yellow Quill housing, and named Manitoba policing/flood-protection updates. The NCN housing notice now appears on its profile with its own publication date.
- **Events:** Red Pheasant’s explicit calendar occurrences, Ahtahkakoop’s published leadership-program sessions, the Sagkeeng Lawmakers Assembly and Brokenhead AGM, plus valid results from the bounded live event scans. Of the 17 added event records, 11 are upcoming/ongoing at the measurement date and six are recently held. Program applications that have closed are not advertised as open enrollment.
- **Projects:** five Manitoba water projects; Sayisi Dene renewable microgrid; Roseau River and Tataskweyak pathways; transit feasibility studies; community-specific broadband projects; Fisher River Solar Farm; NCN/Wuskwatim partnership; Peguis/Fisher River flood mitigation; Saskatchewan lagoon proposals, Peepeekisis Funeral Home and Yellow Quill homes; and Bearspaw housing/broadband.
- **Jobs:** verified postings from NCN, MKO, Fisher River, Pasqua, Dene Tha’, Saddle Lake, and precisely scoped Manitoba First Nations School System cards. Sixty-two new listing IDs include 34 currently active records, 25 held candidates, one closed record and two separately labelled date-unavailable listings. Ten older automatic records were merged/replaced during deduplication or document-title correction. Those replacements are why 34 new active IDs are not described as 34 net new opportunities. All previously manual job identity, employer, salary, qualification and application fields were preserved.

## Source research and repeatable monitoring

The reusable catalogue contains **34 reviewed source entries** spanning all four categories. The research cache recorded **69 unique URLs**: {'checked': 66, 'access_restricted': 2, 'robots_unavailable': 1}. A successful fetch does not imply successful extraction. The news, events and jobs collectors also performed their bounded source/detail scans; these request counts are not added to the unique-URL cache count.

Important primary sources include:

- [Manitoba water infrastructure backgrounder](https://www.canada.ca/en/indigenous-services-canada/news/2026/06/five-manitoba-first-nations-reach-major-milestones-in-improving-access-to-safe-drinking-water.html)
- [Manitoba infrastructure and broadband backgrounder](https://www.canada.ca/en/housing-infrastructure-communities/news/2026/05/backgrounder-vital-infrastructure-and-connectivity-supported-across-rural-and-northern-manitoba.html)
- [Saskatoon Tribal Council agreement and named participants](https://www.canada.ca/en/indigenous-services-canada/news/2026/10/minister-gull-masty-joins-the-saskatoon-tribal-council-to-sign-regional-agreement-to-reform-child-and-family-services.html)
- [Official Manitoba school employment board](https://mfnerc.org/about-us/work-here/)
- [NCN employment board](https://www.ncncree.com/business-and-economy/job-opportunities/)

The complete catalogue, source URLs, categories and community IDs are in `community-research-sources.json`; source snapshots/checks are under `research/community-intelligence/phase2-2026-11-02/`. That directory identifies the research campaign; individual check timestamps record the actual retrieval time. Archived evidence used by the 70 reviewed entries is hash-bound. Future source checks use content-addressed snapshots and keep older evidence.

Existing daily news/events/jobs workflows now register reviewed sources before collecting. The jobs workflow includes Manitoba. A weekly coverage workflow rechecks reviewed sources and updates diagnostics and the four-category inventory. Changed project pages are research signals, not permission to overwrite curated ownership, cost or status. Audited project disclosure collection can select MB and defaults to the latest year across all provinces; historical all-year runs remain explicit. These workflow changes take effect when this branch is published.

## Accuracy and implementation changes

- Registered announcement permalinks are themselves collected when article metadata supplies a real publication date; publication dates remain separate from event dates.
- The Eventer adapter reads visible occurrence dates, end dates, venue and times. URL dates must agree with visible dates. Explicit occurrences are handled individually, all-day placeholders are not shown as midnight start times, and cancelled/postponed occurrences cannot remain upcoming.
- Jobs use the existing robots-aware, TLS-validating fetcher. Facebook HTML collection is withheld and historical login-page fetches no longer count as successful job checks.
- Shared school cards keep the job title, location, explicit deadline and application document together. Community association requires a single explicit match; the employer’s membership does not fan jobs out to all Nations. Where robots rules block a PDF, a current readable official card with an explicit open-until-filled deadline can establish availability; the blocked document remains flagged and no qualifications are inferred from it.
- Related links on a job permalink cannot inherit that vacancy’s community. Misattributed related-link candidates are held for review. A fresh, verified closure at the same posting can withdraw a manually reviewed job while preserving its other fields; an offline refresh cannot silently reopen it.
- Project ownership options, provider roles, equity partnerships, service beneficiaries, funded plans and completed works remain distinct. Funding commitments are not project valuations or proof of spending. Completed environmental assessments are not completed construction. Source-dated status is retained, and missing values stay missing.
- The independent news/jobs/projects writers are excluded from the Manitoba financial/profile invariant guard; this prevents legitimate community-feed updates from blocking financial ingestion. Financial/profile fingerprints remain enforced, and all original project records, audit disclosures and partnerships are checked for preservation.

The implementation files are `tools/community_coverage.py`, `tools/research_public_sources.py`, `tools/register_community_sources.py`, `tools/apply_community_enrichment.py`, the existing three collectors, the project-disclosure CLI selector, the preservation guard and their tests/workflows. Data is integrated in the existing JSON datasets and rebuilt profile/regional routes. No frontend redesign, financial-value change, logo, seasonal-motion, enterprise or analytics change was made.

## Reproduction and review

```sh
python -m tools.register_community_sources
python -m tools.apply_community_enrichment
python tools/jobs_collector.py --offline
python -m tools.community_coverage --today 2026-11-03 --baseline research/community-intelligence/phase2-2026-11-02/before
python tools/build_site.py
python -m unittest discover -s tests
```

The reviewed backfill is idempotent: matching existing IDs are preserved, not overwritten with older reviewed snapshots. Offline collection never claims a fresh network check. Live campaign logs record a 12-community news scan, a six-community follow-up, a Manitoba-wide event scan, a four-community event follow-up, and targeted job-source scans. Each scan was bounded; this is a substantive enrichment pass, not an exhaustive live inspection of every page for every Nation.

## Remaining obstacles, in priority order

1. **Reach communities with no verified records:** 27 Manitoba Nations and one Alberta Nation still have no verified information in these four inventories. This does not establish an absence of public activity. The full per-community missing-category/source-state queue is in `community-coverage-report.json` and the exported research-priorities CSV.
2. **Broaden upcoming events:** Saskatchewan increased from two to four Nations and Manitoba from two to four; Alberta remains five. Many public posters are images or omit an explicit year. No guessed year was published. Local OCR CLI tools were unavailable, so image/scanned-PDF gaps remain; supported born-digital PDF extraction was exercised, and scheduled Linux workflows retain their free OCR tools.
3. **Resolve authorization and source failures:** no authorized Facebook collection was performed. Bigstone Health pages were access-restricted for the direct collector, one syndicated press-release host had unavailable robots rules, and existing TLS, DNS, JavaScript and unavailable-source gaps remain visible. Restrictions were not bypassed.
4. **Confirm project milestones and ownership with newer evidence:** many records are valid historical or source-dated plans, not verified current construction. Wuskwatim’s up-to-33% option was not converted into a completed 33% ownership claim; planned commissioning dates were not converted into completion dates.
5. **Continue job verification:** expiry and 21-day check freshness still apply. Held candidates and date-unavailable listings are excluded from confirmed-active coverage. Regional job source coverage is distinct from a vacancy located in every member Nation.
6. **Improve consistency before Follow:** only NCN now has all four categories populated under these strict metrics. Broader dependable content and presentation are still needed before personalized subscriptions would be worthwhile.

Communities currently with no verified information:

- AB: Tthebatthie Denesųłiné Nation (477) — news: checked, events: checked, jobs: checked, projects: not_registered
- MB: Barren Lands (308) — news: checked, events: checked, jobs: checked, projects: not_registered
- MB: Buffalo Point First Nation (265) — news: checked, events: checked, jobs: checked, projects: not_registered
- MB: Bunibonibee Cree Nation (301) — news: checked, events: checked, jobs: checked, projects: not_registered
- MB: Canupawakpa Dakota First Nation (289) — news: source_failure_or_restriction, events: source_failure_or_restriction, jobs: checked, projects: not_registered
- MB: Chemawawin Cree Nation (309) — news: checked, events: checked, jobs: checked, projects: not_registered
- MB: Cross Lake Band of Indians (276) — news: not_registered, events: not_registered, jobs: not_registered, projects: not_registered
- MB: Dakota Plains (288) — news: not_registered, events: not_registered, jobs: not_registered, projects: not_registered
- MB: Dakota Tipi (295) — news: checked, events: checked, jobs: not_registered, projects: not_registered
- MB: God's Lake First Nation (296) — news: checked, events: checked, jobs: checked, projects: not_registered
- MB: Lake Manitoba (271) — news: checked, events: checked, jobs: not_registered, projects: not_registered
- MB: Little Grand Rapids (270) — news: checked, events: checked, jobs: source_failure_or_restriction, projects: not_registered
- MB: Manto Sipi Cree Nation (302) — news: checked, events: checked, jobs: checked, projects: not_registered
- MB: Marcel Colomb First Nation (328) — news: not_registered, events: not_registered, jobs: not_registered, projects: not_registered
- MB: Mathias Colomb (311) — news: checked, events: checked, jobs: not_registered, projects: not_registered
- MB: O-Chi-Chak-Ko-Sipi First Nation (279) — news: not_registered, events: not_registered, jobs: not_registered, projects: not_registered
- MB: O-Pipon-Na-Piwin Cree Nation (318) — news: not_registered, events: not_registered, jobs: not_registered, projects: not_registered
- MB: Opaskwayak Cree Nation (315) — news: source_failure_or_restriction, events: source_failure_or_restriction, jobs: source_failure_or_restriction, projects: not_registered
- MB: Pinaymootang First Nation (272) — news: checked, events: checked, jobs: not_registered, projects: not_registered
- MB: Poplar River First Nation (277) — news: checked, events: checked, jobs: checked, projects: not_registered
- MB: Rolling River (291) — news: not_registered, events: not_registered, jobs: not_registered, projects: not_registered
- MB: Sandy Bay (283) — news: checked, events: checked, jobs: not_registered, projects: not_registered
- MB: Sapotaweyak Cree Nation (314) — news: not_registered, events: not_registered, jobs: not_registered, projects: not_registered
- MB: Shamattawa First Nation (307) — news: checked, events: checked, jobs: checked, projects: not_registered
- MB: Skownan First Nation (281) — news: not_registered, events: not_registered, jobs: not_registered, projects: not_registered
- MB: War Lake First Nation (323) — news: checked, events: checked, jobs: checked, projects: not_registered
- MB: Waywayseecappo First Nation Treaty Four - 1874 (285) — news: checked, events: checked, jobs: not_registered, projects: not_registered
- MB: Wuskwi Sipihk First Nation (324) — news: not_registered, events: not_registered, jobs: not_registered, projects: not_registered

## Validation

- **538 Python tests passed**, including 26 new Phase 2 cases.
- **13 JavaScript suites passed.**
- All 180 profile pages and regional routes rebuilt successfully.
- `git diff --check` passed. The financial/profile preservation guard passed.
- Original financial, capital, membership, contact, map, elections, enterprise, logo and seasonal-motion files are unchanged from the input branch. All original project, partnership and audited disclosure records were preserved. Original manual job identity, employer, salary, qualifications and application fields were preserved.
- Browser QA verified NCN’s project ownership caveat, three confirmed active jobs, three upcoming workshops and the current housing notice on the expected profile tabs. A wrongly attributed related-job link was held and confirmed absent from the public tab after the correction.
- The reports and screenshots were captured during local review; deployment is tracked separately.

## Deployment integration

The release preserves upstream financial sanitation, Manitoba logos, ISC number display, and map improvements. At the owner's request, six recent Saskatchewan additions were withdrawn before publication: the directory is restored to 180 profiles (SK 69, AB 48, MB 63). Existing profiles and their financial values are unchanged. The historical 69-community project audit now matches the restored Saskatchewan registry. Archived roster research remains historical evidence, not published coverage.
