"""Generate a structured queue of remuneration filings needing manual review."""

import json
import re
import sys
from collections import Counter
from pathlib import Path


def is_remuneration(filing):
    return "remuneration" in str(filing.get("docType", "")).lower()


def review_reason(filing):
    warnings = filing.get("warnings") or []
    for warning in reversed(warnings):
        match = re.search(r"Quarantined parsed rows:\s*(.+)", str(warning))
        if match:
            return match.group(1)
    if filing.get("parse_confidence") == "low":
        return "parser confidence is low"
    return "no reliable official rows remain after validation"


def build_report(data):
    filings = []
    reasons = Counter()

    for band in data.get("bands", []):
        for filing in band.get("filings", []):
            if not is_remuneration(filing):
                continue
            if filing.get("parse_status") not in {
                "pending_manual_review", "manual_review", "pending_openai_opt_in"
            } and not filing.get('manual_review_required'):
                continue

            reason = review_reason(filing)
            reasons[reason] += 1
            filings.append(
                {
                    "bandId": band.get("id"),
                    "band": band.get("name"),
                    "province": band.get("province"),
                    "year": filing.get("year"),
                    "reason": reason,
                    "sourcePdf": filing.get("href"),
                    "warnings": filing.get("warnings") or [],
                }
            )

    filings.sort(key=lambda item: (item["band"] or "", item["year"] or ""), reverse=False)
    return {
        "generatedFrom": data.get("generated"),
        "manualReviewCount": len(filings),
        "reasonCounts": dict(sorted(reasons.items())),
        "filings": filings,
    }


def main():
    data_path = Path(sys.argv[1] if len(sys.argv) > 1 else "data.json")
    output_path = Path(sys.argv[2] if len(sys.argv) > 2 else "manual-review-report.json")
    data = json.loads(data_path.read_text(encoding="utf-8"))
    report = build_report(data)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"manual review filings: {report['manualReviewCount']}")
    print(f"saved: {output_path}")


if __name__ == "__main__":
    main()
