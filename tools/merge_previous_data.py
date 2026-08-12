"""Merge previous scraper state back into a fresh scraper output.

The scraper rebuilds data.json from ISC each run. When a run only targets a few
fiscal years, older parsed rows and pending parse status can disappear unless we
merge them back from the snapshot taken before the run. This keeps scraper runs
incremental and keeps audit-results.txt honest.
"""

import json
import sys
from pathlib import Path

DEFAULT_STATUSES = {"", "not_applicable", None}
LOGO_FIELDS = (
    "logo_url",
    "logo_source",
    "logo_asset_source",
    "logo_verified",
    "logo_status",
)


def band_key(band):
    band_id = band.get("id")
    if band_id is not None:
        return ("id", str(band_id))
    return ("name", " ".join(band.get("name", "").lower().split()))


def filing_key(filing):
    return (
        str(filing.get("year", "")),
        " ".join(filing.get("docType", "").lower().split()),
    )


def has_people(filing):
    return bool(filing.get("people"))


def merge_warnings(previous_filing, current_filing, note):
    warnings = []
    for warning in previous_filing.get("warnings", []) + current_filing.get("warnings", []):
        if warning and warning not in warnings:
            warnings.append(warning)
    if note not in warnings:
        warnings.append(note)
    return warnings


def merge_band(previous_band, current_band):
    # Logo verification is curated separately from the ISC filings scraper.
    # Preserve it whenever a fresh scraper run rebuilds a band record.
    for field in LOGO_FIELDS:
        if field in previous_band:
            current_band[field] = previous_band[field]

    previous_filings = {filing_key(filing): filing for filing in previous_band.get("filings", [])}
    restored_people = 0
    restored_statuses = 0

    for filing in current_band.get("filings", []):
        previous_filing = previous_filings.get(filing_key(filing))
        if not previous_filing or has_people(filing):
            continue

        if has_people(previous_filing):
            filing["people"] = previous_filing.get("people", [])
            filing["parse_status"] = previous_filing.get("parse_status", "preserved_previous_parse")
            filing["warnings"] = merge_warnings(
                previous_filing,
                filing,
                "Preserved parsed rows from previous data.json snapshot",
            )
            restored_people += 1
            continue

        previous_status = previous_filing.get("parse_status")
        current_status = filing.get("parse_status")
        if current_status in DEFAULT_STATUSES and previous_status not in DEFAULT_STATUSES:
            filing["parse_status"] = previous_status
            filing["warnings"] = merge_warnings(
                previous_filing,
                filing,
                "Preserved pending parse status from previous data.json snapshot",
            )
            restored_statuses += 1

    return restored_people, restored_statuses


def main():
    before_path = Path(sys.argv[1] if len(sys.argv) > 1 else "data.before.json")
    after_path = Path(sys.argv[2] if len(sys.argv) > 2 else "data.json")

    if not before_path.exists():
        print(f"No previous data snapshot found at {before_path}; skipping merge")
        return

    previous = json.loads(before_path.read_text(encoding="utf-8"))
    current = json.loads(after_path.read_text(encoding="utf-8"))

    previous_bands = {band_key(band): band for band in previous.get("bands", [])}
    current_keys = {band_key(band) for band in current.get("bands", [])}
    restored_people = 0
    restored_statuses = 0
    appended = 0

    for band in current.get("bands", []):
        previous_band = previous_bands.get(band_key(band))
        if previous_band:
            people_count, status_count = merge_band(previous_band, band)
            restored_people += people_count
            restored_statuses += status_count

    for key, previous_band in previous_bands.items():
        if key not in current_keys:
            current.setdefault("bands", []).append(previous_band)
            appended += 1

    current["band_count"] = len(current.get("bands", []))
    after_path.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"restored parsed filings: {restored_people}")
    print(f"restored pending parse statuses: {restored_statuses}")
    print(f"appended missing previous bands: {appended}")


if __name__ == "__main__":
    main()
