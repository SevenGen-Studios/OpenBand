"""Parse conservative Community Capital summaries from audited statements.

The parser targets a small set of high-value public-record fields and refuses
to publish a summary when the operations statement cannot be reconciled.
"""

import argparse
import base64
import io
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

try:
    import pdfplumber
except ImportError:  # pragma: no cover
    pdfplumber = None


_openai_blocked_reason = None


MONEY_RE = re.compile(r"\(?\$?\s*-?\d[\d,]*(?:\.\d+)?\)?")
YEAR_RE = re.compile(r"\b20\d{2}\b")
OPERATIONS_RE = re.compile(
    r"statement of (?:consolidated )?(?:operations|revenues? and expenses|"
    r"financial activities|activities)",
    re.I,
)
POSITION_RE = re.compile(r"statement of financial position", re.I)
NET_ASSET_RE = re.compile(
    r"statement of (?:changes? in )?net (?:financial assets|financial debt|debt)",
    re.I,
)
TOTAL_REVENUE_RE = re.compile(r"^(?:total\s+)?revenues?$", re.I)
REVENUE_SECTION_RE = re.compile(
    r"^revenues?(?:\s+\(.*\))?$",
    re.I,
)
TOTAL_EXPENSE_RE = re.compile(
    r"^(?:total\s+)?(?:(?:program|operating)\s+)?"
    r"(?:expenses?|expenditures?)(?:\s+\(.*\))?$",
    re.I,
)
EXPENSE_SECTION_RE = re.compile(
    r"^(?:program\s+)?(?:expenses?|expenditures?)(?:\s+\(.*\))?$",
    re.I,
)
FINAL_SURPLUS_RE = re.compile(
    r"^(?:(?:annual|current)\s+)?"
    r"(?:surplus|deficit)(?:\s+\(deficit\))?$",
    re.I,
)
BEFORE_OTHER_RE = re.compile(
    r"^.*\b(?:surplus|deficit)\b.*\bbefore\s+(?:other|trust settlement)",
    re.I,
)
EXPENSE_SECTION_END_RE = re.compile(
    r"^(?:total\s+(?:(?:program|operating)\s+)?(?:expenses?|expenditures?)"
    r"|.*\b(?:surplus|deficit)\b.*(?:before\s+(?:other|trust settlement)|$))",
    re.I,
)
CAPITAL_PURCHASE_RE = re.compile(
    r"^(?:purchases?|acquisition|additions?)\s+(?:of\s+)?tangible\s+capital\s+assets?",
    re.I,
)
SKIP_LINE_RE = re.compile(
    r"^(schedules?|budget|actual|note|the accompanying|for the year|as at|"
    r"continued|page \d+)",
    re.I,
)
REMUNERATION_DOCUMENT_RE = re.compile(
    r"schedule of remuneration and expenses|chief and council",
    re.I,
)
SEGMENT_SCHEDULE_RE = re.compile(
    r"(?:schedule|statement).{0,45}(?:revenues?|income).{0,20}(?:expenses?|expenditures?)",
    re.I,
)
DETAIL_SECTION_END_RE = re.compile(
    r"^(?:surplus|deficit|excess|shortfall|other income|other revenue|"
    r"transfers? between programs?|net revenue|net expenses?)\b",
    re.I,
)


def now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def clean_text(value):
    text = str(value or "")
    replacements = {
        "\u00a0": " ",
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\ufb01": "fi",
        "\ufb02": "fl",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
    }
    for source, replacement in replacements.items():
        text = text.replace(source, replacement)
    return " ".join(text.split()).strip()


