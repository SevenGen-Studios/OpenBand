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
RESERVE_LAND_URL = (
    "https://data.sac-isc.gc.ca/geomatics/rest/services/ILRS_PRD/"
    "ERIP_E_NRCan/MapServer/26/query"
)
FSIN_LISTING_URL = "https://www.fsin.ca/sask-fn-listings"

# The reserve layer uses short administrative names rather than the public
# community names used by OpenBand. Band-number keyed aliases keep attribution
# explicit, including renamed Nations and the three-part Mosquito community.
RESERVE_OWNER_ALIASES = {
    340: ["Little Pine"], 341: ["Lucky Man"], 342: ["Moosomin"],
    343: ["Mosquito", "Grizzly Bear's Head", "Lean Man First Nations"],
    344: ["Onion Lake Cree Nation"], 345: ["Poundmaker"], 346: ["Red Pheasant"],
    347: ["Saulteaux"], 348: ["Sweetgrass"], 349: ["Thunderchild First Nation"],
    350: ["Cumberland House Cree Nation"], 351: ["Fond du Lac"],
    352: ["Hatchet Lake"], 353: ["Lac La Ronge"], 354: ["Montreal Lake"],
    355: ["Peter Ballantyne Cree Nation"], 356: ["Red Earth"],
    357: ["Shoal Lake Cree Nation"], 358: ["Wahpeton Dakota Nation"],
    359: ["Black Lake"], 360: ["Sturgeon Lake First Nation"], 361: ["Cowessess"],
    362: ["Kahkewistahaw"], 363: ["Ochapowace"], 364: ["Zagime Anishinabek"],
    365: ["White Bear"], 366: ["Cote First Nation 366"], 367: ["Keeseekoose"],
    368: ["The Key First Nation"], 369: ["Beardy's and Okemasis"],
    370: ["James Smith"], 371: ["Muskoday First Nation"],
    372: ["Whitecap Dakota Nation"], 373: ["One Arrow First Nation"],
    374: ["Mistawasis Nêhiyawak"], 375: ["Muskeg Lake Cree Nation #102"],
    376: ["Yellow Quill"], 377: ["Kinistin Saulteaux Nation"],
    378: ["Carry The Kettle"], 379: ["Little Black Bear"], 380: ["Nekaneet"],
    381: ["Muscowpetung"], 382: ["Okanese"], 383: ["Pasqua First Nation #79"],
    384: ["Peepeekisis Cree Nation No.81"], 385: ["Piapot"],
    386: ["Standing Buffalo"], 387: ["Star Blanket Cree Nation"],
    388: ["Wood Mountain"], 389: ["Day Star"], 390: ["Fishing Lake First Nation"],
    391: ["George Gordon First Nation"], 392: ["Muskowekwan"],
    393: ["Kawacatoose"], 394: ["Canoe Lake Cree Nation"],
    395: ["Flying Dust First Nation"], 396: ["Makwa Sahgaiehcan First Nation"],
    397: ["Ministikwan Lake Cree Nation"], 398: ["Buffalo River Dene Nation"],
    400: ["English River First Nation"], 401: ["Clearwater River Dene"],
    402: ["Waterhen Lake"], 403: ["Birch Narrows First Nation"],
    404: ["Big River"], 405: ["Pelican Lake"], 406: ["Ahtahkakoop"],
    407: ["Witchekan Lake"], 408: ["Ocean Man"], 409: ["Pheasant Rump Nakota"],
}

COUNCIL_DISPLAY_NAMES = {
    "BATTLEFORDS AGENCY TRIBAL CHIEFS INC": "Battlefords Agency Tribal Chiefs (BATC)",
    "FILE HILLS QU'APPELLE TRIBAL COUNCIL INC.": "File Hills Qu'Appelle Tribal Council",
    "MLTC PROGRAM SERVICES INC.": "Meadow Lake Tribal Council",
    "NORTHWEST PROFESSIONAL SERVICES CORP.": "Battlefords Agency Tribal Chiefs (BATC)",
    "PADC MANAGEMENT COMPANY LTD.": "Prince Albert Grand Council",
    "TOUCHWOOD AGENCY TRIBAL COUNCIL INC.": "Touchwood Agency Tribal Council",
    "YORKTON TRIBAL ADMINISTRATION INC.": "Yorkton Tribal Council",
}

