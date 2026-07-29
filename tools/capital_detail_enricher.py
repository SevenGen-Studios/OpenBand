"""Add source-backed expense details without changing existing capital totals."""

import argparse
import json
from pathlib import Path

try:
    from tools.capital_parser import (
        fetch_pdf,
        nearly_equal,
        parse_money,
        parse_pdf_bytes,
    )
except ModuleNotFoundError:  # Direct execution from the tools directory.
    from capital_parser import fetch_pdf, nearly_equal, parse_money, parse_pdf_bytes


def source_row_map(summary):
    rows = {}
    for row in summary.get("sourceExpenseRows") or []:
        label = str(row.get("label") or "").strip().lower()
        amount = parse_money(row.get("amount"))
        if label and amount is not None:
            rows[label] = amount
    return rows


def select_safe_details(existing, parsed):
    """Keep only schedules that reconcile to an existing published program row."""
    existing_rows = source_row_map(existing)
    selected_schedules = []
    selected_labels = set()

    for schedule in parsed.get("expenseDetailSchedules") or []:
        label = str(schedule.get("sourceLabel") or "").strip()
        expected = existing_rows.get(label.lower())
        reported = parse_money(schedule.get("reportedTotal"))
        if (
            not label
            or schedule.get("reconciles") is not True
            or expected is None
            or reported is None
            or not nearly_equal(reported, expected, tolerance=0.001)
        ):
            continue
        selected_schedules.append(schedule)
        selected_labels.add(label)

    selected_details = [
        row
        for row in parsed.get("expenseDetails") or []
        if row.get("sourceLabel") in selected_labels
    ]
    return selected_details, selected_schedules


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="capital-data.json")
    parser.add_argument("--year", action="append", default=[])
    parser.add_argument("--band-id", action="append", default=[])
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--force-details", action="store_true")
    args = parser.parse_args()

    path = Path(args.data)
    capital_data = json.loads(path.read_text(encoding="utf-8"))
    candidates = []
    for band_id, band in capital_data.get("bands", {}).items():
        if args.band_id and str(band_id) not in {str(value) for value in args.band_id}:
            continue
        for fiscal_year, summary in band.get("years", {}).items():
            if args.year and fiscal_year not in args.year:
                continue
            if summary.get("parseStatus") != "parsed" or summary.get("publishable") is False:
                continue
            if summary.get("expenseDetails") and not args.force_details:
                continue
            if not summary.get("sourceUrl") or not summary.get("sourceExpenseRows"):
                continue
            candidates.append((band_id, band, fiscal_year, summary))

    candidates.sort(key=lambda item: (item[2], item[1].get("name", "")), reverse=True)
    if args.limit:
        candidates = candidates[: args.limit]

    enriched = 0
    skipped = 0
    failed = 0
    for index, (band_id, band, fiscal_year, summary) in enumerate(candidates, start=1):
        print(f"[{index}/{len(candidates)}] {band.get('name')} {fiscal_year}")
        try:
            parsed = parse_pdf_bytes(
                fetch_pdf(summary["sourceUrl"]),
                summary["sourceUrl"],
                fiscal_year,
            )
            details, schedules = select_safe_details(summary, parsed)
            if not details:
                skipped += 1
                print("  skipped: no reconciled schedule details matched existing program totals")
                continue
            summary["expenseDetails"] = details
            summary["expenseDetailSchedules"] = schedules
            summary["expenseDetailStatus"] = "source_reconciled"
            enriched += 1
            print(f"  enriched: {len(details)} line items across {len(schedules)} schedules")
        except Exception as exc:
            failed += 1
            print(f"  failed: {type(exc).__name__}: {exc}")

    path.write_text(
        json.dumps(capital_data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"complete: enriched={enriched} skipped={skipped} failed={failed}")


if __name__ == "__main__":
    main()
