"""Read-only by default. Audit every published SK/AB/MB row; apply evidence only.

Stored references and matching rules are not independent PDF verification.
Evidence manifests bind decisions to the input row, source URL and PDF hash.
No financial amount, total, publication flag or source label is changed.
"""
import argparse
import copy
import hashlib
import json
import re
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path

try:
    from tools.capital_classification import classify, reviewed_row
    from tools.capital_parser import is_verified_summary, year_over_year_warnings
except ModuleNotFoundError:
    from capital_classification import classify, reviewed_row
    from capital_parser import is_verified_summary, year_over_year_warnings

PROVINCES = {'SK', 'AB', 'MB'}
CHECKS = {'nation', 'fiscalYear', 'section', 'actualColumn', 'amount', 'notDuplicated', 'accountingContext'}
STATUSES = ('verified_correct', 'verified_misclassification', 'ambiguous', 'extraction_issue')


def dollars(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value).replace(',', '').replace('$', '').replace('(', '-').replace(')', '').strip())
        return result if result.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def total(rows):
    values = [dollars(row.get('amount')) for row in rows]
    return None if any(value is None for value in values) else sum(values, Decimal(0))


def number(value):
    if value is None:
        return None
    return int(value) if value == int(value) else float(value)


def row_key(band_id, year, kind, index):
    return f'{band_id}:{year}:{kind}:{index}'


def published(summary):
    # Same visibility predicate as the capital UI.
    return summary.get('parseStatus') == 'parsed' and summary.get('publishable') is not False


def evidence_index(manifest):
    records = {}
    for item in manifest.get('rows', []):
        key = row_key(item['bandId'], item['fiscalYear'], item['kind'], item['rowIndex'])
        if key in records:
            raise ValueError('Duplicate evidence key: ' + key)
        records[key] = item
    return records


def valid_evidence(evidence, row, summary, root):
    errors = []
    if evidence.get('sourceLabel') != (row.get('label') or row.get('sourceLabel')):
        errors.append('Evidence label does not match input')
    if dollars(evidence.get('amount')) != dollars(row.get('amount')):
        errors.append('Evidence amount does not match input')
    if evidence.get('originalCategory') != row.get('category'):
        errors.append('Evidence category lease does not match input')
    if evidence.get('sourceUrl') != summary.get('sourceUrl'):
        errors.append('Evidence source URL does not match input')
    if not evidence.get('explanation') or not evidence.get('excerpt'):
        errors.append('Missing explanation or PDF excerpt')
    if not isinstance(evidence.get('pdfPage'), int) or evidence['pdfPage'] < 1:
        errors.append('Missing PDF page')
    if not evidence.get('reviewer') or evidence.get('verificationMethod') != 'independent_pdf_review':
        errors.append('Not an independent PDF review')
    pdf = root / evidence.get('pdfPath', '')
    if not pdf.is_file() or hashlib.sha256(pdf.read_bytes()).hexdigest() != evidence.get('pdfSha256'):
        errors.append('Evidence PDF missing or hash mismatch')
    if evidence.get('status') in {'verified_correct', 'verified_misclassification'}:
        if not CHECKS.issubset(evidence.get('checks', {})) or any(evidence['checks'].get(k) is not True for k in CHECKS):
            errors.append('Verification checks incomplete')
        if not evidence.get('proposedCategory'):
            errors.append('Verified decision needs a category')
        changed = evidence.get('proposedCategory') != row.get('category')
        if changed != (evidence.get('status') == 'verified_misclassification'):
            errors.append('Verification status inconsistent with category')
    elif evidence.get('status') not in {'ambiguous', 'extraction_issue'}:
        errors.append('Unknown evidence status')
    return errors


