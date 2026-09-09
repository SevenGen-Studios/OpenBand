# Waterhen Map Lab

Isolated CesiumJS prototype at `/map-lab/waterhen/`. Production Leaflet,
navigation, financial datasets, and build pipelines are unchanged. This page
is intentionally excluded from indexing.

Serve the repository with `python3 -m http.server 8140` and open
`http://localhost:8140/map-lab/waterhen/`.

## Data and refresh

Run `python3 tools/build_waterhen_lab.py` from the repository root to refresh
the saved ISC boundary and OSM ways. Review the resulting diff before publishing.
Source URLs, retrieval time, query, and counts are in `data/metadata.json`.
The browser reads local snapshots; it does not query Overpass on each visit.
OSM data is credited to OpenStreetMap contributors under ODbL.

## Limits

- The study bounding box includes surrounding land, not only reserve land.
- Valid OSM height tags are preserved; `building:levels` is converted at 3 m
  per level. Untagged buildings use an illustrative 4 m extrusion.
- Footprints do not establish building use, occupancy, or project identity.
- OSM water multipolygon relations are assembled when member ways close cleanly.
  Mapping coverage may still be incomplete.
- ISC administrative geometry is not a substitute for a legal survey.
- Terrain uses the public ArcGIS World Elevation service. Esri World Imagery is
  the aerial base layer. Neither is high-resolution local survey data.
- CesiumJS, imagery, and terrain assets require network access.

Before expanding beyond V0, verify local landmarks with the community and
evaluate maintained terrain hosting. Do not
automatically associate financial project records with unnamed footprints.
