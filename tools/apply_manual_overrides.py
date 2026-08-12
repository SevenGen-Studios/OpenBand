"""Apply manually reviewed FNFTA remuneration overrides to data.json.

Override files live in manual_overrides/*.json so human corrections stay
separate from generated scraper output. The script supports the existing
OpenBand formats:

- {"band": "...", "filings": {"2024-2025": [[...], {...}]}}
- {"overrides": [{"band": "...", "filings": {...}}]}
"""

import json
import sys
from pathlib import Path

try:
    from tools import parser_quality
except ImportError:  # pragma: no cover
    import parser_quality


def key(value):
    return " ".join(str(value or "").lower().split())


def is_remuneration(filing):
    return "remuneration" in key(filing.get("docType"))


def normalize_row(row):
    if isinstance(row, dict):
        person = dict(row)
    elif isinstance(row, list):
        values = list(row) + [None] * 7
        person = {
            "name": values[0],
            "role": values[1],
            "months": values[2],
            "remuneration": values[3],
            "travel": values[4],
            "expenses": 0,
            "creditCard": 0,
            "otherPayments": values[5],
            "total": values[6],
        }
    else:
        raise ValueError(f"Unsupported override row: {row!r}")

    person.setdefault("travel", person.get("travelExpenses"))
    person.setdefault("expenses", 0)
    person.setdefault("creditCard", 0)
    person.setdefault("otherPayments", person.get("other"))
    return parser_quality.normalize_person(person)


def iter_override_records(path):
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get("overrides")
    if records is None:
        records = [payload]
    for record in records:
        merged = dict(record)
        merged.setdefault("source", payload.get("source"))
        merged.setdefault("status", payload.get("status", "manual_override"))
        yield merged


def apply_record(data, record):
    band_name = record.get("band") or record.get("requestedBand")
    if not band_name:
        return 0

    target_band = None
    for band in data.get("bands", []):
        if key(band.get("name")) == key(band_name):
            target_band = band
            break
    if target_band is None:
        return 0

    applied = 0
    for year, rows in (record.get("filings") or {}).items():
        target_filing = None
        for filing in target_band.get("filings", []):
            if filing.get("year") == year and is_remuneration(filing):
                target_filing = filing
                break
        if target_filing is None:
            continue

        people = [normalize_row(row) for row in rows]
        validation = parser_quality.validate_people(people)
        target_filing["people"] = validation["people"]
        target_filing["parse_status"] = record.get("status") or "manual_override"
        target_filing["parse_confidence"] = "manual_reviewed"
        target_filing["manual_review_required"] = False
        target_filing["manual_override"] = True
        target_filing["override_source"] = record.get("source") or "manual_overrides"
        warnings = []
        existing_warnings = [] if record.get("replaceWarnings") else target_filing.get("warnings", [])
        for warning in existing_warnings:
            if warning:
                warnings.append(warning)
        note = f"Manual override applied from {record.get('source') or 'manual_overrides'}"
        if note not in warnings:
            warnings.append(note)
        for warning in validation["warnings"]:
            if warning not in warnings:
                warnings.append(warning)
        target_filing["warnings"] = warnings
        applied += 1
    return applied


def main():
    data_path = Path(sys.argv[1] if len(sys.argv) > 1 else "data.json")
    override_path = Path(sys.argv[2] if len(sys.argv) > 2 else "manual_overrides")
    data = json.loads(data_path.read_text(encoding="utf-8"))

    applied = 0
    if override_path.is_file():
        paths = [override_path]
    elif override_path.exists():
        paths = sorted(override_path.glob("*.json"))
    else:
        paths = []
    for path in paths:
        for record in iter_override_records(path):
            applied += apply_record(data, record)

    data_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"manual overrides applied: {applied}")


if __name__ == "__main__":
    main()
