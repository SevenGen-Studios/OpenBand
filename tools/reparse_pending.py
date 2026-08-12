"""Recover pending posted remuneration PDFs with the validated local parser."""

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


def cached_pdf_path(directory, band, filing):
    if not directory:
        return None
    return directory / f"{band.get('id')}-{filing.get('year')}.pdf"


def pdf_bytes(directory, band, filing):
    cached = cached_pdf_path(directory, band, filing)
    if cached and cached.exists():
        return cached.read_bytes(), "cached PDF"
    content = run_scraper.scraper.fetch_url(
        run_scraper.scraper.normalize_pdf_url(filing["href"]),
        timeout=30,
    )
    if cached:
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_bytes(content)
    return content, "downloaded PDF"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", default="data.json")
    parser.add_argument("--pdf-dir")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--min-year")
    parser.add_argument("--band", action="append", default=[])
    parser.add_argument("--year", action="append", default=[])
    args = parser.parse_args()

    path = Path(args.path)
    directory = Path(args.pdf_dir) if args.pdf_dir else None
    data = json.loads(path.read_text(encoding="utf-8"))
    candidates = []
    for band in data.get("bands", []):
        if args.band and band.get("name") not in args.band:
            continue
        for filing in band.get("filings", []):
            if args.year and filing.get("year") not in args.year:
                continue
            if args.min_year and str(filing.get("year", "")) < args.min_year:
                continue
            if (
                filing.get("posted")
                and filing.get("href")
                and is_remuneration(filing)
                and not filing.get("people")
                and filing.get("parse_status") not in {"not_required", "not_posted"}
            ):
                candidates.append((band, filing))
    if args.limit:
        candidates = candidates[: args.limit]

    recovered = 0
    attempted = 0
    recovered_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    for index, (band, filing) in enumerate(candidates, start=1):
        label = f"{band.get('name')} {filing.get('year')}"
        print(f"[{index}/{len(candidates)}] {label}")
        try:
            content, source = pdf_bytes(directory, band, filing)
            attempted += 1
            people = run_scraper._extract_people_from_text(content)
            validation = parser_quality.validate_people(people)
            problems = filing_problems(validation.get("people") or [])
            if validation.get("manual_review_required") or problems:
                reasons = list(
                    dict.fromkeys((validation.get("warnings") or []) + problems)
                )
                print("  unresolved: " + "; ".join(reasons[:4]))
                continue

            filing["people"] = validation["people"]
            filing["parse_status"] = "ok_pdf_text_reparse"
            filing["parse_confidence"] = validation.get("confidence", "high")
            filing["manual_review_required"] = False
            filing["warnings"] = [
                f"Recovered from {source} with corrected local text parser"
            ]
            filing["parse_stages"] = [
                {"stage": "local_reparse", "status": "ok_pdf_text_reparse"}
            ]
            filing["reparsed"] = recovered_at
            band["scraped"] = recovered_at
            recovered += 1
            print(f"  recovered: {len(filing['people'])} rows")
        except Exception as exc:
            print(f"  unresolved: {type(exc).__name__}: {exc}")

    print(f"pending filings attempted: {attempted}")
    print(f"filings recovered: {recovered}")
    if args.write and recovered:
        data["generated"] = recovered_at
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"saved: {path}")
    elif recovered:
        print("dry run only; pass --write to save")


if __name__ == "__main__":
    main()
