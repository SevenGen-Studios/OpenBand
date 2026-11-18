# British Columbia — Phase 2 implementation and review

The feature branch `codex/british-columbia-phase2` builds on the completed local Phase 1 commit `ed2312fa`. The GitHub connection confirmed that the remote `main` branch did not yet contain Phase 1 when this work began. No Phase 1 UI was recreated, no changes were deployed, and Phase 3 financial collection was not started.

## Roster and publication scope

The published set contains **204 source-verified government and community-administration profiles**:

- 199 identities returned by ISC’s BC search.
- Dease River (ISC 504) and Taku River Tlingit (ISC 501), whose BC communities are served by ISC’s Yukon Region.
- Nisga’a Lisims Government, Council of the Haida Nation, and Daylu Dena Council as separately identified national/community administrations with no invented ISC band number.

This count spans overlapping governance levels. It is not a count of non-overlapping Nations or populations. The four Nisga’a village identities remain distinct from Nisga’a Lisims Government. Daylu Dena retains its relationship to Liard First Nation (ISC 502), without copying Liard’s registered population or leadership. Source-derived namespaced application IDs are explicitly separate from ISC band numbers.

All 290 provincial A–Z listing rows are retained in the reconciliation registry, including historical-name duplicates, outside-BC governments, tribal/regional organizations and authorities needing further review. BCAFN’s eight region-navigation points are excluded from community identities. Its named community points are reconciled separately.

**Broad roster reconciliation is not claimed complete.** Gitanyow hereditary-authority identity and Tsetsaut/Skii km Lax Ha governing-authority scope remain open. Treaty and website field conflicts remain visible in the review queue. These unresolved fields do not justify assigning false identifiers or treaty classifications.

## Reproducible pipeline

Use the repository Python environment and its existing `requirements-maps.txt` dependency for geometry validation. The commands below use cached public responses by default:

```text
python -m tools.bc_sources
python -m tools.bc_provincial_evidence
python -m tools.enrich_bc
python -m tools.build_bc_boundaries
python -m tools.collect_bc_logos
python -m tools.refresh_bc_roster
python -m tools.merge_bc_enrichment
python -m tools.audit_bc
python tools/build_site.py
python -m tools.pack_bc_source_cache
```

`bc_sources`, `bc_provincial_evidence`, and `enrich_bc` expose `--refresh` for explicit source refreshes. Enrichment checkpoints each completed identity and resumes from cache. The original 201-identity publication scope and the reviewed BCAFN mappings must be re-reviewed if source identities or source hashes change; no fuzzy name join promotes an uncertain identity.

The merge rejects cross-province IDs, duplicate ISC numbers, BC financial arrays, protected-record changes and unreviewed changes to existing BC fields. It stages temporary files, stores original-byte backups and a transaction journal under ignored `.openband-ocr/bc-phase2/backups/`, atomically replaces files, validates preservation, and rolls back on a failed multi-file transaction. Already-verified BC changes require a source review followed by explicit `--accept-reviewed-update`; that flag never permits modifying other provinces or BC financial records.

`manual_overrides/bc-logo-reviews.json` and `tools/bc-source-cache/approved-logos.json` hold the three approved visual/source/hash records. The roster/merge validates those identities and optimized asset hashes. Candidate discovery cannot approve a logo.

## Coverage and evidence

[Coverage report](british-columbia-coverage-report.md) gives the counts, scope and unresolved issues. [Machine-readable report](british-columbia-coverage-report.json) includes denominators, completion rates, missing fields, source-access errors, logo searches, and the full review queue. [Dedicated roster](british-columbia-nations.json) preserves verified identity links and classifications.

Raw public responses are retained in `tools/bc-source-cache/`, usually losslessly gzip-compressed. Each source keeps its original URL, final URL, retrieval timestamp, byte count and SHA-256. Cached identity responses are checked before parsing and source hashes are audited. No credentials or cookie values are persisted.

The source-backed profiles include registered population and its reporting period, reserves, source-listed official websites, administrative contact information, dated governance systems and officeholders where available. Registered population is never presented as the full citizenship or resident population of a self-governing Nation. Office titles are retained literally, including “Chief Councillor.” Only officials whose source-listed appointment/expiry interval covers today are displayed as within a current term. Appointment dates are not treated as election results.

Historic treaties, modern treaties in effect, self-government systems, treaty negotiations and regional/council affiliations remain separate fields. No Nation is labelled non-signatory from missing information. The older ISC historic map’s modern-treaty omissions and its disagreement with legislative descriptions of ancestral Douglas Treaty associations are recorded rather than silently propagated.

## Maps and logos

The existing Leaflet map, BC bounds, controls and styling are preserved. The map supports multiple verified locations for a government through `locations[]`, retaining one primary point for existing consumers. Invalid or unverified coordinates are rejected. Nisga’a Lisims and Haida national-government profiles have no copied village coordinates; absent locations remain explicit.

The existing geometry validator checked 1,602 official BC reserve parcels before addition. Stable parcel IDs and ownership labels are retained, and existing SK/AB/MB features are preserved. Display simplification and any permitted validity repairs are recorded in `tools/bc-source-cache/boundary-validation.json`. These are reserve-display polygons, not traditional territories, negotiation areas or legal surveys.

