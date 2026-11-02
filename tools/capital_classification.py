"""Conservative proposals, not evidence that a published classification is verified.

Keep the established public categories. An Operations fallback always carries a
review requirement; only explicit operating objects are positively identified.
A caller may provide a source-backed parent program/heading, never an inferred
funding residual. Reviewed row decisions take precedence over these rules.
"""
import re

RULE_VERSION = 'classification_v1'


def reviewed_row(row):
    review = row.get('classificationReview') or {}
    return bool(row.get('manualVerified') or row.get('manual_override') or
                row.get('verified') or review.get('status') in
                {'verified_correct', 'verified_misclassification', 'verified'})


def classify(label, kind, *, reference=None, parent_label=None, row=None):
    row = row or {}
    if reviewed_row(row) and row.get('category'):
        return dict(category=row['category'], rule='reviewed_override',
                    reviewRequired=False, reason='Preserved reviewed row decision',
                    evidenceLevel='stored_manual_review')
    low = re.sub(r'\s+', ' ', str(label or '').lower()).strip()
    ref = reference or {}
    def decision(category, rule, review=False, reason=None):
        return dict(category=category, rule=rule, reviewRequired=review,
                    reason=reason or rule.replace('_', ' '), evidenceLevel='automated_label_rule',
                    ruleVersion=RULE_VERSION)
    fallback = 'Unclassified' if kind == 'revenue' else 'Operations'
    if not low:
        return decision(fallback, 'missing_label', True)
    if ref.get('section') and ref['section'] != ('revenue' if kind == 'revenue' else 'expenses'):
        return decision(fallback, 'wrong_statement_section', True)
    if re.search(r'^(?:total\s+)?(?:revenue|expenses?|expenditures?)(?:\s*\(continued.*\))?$|'
                 r'eliminations?|consolidation adjustments?', low):
        return decision(fallback, 'subtotal_or_consolidation', True)
    if kind == 'revenue':
        # Recognition/deferral adjustments need attribution from the notes.
        if re.search(r'defer|unexpended|carried (?:forward|over)|repayment of funding', low):
            return decision('Unclassified', 'recognition_adjustment', True)
        if re.search(r'loan proceeds|financing proceeds|borrowings|return of capital|internal transfer', low):
            return decision('Unclassified', 'financing_or_internal_transfer', True)
        text = (str(parent_label or '') + ' ' + low).lower().strip()
        if re.search(r'(?:income|earnings?|loss|gain).*government business enterprises?|'
                     r'(?:earnings?|gain|loss).*investment in (?:nation )?business', text):
            return decision('Business and enterprise revenue', 'equity_accounted_business')
        if re.search(r'\btrust\b', low):
            if re.search(r'interest|investment income|dividend', low):
                return decision('Investment income', 'explicit_investment_return')
            return decision('Unclassified', 'trust_nature_requires_notes', True)
        if re.search(r'settlement|\bland claims?\b', low):
            return decision('Settlement and claim revenue', 'explicit_settlement')
        if re.search(r'gain on|loss on|proceeds.*(?:asset|disposal)|asset sales', low):
            return decision('Other revenue', 'asset_disposal_requires_context', True)
        if re.search(r'indigenous services|indigenous and northern affairs|aboriginal affairs|'
                     r'indian (?:and northern )?affairs|\b(?:isc|inac|aandc|cmhc)\b|'
                     r'canada mortgage|\bhealth canada\b|first nations? and inuit health|'
                     r'employment and social development canada|canadian heritage|'
                     r'government|(?:saskatchewan|alberta|manitoba) ministry', low):
            return decision('Government funding and transfers', 'named_government_funder')
        if re.search(r'tribal council|health.*authority|child.*family|\bsitag\b', low):
            return decision('Unclassified', 'intermediary_funder_requires_notes', True)
        if re.search(r'\btax(?:ation|es)?\b|local revenue|\blevy\b', low):
            return decision('Taxation and local revenue', 'explicit_tax_or_local_revenue')
        if re.search(r'\brent|\blease|property income', low):
            return decision('Rental and property income', 'explicit_property_revenue')
        if re.search(r'\binterest\b|investment income|\bdividend', low):
            return decision('Investment income', 'explicit_investment_return')
        if re.search(r'\bbusiness|enterprise|limited partnership|\blp\b|holdings?|'
                     r'\bstore|retail|gaming|bingo|casino|\bsales\b|royalt|farming', low):
            if re.search(r'fundrais|donation', low):
                return decision('Unclassified', 'mixed_business_and_donation', True)
            return decision('Business and enterprise revenue', 'explicit_business_revenue')
        if re.search(r'donation|sponsor|fundrais', low):
            return decision('Donations or contributions', 'explicit_donation')
        if re.search(r'contribution|\bgrant', low):
            return decision('Unclassified', 'unidentified_contributor', True)
        if re.search(r'program|service|administration fee|management fee|tuition|'
                     r'user fees|daycare fees|licensing fees', low):
            return decision('Program and service revenue', 'explicit_service_revenue')
        if re.fullmatch(r'other(?: revenue| income)?|miscellaneous|insurance proceeds?', low):
            return decision('Other revenue', 'explicit_other_revenue')
        return decision('Unclassified', 'unknown_revenue_label', True)
    if re.search(r'capital assets?|asset balances?|construction in progress|cash flows?', low):
        return decision('Operations', 'asset_or_cash_flow_requires_review', True)
    if re.search(r'transfer.*trust|settlement trust|program administration', low):
        return decision('Operations', 'program_or_trust_context_required', True)
    # Use parent context only when supplied from the actual schedule heading.
    text = (str(parent_label or '') + ' ' + low).lower().strip()
    patterns = [
        (r'\bland claims?\b', 'Land Claims', 'explicit_land_claim_program'),
        (r'housing|\bc\.?m\.?h\.?c\.?\b', 'Housing', 'housing_program'),
        (r'education|school|post[- ]secondary|training|tuition', 'Education', 'education_program'),
        (r'health|medical|nursing', 'Health', 'health_program'),
        (r'social|child|family|income assistance|community based services', 'Social programs', 'social_program'),
        (r'infrastructure|public works|community development|\bcapital\b|'
         r'facilit(?:y|ies) maintenance|operations?\s*(?:&|and)\s*maintenance',
         'Infrastructure / public works', 'infrastructure_program'),
        (r'economic|lands? management|band development|first nation owned|retail operations|commercial enterprises?',
         'Economic development', 'economic_program'),
        (r'governance|chief and council|government (?:support|services)|band government|'
         r'^(?:band )?administration$|registration(?: and)? membership|membership',
         'Administration', 'governance_program'),
    ]
    for pattern, category, rule in patterns:
        if re.search(pattern, text):
            return decision(category, rule)
    if re.fullmatch(r'amortization|depreciation|general operations|general operating expenses', low):
        return decision('Operations', 'explicit_operating_object')
    return decision('Operations', 'unresolved_operations_fallback', True)
