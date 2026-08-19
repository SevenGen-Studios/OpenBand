"""Audit OpenBand data.json for coverage and parser health.

This script is intentionally report-only. Missing bands and pending posted
filings are work queues, not workflow failures. The scraper workflow has the
hard safety checks that prevent bad data from being committed.
"""

import json
from collections import Counter
from pathlib import Path

EXPECTED_SK_BANDS = [
    "Ahtahkakoop Cree Nation",
    "Beardy's and Okemasis' Cree Nation",
    "Big River First Nation",
    "Birch Narrows Dene Nation",
    "Black Lake Denesuline First Nation",
    "Buffalo River Dene Nation",
    "Canoe Lake Cree First Nation",
    "Carry the Kettle Nakoda Nation",
    "Clearwater River Dene Nation",
    "Cowessess First Nation",
    "Witchekan Lake First Nation",
    "Cumberland House Cree Nation",
    "Day Star First Nation",
    "English River First Nation",
    "Fishing Lake First Nation",
    "Flying Dust First Nation",
    "Fond du Lac Denesuline First Nation",
    "George Gordon First Nation",
    "Hatchet Lake Denesuline",
    "Hatchet Lake Denesuline Nation",
    "James Smith Cree Nation",
    "Kahkewistahaw First Nation",
    "Kawacatoose First Nation",
    "Keeseekoose First Nation",
    "Key First Nation",
    "Kinistin Saulteaux Nation",
    "Lac La Ronge Indian Band",
    "Little Black Bear First Nation",
    "Little Pine First Nation",
    "Lucky Man Cree Nation",
    "Makwa Sahgaiehcan First Nation",
    "Mistawasis Nehiyawak",
    "Montreal Lake Cree Nation",
    "Mosquito, Grizzly Bear's Head, Lean Man",
    "Mosquito, Grizzly Bear's Head, Lean Man First Nation",
    "Muscowpetung First Nation",
    "Muscowpetung Saulteaux Nation",
    "Muskeg Lake Cree Nation",
    "Muskoday First Nation",
    "Muskowekwan First Nation",
    "Nekaneet Cree Nation",
    "Nekaneet First Nation",
    "Ocean Man First Nation",
    "Ochapowace First Nation",
    "Ochapowace Nation",
    "Okanese First Nation",
    "One Arrow First Nation",
    "Onion Lake Cree Nation",
    "Pasqua First Nation",
    "Peepeekisis Cree Nation",
    "Pelican Lake First Nation",
    "Peter Ballantyne Cree Nation",
    "Pheasant Rump Nakota Nation",
    "Piapot First Nation",
    "Poundmaker Cree Nation",
    "Red Earth Cree Nation",
    "Red Pheasant Cree Nation",
    "Sakimay First Nation",
    "Saulteaux First Nation",
    "Shoal Lake Cree Nation",
    "Standing Buffalo Dakota Nation",
    "Star Blanket Cree Nation",
    "Sturgeon Lake First Nation",
    "Sweetgrass First Nation",
    "The Key First Nation",
    "Thunderchild First Nation",
    "Wahpeton Dakota Nation",
]

ALIASES = {
    "English River First Nation": "English River Dene Nation",
    "Hatchet Lake Denesuline Nation": "Hatchet Lake Denesuline",
    "Mosquito, Grizzly Bear's Head, Lean Man First Nation": "Mosquito, Grizzly Bear's Head, Lean Man",
    "Muscowpetung Saulteaux Nation": "Muscowpetung First Nation",
    "Nekaneet First Nation": "Nekaneet Cree Nation",
    "Ochapowace Nation": "Ochapowace First Nation",
    "Key First Nation": "The Key First Nation",
    "Sakimay First Nation": "Sakimay First Nations",
}


def has_people(filing):
    return bool(filing.get("people"))


def is_remuneration(filing):
    return "remuneration" in filing.get("docType", "").lower()


def normalize(name):
    return " ".join(name.lower().replace("&", "and").split())


def is_present(name, by_name):
    if normalize(name) in by_name:
        return True
    alias = ALIASES.get(name)
    return bool(alias and normalize(alias) in by_name)


def main():
    data = json.loads(Path("data.json").read_text(encoding="utf-8"))
    bands = data.get("bands", [])
    by_name = {normalize(band.get("name", "")): band for band in bands}

    parsed_bands = []
    parsed_filings = 0
    pending_posted = []
    pending_by_year = Counter()
    parsed_by_year = Counter()
    pending_by_status = Counter()

    for band in bands:
        band_has_parsed = False
        for filing in band.get("filings", []):
            if not is_remuneration(filing):
                continue
            year = filing.get("year") or "unknown"
            if has_people(filing):
                parsed_filings += 1
                parsed_by_year[year] += 1
                band_has_parsed = True
            elif filing.get("posted"):
                status = filing.get("parse_status") or "unknown"
                pending_posted.append((band.get("name"), year, status))
                pending_by_year[year] += 1
                pending_by_status[status] += 1
        if band_has_parsed:
            parsed_bands.append(band.get("name"))

    missing = [name for name in EXPECTED_SK_BANDS if not is_present(name, by_name)]

    print(f"generated: {data.get('generated')}")
    print(f"bands: {len(bands)}")
    print(f"error_count: {data.get('error_count')}")
    print(f"bands with parsed remuneration: {len(parsed_bands)}")
    print(f"parsed remuneration filings: {parsed_filings}")
    print(f"posted remuneration filings still pending: {len(pending_posted)}")

    print("\npending by fiscal year:")
    for year, count in sorted(pending_by_year.items(), reverse=True):
        parsed = parsed_by_year.get(year, 0)
        print(f"  {year}: {count} pending, {parsed} parsed")

    print("\npending by parse status:")
    for status, count in pending_by_status.most_common():
        print(f"  {status}: {count}")

    print(f"\nexpected SK names missing: {len(missing)}")
    for name in missing:
        print(f"  MISSING: {name}")

    print("\nfirst pending examples:")
    for name, year, status in pending_posted[:40]:
        print(f"  PENDING: {name} {year} ({status})")

    if missing:
        print("\nAudit note: missing names are informational until the next successful scraper run updates data.json.")


if __name__ == "__main__":
    main()
