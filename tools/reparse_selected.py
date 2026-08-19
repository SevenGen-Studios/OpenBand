"""Reparse an exact, reviewable set of band/year remuneration filings."""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import run_scraper
from tools import parser_quality
from tools.reparse_suspicious import filing_problems


def is_remuneration(filing):
    return "remuneration" in str(filing.get("docType", "")).lower()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("selection", help="JSON object mapping exact band names to fiscal-year arrays")
    parser.add_argument("--data", default="data.json")
    parser.add_argument("--results")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--part-index", type=int, default=0)
    parser.add_argument("--part-count", type=int, default=1)
    args = parser.parse_args()

    data_path = Path(args.data)
    data = json.loads(data_path.read_text(encoding="utf-8"))
    selections = json.loads(Path(args.selection).read_text(encoding="utf-8"))
    bands = {band.get("name"): band for band in data.get("bands", [])}
    repaired_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    outcomes = []

    selected_pairs = [
        (band_name, year)
        for band_name, years in selections.items()
        for year in years
    ]
    if args.part_count < 1 or not 0 <= args.part_index < args.part_count:
        parser.error("--part-index must be between zero and --part-count minus one")
    selected_pairs = [
        pair for index, pair in enumerate(selected_pairs)
        if index % args.part_count == args.part_index
    ]

    for band_name, year in selected_pairs:
        band = bands.get(band_name)
        if not band:
            outcomes.append({"band": band_name, "status": "band_missing"})
            continue
        filings = {
            filing.get("year"): filing
            for filing in band.get("filings", [])
            if is_remuneration(filing)
        }
        filing = filings.get(year)
        label = f"{band_name} {year}"
        if not filing:
            print(f"{label}: filing missing", flush=True)
            outcomes.append({"band": band_name, "year": year, "status": "filing_missing"})
            continue
        before = {
                "parse_status": filing.get("parse_status"),
                "people": len(filing.get("people") or []),
        }
        result = run_scraper._extract_remuneration_rows_enhanced(filing.get("href"))
        validation = parser_quality.validate_people(result.get("people") or [])
        people = validation.get("people") or []
        problems = filing_problems(people)
        if validation.get("manual_review_required") or problems:
            reasons = list(dict.fromkeys(
                (result.get("warnings") or [])
                + (validation.get("warnings") or [])
                + problems
            ))
            print(f"{label}: unresolved - {'; '.join(reasons[:5])}", flush=True)
            outcomes.append({
                "band": band_name,
                "year": year,
                "status": "unresolved",
                "before": before,
                "parser_status": result.get("parse_status"),
                "reasons": reasons,
            })
            continue

        filing["people"] = people
        filing["posted"] = True
        filing["parse_status"] = result.get("parse_status", "ok_selected_reparse")
        filing["parse_confidence"] = validation.get("confidence", "high")
        filing["manual_review_required"] = False
        filing["warnings"] = list(dict.fromkeys(
            (result.get("warnings") or [])
            + (validation.get("warnings") or [])
            + ["Reparsed from the official ISC filing in the requested repair batch"]
        ))
        filing["parse_stages"] = result.get("parse_stages", [])
        filing["reparsed"] = repaired_at
        band["scraped"] = repaired_at
        print(f"{label}: repaired {len(people)} rows via {filing['parse_status']}", flush=True)
        outcomes.append({
            "band": band_name,
            "year": year,
            "status": "repaired",
            "before": before,
            "parser_status": filing["parse_status"],
            "people": len(people),
        })

    repaired = sum(outcome.get("status") == "repaired" for outcome in outcomes)
    if args.results:
        Path(args.results).write_text(
            json.dumps({"generated": repaired_at, "outcomes": outcomes}, indent=2) + "\n",
            encoding="utf-8",
        )
    if args.write and repaired:
        data["generated"] = repaired_at
        data_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"selected filings repaired: {repaired}/{len(selected_pairs)}", flush=True)


if __name__ == "__main__":
    main()
