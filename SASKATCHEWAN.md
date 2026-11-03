# Saskatchewan roster coverage

On November 3, 2026, the official ISC provincial search returned 70 Saskatchewan
band identities. The previous directory contained 69; Big Island Lake Cree
Nation (399) was missing. It now has a profile, official location, registered
population, reserve area, Band Office contact, and 18 original ISC filing links.
Those documents remain pending extraction; no financial values were invented.

FSIN's listings also identify five communities outside the 70-identity ISC
roster: Big Bear Band, Chakastaypasin First Nation, Chacachas Treaty Nation,
Peter Chapman First Nation, and Young Chippewayan First Nation / Stoney Knoll
Band. These have separate searchable profiles with stable application IDs.
Together with all 70 ISC identities, OpenBand lists 75 Saskatchewan communities.
FSIN identifies Big Island separately as a non-member, so this total is not a
claim that FSIN has 75 members.

Canada's December 18, 2025 James Smith settlement announcement explicitly places
Chakastaypasin and Peter Chapman within James Smith Cree Nation #370. Their
profiles show shared ISC number 370 with a visible identity note. James Smith's
financial filings, population, leadership, and coordinates are not copied into
their separate profiles.

Current ISC numbers for Big Bear, Chacachas, and Young Chippewayan have not been
verified. Their database values remain null, their profiles show a verification
notice, and their source links go to FSIN rather than an invented ISC URL.
Historical band, reserve, and treaty numbers are not used as substitutes.

Sources:

- [ISC First Nations provincial search](https://services.sac-isc.gc.ca/fnp/main/Search/SearchFN.aspx?lang=eng)
- [FSIN Saskatchewan First Nations listings](https://www.fsin.ca/sask-fn-listings)
- [Canada's James Smith #370 settlement announcement](https://www.canada.ca/en/crown-indigenous-relations-northern-affairs/news/2025/12/james-smith-cree-nation-370-and-canada-reach-a-settlement-agreement-for-long-standing-land-grievances.html)
- [Big Island Lake's ISC profile](https://services.sac-isc.gc.ca/fnp/main/Search/FNMain.aspx?BAND_NUMBER=399&lang=eng)

The exact provincial search responses, request provinces, retrieval dates,
SHA-256 digests, regional source pages, and reviewed name mappings are retained
under `research/band-numbers/2026-11-03/`. The national geomatics roster independently
checks band-number/name pairs. `saskatchewan-nations.json` stores the reconciled
roster; `provincial-roster-audit.json` checks provincial completeness, while
`band-number-audit.json` keeps the three-number verification queue explicit.

The 180 previously listed Nation records and their financials are unchanged
except for adding 69 missing, verified `iscBandNumber` fields. Existing contact,
location, population, and logo rows are preserved. Archived Manitoba preservation
baselines retain the earlier evidence; the current baseline also protects the
authorized additions and explicit empty research coverage. No new logos,
election results, enterprise ownership, or financial extractions were inferred.