# ISC's relationship layer omits some current Saskatchewan affiliations. FSIN's
# public listings fill only those documented gaps and remain separate from the
# original ISC relationship label.
FSIN_COUNCIL_OVERRIDES = {
    340: "Battlefords Agency Tribal Chiefs (BATC)",
    363: "South East Treaty 4 Tribal Council",
    365: "South East Treaty 4 Tribal Council",
    404: "Agency Chiefs Tribal Council",
    405: "Agency Chiefs Tribal Council",
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


def fetch_reserve_lands() -> dict:
    return request_json(
        RESERVE_LAND_URL,
        {
            "where": "CPC_CODE='SK'",
            "outFields": "OBJECTID,ADMIN_LAND_ID,SHORT_NAME,FIRST_NATIONS",
            "returnGeometry": "true",
            # Statistics Canada Lambert is an equal-area projection in metres.
            "outSR": "3347",
            "geometryPrecision": "2",
            "resultRecordCount": "2000",
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


def normalized_owner(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def projected_ring_area(ring: list[list[float]]) -> float:
    if len(ring) < 3:
        return 0.0
    return sum(
        float(ring[index][0]) * float(ring[(index + 1) % len(ring)][1])
        - float(ring[(index + 1) % len(ring)][0]) * float(ring[index][1])
        for index in range(len(ring))
    ) / 2


def reserve_feature_area_hectares(feature: dict) -> float:
    rings = (feature.get("geometry") or {}).get("rings") or []
    # Esri rings use opposite winding for exterior rings and holes, so the
    # signed sum removes holes before conversion from square metres.
    return abs(sum(projected_ring_area(ring) for ring in rings)) / 10_000


def reserve_land_totals(bands: list[dict], reserve_lands: dict) -> dict[int, dict]:
    totals = {int(band["id"]): {"hectares": 0.0, "parcelCount": 0} for band in bands}
    aliases = {
        band_id: {normalized_owner(alias) for alias in owner_names}
        for band_id, owner_names in RESERVE_OWNER_ALIASES.items()
    }
    for feature in reserve_lands.get("features", []):
        attributes = feature.get("attributes") or feature.get("properties") or {}
        owners = {
            normalized_owner(owner)
            for owner in str(attributes.get("FIRST_NATIONS") or "").split(",")
            if owner.strip()
        }
        hectares = reserve_feature_area_hectares(feature)
        for band_id, band_aliases in aliases.items():
            if owners & band_aliases and band_id in totals:
                totals[band_id]["hectares"] += hectares
                totals[band_id]["parcelCount"] += 1
    return totals


def build_map_data(
    bands: list[dict], locations: dict, relations: dict, reserve_lands: Optional[dict] = None
) -> dict:
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
            "tribalCouncilSourceUrl": RELATION_URL.rsplit("/query", 1)[0],
        }

    land_totals = reserve_land_totals(bands, reserve_lands) if reserve_lands else {}
    communities = []
    missing_locations = []
    for band in sorted(bands, key=lambda row: row["name"]):
        band_id = int(band["id"])
        location = location_by_id.get(band_id)
        if not location:
            missing_locations.append({"id": band_id, "name": band["name"]})
            continue
        relation = relation_by_id.get(band_id, {})
        if band_id in FSIN_COUNCIL_OVERRIDES:
            relation = {
                "tribalCouncil": FSIN_COUNCIL_OVERRIDES[band_id],
                "tribalCouncilSourceLabel": FSIN_COUNCIL_OVERRIDES[band_id],
                "tribalCouncilNumber": None,
                "tribalCouncilSourceUrl": FSIN_LISTING_URL,
            }
        community = {
            "id": band_id,
            "name": band["name"],
            "latitude": location["latitude"],
            "longitude": location["longitude"],
            "treaty": band.get("treaty") or None,
            "tribalCouncil": relation.get("tribalCouncil"),
            "tribalCouncilSourceLabel": relation.get("tribalCouncilSourceLabel"),
            "tribalCouncilNumber": relation.get("tribalCouncilNumber"),
            "tribalCouncilSourceUrl": relation.get("tribalCouncilSourceUrl"),
        }
        if reserve_lands is not None:
            land = land_totals.get(band_id, {})
            community.update({
                "reserveHectares": round(float(land.get("hectares", 0)), 1),
                "reserveParcelCount": int(land.get("parcelCount", 0)),
                "reserveLandSourceUrl": RESERVE_LAND_URL.rsplit("/query", 1)[0],
            })
        communities.append(community)

    return {
        "schemaVersion": 1,
        "generated": date.today().isoformat(),
        "sources": {
            "locations": LOCATION_URL.rsplit("/query", 1)[0],
            "tribalCouncilRelationships": RELATION_URL.rsplit("/query", 1)[0],
            "supplementalTribalCouncilRelationships": FSIN_LISTING_URL,
            "reserveLands": RESERVE_LAND_URL.rsplit("/query", 1)[0],
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
    parser.add_argument("--reserve-json", type=Path, help="Use a saved projected ISC reserve-land JSON response")
    args = parser.parse_args()

    data = json.loads(args.data.read_text(encoding="utf-8"))
    locations = json.loads(args.geojson.read_text(encoding="utf-8")) if args.geojson else fetch_locations()
    if args.relations_json:
        relations = json.loads(args.relations_json.read_text(encoding="utf-8"))
    elif args.relations_text:
        relations = parse_relation_text(args.relations_text.read_text(encoding="utf-8"))
    else:
        relations = fetch_relations()

    reserve_lands = (
        json.loads(args.reserve_json.read_text(encoding="utf-8"))
        if args.reserve_json else fetch_reserve_lands()
    )

    result = build_map_data(data.get("bands", []), locations, relations, reserve_lands)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if result["missingLocations"]:
        raise SystemExit(f"Missing official locations for {len(result['missingLocations'])} communities")
    missing_land = [row["name"] for row in result["communities"] if row.get("reserveHectares", 0) <= 0]
    if missing_land:
        raise SystemExit(f"Missing official reserve-land totals for: {', '.join(missing_land)}")
    print(f"Wrote {result['communityCount']} communities to {args.output}")


if __name__ == "__main__":
    main()