def parse_money(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = clean_text(value)
    if not text or text in {"-", "--", "N/A", "n/a"}:
        return None
    negative = text.startswith("(") and text.endswith(")")
    cleaned = re.sub(r"[^0-9.\-]", "", text)
    if cleaned in {"", "-", "."}:
        return None
    try:
        amount = float(cleaned)
    except ValueError:
        return None
    return -amount if negative and amount > 0 else amount


def rounded(value):
    if value is None:
        return None
    return int(value) if float(value).is_integer() else round(float(value), 2)


def line_parts(line):
    line = re.sub(r"\((?:note|schedule)[^)]*\)", "", line, flags=re.I)
    matches = list(MONEY_RE.finditer(line))
    if not matches:
        return clean_text(line), []
    if len(matches) > 1:
        first_value = parse_money(matches[0].group(0))
        between = line[matches[0].end() : matches[1].start()]
        if (
            first_value is not None
            and 1900 <= first_value <= 2099
            and re.search(r"[A-Za-z]", between)
        ):
            matches.pop(0)
    while len(matches) > 1:
        raw = matches[0].group(0).strip()
        amount = parse_money(raw)
        later = [parse_money(match.group(0)) for match in matches[1:]]
        is_schedule_index = (
            amount is not None
            and (
                0 <= amount <= 99
                or (
                    len(matches) >= 4
                    and 0 <= amount <= 9999
                )
            )
            and "," not in raw
            and "." not in raw
            and "$" not in raw
            and "(" not in raw
            and any(value is not None and abs(value) >= 100 for value in later)
        )
        if not is_schedule_index:
            break
        matches.pop(0)
    label = clean_text(line[: matches[0].start()]).strip(" :-$")
    values = [parse_money(match.group(0)) for match in matches]
    return label, [value for value in values if value is not None]


def actual_value(values, page_text, line=""):
    if not values:
        return None
    header = "\n".join(page_text.splitlines()[:12]).lower()
    if "budget" in header:
        if len(values) >= 3:
            return values[1]
        if len(values) == 2 and re.search(
            r"\(?-?\d[\d,]*(?:\.\d+)?\)?\s+"
            r"\(?-?\d[\d,]*(?:\.\d+)?\)?\s+-\s*$",
            line,
        ):
            return values[1]
        if len(values) == 2 and re.search(
            r"\d[\d,]*(?:\.\d+)?\s+-\s+\(?-?\d", line
        ):
            if re.search(
                r"(?:^|\s)\d{1,2}\s+-\s+\(?-?\d[\d,]*(?:\.\d+)?"
                r"\s+\(?-?\d[\d,]*(?:\.\d+)?",
                line,
            ):
                return values[0]
            return 0
        if len(values) == 1 and re.search(
            r"\s-\s+-\s+\(?-?\d", line
        ):
            return 0
        if len(values) == 1 and re.search(
            r"\(?-?\d[\d,]*(?:\.\d+)?\)?\s+-\s+-\s*$",
            line,
        ):
            return 0
    elif len(values) == 1 and re.search(r"\s-\s+\(?-?\d", line):
        return 0
    return values[0]


def normalize_category(label):
    text = clean_text(label)
    text = re.sub(r"\s+\(note.*$", "", text, flags=re.I)
    text = re.sub(r"\s+\(schedule.*$", "", text, flags=re.I)
    text = re.sub(r"\s+\d+$", "", text)
    return text.strip(" :-")


def broad_revenue_category(label):
    low = label.lower()
    if re.search(r"indigenous services|government|cmhc|canada|province|tribal council|health.*authority|child.*family", low):
        return "Government transfers"
    if re.search(r"rent|lease|sales|fees?|royalt|investment|interest|business entit|farming|store|bingo|fundraising", low):
        return "Own-source revenue"
    if "trust" in low:
        return "Trust distributions"
    return "Other revenue"


def broad_expense_category(label):
    low = label.lower()
    if "land claims" in low:
        return "Operations"
    mappings = [
        (r"housing|\bcmhc\b", "Housing"),
        (r"education|school|post[- ]secondary|training", "Education"),
        (r"health", "Health"),
        (
            r"infrastructure|public works|community development|capital|"
            r"facilit(?:y|ies) maintenance|operations?\s*(?:&|and)\s*maintenance",
            "Infrastructure / public works",
        ),
        (
            r"economic|land management|band development|first nation owned|"
            r"retail operations|commercial enterprises?",
            "Economic development",
        ),
        (r"social|child|family|income assistance|community based services", "Social programs"),
        (
            r"government (?:support|services)|administration|band government|"
            r"registration(?: and)? membership|membership|lands and memberships|"
            r"reserves? (?:and|&) trusts?",
            "Administration",
        ),
    ]
    for pattern, category in mappings:
        if re.search(pattern, low):
            return category
    return "Operations"


def statement_pages(page_texts, pattern):
    return [
        text
        for text in page_texts
        if pattern.search("\n".join(text.splitlines()[:8]))
    ]


def likely_operations_pages(page_texts):
    candidates = []
    for text in page_texts:
        lines = text.splitlines()
        header = "\n".join(lines[:12])
        low = text.lower()
        score = 0
        if re.search(r"statement of .{0,30}(?:operations|activities)", header, re.I):
            score += 4
        if re.search(r"^revenues?(?:\s+\(.*\))?$", text, re.I | re.M):
            score += 2
        if re.search(r"^(?:program\s+)?(?:expenses?|expenditures?)", text, re.I | re.M):
            score += 2
        if re.search(r"surplus|deficit", low):
            score += 1
        if score >= 5:
            candidates.append(text)
    return candidates


def inherit_budget_context(page_texts):
    has_budget_layout = any(
        "budget" in "\n".join(text.splitlines()[:12]).lower()
        for text in page_texts
    )
    if not has_budget_layout:
        return page_texts
    return [
        text
        if "budget" in "\n".join(text.splitlines()[:12]).lower()
        else "Budget Actual Actual\n" + text
        for text in page_texts
    ]


def parse_section_rows(
    page_texts,
    start_pattern,
    end_pattern,
    category_fn,
    reject_pattern=None,
):
    rows = []
    active = False
    for page_text in page_texts:
        for raw_line in page_text.splitlines():
            line = clean_text(raw_line)
            if start_pattern.search(line):
                active = True
                continue
            if active and end_pattern.search(line):
                return rows
            if not active:
                continue
            label, values = line_parts(line)
            if not label or not values or SKIP_LINE_RE.search(label):
                continue
            if re.fullmatch(r"page\)?", label, re.I):
                continue
            if reject_pattern and reject_pattern.search(label):
                continue
            if TOTAL_REVENUE_RE.match(label) or TOTAL_EXPENSE_RE.match(label):
                continue
            if len(values) == 1 and re.search(r"\s-\s+-\s+\(", line):
                amount = 0
            else:
                amount = actual_value(values, page_text, line)
            if amount is None:
                continue
            rows.append(
                {
                    "category": category_fn(label),
                    "sourceLabel": normalize_category(label),
                    "amount": rounded(amount),
                }
            )
    return rows


def sum_rows(rows):
    return sum(parse_money(row.get("amount")) or 0 for row in rows)


def find_named_amount(page_texts, pattern, last=False):
    found = []
    for page_text in page_texts:
        for raw_line in page_text.splitlines():
            label, values = line_parts(clean_text(raw_line))
            if pattern.search(label):
                value = actual_value(values, page_text, clean_text(raw_line))
                if value is not None:
                    found.append(value)
    if not found:
        return None
    return found[-1] if last else found[0]


def parse_surplus_adjustments(page_texts):
    rows = []
    active = False
    for page_text in page_texts:
        for raw_line in page_text.splitlines():
            line = clean_text(raw_line)
            label, values = line_parts(line)
            if BEFORE_OTHER_RE.search(label):
                active = True
                continue
            if not active:
                continue
            if FINAL_SURPLUS_RE.match(label):
                return rows
            if not label or not values or SKIP_LINE_RE.search(label):
                continue
            if re.fullmatch(r"page\)?", label, re.I):
                continue
            if re.search(r"accumulated surplus|opening|beginning of year|end of year", label, re.I):
                continue
            amount = actual_value(values, page_text, line)
            if amount is None or amount == 0:
                continue
            raw_values = MONEY_RE.findall(line)
            if (
                abs(amount) < 100
                and len(raw_values) == 1
                and "," not in raw_values[0]
                and "$" not in raw_values[0]
            ):
                continue
            rows.append(
                {
                    "label": normalize_category(label),
                    "amount": rounded(amount),
                }
            )
    return rows


def parse_segment_schedule_expenses(page_texts):
    by_label = {}
    for page_text in page_texts:
        lines = [clean_text(line) for line in page_text.splitlines() if clean_text(line)]
        if len(lines) < 4:
            continue
        header = "\n".join(lines[:8])
        if not SEGMENT_SCHEDULE_RE.search(header):
            continue
        if re.search(r"consolidated expenses by object", header, re.I):
            continue
        schedule_index = next(
            (index for index, line in enumerate(lines[:8]) if SEGMENT_SCHEDULE_RE.search(line)),
            None,
        )
        source_label = normalize_category(
            lines[schedule_index - 1] if schedule_index and schedule_index > 0 else lines[0]
        )
        if re.search(r"first nation|nation$", source_label, re.I):
            continue
        amount = find_named_amount(
            [page_text],
            re.compile(r"^total\s+(?:program\s+)?(?:expenses?|expenditures?)$", re.I),
            last=True,
        )
        if amount is None:
            continue
        existing = by_label.get(source_label)
        if existing is None or abs(amount) > abs(existing):
            by_label[source_label] = amount
    return [
        {
            "category": broad_expense_category(label),
            "sourceLabel": label,
            "amount": rounded(amount),
        }
        for label, amount in by_label.items()
    ]


def schedule_context(lines, page_number):
    """Return source context only for a clearly labelled program expense schedule."""
    header = lines[:14]
    schedule_index = next(
        (index for index, line in enumerate(header) if SEGMENT_SCHEDULE_RE.search(line)),
        None,
    )
    if schedule_index is None:
        return None

    schedule_label = normalize_category(header[schedule_index])
    if re.search(r"consolidated expenses by object", schedule_label, re.I):
        return None

    suffix = re.search(
        r"(?:revenues?|income)\s+(?:and|&)\s+(?:expenses?|expenditures?)"
        r"\s*[-:]\s*(.+)$",
        schedule_label,
        re.I,
    )
    source_label = normalize_category(suffix.group(1)) if suffix else ""
    if not source_label and schedule_index > 0:
        source_label = normalize_category(header[schedule_index - 1])
    if (
        not source_label
        or re.search(r"first nation|financial statements?|year ended", source_label, re.I)
        or re.match(r"^(?:schedule|statement)\b", source_label, re.I)
    ):
        return None

    schedule_number = re.search(r"\bschedule\s+([A-Za-z0-9.-]+)", schedule_label, re.I)
    return {
        "sourceLabel": source_label,
        "category": broad_expense_category(source_label),
        "schedule": f"Schedule {schedule_number.group(1)}" if schedule_number else schedule_label,
        "page": page_number,
    }


def source_program_amount(source_rows, source_label):
    target = normalize_category(source_label).lower()
    for row in source_rows or []:
        label = normalize_category(row.get("label")).lower()
        if label == target:
            return parse_money(row.get("amount"))
    return None


def parse_expense_detail_schedules(page_texts, source_rows=None):
    """Extract explicit current-year expense lines from labelled schedules."""
    details = []
    schedules = []
    seen = set()

    for page_number, page_text in enumerate(page_texts, start=1):
        lines = [clean_text(line) for line in page_text.splitlines() if clean_text(line)]
        if len(lines) < 5:
            continue
        context = schedule_context(lines, page_number)
        if not context:
            continue

        expense_index = next(
            (
                index
                for index, line in enumerate(lines)
                if re.fullmatch(
                    r"(?:program\s+)?(?:expenses?|expenditures?)(?:\s+\(.*\))?",
                    line,
                    re.I,
                )
            ),
            None,
        )
        if expense_index is None:
            continue

        schedule_rows = []
        reported_total = None
        for raw_line in lines[expense_index + 1 :]:
            line = clean_text(raw_line)
            label, values = line_parts(line)
            if DETAIL_SECTION_END_RE.match(label):
                break
            if re.match(
                r"^total\s+(?:(?:program|operating)\s+)?"
                r"(?:expenses?|expenditures?)",
                label,
                re.I,
            ):
                reported_total = actual_value(values, page_text, line)
                break
            if not label and values:
                reported_total = actual_value(values, page_text, line)
                break
            if (
                not label
                or not values
                or SKIP_LINE_RE.search(label)
                or REVENUE_SECTION_RE.match(label)
                or TOTAL_REVENUE_RE.match(label)
            ):
                continue
            amount = actual_value(values, page_text, line)
            if amount in (None, 0):
                continue
            item_label = normalize_category(label)
            key = (
                context["sourceLabel"].lower(),
                item_label.lower(),
                rounded(amount),
                page_number,
            )
            if key in seen:
                continue
            seen.add(key)
            item = {
                **context,
                "label": item_label,
                "amount": rounded(amount),
            }
            schedule_rows.append(item)
            details.append(item)

        if not schedule_rows:
            continue
        extracted_total = sum_rows(schedule_rows)
        expected_total = (
            reported_total
            if reported_total is not None
            else source_program_amount(source_rows, context["sourceLabel"])
        )
        schedules.append(
            {
                **context,
                "reportedTotal": rounded(expected_total),
                "extractedTotal": rounded(extracted_total),
                "reconciles": (
                    nearly_equal(extracted_total, expected_total)
                    if expected_total is not None
                    else None
                ),
                "itemCount": len(schedule_rows),
            }
        )

    return details, schedules


def aggregate_categories(rows):
    totals = {}
    source_rows = []
    for row in rows:
        category = row["category"]
        totals[category] = totals.get(category, 0) + (parse_money(row["amount"]) or 0)
        source_rows.append(
            {
                "label": row["sourceLabel"],
                "category": category,
                "amount": row["amount"],
            }
        )
    return (
        [
            {"category": category, "amount": rounded(amount)}
            for category, amount in sorted(totals.items(), key=lambda item: -item[1])
        ],
        source_rows,
    )


def extract_debt(position_pages):
    patterns = [
        re.compile(r"^bank indebtedness$", re.I),
        re.compile(r"^short[- ]term debt$", re.I),
        re.compile(r"^current portion of long[- ]term debt", re.I),
        re.compile(r"^current portion of term loans", re.I),
        re.compile(r"^current portion of capital lease obligations", re.I),
        re.compile(r"^long[- ]term debt", re.I),
        re.compile(r"^term loans due on demand", re.I),
        re.compile(r"^capital lease obligations", re.I),
    ]
    components = []
    for page_text in position_pages:
        for raw_line in page_text.splitlines():
            label, values = line_parts(clean_text(raw_line))
            if not values or not any(pattern.search(label) for pattern in patterns):
                continue
            value = actual_value(values, page_text, clean_text(raw_line))
            if value is not None:
                components.append({"label": normalize_category(label), "amount": rounded(value)})
    total = sum(parse_money(item["amount"]) or 0 for item in components)
    return {"total": rounded(total), "components": components} if components else None


def nearly_equal(left, right, tolerance=0.01):
    if left is None or right is None:
        return False
    return abs(left - right) <= max(10.0, abs(right) * tolerance)


def validate_summary(summary):
    warnings = []
    severe = []
    revenue = parse_money(summary.get("totalRevenue"))
    expenses = parse_money(summary.get("totalExpenses"))
    surplus = parse_money(summary.get("annualSurplusDeficit"))
    revenue_rows = summary.get("revenueBreakdown") or []
    expense_rows = summary.get("expenseBreakdown") or []
    adjustment_rows = summary.get("surplusAdjustments") or []
    adjustments = sum_rows(adjustment_rows)

    if revenue is None or revenue <= 0:
        severe.append("Total revenue was not extracted")
    if expenses is None or expenses <= 0:
        severe.append("Total expenses were not extracted")
    if len(revenue_rows) < 2:
        severe.append("Revenue breakdown is incomplete")
    if len(expense_rows) < 2:
        severe.append("Expense breakdown is incomplete")
    if revenue_rows and revenue is not None and not nearly_equal(sum_rows(revenue_rows), revenue):
        severe.append("Revenue categories do not reconcile to total revenue")
    expense_sum = sum_rows(expense_rows)
    if expense_rows and expenses is not None and not nearly_equal(expense_sum, expenses):
        if expense_sum > expenses:
            severe.append("Expense categories exceed reported expenses")
        else:
            severe.append("Expense categories do not reconcile to total expenses")
    if revenue is not None and any(
        nearly_equal(parse_money(row.get("amount")), revenue, tolerance=0.001)
        for row in expense_rows
    ):
        severe.append("An expense category appears to contain total revenue")
    if surplus is None:
        warnings.append("Annual surplus or deficit was not extracted")
    elif revenue is not None and expenses is not None and not nearly_equal(
        surplus, revenue - expenses + adjustments
    ):
        severe.append("Revenue, expenses, and annual surplus do not reconcile")
    elif adjustment_rows:
        warnings.append("Annual surplus includes separately reported adjustments")
    if summary.get("capitalSpending") is None:
        warnings.append("Capital spending was not extracted")
    if summary.get("debt") is None:
        warnings.append("Debt summary was not extracted")

    if severe:
        confidence = "low"
        status = "manual_review"
    elif warnings:
        confidence = "medium"
        status = "parsed"
    else:
        confidence = "high"
        status = "parsed"
    return {
        "parseStatus": status,
        "confidence": confidence,
        "warnings": severe + warnings,
        "publishable": not severe,
    }


def parse_page_texts(page_texts, source_url=None, fiscal_year=None):
    operations = statement_pages(page_texts, OPERATIONS_RE)
    if not operations:
        operations = likely_operations_pages(page_texts)
    operations = inherit_budget_context(operations)
    position = statement_pages(page_texts, POSITION_RE)
    net_assets = statement_pages(page_texts, NET_ASSET_RE)
    if not operations:
        full_text = "\n".join(page_texts)
        if REMUNERATION_DOCUMENT_RE.search(full_text):
            return {
                "parseStatus": "not_applicable",
                "confidence": "high",
                "warnings": ["Source document is a remuneration schedule, not an audited financial statement"],
                "publishable": False,
                "extractionCompleteness": "not_applicable",
                "sourceUrl": source_url,
                "fiscalYear": fiscal_year,
                "parser": "capital_text_v2",
            }
        return {
            "parseStatus": "manual_review",
            "confidence": "low",
            "warnings": ["No clear statement of operations found"],
            "publishable": False,
            "extractionCompleteness": "failed",
            "sourceUrl": source_url,
            "fiscalYear": fiscal_year,
            "parser": "capital_text_v2",
        }

    revenue_rows = parse_section_rows(
        operations,
        REVENUE_SECTION_RE,
        EXPENSE_SECTION_RE,
        broad_revenue_category,
    )
    expense_rows = parse_section_rows(
        operations,
        EXPENSE_SECTION_RE,
        EXPENSE_SECTION_END_RE,
        broad_expense_category,
    )
    if len(expense_rows) < 2:
        expense_rows = parse_segment_schedule_expenses(page_texts)
    revenue_breakdown, revenue_source_rows = aggregate_categories(revenue_rows)
    expense_breakdown, expense_source_rows = aggregate_categories(expense_rows)
    expense_details, expense_detail_schedules = parse_expense_detail_schedules(
        page_texts,
        expense_source_rows,
    )

    total_revenue = find_named_amount(operations, TOTAL_REVENUE_RE) or sum_rows(revenue_rows)
    total_expenses = find_named_amount(operations, TOTAL_EXPENSE_RE) or sum_rows(expense_rows)
    surplus_adjustments = parse_surplus_adjustments(operations)
    surplus = find_named_amount(operations, FINAL_SURPLUS_RE, last=True)
    if surplus is None and not surplus_adjustments:
        surplus = find_named_amount(operations, BEFORE_OTHER_RE, last=True)

    cash = find_named_amount(
        position,
        re.compile(r"^(?:cash|cash resources|cash and cash equivalents)$", re.I),
    )
    investments = find_named_amount(
        position,
        re.compile(r"^(?:marketable securities|investments)$", re.I),
    )
    capital_assets = find_named_amount(
        position,
        re.compile(r"^tangible capital assets", re.I),
    )
    capital_spending = find_named_amount(net_assets, CAPITAL_PURCHASE_RE)
    debt = extract_debt(position)

    summary = {
        "totalRevenue": rounded(total_revenue),
        "totalExpenses": rounded(total_expenses),
        "annualSurplusDeficit": rounded(surplus),
        "cashInvestments": rounded((cash or 0) + (investments or 0)) if cash is not None else None,
        "revenueBreakdown": revenue_breakdown,
        "expenseBreakdown": expense_breakdown,
        "capitalSpending": {
            "total": rounded(abs(capital_spending)),
            "categories": [],
        }
        if capital_spending is not None
        else None,
        "capitalAssets": rounded(capital_assets),
        "debt": debt,
        "sourceRevenueRows": revenue_source_rows,
        "sourceExpenseRows": expense_source_rows,
        "expenseDetails": expense_details,
        "expenseDetailSchedules": expense_detail_schedules,
        "surplusAdjustments": surplus_adjustments,
        "sourceUrl": source_url,
        "fiscalYear": fiscal_year,
        "parser": "capital_text_v2",
    }
    summary.update(validate_summary(summary))
    summary["extractionCompleteness"] = (
        "complete" if summary.get("publishable") else "partial"
    )
    return summary


def table_page_texts(pdf):
    pages = []
    for page in pdf.pages:
        header_text = page.extract_text(x_tolerance=1, y_tolerance=3) or ""
        header = "\n".join(header_text.splitlines()[:10])
        rows = []
        for table in page.extract_tables() or []:
            for row in table or []:
                cells = [clean_text(cell) for cell in row or []]
                cells = [cell for cell in cells if cell]
                if cells:
                    rows.append(" ".join(cells))
        if rows:
            pages.append(header + "\n" + "\n".join(rows))
    return pages


def summary_score(summary):
    score = 0
    if summary.get("publishable"):
        score += 100
    for key in ("totalRevenue", "totalExpenses", "annualSurplusDeficit"):
        if parse_money(summary.get(key)) is not None:
            score += 10
    score += min(10, len(summary.get("revenueBreakdown") or []))
    score += min(10, len(summary.get("expenseBreakdown") or []))
    score -= len(summary.get("warnings") or []) * 2
    return score


def parse_pdf_bytes(pdf_bytes, source_url=None, fiscal_year=None):
    if pdfplumber is None:
        return {
            "parseStatus": "error",
            "confidence": "low",
            "warnings": ["pdfplumber is unavailable"],
        }

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        page_texts = [
            page.extract_text(x_tolerance=1, y_tolerance=3) or ""
            for page in pdf.pages
        ]
        primary = parse_page_texts(page_texts, source_url, fiscal_year)
        if primary.get("publishable") or primary.get("parseStatus") == "not_applicable":
            return primary
        reconstructed = table_page_texts(pdf)
    if reconstructed:
        fallback = parse_page_texts(reconstructed, source_url, fiscal_year)
        fallback["parser"] = "capital_table_v2"
        if summary_score(fallback) > summary_score(primary):
            fallback.setdefault("warnings", []).append(
                "Primary text extraction was replaced by table reconstruction"
            )
            return fallback
    return primary


def response_output_text(payload):
    if payload.get("output_text"):
        return payload["output_text"]
    chunks = []
    for output in payload.get("output", []):
        for content in output.get("content", []):
            if content.get("text"):
                chunks.append(content["text"])
    return "\n".join(chunks)


def extract_with_openai(pdf_bytes, source_url, fiscal_year):
    global _openai_blocked_reason

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    if _openai_blocked_reason:
        return {
            "parseStatus": "error_openai_quota",
            "confidence": "low",
            "warnings": [_openai_blocked_reason],
        }
    prompt = (
        "Extract a conservative summary from this First Nation audited financial statement. "
        "Use the actual current-year column, not budget or prior-year values. Return JSON only "
        "with keys totalRevenue, totalExpenses, annualSurplusDeficit, cashInvestments, "
        "capitalAssets, capitalSpending, debt, revenueBreakdown, expenseBreakdown, warnings. "
        "Also return expenseDetails when a schedule, note, or supplementary table explicitly "
        "lists the items making up a program expense. Each expenseDetails row must have category, "
        "sourceLabel (the program or schedule name), label (the disclosed expense item), amount, "
        "page, and schedule. Breakdown rows must have category, sourceLabel, and amount. "
        "Do not infer missing values, create categories, or treat revenue as an expense."
    )
    payload = {
        "model": os.getenv("OPENAI_MODEL", "gpt-4.1"),
        "max_output_tokens": 4000,
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {
                        "type": "input_file",
                        "filename": "audited-statement.pdf",
                        "file_data": "data:application/pdf;base64,"
                        + base64.b64encode(pdf_bytes).decode("ascii"),
                    },
                ],
            }
        ],
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            result = json.loads(response.read().decode("utf-8"))
        text = response_output_text(result).strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
        summary = json.loads(text)
        summary["sourceUrl"] = source_url
        summary["fiscalYear"] = fiscal_year
        summary["parser"] = "capital_openai_v1"
        summary.update(validate_summary(summary))
        return summary
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:1200]
        quota_error = exc.code == 429 and (
            "insufficient_quota" in body.lower()
            or "exceeded your current quota" in body.lower()
        )
        if quota_error:
            _openai_blocked_reason = (
                "OpenAI API quota is unavailable; remaining AI fallbacks were skipped"
            )
        return {
            "parseStatus": "error_openai_quota" if quota_error else "error_openai",
            "confidence": "low",
            "warnings": [f"OpenAI capital extraction failed (HTTP {exc.code}): {body}"],
        }
    except Exception as exc:
        return {
            "parseStatus": "error_openai",
            "confidence": "low",
            "warnings": [f"OpenAI capital extraction failed: {type(exc).__name__}: {exc}"],
        }