Every BC profile has a logo record. The logo search visits source-listed sites when robots/access rules allow, recording failed access and unreviewed candidates. Three raster candidates were visually checked, attributed, hashed and optimized using the existing collector. Their reviews are in `manual_overrides/bc-logo-reviews.json`. All unapproved marks retain the existing initials placeholder; no generic or generated symbols are used.

## Reproduce and review

Run from the repository root with the existing Python requirements. Geometry integration uses the existing optional `requirements-maps.txt` dependency. No browser/runtime design dependency was added.

```text
python -m tools.bc_sources
python -m tools.bc_provincial_evidence
python -m tools.enrich_bc
python -m tools.build_bc_boundaries
python -m tools.refresh_bc_roster
python -m tools.merge_bc_enrichment
python tools/build_site.py
python -m tools.audit_bc
```

Source retrieval is cached and rate limited. `--refresh` on the source/enrichment commands deliberately retrieves new evidence. Enrichment checkpoints each Nation and resumes without financial requests. `collect_bc_logos` searches only source-listed official sites and never automatically approves a candidate. Human-reviewed BCAFN alias mappings are bound to source hashes; changed evidence requires another review.

An unchanged merge is repeatable. The merge validates all incoming identities before writes, protects all existing provinces, saves original dataset bytes in ignored `.openband-ocr/bc-phase2/backups/`, stages replacements, and atomically replaces each file. An interrupted multi-file transaction rolls back files already replaced. A changed existing BC record is rejected and queued by default; `--accept-reviewed-update` is an explicit operator action after reviewing verified source changes. Existing financial arrays cannot be replaced through this Phase 2 path.

For existing provinces, both record-level preservation fingerprints and original geometry are checked. Capital, elections, history and enterprise datasets remain byte-preserved. No existing Nation identifiers, source links, remuneration rows or financial figures were changed. Existing untracked Nation/financial files are excluded from the review change.

## Validation and limitations

The final validation results and complete file list are recorded in [Phase 2 review notes](docs/BC-PHASE2-REVIEW.md) and [BC-PHASE2-FILES.txt](docs/BC-PHASE2-FILES.txt).

The browser approval timed out, so live rendering, console inspection and visual desktop/mobile QA remain unverified. Runtime tests cover BC search isolation, profile markup, exact office titles, date handling, unavailable-data states, multiple map points, carousel behaviour and existing provinces. Route/SEO tests inspect generated pages and internal targets.

There is no fabricated BC history narrative. The existing history system remains available when reliable historical records are separately verified. Unknown contacts, population, leaders, locations and logos remain unknown rather than filled with examples.

## Review files and validation

[Complete added/modified file list](docs/BC-PHASE2-FILES.txt) includes all source code, datasets, source-cache responses/provenance, generated BC routes, updated shared pages, tests and approved assets. Existing unrelated untracked files and ignored transaction backups are excluded.

Validation on 2026-11-18:

- All **17 JavaScript suites passed**.
- The full Python run executed **567 tests: 562 passed, 5 failed**. The five failures reproduce the unchanged evidence/baseline problems already present during Phase 1: Cold Lake evidence manifest; Cold Lake historical checkpoint; Day Star/Cote checkpoint bytes; Gordon evidence manifest; Manitoba's older elections-data preservation fingerprint. No fixture was edited to conceal these failures.
- The BC pipeline's 10 tests passed, including duplicate/cross-province rejection, exact identifiers, registered-population periods, distinct governance/treaty classifications, current-term title handling, empty financial scope, map partitioning, all-three-province preservation, repeated merges and rollback of an interrupted transaction.
- 32 focused logo, BC pipeline, BC route and SEO checks passed against the generated pages.
- The BC source audit passed with no errors. The report retains **21 unresolved review items**: two identity/authority cases, fourteen website-domain disagreements, and five ancestral Douglas Treaty scope conflicts. Broader reconciliation is explicitly incomplete.
- A repeat merge left all seven shared dataset files byte-for-byte unchanged. The baseline checks preserve all existing SK/AB/MB record values, original reserve geometry, and immutable financial/elections/history/enterprise files.
- The generator produced 384 profile pages. Original prerender contents were retained for all 180 existing profiles; seven time-dependent jobs refreshes were excluded from this feature change.
- Browser visual QA could not be completed because the native-browser approval timed out; the earlier in-app preview could not connect to localhost. Desktop/mobile rendering and live console inspection are not claimed verified. Map, directory, routing, profile markup and carousel behaviour have runtime/static checks.

The source-linked coverage is 202 map points, 190 profiles with reserve associations, 1,602 validated BC reserve parcels, 201 registered-population profiles, 201 dated governance sources, 167 profiles with officeholders within listed terms, 186 source-listed websites, and 3 visually approved logos. Missing and conflicting fields remain visible in the JSON report. No BC financial data was collected or inferred.

## Phase 3 handoff — separate authorization required

1. Resolve the outstanding authority/identity and field-review items; retain the scope and all source evidence.
2. Use verified ISC identifiers for disclosure discovery. The three non-ISC profiles require a separately verified disclosure-source strategy; do not reuse constituent or Liard identifiers as their own.
3. Establish fiscal-year, reporting-entity, document-identity, shared-scope and financial-source review rules before importing anything.
4. Add financial ingestion, OCR and validation only after a separate Phase 3 instruction. Every BC filing array is currently empty, financial comparisons are unavailable, and missing financial information is not zero.
