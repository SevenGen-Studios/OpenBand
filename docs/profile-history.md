# Profile history

`history-data.json` is the canonical editorial dataset. It covers all 180 current
profiles: 69 in Saskatchewan, 48 in Alberta and 63 in Manitoba. No election,
financial or contact records are changed by this feature. Add future Nations
after reviewing their sources. Schema 2 keys each record by `profile_id` and
retains `band_number` as an identity check. Saddle Lake and Whitefish Lake 128
share ISC number 462 in the profile dataset, so ISC number alone is not unique.

Run `python tools/build_site.py` to generate the static profile and
`assets/profile-history.js`. `tools/profile_history.py` renders both from the same
structured record. The live overview looks up the published markup by profile ID
and confirms the ISC identity, directly after Elections & Leadership. Every
static profile loads the generated history asset. Client-side navigation loads
it on demand when needed, along with the updated stylesheet.
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

## Expansion review — November 3, 2026

The manually written research notes are in
`research/profile-history/2026-11-03/reviewed.json`. The editorial import
`python tools/import_profile_history.py` compiles those 179 notes and preserves
the original Canoe Lake record. Normal site builds read the canonical dataset;
they do not scrape, generate historical claims, or rerun the editorial import.

Research prioritizes Nation and community institution publications, original
treaty transcriptions, tribal councils, treaty organizations, government records
and university historical accounts. Some reviews used retrieved indexed passages
from documents rather than a complete document; the source metadata records that
review method. A verified badge indicates that the displayed account was checked
against the cited published text, not community endorsement or comprehensive
verification of every statement elsewhere in that publication.

Facts vary by available evidence. A treaty date, leader or connection is omitted
when it could not be established for that specific Nation. Several briefs cover
education, displacement, governance or cultural continuity where a longer early
history was unavailable. Treaty membership is never copied from a neighbouring
Nation or inferred from tribal-council membership. The broad Treaty 2 footer on
regional community pages is not used to assign Treaty 2 to all listed Nations.
Sandy Bay's published chronology contains inconsistent dates, so its brief
retains names and broad treaty-era context and explains the limitation. Mathias
Colomb's source accounts differ on adhesion dates; its brief uses other
documented community milestones. Sturgeon Lake Cree Nation's adhesion follows
the original Treaty 8 transcription, June 8, 1900.

Historical Connections appears only when a cited account supports a specific
relationship. It remains inside a closed native Read More disclosure. No View
Sources control or source panel is rendered; numbered citations link directly to
the supporting publications. Shared markup provides the same content in static
HTML and interactive navigation.

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
