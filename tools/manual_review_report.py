"""Generate a structured queue of remuneration filings needing manual review."""

import argparse
import json
import re
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


def independently_ocr_checked(filing):
    digest = filing.get('sha256') or ''
    people = filing.get('people') or []
    if (not re.fullmatch(r'[a-f0-9]{64}', digest) or not people
            or filing.get('manual_review_required')):
        return False

    review = filing.get('manualSourceReview') or {}
    ocr = review.get('ocrVerification') or {}
    reviewed_ocr = ocr.get('engine') and ocr.get('sha256') == digest
    legacy_method = re.search(r'\b(?:RapidOCR|independent Apple Vision OCR)\b',
                              str(review.get('reviewMethod') or ''), re.I)
    if (review.get('completeSchedule') and review.get('identityAndYearConfirmed')
            and review.get('sha256') == digest and review.get('sourcePdf') == filing.get('href')
            and review.get('sourceRowCount') == len(people) and (reviewed_ocr or legacy_method)):
        return True

    independent = filing.get('independentVerification') or {}
    secondary = filing.get('secondaryExtraction') or {}
    return (
        independent.get('status') == 'source_checks_passed'
        and independent.get('sourceSha256') == digest
        and secondary.get('sha256') == digest
        and bool(secondary.get('engine'))
        and any(page.get('rawText') for page in secondary.get('pages', []))
    )


def build_ocr_queue(data):
    queue = []
    checked = Counter()
    priorities = {'manual_review': 0, 'independent_ocr_needed': 1, 'source_needed': 2}

    for band in data.get('bands', []):
        for filing in band.get('filings', []):
            if not is_remuneration(filing) or not filing.get('posted'):
                continue
            province = band.get('province') or 'unknown'
            evidence = filing.get('manualReviewEvidence') or {}
            discrepancy = (
                evidence.get('outcome') == 'printed_totals_differ'
                and evidence.get('sha256') == filing.get('sha256')
            )
            if independently_ocr_checked(filing) and not discrepancy:
                checked[province] += 1
                continue
            warnings = filing.get('warnings') or []
            wrong_source = (filing.get('verificationStatus') == 'wrong_document_type'
                            or 'wrong_document' in str(filing.get('parse_status') or ''))
            if not filing.get('href') or wrong_source:
                status = 'source_needed'
                reason = warnings[0] if warnings else 'Obtain the original remuneration schedule.'
            elif (discrepancy or filing.get('manual_review_required') or not filing.get('people')
                  or filing.get('parse_confidence') == 'low'):
                status = 'manual_review'
                reason = evidence.get('reason') if discrepancy else None
                reason = reason or (warnings[0] if warnings else review_reason(filing))
            else:
                status = 'independent_ocr_needed'
                reason = 'Compare the published rows to independent OCR and the original page.'
            queue.append({
                'bandId': band.get('id'), 'band': band.get('name'), 'province': province,
                'year': filing.get('year'), 'status': status, 'reason': reason,
                'sourcePdf': filing.get('href'), 'sourceSha256': filing.get('sha256'),
                'publishedRows': len(filing.get('people') or []),
            })

    queue.sort(key=lambda row: (
        -int(str(row['year'] or '')[:4]) if str(row['year'] or '')[:4].isdigit() else 0,
        priorities[row['status']], row['province'], row['band'] or '',
    ))
    return {
        'generatedFrom': data.get('generated'),
        'postedFilingCount': sum(checked.values()) + len(queue),
        'independentlyCheckedCount': sum(checked.values()),
        'independentlyCheckedByProvince': dict(sorted(checked.items())),
        'queueCounts': dict(sorted(Counter(row['status'] for row in queue).items())),
        'filings': queue,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('data', nargs='?', type=Path, default=Path('data.json'))
    parser.add_argument('output', nargs='?', type=Path)
    parser.add_argument('--ocr-queue', action='store_true', help='Prioritize independent OCR and source review.')
    args = parser.parse_args()
    data_path = args.data
    output_path = args.output or Path('ocr-review-queue.json' if args.ocr_queue else 'manual-review-report.json')
    data = json.loads(data_path.read_text(encoding="utf-8"))
    report = build_ocr_queue(data) if args.ocr_queue else build_report(data)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if args.ocr_queue:
        print(f"OCR review filings queued: {len(report['filings'])}")
    else:
        print(f"manual review filings: {report['manualReviewCount']}")
    print(f"saved: {output_path}")


if __name__ == "__main__":
    main()
