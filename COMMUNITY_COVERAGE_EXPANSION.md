# Community coverage expansion — November 3–4, 2026

Data-only release. The campaign figures below describe the reviewed local expansion. Integration with main `67125e4c` preserves its newer profile histories, election labels and job checks. The combined release contains 82 confirmed active jobs (77 on the upstream parent at the same November 4 cutoff). Map files are excluded from this release. No Follow/account/notification feature is included. All comparisons below evaluate the frozen starting inventory and the current inventory on November 4, 2026, so jobs that closed during the overnight research session are not counted as active.

| Category | Before | After | Added IDs | Removed / merged |
|---|---:|---:|---:|---:|
| News | 571 | 591 | 21 | 1 |
| Events | 201 | 234 | 34 | 1 |
| Projects | 168 | 188 | 20 | 0 |
| Jobs | 807 | 815 | 25 | 17 |

Confirmed active job listings increased from **72 to 80** at the same November 4 cutoff. Added job IDs include held or closed candidates and are not all vacancies. The news additions include **7 published within 90 days**; older notices retain their original dates. **30 added events remain upcoming or ongoing** on November 4. Recurring sessions retain separate explicitly published occurrences, not invented recurrence dates.

## Breadth across communities

| Province | Recent news ≤90d | Upcoming events | Projects / partnerships | Active jobs | All four together |
|---|---:|---:|---:|---:|---:|
| SK | 21 → 26 | 4 → 4 | 69 → 69 | 24 → 24 | 0 → 0 |
| AB | 17 → 17 | 5 → 6 | 47 → 48 | 5 → 5 | 0 → 1 |
| MB | 11 → 12 | 4 → 4 | 20 → 26 | 10 → 10 | 1 → 2 |

## Verified additions

- Siksika Health Services calendar occurrences and two Siksika housing workshops, with source dates, venues and occurrence times kept separate from publication dates.
- Guardian/stewardship programs named in the federal 2025–2026 backgrounder, including Chemawawin, Marcel Colomb, Mosakahiken, Keeseekoowenin and Tthebatthie. Historical funding descriptions are not presented as current construction or completion milestones.
- Hollow Water and Sagkeeng water stewardship; the explicitly named FML #1 consortium; Wuskwi Sipihk and Beaver forestry planning; Waterhen temporary and permanent-school planning; and the Cree Nations Miyoyawin Centre. Shared funding and board participation are not turned into per-Nation costs or ownership percentages.
- Refreshed employer postings from Dene Tha’, Siksika, Bigstone, Fisher River, NCN and Sagkeeng. All **112 previously reviewed job records** retained their identity, employer, pay, qualifications and application fields. Duplicate automatic rows are merged into reviewed records when the same permalink and role establish the same vacancy.

## Pipeline improvements

1. Read embedded PDF text through the existing pdfplumber dependency when Poppler command-line tools are unavailable. Scanned/unreadable documents remain held for OCR or review.
2. Parse career tables by labeled columns, keeping each row’s posted date and deadline separate and holding blank deadlines.
3. Recognize publisher `dcterms.issued` publication metadata without treating `dcterms.modified` as publication.
4. Reject calendar day-navigation links as events while retaining structured, explicitly dated occurrences.
5. Deduplicate title-suffix variants on the same job permalink while preserving manual details.
6. Keep campaign-scoped source evidence and combine diagnostics across campaigns. Source registration preserves reviewed adapters and bounded detail/media budgets.
7. Run the new extraction/evidence tests in scheduled news, events, jobs and research workflows.

The reusable catalogue now contains **46 sources**. This campaign archived **12 unique research pages** with hashes; the live collectors performed additional bounded requests reported in their source-run diagnostics. No denied-access page was bypassed and no paid service was introduced.

## Follow is still a coverage goal

Only **3 of 180 communities** currently have recent news, an upcoming/ongoing event, a verified project and an active job simultaneously. This is a coverage measurement, not a product readiness threshold. The next priority is broader event coverage and more employers in Nations that still have no active jobs, rather than increasing repeated records for already well-covered communities.

The complete next-research queue is `research-priorities.csv`; empty coverage does not mean no public activity exists. Original profile/financial records and the 69 SK / 48 AB / 63 MB roster are unchanged. The parked map work remains local.

Validation of the data-only release: **568 Python tests and 15 JavaScript suites passed.**
