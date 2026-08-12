"""Apply source-verified Community Capital overrides to capital-data.json."""

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import capital_parser


def override_paths(path):
    if path.is_file():
        return [path]
    if path.exists():
        return sorted(path.glob("*.json"))
    return []


def apply_override(capital_data, payload):
    band_id = str(payload["bandId"])
    band_record = capital_data.setdefault("bands", {}).setdefault(
        band_id,
        {"name": payload["band"], "years": {}},
    )
    band_record["name"] = payload["band"]

    applied = 0
    for fiscal_year, raw_summary in payload.get("years", {}).items():
        summary = dict(raw_summary)
        summary.setdefault("fiscalYear", fiscal_year)
        summary.setdefault("parser", "manual_official_pdf_v1")
        summary["manualVerified"] = True
        summary["verified"] = True
        validation = capital_parser.validate_summary(summary)
        if not validation["publishable"]:
            reasons = "; ".join(validation["warnings"])
            raise ValueError(f"{payload['band']} {fiscal_year}: {reasons}")
        summary.update(validation)
        summary["extractionCompleteness"] = "complete"
        band_record.setdefault("years", {})[fiscal_year] = summary
        applied += 1
    return applied


def main():
    data_path = Path(sys.argv[1] if len(sys.argv) > 1 else "capital-data.json")
    overrides_path = Path(sys.argv[2] if len(sys.argv) > 2 else "capital_overrides")
    capital_data = json.loads(data_path.read_text(encoding="utf-8"))

    applied = 0
    for path in override_paths(overrides_path):
        payload = json.loads(path.read_text(encoding="utf-8"))
        applied += apply_override(capital_data, payload)

    # capital-data.json is large; stream the encoded JSON to avoid building a
    # second full-size string in memory, then replace the destination only
    # after the write succeeds.
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        newline="\n",
        dir=data_path.parent,
        prefix=f".{data_path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temp_path = Path(handle.name)
        json.dump(capital_data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    temp_path.replace(data_path)
    print(f"capital overrides applied: {applied}")


if __name__ == "__main__":
    main()
