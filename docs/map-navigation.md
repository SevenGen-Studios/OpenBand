# Directory map navigation

The Browse map starts at a 50 km metric scale, centred on the selected province
or territory's geographic envelope. The starting zoom is calculated from centre
latitude and the metric scale's 100px maximum width, with 0.1 zoom snapping.
The closer starting view shows part of the province; the rest remains accessible
by panning and zooming out. All 13 Canadian regions
are selectable; indexed community coverage remains Saskatchewan, Alberta and
Manitoba. Empty regions show the existing coverage message. With no region
selected, the existing combined indexed-province overview is retained.

## Boundary provenance

`PROVINCE_MAP_BOUNDS` in `assets/openband.js` contains the minimum and maximum
latitude/longitude of every vertex of each Canadian Admin-1 polygon in
[Natural Earth's 1:10m dataset](https://www.naturalearthdata.com/downloads/10m-cultural-vectors/10m-admin-1-states-provinces/).
The [source GeoJSON](https://github.com/nvkelso/natural-earth-vector/blob/master/geojson/ne_10m_admin_1_states_provinces.geojson)
was retrieved November 3, 2026. The bounds include coastal islands and detached
parcels (including Nunavut's southern islands). They are geographic envelopes,
not legal boundary data or a polygon clip. Natural Earth is public domain.

To reproduce, download that GeoJSON and run this JavaScript with Node, passing
the downloaded filename as the first argument:

```js
const fs = require('node:fs');
const data = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const points = coordinates => typeof coordinates[0] === 'number'
  ? [coordinates] : coordinates.flatMap(points);
const bounds = {};
for (const feature of data.features.filter(f => f.properties.admin === 'Canada')) {
  const vertices = points(feature.geometry.coordinates);
  const lat = vertices.map(p => p[1]), lng = vertices.map(p => p[0]);
  bounds[feature.properties.iso_3166_2.slice(3)] = [
    [Math.min(...lat), Math.min(...lng)],
    [Math.max(...lat), Math.max(...lng)]
  ].map(pair => pair.map(n => Math.round(n * 1e5) / 1e5));
}
console.log(JSON.stringify(bounds));
```

## Camera and interaction

- The first frame fits immediately; subsequent selections use a 0.7 second
  Leaflet flight. Reduced-motion preferences disable camera flights and the
  map's zoom/fade animation and inertia.
- The camera only reframes when province or filters change. Background boundary
  loads and legend rendering preserve manual navigation. Reset map restores the
  selected province's 50 km starting view while retaining active community filters.
- Valid community points belonging to the province's roster extend its navigable
  envelope where needed for cross-border locations. Search results fit independently,
  with a maximum zoom of 8 for single-point matches.
- Pan limits allow 12% geographic padding and soft dragging resistance. The
  current half-viewport is added in projected pixel space before setting Leaflet
  maxBounds. This avoids the old off-centre framing regression on wide screens.
  Limits update on zoom and resize; province changes clear old limits before
  animating. Zooming out is limited to 0.75 levels below the province's fitted
  view or starting zoom (whichever is lower), with a floor of 1 for northern territories.
- Native Leaflet wheel zoom remains cursor-centred, with 80 wheel pixels per
  zoom level (previously 180), 0.1 zoom snapping and full-level zoom-button increments.
  Native pinch zoom and
  inertial dragging remain available. Canvas markers stay geographically
  anchored. Tiles retain a four-tile buffer and avoid intermediate zoom loads.
- Community markers use a 6.5px radius, growing to 7.5px on hover or focus and
  returning to their normal size on exit. Their reserve parcels use a 1.5px
  dark-red stroke, 45% red fill, and a soft 4px white halo.
  Both geometry layers live below community markers, and both are removed
  together on hover exit. Touch selection uses the same boundary highlight.
- The map instance and tile layer persist when switching regions. Province
  selection updates the Browse URL and works with browser back/forward.

Run `node tests/test_directory_map.js`, `node tests/test_provinces.js` and
`node tests/test_manitoba.js`. Browser QA should cover wheel/trackpad and pinch
gestures on real input hardware, reset, province switching, reduced motion,
portrait/landscape layouts, and rapid selection during a flight. Tile delivery
still depends on the existing OpenStreetMap service and network connection.
