# Prairie flag selector release

Based on live main d7b9e6ea. Scope: Saskatchewan, Alberta and Manitoba only. British Columbia remains withdrawn; no BC routes, datasets, extraction checkpoints or leadership-label changes are included.

The gateway uses a continuous rotating ring with direct horizontal dragging, touch swipes, keyboard arrows, both-direction wraparound and native province links. Reduced-motion preferences are respected. Responsive flag sizing reserves space for the heading and controls; compact phone/tablet navigation avoids horizontal overflow. Original Prairie SVG artwork is served locally with source attribution in each file.

Shared CSS and carousel asset cache versions are updated in index.html; generated routes contain only matching asset-version updates. Financial data, other datasets and application rendering logic are unchanged.

Validation: 11 browser-logic regression scripts passed. The Python suite ran 689 tests with three skips; its sole initial failure was the deliberate public-asset fingerprint, updated for this intentional CSS/cache-version change. All 20 financial-entry tests then passed. Chrome/WebKit responsive validation is recorded outside this release in outputs/prairie-flags-{layout,webkit}-validation.json.

This branch is prepared locally. Committing this branch does not deploy it; publishing main remains a separate step. Physical iOS, iPadOS, macOS and Windows devices have not all been tested.