def normalize_pdf_url(url):
    parts = urllib.parse.urlsplit(url)
    pairs = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    query = urllib.parse.urlencode(pairs, quote_via=urllib.parse.quote)
    return urllib.parse.urlunsplit(
        (parts.scheme, parts.netloc, parts.path, query, parts.fragment)
    )


def fetch_pdf(url):
    request = urllib.request.Request(
        normalize_pdf_url(url),
        headers={"User-Agent": "OpenBand/1.0 audited statement parser"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def is_audited_statement(filing):
    return bool(
        re.search(r"audited.*financial|financial.*statements", filing.get("docType", ""), re.I)
    )


def load_capital_data(path):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"schemaVersion": 1, "generated": None, "bands": {}}


def save_summary(capital_data, band, filing, summary):
    band_record = capital_data.setdefault("bands", {}).setdefault(
        str(band["id"]),
        {"name": band["name"], "years": {}},
    )
    band_record["name"] = band["name"]
    band_record.setdefault("years", {})[filing["year"]] = summary


def is_verified_summary(summary):
    if not summary:
        return False
    return bool(
        summary.get("verified")
        or summary.get("manualVerified")
        or summary.get("manual_override")
        or str(summary.get("parser", "")).startswith("manual")
    )


def source_inventory(data):
    records = []
    seen = set()
    for band in data.get("bands", []):
        for filing in band.get("filings", []):
            if (
                not filing.get("posted")
                or not filing.get("href")
                or not is_audited_statement(filing)
            ):
                continue
            key = (str(band.get("id")), str(filing.get("year")))
            if key in seen:
                continue
            seen.add(key)
            records.append(
                {
                    "bandId": str(band.get("id")),
                    "band": band.get("name"),
                    "fiscalYear": filing.get("year"),
                    "sourceUrl": filing.get("href"),
                }
            )
    return records


def coverage_snapshot(data, capital_data):
    sources = source_inventory(data)
    counts = {
        "postedSources": len(sources),
        "parsed": 0,
        "partial": 0,
        "failed": 0,
        "notApplicable": 0,
        "missing": 0,
    }
    unresolved = []
    for source in sources:
        summary = (
            capital_data.get("bands", {})
            .get(source["bandId"], {})
            .get("years", {})
            .get(source["fiscalYear"])
        )
        if not summary:
            counts["missing"] += 1
            unresolved.append({**source, "status": "missing", "reasons": ["Not attempted"]})
            continue
        status = summary.get("parseStatus")
        if status == "parsed" and summary.get("publishable") is not False:
            counts["parsed"] += 1
        elif status == "not_applicable":
            counts["notApplicable"] += 1
            unresolved.append(
                {
                    **source,
                    "status": "not_applicable",
                    "reasons": summary.get("warnings") or [],
                }
            )
        elif any(
            summary.get(key) not in (None, [], {})
            for key in ("totalRevenue", "totalExpenses", "revenueBreakdown", "expenseBreakdown")
        ):
            counts["partial"] += 1
            unresolved.append(
                {
                    **source,
                    "status": "partial",
                    "reasons": summary.get("warnings") or [],
                }
            )
        else:
            counts["failed"] += 1
            unresolved.append(
                {
                    **source,
                    "status": status or "failed",
                    "reasons": summary.get("warnings") or ["Extraction failed"],
                }
            )
    denominator = max(1, counts["postedSources"] - counts["notApplicable"])
    counts["coveragePercent"] = round(counts["parsed"] / denominator * 100, 2)
    return counts, unresolved


def extraction_records(capital_data):
    records = {
        "successful": [],
        "partial": [],
        "failed": [],
        "notApplicable": [],
    }
    for band_id, band in capital_data.get("bands", {}).items():
        for fiscal_year, summary in band.get("years", {}).items():
            record = {
                "bandId": band_id,
                "band": band.get("name"),
                "fiscalYear": fiscal_year,
                "status": summary.get("parseStatus"),
                "completeness": summary.get("extractionCompleteness"),
                "confidence": summary.get("confidence"),
                "parser": summary.get("parser"),
                "sourceUrl": summary.get("sourceUrl"),
                "reasons": summary.get("warnings") or [],
            }
            if (
                summary.get("parseStatus") == "parsed"
                and summary.get("publishable") is not False
            ):
                records["successful"].append(record)
            elif summary.get("parseStatus") == "not_applicable":
                records["notApplicable"].append(record)
            elif any(
                summary.get(key) not in (None, [], {})
                for key in (
                    "totalRevenue",
                    "totalExpenses",
                    "revenueBreakdown",
                    "expenseBreakdown",
                )
            ):
                records["partial"].append(record)
            else:
                records["failed"].append(record)
    return records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="data.json")
    parser.add_argument("--output", default="capital-data.json")
    parser.add_argument("--band", action="append", default=[])
    parser.add_argument("--year", action="append", default=[])
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--use-openai", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--report", default="capital-extraction-report.json")
    args = parser.parse_args()

    data = json.loads(Path(args.data).read_text(encoding="utf-8"))
    output_path = Path(args.output)
    capital_data = load_capital_data(output_path)
    before_coverage, _ = coverage_snapshot(data, capital_data)
    candidates = []
    attempts = []
    for band in data.get("bands", []):
        if args.band and band.get("name") not in args.band:
            continue
        for filing in band.get("filings", []):
            if not filing.get("posted") or not filing.get("href") or not is_audited_statement(filing):
                continue
            if args.year and filing.get("year") not in args.year:
                continue
            existing = (
                capital_data.get("bands", {})
                .get(str(band.get("id")), {})
                .get("years", {})
                .get(filing.get("year"))
            )
            if is_verified_summary(existing):
                attempts.append(
                    {
                        "bandId": str(band.get("id")),
                        "band": band.get("name"),
                        "fiscalYear": filing.get("year"),
                        "status": "preserved_verified",
                        "reasons": ["Verified data is never overwritten"],
                    }
                )
                continue
            if existing and existing.get("parseStatus") == "parsed" and not args.force:
                continue
            candidates.append((band, filing, existing))

    candidates.sort(
        key=lambda item: (str(item[1].get("year", "")), item[0].get("name", "")),
        reverse=True,
    )
    if args.limit:
        candidates = candidates[: args.limit]

    parsed = 0
    reviewed = 0
    for index, (band, filing, existing) in enumerate(candidates, start=1):
        print(f"[{index}/{len(candidates)}] {band['name']} {filing['year']}")
        try:
            pdf_bytes = fetch_pdf(filing["href"])
            summary = parse_pdf_bytes(pdf_bytes, filing["href"], filing["year"])
            if not summary.get("publishable") and args.use_openai:
                ai_summary = extract_with_openai(pdf_bytes, filing["href"], filing["year"])
                if ai_summary and ai_summary.get("publishable"):
                    summary = ai_summary
            preserved = bool(
                existing
                and existing.get("publishable")
                and not summary.get("publishable")
            )
            if not preserved:
                save_summary(capital_data, band, filing, summary)
            attempts.append(
                {
                    "bandId": str(band.get("id")),
                    "band": band.get("name"),
                    "fiscalYear": filing.get("year"),
                    "status": "preserved_existing" if preserved else summary.get("parseStatus"),
                    "completeness": summary.get("extractionCompleteness"),
                    "parser": summary.get("parser"),
                    "reasons": (
                        ["New extraction was less complete; existing publishable data preserved"]
                        if preserved
                        else summary.get("warnings") or []
                    ),
                }
            )
            if summary.get("publishable"):
                parsed += 1
                print(
                    f"  parsed ({summary.get('confidence')}): "
                    f"revenue={summary.get('totalRevenue')} expenses={summary.get('totalExpenses')}"
                )
            else:
                reviewed += 1
                print("  manual review:", "; ".join(summary.get("warnings") or []))
        except Exception as exc:
            reviewed += 1
            error_summary = {
                "fiscalYear": filing["year"],
                "sourceUrl": filing["href"],
                "parseStatus": "error",
                "confidence": "low",
                "warnings": [f"Capital parse failed: {type(exc).__name__}: {exc}"],
                "publishable": False,
                "extractionCompleteness": "failed",
                "parser": "capital_text_v2",
            }
            if not (existing and existing.get("publishable")):
                save_summary(capital_data, band, filing, error_summary)
            attempts.append(
                {
                    "bandId": str(band.get("id")),
                    "band": band.get("name"),
                    "fiscalYear": filing.get("year"),
                    "status": "error",
                    "completeness": "failed",
                    "parser": "capital_text_v2",
                    "reasons": error_summary["warnings"],
                }
            )
            print(f"  error: {exc}")

    capital_data["generated"] = now_iso()
    capital_data["schemaVersion"] = 1
    output_path.write_text(
        json.dumps(capital_data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    after_coverage, unresolved = coverage_snapshot(data, capital_data)
    report = {
        "generated": now_iso(),
        "dataFile": str(output_path),
        "before": before_coverage,
        "after": after_coverage,
        "attempted": len(candidates),
        "attempts": attempts,
        "records": extraction_records(capital_data),
        "unresolved": unresolved,
    }
    Path(args.report).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"capital filings parsed: {parsed}")
    print(f"capital filings needing review: {reviewed}")
    print(f"saved: {output_path}")
    print(
        "coverage: "
        f"{before_coverage['parsed']}/{before_coverage['postedSources']} "
        f"({before_coverage['coveragePercent']}%) -> "
        f"{after_coverage['parsed']}/{after_coverage['postedSources']} "
        f"({after_coverage['coveragePercent']}%)"
    )
    print(f"extraction report: {args.report}")


if __name__ == "__main__":
    main()
