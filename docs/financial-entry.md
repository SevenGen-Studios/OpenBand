# Manual remuneration entry and correction

## Current delivery and live gate

This implements remuneration only. Community Capital is deliberately not extended
until a real authenticated remuneration publication has passed validation,
committed to main, and been confirmed on GitHub Pages. The local/API/browser
publication tests use simulated GitHub responses; they are not proof of deployment.
No live financial records were edited to test this feature.

The existing Cloudflare OAuth login was successfully checked during implementation.
Production secret names were inspected: only analytics and Stripe credentials were
present. `FINANCIAL_ADMINS`, `FINANCIAL_GITHUB_TOKEN`, and the repository publishing
secret still need provisioning. Keep financial writes disabled until setup is complete.

## Architecture audit

- `/admin/` is static GitHub Pages. Existing administration uses a separate
  Cloudflare Worker (`analytics-worker/src/index.ts`), not a writable Pages server.
- The public remuneration renderer uses `remuneration`, the sum of `travel`,
  `expenses`, and `creditCard`, and `otherPayments`. Canonical aggregate aliases
  also exist. Reported totals may be independently supplied.
- Legacy `manual_overrides/*.json` records replace entire people arrays by Nation
  name/year. Source-protected schedules cannot be changed by those legacy records.
  An arbitrary partial replacement array would therefore lose unrelated officials.
- The scraper and previous-data merge have different responsibilities. Preserving
  an old parse only when the new parse is empty is insufficient to protect a correction.
- Saskatchewan uses the compatibility scraper through `run_scraper_v2.py`;
  Alberta and Manitoba share ingestion writer boundaries. The existing scrape,
  retry, backfill and sanitation workflows already apply legacy overrides.
- Community Capital has a distinct schema, taxonomy, validator, and overrides,
  including shallow patches. It needs its own field-aware editor after the live gate.
- README configures Pages as main/root. GitHub documents that commits using the
  Actions `GITHUB_TOKEN` do not trigger branch-based Pages builds. This workflow
  therefore requires a separately scoped publishing credential:
  https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site

## Data and publishing path

1. `/admin/manual-entry/` signs in using an assigned financial credential, held
   only in memory. Existing analytics credentials do not grant financial writes.
2. The Worker authenticates every request, checks the exact configured Origin,
   constrains identity/year/size, and reads the latest repository `data.json`.
   It uses the raw GitHub content media type because data.json exceeds 1 MB.
3. The browser sends changed fields keyed to original row indexes, explicit
   additions, and explicit removals. The server constructs a complete result
   from the before-image. Arbitrary extra fields cannot be written by the browser.
4. Drafts live on branch `financial-drafts` under
   `admin_drafts/{bandId}-{fiscalYear}.json`. An atomic Git tree/commit also updates
   `admin_drafts/index.json`, so catalog loading does not issue one request per draft.
   Non-fast-forward branch updates and blob leases reject concurrent saves.
   Drafts, names of editors, reasons, source details and history are PUBLIC because
   OpenBand is public. Credentials are never included. Do not enter private notes.
5. Saving drafts permits incomplete figures. Submitting requires names, positions,
   valid amounts/months, no duplicate identities or total rows, source pages, and
   reconciliation of supplied totals. Blank is null, never an implied zero.
   Official source URLs are restricted to the two existing ISC hosts. The Worker
   retrieves a PDF with a 25 MB limit, no redirects, and hashes its actual bytes.
6. A distinct verifier checks the complete source, identity/year and figures.
   Approval re-fetches the PDF and checks the digest. Editing or resubmitting
   discards approval. Arithmetic alone never supplies verification flags.
7. Only the approving verifier can dispatch publication. The immutable draft SHA,
   path and revision are sent to `publish-financial-entry.yml` on main. The workflow
   reads draft JSON as data; no branch code or shell expressions are executed.
8. The workflow validates the approved snapshot, checks its entire before-image
   against current main, writes the deterministic override
   `manual_overrides/zz-admin-{bandId}-{year}.json`, and updates data.json. It runs
   the existing override, sanitizer, review report and route generation pipeline.
   It asserts the approved rows survive normalization before committing all results.
   It shares `openband-v2-data-writers` concurrency with existing data writers.
9. The publishing PAT commits to main, triggering existing site checks and Pages.
   “Queued” is not success. The status action checks the exact workflow revision,
   successful completion, a successful Pages build containing the correction
   commit, and the revision in live OpenBand data.json. Pending/failure stays visible.

No financial database is added. The approved override and Git history are permanent
records. There is one managed override per ID/year; publishing a new revision updates
that file and retains prior versions in Git. The full before-image, corrected rows,
reason, source URL/hash/pages, edit identity/time and verifier identity/time are retained.

## Editing and reversing

Both Add Missing Data and Edit Existing Data use the same editor. Existing schedules
populate automatically. Unchanged raw fields and component breakdowns are retained.
Only explicitly changing Travel / Expenses replaces its component breakdown, by
setting travel to the corrected aggregate and clearing expenses/creditCard to null.
Other updates both aliases. An implicit total is recomputed only for a previously
reconciled complete row. Independently reported inconsistent totals require explicit
correction; reconciliation tolerance is $1.01 for rounding. Unknown components remain
unknown, and unknown totals are labelled unavailable in administrative previews.

