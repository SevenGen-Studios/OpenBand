"""Update sourced registered population counts from ISC First Nation Profiles."""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.request
from datetime import date, datetime, timezone
from html import unescape
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data.json"
MEMBER_PATH = ROOT / "member-counts.json"
SOURCE_NAME = "Indigenous Services Canada First Nation Profiles"
SOURCE_URL = "https://fnp-ppn.aadnc-aandc.gc.ca/fnp/Main/Search/FNRegPopulation.aspx?BAND_NUMBER={band_id}&lang=eng"


class TextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        value = " ".join(data.split())
        if value:
            self.parts.append(value)

    def text(self) -> str:
        return " ".join(self.parts)


def parse_population_page(page: str) -> dict:
    parser = TextParser()
    parser.feed(page)
    text = unescape(parser.text())
    total_match = re.search(r"Total Registered Population\s+([0-9][0-9,]*)", text, re.I)
    period_match = re.search(r"Registered Population as of\s+([A-Za-z]+,?\s+\d{4})", text, re.I)
    name_match = re.search(r"Official Name\s+(.+?)\s+Number\s+\d+", text, re.I)
    number_match = re.search(r"\bNumber\s+(\d+)\b", text, re.I)
    if not total_match:
        raise ValueError("ISC page did not contain Total Registered Population")
    total = int(total_match.group(1).replace(",", ""))
    if total <= 0:
        raise ValueError("ISC total registered population was not positive")
    return {
        "registeredMembers": total,
        "sourcePeriod": period_match.group(1).replace(",", "") if period_match else "",
        "officialName": name_match.group(1).strip() if name_match else "",
        "bandNumber": int(number_match.group(1)) if number_match else None,
    }


def fetch_population(band_id: int, timeout: int = 30) -> dict:
    url = SOURCE_URL.format(band_id=band_id)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "OpenBand/1.0 (public-records indexing; https://openband.ca/)"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        page = response.read().decode("utf-8", errors="replace")
    result = parse_population_page(page)
    if result["bandNumber"] not in (None, int(band_id)):
        raise ValueError(f"ISC returned band {result['bandNumber']} for requested band {band_id}")
    result["sourceUrl"] = url
    return result


def load_member_data() -> dict:
    if MEMBER_PATH.exists():
        return json.loads(MEMBER_PATH.read_text(encoding="utf-8"))
    return {"schemaVersion": 1, "bands": {}}


def update_counts(*, only_missing: bool = False, limit: int = 0, delay: float = 0.35) -> dict:
    site_data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    output = load_member_data()
    output.setdefault("schemaVersion", 1)
    output.setdefault("description", "Registered population counts sourced from ISC First Nation Profiles.")
    records = output.setdefault("bands", {})
    checked = date.today().isoformat()
    attempts = successes = failures = 0

    for band in site_data.get("bands", []):
        if band.get('sharedIscIdentity'):
            continue  # Shared band totals cannot be assigned to a component government.
        key = str(band["id"])
        if only_missing and records.get(key, {}).get("registeredMembers"):
            continue
        if limit and attempts >= limit:
            break
        attempts += 1
        try:
            population = fetch_population(int(band["id"]))
            records[key] = {
                "registeredMembers": population["registeredMembers"],
                "sourceName": SOURCE_NAME,
                "sourceUrl": population["sourceUrl"],
                "sourceYear": population["sourcePeriod"],
                "lastChecked": checked,
                "officialName": population["officialName"],
                "notes": "Total registered population reported by ISC; this is not an on-reserve population count.",
            }
            successes += 1
            print(f"OK {band['id']} {band['name']}: {population['registeredMembers']:,}")
        except Exception as exc:
            failures += 1
            print(f"ERROR {band['id']} {band['name']}: {exc}")
        if delay:
            time.sleep(delay)

    output["generated"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    output["source"] = {"name": SOURCE_NAME, "urlPattern": SOURCE_URL}
    output["coverage"] = {
        "trackedBands": len(site_data.get("bands", [])),
        "countsAvailable": sum(
            1 for record in records.values() if record.get("registeredMembers")
        ),
        "attemptedThisRun": attempts,
        "updatedThisRun": successes,
        "failedThisRun": failures,
    }
    temporary = MEMBER_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(MEMBER_PATH)
    return output["coverage"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only-missing", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--delay", type=float, default=0.35)
    args = parser.parse_args()
    coverage = update_counts(only_missing=args.only_missing, limit=max(0, args.limit), delay=max(0, args.delay))
    print(json.dumps(coverage, indent=2))
    if coverage["countsAvailable"] == 0:
        raise SystemExit("No registered population counts are available")


if __name__ == "__main__":
    main()