def row_issues(row, summary, year, kind, seen):
    issues = []
    label = row.get('label') or row.get('sourceLabel') or ''
    ref = row.get('sourceReference') or {}
    expected = 'revenue' if kind == 'revenue' else 'expenses'
    if not label or dollars(row.get('amount')) is None:
        issues.append('Missing label or unreadable amount')
    if summary.get('fiscalYear') and summary['fiscalYear'] != year:
        issues.append('Summary fiscal year differs from Nation-year key')
    if ref.get('section') and ref['section'] != expected:
        issues.append('Wrong source statement section')
    if ref.get('fiscalYear') and ref['fiscalYear'] != year:
        issues.append('Wrong source fiscal year')
    if ref.get('selectedYear') and str(ref['selectedYear']) != year[-4:]:
        issues.append('Selected source year differs from filing year')
    if ref.get('yearValidated') is False or re.search('budget|prior|previous', str(ref.get('selectedColumn', '')), re.I):
        issues.append('Wrong or unvalidated actual column')
    signature = (label.casefold(), str(row.get('amount')), json.dumps(ref, sort_keys=True))
    if signature in seen:
        issues.append('Possible duplicate source row; inspect consolidation and schedules')
    seen.add(signature)
    if re.search(r'^(?:total\s+)?revenues?\b.*continued|^total (?:revenue|expenses?|expenditures?)\b', label, re.I):
        issues.append('Possible subtotal included as an activity row')
    table = str(ref.get('table', ''))
    if re.search(r'financial position|cash flow|tangible capital assets', table, re.I):
        issues.append('Source table is not an operations statement or program schedule')
    return issues


def reconciliation(summary, kind):
    title = 'Revenue' if kind == 'revenue' else 'Expense'
    rows = summary.get('source' + title + 'Rows') or []
    breakdown = summary.get(kind + 'Breakdown') or []
    reported = dollars(summary.get('totalRevenue' if kind == 'revenue' else 'totalExpenses'))
    source_total, category_total = total(rows), total(breakdown)
    differences = {}
    if reported is None:
        differences['reportedTotalMissing'] = True
    if not rows:
        differences['sourceRowsMissing'] = True
    if not breakdown:
        differences['categoryBreakdownMissing'] = True
    for name, value in [('source', source_total), ('category', category_total)]:
        delta = value - reported if value is not None and reported is not None else None
        if delta is None or delta != 0:
            differences[name + 'Difference'] = number(delta)
    by_source, by_category = defaultdict(Decimal), defaultdict(Decimal)
    for target, values in [(by_source, rows), (by_category, breakdown)]:
        for row in values:
            if dollars(row.get('amount')) is not None:
                target[row.get('category')] += dollars(row['amount'])
    category_delta = {str(k): number(by_source[k] - by_category[k]) for k in set(by_source) | set(by_category)
                      if by_source[k] != by_category[k]}
    if category_delta:
        differences['sourceCategoryDifferences'] = category_delta
    return dict(reportedTotal=number(reported), sourceTotal=number(source_total),
                categoryTotal=number(category_total), differences=differences)