A verifier must review the final preview and the official PDF. Restoring a previous
populated schedule creates a new reversal revision requiring independent verification;
it never silently deletes correction history. Withdrawal of a previously missing
schedule, or replacing a schedule with a different PDF URL, requires a source-identity
review in the repository and is intentionally rejected by the financial editor.

After a publication, use **Start a new revision from published data** to edit again.
If the published before-image changed concurrently, reload and start a new revision;
never force through a stale save. Duplicate dispatch of an already-published revision
is harmless. A changed source URL or known PDF hash during scraper replay fails closed
and requires source review rather than silently attaching old amounts to a new source.

## Scraper protection and public compatibility

Managed full snapshots run after all legacy overrides. They can supersede a protected
source review only after explicit approval, without weakening legacy protections.
Managed snapshots replay at the compatibility scraper, previous-data merge,
Alberta writer, Manitoba writer, and standalone sanitizer boundaries. Province-only
outputs skip overrides for absent Nations until the previous-data merge restores them.
Sanitization preserves source-referenced zero/null values and approved Alberta names.

The public JS, public CSS, homepage and Community Capital dataset are unchanged.
No manual badges or public columns are introduced. Existing generated pages use the
same data schema and templates. Public asset hashes and existing browser tests enforce
this boundary. Future intentional public changes must explicitly update the baselines.

## Secure deployment configuration

1. Merge the reviewed implementation and passing financial regression checks first.
2. Create repository-scoped credentials for `SevenGen-Studios/OpenBand`:
   - Worker `FINANCIAL_GITHUB_TOKEN`: Contents read/write, Actions read/write,
     and Pages read. It writes only draft records via the API and dispatches the workflow.
   - Actions secret `FINANCIAL_PUBLISH_TOKEN`: Contents read/write, tied to a
     verified GitHub identity permitted to push main and trigger Pages. Respect
     main branch protection; use an authorized automation identity, not a blanket bypass.
   Set that second value in GitHub repository Actions secrets. Do not paste either
   credential into chat, a public file, command arguments, or frontend configuration.
3. Use the existing deployment's PRIVATE wrangler.toml. Preserve the D1 binding,
   payment rate limiter, Stripe enablement, origins, cron and all existing variables.
   The example is not a replacement for production configuration. From analytics-worker:

   ```sh
   wrangler secret put FINANCIAL_GITHUB_TOKEN
   wrangler secret put FINANCIAL_ADMINS
   ```

   The latter is JSON shaped as below, with separately generated random credentials
   of at least 32 characters and distinct real administrator identities. The same
   person should not receive both roles for approving their own edits.

   ```json
   {"editor-identity":{"token":"REPLACE_WITH_LONG_RANDOM_EDITOR_CREDENTIAL","role":"editor"},
    "verifier-identity":{"token":"REPLACE_WITH_DIFFERENT_LONG_RANDOM_CREDENTIAL","role":"verifier"}}
   ```

   Rotate/revoke a credential by replacing that secret map. The browser never stores
   these credentials in localStorage or sessionStorage. The GitHub tokens remain server-side.
4. Set `FINANCIAL_ENTRY_ENABLED = "true"` only in the real Worker configuration,
   deploy with the normal established procedure, and verify analytics and payment
   smoke checks still pass. Keep all other Worker settings intact.
5. Test one source-checked REAL remuneration correction with the responsible editor
   and verifier. Do not invent figures or put synthetic financial records on main.
   Confirm review, draft resumption, approval, workflow checks, dataset update,
   successful Pages status and the exact values on the public profile.
6. Check one further scraper replay against that approved override. Then extend the
   same system to Community Capital using its actual taxonomy/validation contract.

If Pages has been migrated away from main/root, update the publishing workflow and
status checks to that verified deployment mechanism before enabling publication.

## Tests and maintenance

```sh
python -m unittest tests.test_financial_entry tests.test_manual_overrides
node --experimental-strip-types --test tests/test_financial_entry.mjs
# Install Playwright locally and its Chromium, then:
node --experimental-strip-types tests/test_financial_entry_browser.mjs
```

`financial-entry-tests.yml` runs API, Python, TypeScript, browser and existing public
logic regressions on PRs. Publication repeats the core validation tests. Browser
integration uses simulated GitHub/PDF services and covers a single-figure correction,
preserved officials/components/nulls, draft saving, separate verifier sign-in,
approval, queued publication, memory-only credentials and desktop/mobile viewports.
Python tests cover replay, before-image conflicts, missing schedules, reversals,
source changes, idempotency, malformed values and exact public asset baselines.

Local validation: all targeted tests passed; the broader 612-test Python run had nine
image-evidence subtest errors caused by unavailable RapidOCR/Tesseract, with three
skips. These belong to the existing community evidence test, not financial publishing.
Live GitHub/Pages publishing and Community Capital remain gated on secure setup and a
real approved source correction. Do not describe mocked tests as live end-to-end proof.
