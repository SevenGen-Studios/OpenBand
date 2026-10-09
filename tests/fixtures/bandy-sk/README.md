# Saskatchewan audited statement regressions

These fixtures were extracted from three actual ISC public audited consolidated
statements on October 9, 2026. `manifest.json` records the original source URLs,
band identifiers, filing years, retrieval date and original PDF SHA-256 hashes.
Fixture JSON contains native page text with original one-based PDF page numbers
and PDF word coordinates for the primary operations and financial-position pages.
No amounts or column positions were fabricated. Original PDFs remain in the
ignored local download cache and can be downloaded again with the research CLI.

| Band | Nation | Financial position PDF pages | Operations PDF pages | Reporting entity note PDF pages |
| --- | --- | --- | --- | --- |
| 362 | Kahkewistahaw First Nation | 6-7 | 8-9 | 12-13 |
| 391 | George Gordon First Nation | 5 | 6-7 | 10 |
| 377 | Kinistin Saulteaux Nation | 5 | 6 | 9 |

All three statements are for 2024-2025 and contain 2023-2024 comparatives.
Operations columns are budget/current actual/prior actual; financial-position
columns are current/prior. Tests assert independently transcribed totals and
additional fields against these original page locations. Key primary statement
pages were rendered and visually reviewed during implementation.

Kahkewistahaw's settlement and legal-fee rows must retain the `Treaty 4` label;
`1907` is part of the trust name, including on wrapped text lines. Its large
settlement-related changes stay flagged even when accounting reconciles.
George Gordon's ISC heading applies to its indented funding components.
Kinistin's negative net-debt balance must retain its printed sign. A printed
dash is zero; a missing actual cell must never consume a budget or prior cell.
