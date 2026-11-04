# Profile history

`history-data.json` is the canonical editorial dataset. It contains only Canoe
Lake Cree First Nation (ISC band 394). No election, financial or contact records
are changed by this feature. Add future Nations as independent records keyed by
`band_number`, after reviewing their sources.

Run `python tools/build_site.py` to generate the static profile and
`assets/profile-history.js`. `tools/profile_history.py` renders both from the same
structured record. The live overview looks up the published markup by
`iscBandNumber`, directly after Elections & Leadership. Only Canoe Lake’s static page loads the generated history asset. Client-side
navigation to Canoe Lake loads it on demand, along with the updated stylesheet.
No history is inferred for Nations without a record. The generated asset must not be edited manually.

Overview segments, facts, events and connections reference source IDs. Sources
record title, publisher, HTTPS URL, supported claims, a document locator, review
status and check date. Connections record relationship and entity types, an
optional target profile ID, and optional related present-day profile IDs.
Historical bands must remain distinct from present-day Nations.

The badge requires record status `verified`, a review date, and a checked status
and check date for every cited source. Suggested further reading can remain
unchecked but must not support displayed claims. A date records editorial review;
it is not a promise of continuous source availability.

## Canoe Lake review — November 3, 2026

Reviewed the Government of Canada English and French treaty transcriptions,
the Nation's Our History page, the university's Canoe Lake and Buffalo River
encyclopedia entries, OTC biographies and Treaty 10 Gathering page, and Birch
Narrows' community plan (printed pages 9–11). URLs and claim mappings are stored
in the dataset. These documentary accounts do not replace the Nation's oral
histories or represent the whole of its Indigenous history.

Two research details affect the supplied brief:

- McKenna's contemporary report places the Canoe Lake band signing at
  Île-à-la-Crosse on September 19, 1906. The later OTC Gathering page lists Canoe
  Lake. The UI follows the contemporary report and explicitly records the
  discrepancy in Read More. The Nation's About Us page confirms the date and
  leaders but does not specify a signing location.
- The English treaty transcription truncates Raphael's surname. Its French
  counterpart supplies Bedshi-Dekkge. Birch Narrows' plan uses a different
  transliteration. The community plan traces Clear Lake/Peter Pond/Turnor Lake
  and the 1990 Birch Narrows name change; the university's Buffalo River entry
  explicitly confirms the Peter Pond division in 1972.

The requested OTC *In Their Own Land* PDF could not be retrieved. It is retained
as clearly marked, unchecked further reading and is excluded from claim
verification. No current population or governance claims were taken from these
historical sources.

Validation: `python -m unittest discover -s tests -p test_profile_history.py`
and `node tests/test_profile_history.js`.
