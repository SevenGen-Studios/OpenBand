"""Revalidate every stored Community Capital summary without changing source values."""

import argparse
import json
from copy import deepcopy
from pathlib import Path

try:
    from tools.capital_parser import (
        aggregate_categories,
        broad_expense_category,
        broad_revenue_category,
        nearly_equal,
        parse_money,
        sum_rows,
        validate_summary,
        year_over_year_warnings,
    )
except ModuleNotFoundError:  # Direct execution from tools/.
    from capital_parser import (
        aggregate_categories,
        broad_expense_category,
        broad_revenue_category,
        nearly_equal,
        parse_money,
        sum_rows,
        validate_summary,
        year_over_year_warnings,
    )


def normalized_rows(rows, category_fn):
    normalized = []
    for row in rows or []:
        label = row.get("label") or row.get("sourceLabel") or ""
        amount = parse_money(row.get("amount"))
        if not label or amount is None:
            continue
        normalized.append(
            {
                "sourceLabel": label,
                "category": category_fn(label),
                "amount": row.get("amount"),
                **(
                    {"sourceReference": row["sourceReference"]}
                    if row.get("sourceReference")
                    else {}
                ),
            }
        )
    return normalized


def safely_rebuild_breakdown(summary, source_key, total_key, category_fn):
    rows = normalized_rows(summary.get(source_key), category_fn)
    total = parse_money(summary.get(total_key))
    if not rows or total is None or not nearly_equal(sum_rows(rows), total):
        return False
    breakdown, source_rows = aggregate_categories(rows)
    target = "revenueBreakdown" if source_key == "sourceRevenueRows" else "expenseBreakdown"
    changed = breakdown != summary.get(target) or source_rows != summary.get(source_key)
    summary[target] = breakdown
    summary[source_key] = source_rows
    return changed


def audit_dataset(capital_data):
    report = {
        "audited": 0,
        "corrected": [],
        "suppressed": [],
        "flagged": [],
        "manualReview": [],
    }
    for band_id, band in capital_data.get("bands", {}).items():
        years = band.get("years", {})
        for fiscal_year, summary in years.items():
            report["audited"] += 1
            before = deepcopy(summary)
            revenue_changed = safely_rebuild_breakdown(
                summary,
                "sourceRevenueRows",
                "totalRevenue",
                broad_revenue_category,
            )
            expense_changed = safely_rebuild_breakdown(
                summary,
                "sourceExpenseRows",
                "totalExpenses",
                broad_expense_category,
            )
            validation = validate_summary(summary)
            if summary.get("publishable") is not False and not validation["publishable"]:
                summary.update(validation)
                summary["extractionCompleteness"] = "partial"
            elif revenue_changed or expense_changed:
                summary["warnings"] = list(
                    dict.fromkeys((summary.get("warnings") or []) + validation["warnings"])
                )
            record = {
                "bandId": str(band_id),
                "band": band.get("name"),
                "fiscalYear": fiscal_year,
                "warnings": summary.get("warnings") or [],
            }
            if revenue_changed or expense_changed or before.get("publishable") != summary.get("publishable"):
                report["corrected"].append(record)
            if before.get("publishable") is not False and summary.get("publishable") is False:
                report["suppressed"].append(record)
            if summary.get("publishable") is False:
                report["manualReview"].append(record)

        ordered = sorted(years.items())
        for index in range(1, len(ordered)):
            _, previous = ordered[index - 1]
            fiscal_year, current = ordered[index]
            flags = year_over_year_warnings(current, previous)
            if not flags:
                continue
            current["validationFlags"] = list(
                dict.fromkeys((current.get("validationFlags") or []) + flags)
            )
            report["flagged"].append(
                {
                    "bandId": str(band_id),
                    "band": band.get("name"),
                    "fiscalYear": fiscal_year,
                    "warnings": flags,
                }
            )

    for key in ("corrected", "flagged"):
        report[key] = list(
            {f"{row['bandId']}:{row['fiscalYear']}": row for row in report[key]}.values()
        )
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="capital-data.json")
    parser.add_argument("--report", default="capital-validation-report.json")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    path = Path(args.data)
    capital_data = json.loads(path.read_text(encoding="utf-8"))
    report = audit_dataset(capital_data)
    if args.apply:
        path.write_text(
            json.dumps(capital_data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    Path(args.report).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"audited={report['audited']} corrected={len(report['corrected'])} "
        f"suppressed={len(report['suppressed'])} flagged={len(report['flagged'])} "
        f"manual_review={len(report['manualReview'])}"
    )


if __name__ == "__main__":
    main()