def audit_dataset(data, inventory, manifest=None, evidence_root=Path('.')):
    evidence = evidence_index(manifest or {})
    identities = {str(b['id']): b for b in inventory['bands']}
    report = dict(schemaVersion=1, scope='Published SK/AB/MB Community Capital breakdowns',
                  completeIndependentPdfVerification=False, automatedChecksAreNotPdfVerification=True,
                  rows=[], summaries=[], excludedSummaries=[], unusedEvidence=[], evidenceErrors=[])
    used = set()
    for bid, band in sorted(data['bands'].items()):
        identity = identities.get(str(bid), {})
        province = identity.get('province')
        for year, summary in sorted(band.get('years', {}).items()):
            base = dict(bandId=str(bid), nation=band['name'], province=province, fiscalYear=year,
                        sourceUrl=summary.get('sourceUrl'))
            if province not in PROVINCES or not published(summary):
                report['excludedSummaries'].append({**base, 'reason': 'unresolved_province' if province not in PROVINCES else 'not_published'})
                continue
            previous = [y for y in band['years'] if y < year and published(band['years'][y])]
            movement = year_over_year_warnings(summary, band['years'][max(previous)]) if previous else []
            rec = {kind: reconciliation(summary, kind) for kind in ('revenue', 'expense')}
            rev, exp, surplus = [dollars(summary.get(k)) for k in ('totalRevenue', 'totalExpenses', 'annualSurplusDeficit')]
            adj = total(summary.get('surplusAdjustments') or [])
            surplus_delta = surplus - (rev - exp + adj) if all(v is not None for v in (rev, exp, surplus, adj)) else None
            report['summaries'].append({**base, 'reconciliation': rec,
                'surplusDifference': number(surplus_delta), 'surplusMissing': surplus is None,
                'separatelyReportedAdjustments': number(adj), 'movementWarnings': movement,
                'previouslyReviewed': is_verified_summary(summary)})
            for kind, title in [('revenue', 'Revenue'), ('expense', 'Expense')]:
                rows = summary.get('source' + title + 'Rows') or []
                seen = set()
                for index, row in enumerate(rows):
                    key = row_key(bid, year, kind, index)
                    proposal = classify(row.get('label') or row.get('sourceLabel'), kind,
                                        reference=row.get('sourceReference'), row=row)
                    issues = row_issues(row, summary, year, kind, seen)
                    url_band = re.search(r'BAND_NUMBER_FF=(\d+)', str(row.get('sourceDocument') or summary.get('sourceUrl') or ''), re.I)
                    if url_band and url_band.group(1) != str(bid):
                        issues.append('Source URL belongs to another Nation')
                    ref = row.get('sourceReference') or {}
                    notes = []
                    if not ref:
                        notes.append('Source page/column metadata missing')
                    if not summary.get('sourceUrl'):
                        notes.append('Original PDF URL missing')
                    if proposal['reviewRequired']:
                        notes.append(proposal['reason'])
                    if dollars(row.get('amount')) is not None and dollars(row['amount']) < 0:
                        notes.append('Negative amount: inspect recovery, deferral, loss or elimination context')
                    item = {**base, 'id': key, 'kind': kind, 'rowIndex': index,
                        'sourceLabel': row.get('label') or row.get('sourceLabel'),
                        'originalCategory': row.get('category'), 'amount': row.get('amount'),
                        'pdfPage': ref.get('pdfPage'), 'sourceReference': ref,
                        'proposedCategory': proposal['category'] if proposal['category'] != row.get('category') else None,
                        'automatedProposal': proposal, 'status': 'extraction_issue' if issues else 'ambiguous',
                        'verificationConfidence': 'unverified', 'evidenceLevel': 'automated_checks_only',
                        'manualReviewRequired': True, 'previouslyReviewed': is_verified_summary(summary) or reviewed_row(row),
                        'issues': issues, 'reviewNotes': notes,
                        'explanation': '; '.join(issues + notes) or 'Label rule agrees; original PDF has not been independently reviewed'}
                    ev = evidence.get(key)
                    if ev:
                        used.add(key)
                        errors = valid_evidence(ev, row, summary, evidence_root)
                        if errors:
                            report['evidenceErrors'].append(dict(id=key, errors=errors))
                        else:
                            item.update(status=ev['status'], proposedCategory=ev.get('proposedCategory'),
                                pdfPage=ev['pdfPage'], explanation=ev['explanation'],
                                verificationConfidence=ev.get('confidence', 'high'),
                                evidenceLevel='independent_pdf_review', evidence=ev,
                                manualReviewRequired=ev['status'] in {'ambiguous', 'extraction_issue'})
                            # Objective structural contradictions cannot be bypassed by a review manifest.
                            if issues and ev['status'] in {'verified_correct', 'verified_misclassification'}:
                                item.update(status='extraction_issue', manualReviewRequired=True,
                                            explanation=ev['explanation'] + '; ' + '; '.join(issues))
                    report['rows'].append(item)
                if not rows:
                    # A category total with no activity rows remains an explicit coverage gap.
                    for index, row in enumerate(summary.get(kind + 'Breakdown') or []):
                        report['rows'].append({**base, 'id': f'{bid}:{year}:{kind}:missing:{index}',
                            'kind': kind, 'rowIndex': None, 'sourceLabel': None, 'originalCategory': row.get('category'),
                            'proposedCategory': None, 'amount': row.get('amount'), 'pdfPage': None,
                            'status': 'extraction_issue', 'verificationConfidence': 'unverified',
                            'evidenceLevel': 'category_total_without_source_rows', 'manualReviewRequired': True,
                            'explanation': 'Published category has no underlying source activity rows',
                            'issues': ['Missing source rows'], 'reviewNotes': []})
    report['unusedEvidence'] = sorted(set(evidence) - used)
    report['counts'] = summarize(report)
    return report


