"""Merge validated recovery candidates without replacing existing usable data."""
import argparse
import copy
import json
from pathlib import Path

from tools.capital_parser import is_verified_summary, validate_summary


def merge_recovery(current, recovered):
    merged = copy.deepcopy(current)
    accepted = []
    for band_id, band in recovered.get("bands", {}).items():
        for year, candidate in band.get("years", {}).items():
            existing = current.get("bands", {}).get(band_id, {}).get("years", {}).get(year)
            if existing and (is_verified_summary(existing) or
                             (existing.get("parseStatus") == "parsed" and existing.get("publishable") is not False)):
                continue
            if candidate.get("parseStatus") != "parsed" or candidate.get("publishable") is not True:
                continue
            if not candidate.get("sourceUrl") or not validate_summary(candidate)["publishable"]:
                continue
            if candidate.get("fiscalYear") != year:
                continue
            target = merged.setdefault("bands", {}).setdefault(band_id, {"name": band.get("name"), "years": {}})
            target.setdefault("years", {})[year] = copy.deepcopy(candidate)
            accepted.append({"bandId": band_id, "community": band.get("name"), "year": year,
                             "parser": candidate.get("parser"), "sourceUrl": candidate["sourceUrl"]})
    if accepted:
        merged["generated"] = recovered.get("generated", current.get("generated"))
    return merged, accepted


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--recovery", required=True)
    parser.add_argument("--current", default="capital-data.json")
    parser.add_argument("--report", default="capital-recovery-merge-report.json")
    args = parser.parse_args()
    path = Path(args.current)
    merged, accepted = merge_recovery(json.loads(path.read_text()), json.loads(Path(args.recovery).read_text()))
    if accepted:
        path.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n")
    Path(args.report).write_text(json.dumps({"accepted": accepted, "count": len(accepted)}, indent=2) + "\n")
    print(json.dumps(accepted, indent=2))


if __name__ == "__main__":
    main()
