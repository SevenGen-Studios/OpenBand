#!/usr/bin/env python3
"""Build the static OpenBand map dataset from official ISC map services."""

from __future__ import annotations

import argparse
import json
import re
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path
from typing import Optional


ROOT = Path(__file__).resolve().parents[1]
LOCATION_URL = (
    "https://data.sac-isc.gc.ca/geomatics/rest/services/"
    "Donnees_Ouvertes-Open_Data/Premiere_Nation_First_Nation/FeatureServer/0/query"
)
RELATION_URL = (
    "https://data.sac-isc.gc.ca/geomatics/rest/services/ATRIS_PRD/"
    "TRIBAL_COUNCILS_FIRST_NATIONS_E/MapServer/6/query"
)

COUNCIL_DISPLAY_NAMES = {
    "BATTLEFORDS AGENCY TRIBAL CHIEFS INC": "Battlefords Agency Tribal Chiefs",
    "FILE HILLS QU'APPELLE TRIBAL COUNCIL INC.": "File Hills Qu'Appelle Tribal Council",
    "MLTC PROGRAM SERVICES INC.": "Meadow Lake Tribal Council",
    "NORTHWEST PROFESSIONAL SERVICES CORP.": "Battlefords Tribal Council",
    "PADC MANAGEMENT COMPANY LTD.": "Prince Albert Grand Council",
    "TOUCHWOOD AGENCY TRIBAL COUNCIL INC.": "Touchwood Agency Tribal Council",
    "YORKTON TRIBAL ADMINISTRATION INC.": "Yorkton Tribal Council",
}


def request_json(url: str, params: dict[str, str]) -> dict:
    payload = urllib.parse.urlencode(params).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        headers={"User-Agent": "OpenBand/2.0 (public records map builder)"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_locations() -> dict:
    return request_json(
        LOCATION_URL,
        {
            "where": "1=1",
            "outFields": "BAND_NUMBER,BAND_NAME",
            "returnGeometry": "true",
            "outSR": "4326",
            "f": "geojson",
        },
    )


def fetch_relations() -> dict:
    return request_json(
        RELATION_URL,
        {
            "where": "1=1",
            "outFields": "BAND_NUMBER,BAND_NAME,TRIBAL_COUNCIL_NUMBER,TRIBAL_COUNCIL_NAME",
            "returnGeometry": "false",
            "f": "json",
        },
    )


def parse_relation_text(text: str) -> dict:
    """Parse the human-readable ArcGIS result used for an offline rebuild."""
    features = []
    pattern = re.compile(
        r"BAND_NUMBER:\s*(?P<band>\d+)\s*\n"
        r"BAND_NAME:\s*(?P<name>[^\n]+)\s*\n"
        r"TRIBAL_COUNCIL_NUMBER:\s*(?P<council_number>[\d.]+)\s*\n"
        r"TRIBAL_COUNCIL_NAME:\s*(?P<council>[^\n]+)",
        re.MULTILINE,
    )
    for match in pattern.finditer(text):
        features.append({"attributes": {
            "BAND_NUMBER": int(match.group("band")),
            "BAND_NAME": match.group("name").strip(),
            "TRIBAL_COUNCIL_NUMBER": float(match.group("council_number")),
            "TRIBAL_COUNCIL_NAME": match.group("council").strip(),
        }})
    return {"features": features}


def council_display_name(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    clean = " ".join(str(value).split())
    return COUNCIL_DISPLAY_NAMES.get(clean.upper(), clean)


def build_map_data(bands: list[dict], locations: dict, relations: dict) -> dict:
    location_by_id = {}
    for feature in locations.get("features", []):
        properties = feature.get("properties") or feature.get("attributes") or {}
        band_id = properties.get("BAND_NUMBER")
        coordinates = (feature.get("geometry") or {}).get("coordinates")
        if band_id is not None and coordinates and len(coordinates) >= 2:
            location_by_id[int(band_id)] = {
                "longitude": float(coordinates[0]),
                "latitude": float(coordinates[1]),
                "sourceName": properties.get("BAND_NAME"),
            }

    relation_by_id = {}
    for feature in relations.get("features", []):
        attributes = feature.get("attributes") or feature.get("properties") or {}
        band_id = attributes.get("BAND_NUMBER")
        council = attributes.get("TRIBAL_COUNCIL_NAME")
        if band_id is None or not council:
            continue
        relation_by_id[int(band_id)] = {
            "tribalCouncil": council_display_name(council),
            "tribalCouncilSourceLabel": str(council).strip(),
            "tribalCouncilNumber": attributes.get("TRIBAL_COUNCIL_NUMBER"),
        }

    communities = []
    missing_locations = []
    for band in sorted(bands, key=lambda row: row["name"]):
        band_id = int(band["id"])
        location = location_by_id.get(band_id)
        if not location:
            missing_locations.append({"id": band_id, "name": band["name"]})
            continue
        relation = relation_by_id.get(band_id, {})
        communities.append({
            "id": band_id,
            "name": band["name"],
            "latitude": location["latitude"],
            "longitude": location["longitude"],
            "treaty": band.get("treaty") or None,
            "tribalCouncil": relation.get("tribalCouncil"),
            "tribalCouncilSourceLabel": relation.get("tribalCouncilSourceLabel"),
            "tribalCouncilNumber": relation.get("tribalCouncilNumber"),
        })

    return {
        "schemaVersion": 1,
        "generated": date.today().isoformat(),
        "sources": {
            "locations": LOCATION_URL.rsplit("/query", 1)[0],
            "tribalCouncilRelationships": RELATION_URL.rsplit("/query", 1)[0],
        },
        "communityCount": len(communities),
        "missingLocations": missing_locations,
        "communities": communities,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=ROOT / "data.json")
    parser.add_argument("--output", type=Path, default=ROOT / "map-data.json")
    parser.add_argument("--geojson", type=Path, help="Use a saved ISC GeoJSON response")
    parser.add_argument("--relations-json", type=Path, help="Use a saved ISC relation JSON response")
    parser.add_argument("--relations-text", type=Path, help="Use a saved ArcGIS HTML result as text")
    args = parser.parse_args()

    data = json.loads(args.data.read_text(encoding="utf-8"))
    locations = json.loads(args.geojson.read_text(encoding="utf-8")) if args.geojson else fetch_locations()
    if args.relations_json:
        relations = json.loads(args.relations_json.read_text(encoding="utf-8"))
    elif args.relations_text:
        relations = parse_relation_text(args.relations_text.read_text(encoding="utf-8"))
    else:
        relations = fetch_relations()

    result = build_map_data(data.get("bands", []), locations, relations)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if result["missingLocations"]:
        raise SystemExit(f"Missing official locations for {len(result['missingLocations'])} communities")
    print(f"Wrote {result['communityCount']} communities to {args.output}")


if __name__ == "__main__":
    main()