def summarize(report):
    rows = report['rows']
    failures = [s for s in report['summaries'] if any(r['differences'] for r in s['reconciliation'].values())
                or s['surplusDifference'] not in (None, 0)]
    unclassified = [r for r in rows if r['kind'] == 'revenue' and r['originalCategory'] == 'Unclassified']
    counts = dict(nationYears=len(report['summaries']),
        revenueRows=sum(r['kind'] == 'revenue' and r['rowIndex'] is not None for r in rows),
        expenseRows=sum(r['kind'] == 'expense' and r['rowIndex'] is not None for r in rows),
        missingSourceCategoryRows=sum(r['rowIndex'] is None for r in rows),
        statuses=dict(Counter(r['status'] for r in rows)),
        independentlyPdfReviewedRows=sum(r['evidenceLevel'] == 'independent_pdf_review' for r in rows),
        unclassifiedRevenueRows=len(unclassified), unclassifiedRevenueNet=number(total(unclassified)),
        unclassifiedRevenueAbsolute=sum(abs(r['amount']) for r in unclassified),
        unresolvedOperationsFallbackRows=sum(r.get('automatedProposal', {}).get('rule') == 'unresolved_operations_fallback' for r in rows),
        classificationProposalDifferences=sum(r.get('proposedCategory') is not None and r.get('proposedCategory') != r.get('originalCategory') for r in rows),
        reconciliationFailures=len(failures), missingSurplus=sum(s['surplusMissing'] for s in report['summaries']),
        provinces={})
    for province in sorted(PROVINCES):
        subset = [r for r in rows if r['province'] == province]
        counts['provinces'][province] = dict(nationYears=sum(s['province'] == province for s in report['summaries']),
            revenueRows=sum(r['kind'] == 'revenue' and r['rowIndex'] is not None for r in subset),
            expenseRows=sum(r['kind'] == 'expense' and r['rowIndex'] is not None for r in subset),
            statuses=dict(Counter(r['status'] for r in subset)))
    return counts


def apply_verified(data, report):
    """All-or-nothing copy, strict row leases, category deltas only, full undo trail."""
    if report['evidenceErrors'] or report['unusedEvidence']:
        raise ValueError('Resolve evidence errors/unused evidence before applying')
    result = copy.deepcopy(data)
    trail, snapshots = [], {}
    for item in report['rows']:
        if item['status'] != 'verified_misclassification':
            continue
        if item['evidenceLevel'] != 'independent_pdf_review' or item['manualReviewRequired'] or item.get('issues'):
            raise ValueError('Unsafe correction: ' + item['id'])
        bid, year, kind = item['bandId'], item['fiscalYear'], item['kind']
        s = result['bands'][bid]['years'][year]
        key = 'sourceRevenueRows' if kind == 'revenue' else 'sourceExpenseRows'
        row = s[key][item['rowIndex']]
        if (row.get('category') != item['originalCategory'] or row.get('amount') != item['amount'] or
            (row.get('label') or row.get('sourceLabel')) != item['sourceLabel']):
            raise ValueError('Stale row lease: ' + item['id'])
        if reviewed_row(row) or is_verified_summary(s):
            # Explicit supersession must name the reviewed decision; never use automation.
            if item['evidence'].get('supersedesReviewedDecision') is not True:
                raise ValueError('Reviewed decision requires explicit source-backed supersession: ' + item['id'])
        summary_key = f'{bid}:{year}'
        snapshots.setdefault(summary_key, copy.deepcopy(data['bands'][bid]['years'][year]))
        breakdown_key = kind + 'Breakdown'
        old = next((r for r in s[breakdown_key] if r['category'] == row['category']), None)
        if old is None:
            raise ValueError('Old category missing from breakdown: ' + item['id'])
        before = copy.deepcopy(row)
        amount = dollars(row['amount'])
        old['amount'] = number(dollars(old['amount']) - amount)
        target = next((r for r in s[breakdown_key] if r['category'] == item['proposedCategory']), None)
        if target is None:
            target = dict(category=item['proposedCategory'], amount=0)
            s[breakdown_key].append(target)
        target['amount'] = number(dollars(target['amount']) + amount)
        row['category'] = item['proposedCategory']
        if 'normalizedCategory' in row:
            row['normalizedCategory'] = item['proposedCategory']
        if 'subcategory' in row:
            try:
                from tools.capital_parser import revenue_subcategory
            except ModuleNotFoundError:
                from capital_parser import revenue_subcategory
            row['subcategory'] = revenue_subcategory(item['evidence'].get('fullSourceLabel') or item['sourceLabel'], item['proposedCategory'])
        row['classificationReview'] = dict(status='verified_misclassification', evidenceId=item['id'],
            method='independent_pdf_review', pdfSha256=item['evidence']['pdfSha256'],
            pdfPage=item['pdfPage'], originalCategory=item['originalCategory'],
            explanation=item['explanation'], reviewRequired=False)
        for detail_key in ('expenseDetails', 'expenseDetailSchedules') if kind == 'expense' else ():
            for detail in s.get(detail_key) or []:
                if detail.get('sourceLabel') == item['sourceLabel'] and detail.get('category') == item['originalCategory']:
                    detail['category'] = item['proposedCategory']
        trail.append(dict(id=item['id'], before=before, after=copy.deepcopy(row), evidence=item['evidence']))
    for summary_key, before in snapshots.items():
        bid, year = summary_key.split(':')
        after = result['bands'][bid]['years'][year]
        for key in ('revenueBreakdown', 'expenseBreakdown'):
            if total(before.get(key) or []) != total(after.get(key) or []):
                raise ValueError('Category sum changed')
        # Only the activity categories, review metadata and matching detail categories may differ.
        allowed = {'sourceRevenueRows', 'sourceExpenseRows', 'revenueBreakdown', 'expenseBreakdown', 'expenseDetails', 'expenseDetailSchedules'}
        if {k: v for k, v in before.items() if k not in allowed} != {k: v for k, v in after.items() if k not in allowed}:
            raise ValueError('Financial/source metadata changed')
    return result, dict(changes=trail, beforeSummaries=snapshots)


