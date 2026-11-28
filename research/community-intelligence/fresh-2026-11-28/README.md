# Fresh coverage reviewed 2026-11-28

This batch adds ten verified records across Flying Dust, Lubicon Lake Band and Fisher River: two recent news articles, five upcoming events and three active job postings. It also updates the existing Flying Dust water-treatment project description with explicitly dated evidence; it creates no new project or completion claim.

Same-day inventory against main 907de0a4: recent news (30 days) 44 → 46 Nations; news (90 days) 69 → 71; upcoming events 27 → 28; active jobs 64 → 65; all four categories 20 → 22. Flying Dust and Fisher River gain all four. These are coverage counts, not numbers of records.

## Sources and interpretation

`reviewed-enrichment.json` holds the ten records and their evidence. `source-checks.json` records archived-source SHA-256 digests; `source-urls.json` maps their original URLs. The two Alberta Native News articles explicitly identify their Nation associations. Lubicon's page displays November 25 while its original publication metadata is November 26; the record preserves that distinction. Flying Dust's article is a member profile, not a claim that the Nation owns the member's business.

The Flying Dust Fall 2026 newsletter supplies five December community Christmas meals with named venues. Its noon instruction is for PCD distributions, not a verified meal start time: no meal times are invented. Two other calendar entries without clear venues were held back. The original 22-page PDF is represented here by untouched content pages 1 and 6 copied with pypdf, compressed for repository size. Source checks preserve the original full-document digest, selected-page digest, page numbers and preparation method. Both pages were visually reviewed.

Fisher River employer postings explicitly state that both education vacancies are open until filled. The Jordan's Principle role starts January 7, 2027. The ICFS intake posting closes December 2 and lists separate Fisher River and Winnipeg competitions; the record names both locations without implying that every position is based in Fisher River. Actual posting evidence is required to renew availability. No index-wide phrase renews a vacancy.

`project-update.json` preserves the before/after Flying Dust water-treatment record. Cost and funding fields, historical Under Construction status and December 2025 status date are preserved. The Fall 2026 newsletter describes producing water and a scheduled ribbon cutting, but does not establish formal completion or confirm that ceremony occurred. The description explicitly explains that its construction status remains historical.

An unrelated IOPPS market listing was excluded: its detailed page describes a Saskatoon market and does not support a One Arrow association.

## Collector and validation

The actual archived Fisher River index reproduced a collector gap: singular assistant/worker terms missed plural assistants/workers. The role regex now accepts both forms without changing date, provenance, closure or freshness safeguards. The source-derived regression confirms all three direct posting URLs fall within the configured detail-scan budget.

Seven focused regressions validate archived evidence, news publication eligibility, event dates/time zones, plural-role discovery, job freshness expiry, both all-four gains and historical project status. Run `python -m unittest tests.test_fresh_coverage_20261128 -v`; full suite and deployment results are recorded in the PR. Generated profiles, Follow feeds and coverage reports are rebuilt from the canonical datasets. Financial datasets are unchanged.
