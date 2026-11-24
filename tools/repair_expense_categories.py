"""Audit all stored years; repair explicit stale Operations mappings only.

Unknown program names stay in the report. Source-verified decisions always win.
No financial amounts, publication flags or original labels are rewritten.
"""
import argparse
import copy
import json
from decimal import Decimal
from pathlib import Path
from tools.capital_classification import classify, reviewed_row
from tools.capital_parser import is_verified_summary


def audit(data, evidence):
    result = copy.deepcopy(data)
    report = dict(nationYears=0, publishedYears=0, expenseRows=0, corrections=[], reviewQueue=[], missingSourceRows=[])
    for bid, band in result['bands'].items():
        for year, summary in band['years'].items():
            report['nationYears'] += 1
            published = summary.get('parseStatus') == 'parsed' and summary.get('publishable') is not False
            report['publishedYears'] += int(published)
            rows = summary.get('sourceExpenseRows') or []
            if published and not rows:
                report['missingSourceRows'].append(dict(bandId=bid, year=year))
            changed = False
            for index, row in enumerate(rows):
                report['expenseRows'] += 1
                label = row.get('label') or row.get('sourceLabel') or ''
                key = f'{bid}:{year}:{index}'
                ev = evidence.get(key)
                proposal = classify(label, 'expense', reference=row.get('sourceReference'), row=row)
                record = dict(bandId=bid, band=band.get('name'), year=year, index=index,
                              label=label, amount=row['amount'], originalCategory=row['category'], published=published,
                              sourceUrl=summary.get('sourceUrl'), sourceReference=row.get('sourceReference'))
                if reviewed_row(row) or is_verified_summary(summary):
                    continue
                if ev:
                    assert ev['label'] == label and ev['amount'] == row['amount'], key
                    proposal = dict(category=ev['category'], reviewRequired=False, rule='source_verified_label')
                # Only repair the known catch-all bug; never undo other stored categories.
                if row['category'] == 'Operations' and proposal['category'] != 'Operations' and not proposal['reviewRequired']:
                    category = proposal['category']
                    breakdown = summary.get('expenseBreakdown') or []
                    old = next((r for r in breakdown if r['category'] == row['category']), None)
                    if old is None:
                        report['reviewQueue'].append({**record, 'reason':'Missing source category in aggregate'})
                        continue
                    old['amount'] -= row['amount']
                    target = next((r for r in breakdown if r['category'] == category), None)
                    if target is None:
                        target = dict(category=category, amount=0)
                        breakdown.append(target)
                    target['amount'] += row['amount']
                    row['category'] = category
                    if 'normalizedCategory' in row: row['normalizedCategory'] = category
                    if ev:
                        row['fullSourceLabel'] = ev['fullSourceLabel']
                    row['classificationReview'] = dict(status='verified_misclassification' if ev else 'automated_proposal',
                        originalCategory='Operations', proposedCategory=category, rule=proposal['rule'],
                        ruleVersion='expense_repair_v1', reviewRequired=False,
                        evidenceLevel='independent_pdf_review' if ev else 'explicit_source_label', **({'evidence':ev} if ev else {}))
                    for field in ('expenseDetails', 'expenseDetailSchedules'):
                        for detail in summary.get(field) or []:
                            if detail.get('sourceLabel') == label and detail.get('category') == 'Operations': detail['category'] = category
                    report['corrections'].append({**record, 'category':category, 'evidenceLevel':row['classificationReview']['evidenceLevel']})
                    changed = True
                elif row['category'] == 'Operations' and proposal['reviewRequired']:
                    report['reviewQueue'].append({**record, 'reason':proposal['rule']})
            if changed:
                summary['expenseBreakdown'] = sorted((r for r in summary['expenseBreakdown'] if r['amount'] != 0),key=lambda r:-r['amount'])
            original = data['bands'][bid]['years'][year]
            assert sum(Decimal(str(r['amount'])) for r in summary.get('expenseBreakdown') or []) == sum(Decimal(str(r['amount'])) for r in original.get('expenseBreakdown') or [])
            allowed = {'sourceExpenseRows','expenseBreakdown','expenseDetails','expenseDetailSchedules'}
            assert {k:v for k,v in summary.items() if k not in allowed} == {k:v for k,v in original.items() if k not in allowed}
    return result, report


def main():
    p=argparse.ArgumentParser();p.add_argument('--apply',action='store_true');p.add_argument('--data',default='capital-data.json');p.add_argument('--evidence',default='research/expense-category-repair/2026-11-24/evidence.json');p.add_argument('--report',default='research/expense-category-repair/2026-11-24/audit.json');args=p.parse_args()
    data=json.loads(Path(args.data).read_text()); fixed,report=audit(data,json.loads(Path(args.evidence).read_text()))
    Path(args.report).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    if args.apply:Path(args.data).write_text(json.dumps(fixed,ensure_ascii=False,separators=(',', ':'))+'\n')
    print(json.dumps({k:len(v) if isinstance(v,list) else v for k,v in report.items()}))
if __name__ == '__main__':main()