def markdown(report):
    c = report['counts']; st = c['statuses']
    remaining = report.get('remainingUnclassifiedAfterApply', c)
    lines = ['# Community Capital classification audit', '',
        'This is a complete automated inventory of published SK/AB/MB breakdowns, with a limited, explicitly recorded independent PDF review. It is **not** 100% source verification.', '',
        f"- Published Nation-years checked: {c['nationYears']}",
        f"- Revenue activity rows: {c['revenueRows']}; expense activity rows: {c['expenseRows']}",
        f"- Published category rows without underlying source rows: {c['missingSourceCategoryRows']}",
        f"- Independently PDF-reviewed rows: {c['independentlyPdfReviewedRows']}",
        f"- Verified correct: {st.get('verified_correct', 0)}; verified corrections proposed: {st.get('verified_misclassification', 0)}",
        f"- Ambiguous / awaiting source review: {st.get('ambiguous', 0)}; extraction issues: {st.get('extraction_issue', 0)}",
        f"- Nation-years with exact reconciliation differences: {c['reconciliationFailures']}; missing surplus: {c['missingSurplus']}",
        f"- Remaining published Unclassified revenue: {remaining['unclassifiedRevenueRows']} rows, ${remaining['unclassifiedRevenueNet']:,} net; ${remaining['unclassifiedRevenueAbsolute']:,} absolute gross across all years. Negative deferrals must not be interpreted as positive income.", '',
        f"Verified corrections applied to this checkout: {report.get('appliedCorrections', 0)}. Original input classifications remain in the report for review; the remaining Unclassified figures above reflect the applied result when applicable.", '',
        'Exact checks use decimal dollars with zero tolerance; a one-dollar source rounding difference is reported for review, not declared a proven extraction error. The existing parser tolerance is reported separately in the implementation notes. Missing evidence stays unresolved even if labels and totals agree.', '',
        '| Province | Nation-years | Revenue rows | Expense rows | Verified correct | Verified corrections | Awaiting review | Extraction issues |',
        '|---|---:|---:|---:|---:|---:|---:|---:|']
    for p, v in c['provinces'].items():
        s = v['statuses']
        lines.append(f"| {p} | {v['nationYears']} | {v['revenueRows']} | {v['expenseRows']} | {s.get('verified_correct',0)} | {s.get('verified_misclassification',0)} | {s.get('ambiguous',0)} | {s.get('extraction_issue',0)} |")
    lines += ['', '## Verified category corrections', '', '| Nation / band | Province / year | Source label | Original → proposed | Amount | PDF page | Explanation |', '|---|---|---|---|---:|---:|---|']
    for r in sorted((r for r in report['rows'] if r['status'] == 'verified_misclassification'), key=lambda r: -abs(r['amount'])):
        label = str(r['sourceLabel']).replace('|', '\\|')
        lines.append(f"| {r['nation']} / {r['bandId']} | {r['province']} / {r['fiscalYear']} | {label} | {r['originalCategory']} → {r['proposedCategory']} | ${r['amount']:,} | [{r['pdfPage']}]({r['sourceUrl']}) | {r['explanation']} |")
    lines += ['', '## Reconciliation exceptions', '', '| Nation / band | Year | Revenue differences | Expense differences | Surplus difference |', '|---|---|---|---|---:|']
    for s in report['summaries']:
        r = s['reconciliation']
        if any(v['differences'] for v in r.values()) or s['surplusDifference'] not in (0, None):
            lines.append(f"| {s['nation']} / {s['bandId']} | {s['fiscalYear']} | {json.dumps(r['revenue']['differences'])} | {json.dumps(r['expense']['differences'])} | {s['surplusDifference']} |")
    lines += ['', '## Evidence and remaining work', '',
        'The JSON report contains every activity row and every source-coverage gap, its original category and amount, proposed category (if any), URL/page, confidence, explanation, evidence level, issues and manual-review requirement. All unreviewed rows remain Ambiguous, including plausible labels; this count is a source-verification backlog, not a count of proven mistakes.', '',
        'Category corrections do not change totals, amounts, labels, URLs, publication status, deferred revenue, surplus adjustments or asset balances. The undo file stores complete prior affected summaries and individual before/after rows. Schedules are corroborating evidence, never additional revenue or expense activity rows.', '',
        'Prior manual reviews are preserved and distinguished from PDF review performed for this audit. Ambiguous trust distributions, intermediaries, combined programs, deferred contribution movements, financing, asset sales and internal transfers require statements, schedules and notes before classification. No residual is assigned to government, Other revenue or Operations.', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', default='capital-data.json')
    parser.add_argument('--inventory', default='data.json')
    parser.add_argument('--evidence')
    parser.add_argument('--evidence-root', default='.')
    parser.add_argument('--report', default='community-capital-classification-audit.json')
    parser.add_argument('--markdown', default='community-capital-classification-audit.md')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--undo', default='community-capital-classification-undo.json')
    args = parser.parse_args()
    path = Path(args.data)
    raw = path.read_bytes(); data = json.loads(raw)
    manifest = json.loads(Path(args.evidence).read_text()) if args.evidence else {}
    report = audit_dataset(data, json.loads(Path(args.inventory).read_text()), manifest, Path(args.evidence_root))
    report['inputSha256'] = hashlib.sha256(raw).hexdigest()
    if args.apply:
        changed, undo = apply_verified(data, report)
        report['appliedCorrections'] = len(undo['changes'])
        undo['inputSha256'] = report['inputSha256']
        compact = raw.count(b'\n') <= 1
        encoded = (json.dumps(changed, ensure_ascii=False, **({'separators': (',', ':')} if compact else {'indent': 2})) + '\n').encode('utf-8')
        undo['outputSha256'] = hashlib.sha256(encoded).hexdigest() if undo['changes'] else undo['inputSha256']
        # Undo must exist before any dataset write. Never overwrite a previous trail.
        with Path(args.undo).open('x', encoding='utf-8') as stream:
            json.dump(undo, stream, ensure_ascii=False, indent=2); stream.write('\n')
        if undo['changes']:
            temporary = path.with_suffix(path.suffix + '.classification.tmp')
            temporary.write_bytes(encoded)
            temporary.replace(path)
        report['outputSha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        post = audit_dataset(changed, json.loads(Path(args.inventory).read_text()))
        report['remainingUnclassifiedAfterApply'] = {k:v for k,v in post['counts'].items() if k.startswith('unclassified')}
    else:
        report['appliedCorrections'] = 0
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    Path(args.markdown).write_text(markdown(report))
    print(json.dumps(report['counts'], indent=2))


if __name__ == '__main__':
    main()
