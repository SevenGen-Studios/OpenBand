type Amount = number | null;

interface SourcePerson {
  name?: unknown;
  role?: unknown;
  months?: unknown;
  remuneration?: unknown;
  expenses?: unknown;
  otherPayments?: unknown;
  other?: unknown;
  travel?: unknown;
  travelExpenses?: unknown;
  creditCard?: unknown;
  total?: unknown;
}

interface SourceFiling {
  year?: unknown;
  docType?: unknown;
  date?: unknown;
  href?: unknown;
  posted?: unknown;
  parse_status?: unknown;
  technical_status?: unknown;
  warnings?: unknown;
  people?: unknown;
}

interface SourceBand {
  id?: unknown;
  name?: unknown;
  province?: unknown;
  filings?: unknown;
}

interface SourceData {
  generated?: unknown;
  band_count?: unknown;
  error_count?: unknown;
  bands?: unknown;
}

type Amounts = {
  remuneration: Amount;
  expenses: Amount;
  otherPayments: Amount;
  travel: Amount;
  creditCard: Amount;
  totalReported: Amount;
};

interface Provenance {
  nationId: string;
  nation: string;
  fiscalYear: string;
  fiscalYearStart: number | null;
  filingId: string;
  recordId: string;
  sourceRecordIndex: number;
  documentType: string;
  filingDate: string;
  sourceUrl: string;
  parseStatus: string;
  technicalStatus: string;
  warnings: string[];
}

interface Change { amount: number; percent: number | null; }

export interface OfficialAnalysis {
  recordId: string;
  officialKey: string;
  official: string;
  role: string;
  months: number | null;
  amounts: Amounts;
  metrics: {
    componentSum: Amount;
    totalComponentDifference: Amount;
    nonRemunerationAmount: Amount;
    expensesPercentage: Amount;
    remunerationPercentage: Amount;
    otherPaymentsPercentage: Amount;
    nonRemunerationPercentage: Amount;
    missingComponents: string[];
  };
  yoy: Record<string, Change | string | null>;
  trends: Record<string, {direction: string; years: string[]; values: number[]; recordIds: string[]}>;
  provenance: Provenance;
}

interface Aggregate {
  value: Amount;
  partialSum: Amount;
  knownRecords: number;
  totalRecords: number;
  complete: boolean;
}

export interface NationAnalysis {
  nationId: string;
  nation: string;
  fiscalYear: string;
  fiscalYearStart: number | null;
  officialCount: number;
  aggregates: Record<string, Aggregate>;
  perOfficialAverages: Record<string, Amount>;
  yoy: Record<string, Change | null>;
  threeYearChange: Record<string, (Change & {basis: string; fromFiscalYear: string; toFiscalYear: string}) | null>;
  trends: Record<string, {direction: string; basis: string; years: string[]; values: number[]}>;
  recordIds: string[];
  sourceUrls: string[];
}

export interface StoryLead {
  leadId: string;
  type: string;
  scope: "official" | "nation" | "filing";
  nation: string;
  nationId: string;
  official: string | null;
  role?: string;
  fiscalYear: string;
  signalStrength: "very_high" | "high" | "moderate";
  credibilityScore?: number;
  credibilityLabel?: "strong" | "supported" | "review";
  signalTypes?: string[];
  reason: string;
  evidence: Record<string, unknown>;
  amounts?: Amounts;
  requiresManualVerification: true;
  interpretationGuardrail: string;
  provenance: Record<string, unknown>;
}

export interface IntelligenceReport {
  generatedAt: string;
  sourceGeneratedAt: string;
  overview: Record<string, unknown>;
  dataQuality: Record<string, unknown>;
  storyLeads: StoryLead[];
  officialAnalysis: OfficialAnalysis[];
  nationAnalysis: NationAnalysis[];
}

const DISCLAIMER = "Interesting research signal only. Verify the source filing manually; this is not a finding of wrongdoing, misuse, or overspending.";
const COMPONENTS: (keyof Amounts)[] = ["remuneration", "expenses", "otherPayments", "travel", "creditCard"];
const FIELDS: (keyof Amounts)[] = ["remuneration", "expenses", "otherPayments", "totalReported"];
const asObjectArray = <T>(value: unknown): T[] => Array.isArray(value) ? value.filter(item => item && typeof item === "object") as T[] : [];
const text = (value: unknown) => typeof value === "string" ? value.trim() : value == null ? "" : String(value);
const amount = (value: unknown): Amount => typeof value === "number" && Number.isFinite(value) ? value : null;
const canonical = (value: unknown) => {
  let normalized = text(value).normalize("NFKC");
  const comma = normalized.indexOf(",");
  if (comma > 0 && comma < normalized.length - 1) normalized = `${normalized.slice(comma + 1)} ${normalized.slice(0, comma)}`;
  return normalized.toLocaleLowerCase("en-CA").replace(/[^\p{L}\p{N}]+/gu, " ").trim().replace(/\s+/g, " ");
};
const fiscalStart = (value: unknown) => { const match = /^(\d{4})-(\d{4})$/.exec(text(value)); return match && Number(match[2]) === Number(match[1]) + 1 ? Number(match[1]) : null; };
const ratio = (numerator: Amount, denominator: Amount): Amount => numerator == null || denominator == null || denominator <= 0 ? null : Math.round(numerator / denominator * 1000000) / 10000;
const completeSum = (values: Amount[]): Amount => values.length && values.every(value => value != null) ? values.reduce((sum, value) => sum + (value as number), 0) : null;
const change = (current: Amount, previous: Amount): Change | null => current == null || previous == null ? null : {amount: current - previous, percent: previous === 0 ? null : Math.round((current - previous) / Math.abs(previous) * 1000000) / 10000};
const fieldLabel = (value: unknown) => text(value).replace(/([a-z])([A-Z])/g, "$1 $2").toLocaleLowerCase("en-CA");
const percentile = (values: number[], fraction: number): number | null => {
  const sorted = values.filter(Number.isFinite).sort((left, right) => left - right);
  if (!sorted.length) return null;
  const position = (sorted.length - 1) * fraction, lower = Math.floor(position), upper = Math.ceil(position);
  return lower === upper ? sorted[lower] : sorted[lower] + (sorted[upper] - sorted[lower]) * (position - lower);
};
const strength = (value: number, p95: number, p99: number | null): StoryLead["signalStrength"] => p99 != null && value >= p99 ? "very_high" : value >= p95 ? "high" : "moderate";
const stableId = (...parts: unknown[]) => parts.map(part => encodeURIComponent(text(part))).join(":");

function normalize(raw: SourceData) {
  const officials: OfficialAnalysis[] = [];
  const filings: Array<Record<string, unknown>> = [];
  for (const band of asObjectArray<SourceBand>(raw.bands)) {
    const nationId = text(band.id) || stableId(band.name), nation = text(band.name);
    asObjectArray<SourceFiling>(band.filings).forEach((filing, filingIndex) => {
      const fiscalYear = text(filing.year), documentType = text(filing.docType);
      const filingId = stableId(nationId, fiscalYear, documentType, filing.href, filingIndex);
      const people = asObjectArray<SourcePerson>(filing.people);
      const filingRecord = {
        filingId, nationId, nation, fiscalYear, fiscalYearStart: fiscalStart(fiscalYear), documentType,
        filingDate: text(filing.date), sourceUrl: text(filing.href), posted: Boolean(filing.posted),
        parseStatus: text(filing.parse_status), technicalStatus: text(filing.technical_status),
        warnings: Array.isArray(filing.warnings) ? filing.warnings.map(text).filter(Boolean) : [],
        isRemunerationFiling: documentType.toLocaleLowerCase("en-CA").includes("remuneration"),
        parsedRecordCount: people.length
      };
      filings.push(filingRecord);
      if (!filingRecord.isRemunerationFiling) return;
      people.forEach((person, sourceRecordIndex) => {
        const official = text(person.name), officialKey = canonical(official), recordId = stableId(filingId, sourceRecordIndex, officialKey, person.role);
        const amounts: Amounts = {
          remuneration: amount(person.remuneration), expenses: amount(person.expenses),
          otherPayments: amount(person.otherPayments),
          travel: amount(person.travel), creditCard: amount(person.creditCard), totalReported: amount(person.total)
        };
        const componentSum = completeSum(COMPONENTS.map(field => amounts[field]));
        const nonRemunerationAmount = completeSum([amounts.expenses, amounts.otherPayments]);
        officials.push({
          recordId, officialKey, official, role: text(person.role), months: amount(person.months), amounts,
          metrics: {
            componentSum, totalComponentDifference: componentSum == null || amounts.totalReported == null ? null : amounts.totalReported - componentSum,
            nonRemunerationAmount, expensesPercentage: ratio(amounts.expenses, amounts.totalReported),
            remunerationPercentage: ratio(amounts.remuneration, amounts.totalReported), otherPaymentsPercentage: ratio(amounts.otherPayments, amounts.totalReported),
            nonRemunerationPercentage: ratio(nonRemunerationAmount, amounts.totalReported), missingComponents: COMPONENTS.filter(field => amounts[field] == null)
          },
          yoy: {}, trends: {},
          provenance: {...filingRecord, recordId, sourceRecordIndex} as unknown as Provenance
        });
      });
    });
  }
  return {officials, filings};
}

function addOfficialHistory(officials: OfficialAnalysis[]) {
  const histories = new Map<string, OfficialAnalysis[]>();
  for (const official of officials) {
    // A person can legitimately appear more than once in a filing after a role
    // change. Keep those role histories separate so YoY comparisons never join
    // a Chief record to a Councillor record (or vice versa).
    const key = `${official.provenance.nationId}:${official.officialKey}:${canonical(official.role)}`;
    if (!histories.has(key)) histories.set(key, []);
    histories.get(key)!.push(official);
  }
  for (const history of histories.values()) {
    history.sort((left, right) => (left.provenance.fiscalYearStart ?? 9999) - (right.provenance.fiscalYearStart ?? 9999));
    for (let index = 1; index < history.length; index++) {
      const previous = history[index - 1], current = history[index];
      if (previous.provenance.fiscalYearStart == null || current.provenance.fiscalYearStart !== previous.provenance.fiscalYearStart + 1) continue;
      current.yoy.previousRecordId = previous.recordId;
      current.yoy.previousFiscalYear = previous.provenance.fiscalYear;
      for (const field of FIELDS) current.yoy[field] = change(current.amounts[field], previous.amounts[field]);
    }
    for (let index = 2; index < history.length; index++) {
      const window = history.slice(index - 2, index + 1), years = window.map(item => item.provenance.fiscalYearStart);
      if (years.some(year => year == null) || (years[2] as number) - (years[0] as number) !== 2) continue;
      for (const field of FIELDS) {
        const values = window.map(item => item.amounts[field]);
        if (values.some(value => value == null)) continue;
        const numbers = values as number[];
        const direction = numbers[0] < numbers[1] && numbers[1] < numbers[2] ? "increasing" : numbers[0] > numbers[1] && numbers[1] > numbers[2] ? "decreasing" : "";
        if (direction) history[index].trends[field] = {direction, years: window.map(item => item.provenance.fiscalYear), values: numbers, recordIds: window.map(item => item.recordId)};
      }
    }
  }
}

const aggregateField = (records: OfficialAnalysis[], field: keyof Amounts): Aggregate => {
  const values = records.map(record => record.amounts[field]), known = values.filter(value => value != null) as number[];
  return {value: known.length === values.length && values.length ? known.reduce((sum, value) => sum + value, 0) : null, partialSum: known.length ? known.reduce((sum, value) => sum + value, 0) : null, knownRecords: known.length, totalRecords: values.length, complete: known.length === values.length && Boolean(values.length)};
};

function nationMetrics(officials: OfficialAnalysis[]): NationAnalysis[] {
  const groups = new Map<string, OfficialAnalysis[]>();
  for (const official of officials) {
    const key = `${official.provenance.nationId}:${official.provenance.fiscalYear}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key)!.push(official);
  }
  const nations = [...groups.values()].map(records => {
    const first = records[0].provenance;
    const aggregates: Record<string, Aggregate> = {};
    const perOfficialAverages: Record<string, Amount> = {};
    for (const field of FIELDS) {
      aggregates[field] = aggregateField(records, field);
      perOfficialAverages[field] = aggregates[field].value == null ? null : Math.round(aggregates[field].value! / records.length * 10000) / 10000;
    }
    return {nationId: first.nationId, nation: first.nation, fiscalYear: first.fiscalYear, fiscalYearStart: first.fiscalYearStart, officialCount: records.length, aggregates, perOfficialAverages, yoy: {}, threeYearChange: {}, trends: {}, recordIds: records.map(record => record.recordId), sourceUrls: [...new Set(records.map(record => record.provenance.sourceUrl).filter(Boolean))]} as NationAnalysis;
  });
  const histories = new Map<string, NationAnalysis[]>();
  for (const nation of nations) { if (!histories.has(nation.nationId)) histories.set(nation.nationId, []); histories.get(nation.nationId)!.push(nation); }
  for (const history of histories.values()) {
    history.sort((left, right) => (left.fiscalYearStart ?? 9999) - (right.fiscalYearStart ?? 9999));
    for (let index = 1; index < history.length; index++) {
      const previous = history[index - 1], current = history[index];
      if (previous.fiscalYearStart == null || current.fiscalYearStart !== previous.fiscalYearStart + 1) continue;
      for (const field of FIELDS) current.yoy[field] = change(current.perOfficialAverages[field], previous.perOfficialAverages[field]);
    }
    for (let index = 2; index < history.length; index++) {
      const window = history.slice(index - 2, index + 1), years = window.map(item => item.fiscalYearStart);
      if (years.some(year => year == null) || (years[2] as number) - (years[0] as number) !== 2) continue;
      for (const field of FIELDS) {
        const values = window.map(item => item.perOfficialAverages[field]);
        if (values.some(value => value == null)) continue;
        const numbers = values as number[];
        const multiYearChange = change(numbers[2], numbers[0]);
        history[index].threeYearChange[field] = multiYearChange && {...multiYearChange, basis: "per_official_average", fromFiscalYear: window[0].fiscalYear, toFiscalYear: window[2].fiscalYear};
        const direction = numbers[0] < numbers[1] && numbers[1] < numbers[2] ? "increasing" : numbers[0] > numbers[1] && numbers[1] > numbers[2] ? "decreasing" : "";
        if (direction) history[index].trends[field] = {direction, basis: "per_official_average", years: window.map(item => item.fiscalYear), values: numbers};
      }
    }
  }
  return nations;
}

function officialLead(type: string, official: OfficialAnalysis, reason: string, signalStrength: StoryLead["signalStrength"], evidence: Record<string, unknown>): StoryLead {
  return {leadId: `${type}:${official.recordId}:${text(evidence.field)}`, type, scope: "official", nation: official.provenance.nation, nationId: official.provenance.nationId, official: official.official, role: official.role, fiscalYear: official.provenance.fiscalYear, signalStrength, reason, evidence, amounts: official.amounts, requiresManualVerification: true, interpretationGuardrail: DISCLAIMER, provenance: official.provenance as unknown as Record<string, unknown>};
}

const MATERIAL_CHANGE: Record<string, number> = {remuneration: 5000, expenses: 2500, otherPayments: 2500, totalReported: 5000};
const TYPE_WEIGHT: Record<string, number> = {data_anomaly: 18, extreme_one_year_value: 12, high_total: 10, large_yoy_change: 8, nation_expense_average: 7, expense_heavy: 6, other_payment_heavy: 6, multi_year_trend: 2};
const STRENGTH_WEIGHT: Record<StoryLead["signalStrength"], number> = {very_high: 74, high: 62, moderate: 44};

function candidateCredibility(lead: StoryLead) {
  let score = STRENGTH_WEIGHT[lead.signalStrength] + (TYPE_WEIGHT[lead.type] || 0);
  const sourceCount = Array.isArray(lead.provenance.sourceUrls) ? lead.provenance.sourceUrls.length : text(lead.provenance.sourceUrl) ? 1 : 0;
  if (sourceCount) score += 4;
  if (Number(lead.evidence.cohortSize) >= 50) score += 4;
  if (lead.evidence.previousFiscalYear || Array.isArray(lead.evidence.years)) score += 4;
  if (lead.amounts?.totalReported != null && lead.amounts.totalReported > 0) score += 3;
  return Math.min(100, score);
}

function consolidateLeads(candidates: StoryLead[]) {
  const groups = new Map<string, StoryLead[]>();
  for (const lead of candidates) {
    const recordId = text(lead.provenance.recordId) || text(lead.provenance.filingId) || `${lead.nationId}:${lead.fiscalYear}`;
    const key = `${lead.scope}:${recordId}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key)!.push(lead);
  }
  const strengthOrder = {very_high: 0, high: 1, moderate: 2};
  const consolidated = [...groups.values()].map(group => {
    const unique = [...new Map(group.map(lead => [`${lead.type}:${lead.reason}`, lead])).values()];
    unique.sort((left, right) => candidateCredibility(right) - candidateCredibility(left) || strengthOrder[left.signalStrength] - strengthOrder[right.signalStrength]);
    const primary = unique[0], secondary = unique.slice(1);
    const credibilityScore = Math.min(100, candidateCredibility(primary) + Math.min(12, secondary.length * 4));
    const credibilityLabel: StoryLead["credibilityLabel"] = credibilityScore >= 85 ? "strong" : credibilityScore >= 70 ? "supported" : "review";
    const signalTypes = [...new Set(unique.map(lead => lead.type))];
    const describeSignal = (lead: StoryLead) => `${lead.type.replace(/_/g, " ")}${lead.evidence.field ? ` (${fieldLabel(lead.evidence.field)})` : ""}`;
    const corroboration = secondary.length ? ` Corroborating signal${secondary.length === 1 ? "" : "s"}: ${secondary.map(describeSignal).join(", ")}.` : "";
    return {
      ...primary,
      leadId: `story:${primary.scope}:${text(primary.provenance.recordId) || text(primary.provenance.filingId) || `${primary.nationId}:${primary.fiscalYear}`}`,
      reason: `${primary.reason}${corroboration}`,
      credibilityScore,
      credibilityLabel,
      signalTypes,
      evidence: {
        ...primary.evidence,
        credibility: {score: credibilityScore, label: credibilityLabel, signalCount: unique.length},
        corroboratingSignals: secondary.map(lead => ({type: lead.type, strength: lead.signalStrength, reason: lead.reason, evidence: lead.evidence}))
      }
    } as StoryLead;
  });
  return consolidated
    // A monotonic pattern by itself is analysis context, not yet a story lead.
    // Filing-quality exceptions remain visible in the Data Quality workflow.
    .filter(lead => lead.scope === "filing" || (lead.credibilityScore || 0) >= 70)
    .sort((left, right) => (right.credibilityScore || 0) - (left.credibilityScore || 0) || strengthOrder[left.signalStrength] - strengthOrder[right.signalStrength] || (Number(right.fiscalYear.slice(0, 4)) || 0) - (Number(left.fiscalYear.slice(0, 4)) || 0) || left.type.localeCompare(right.type));
}

function signals(officials: OfficialAnalysis[], nations: NationAnalysis[], filings: Array<Record<string, unknown>>): StoryLead[] {
  const leads: StoryLead[] = [], years = [...new Set(officials.map(item => item.provenance.fiscalYear))];
  const duplicateCounts = new Map<string, number>();
  for (const official of officials) {
    const key = `${official.provenance.filingId}:${official.officialKey}:${canonical(official.role)}`;
    duplicateCounts.set(key, (duplicateCounts.get(key) || 0) + 1);
  }
  const thresholds = new Map<string, Record<string, {p95: number; p99: number; count: number}>>();
  for (const year of years) {
    const cohort = officials.filter(item => item.provenance.fiscalYear === year), record: Record<string, {p95: number; p99: number; count: number}> = {};
    const getters: Record<string, (item: OfficialAnalysis) => Amount> = {
      expensesPercentage: item => item.metrics.expensesPercentage, otherRatio: item => item.amounts.otherPayments == null || item.amounts.remuneration == null || item.amounts.remuneration === 0 ? null : item.amounts.otherPayments / item.amounts.remuneration * 100,
      totalReported: item => item.amounts.totalReported, remuneration: item => item.amounts.remuneration, expenses: item => item.amounts.expenses, otherPayments: item => item.amounts.otherPayments,
      yoy_remuneration: item => (item.yoy.remuneration as Change | null)?.percent == null ? null : Math.abs((item.yoy.remuneration as Change).percent as number),
      yoy_expenses: item => (item.yoy.expenses as Change | null)?.percent == null ? null : Math.abs((item.yoy.expenses as Change).percent as number),
      yoy_otherPayments: item => (item.yoy.otherPayments as Change | null)?.percent == null ? null : Math.abs((item.yoy.otherPayments as Change).percent as number),
      yoy_totalReported: item => (item.yoy.totalReported as Change | null)?.percent == null ? null : Math.abs((item.yoy.totalReported as Change).percent as number)
    };
    for (const [name, getter] of Object.entries(getters)) {
      const values = cohort.map(getter).filter(value => value != null) as number[];
      const p95 = percentile(values, .95), p99 = percentile(values, .99);
      if (values.length >= 10 && p95 != null && p99 != null) record[name] = {p95, p99, count: values.length};
    }
    thresholds.set(year, record);
  }
  for (const official of officials) {
    const cohort = thresholds.get(official.provenance.fiscalYear) || {};
    const expense = official.metrics.expensesPercentage, expenseT = cohort.expensesPercentage;
    if (expense != null && official.amounts.expenses != null && official.amounts.expenses >= MATERIAL_CHANGE.expenses && expenseT && expense >= Math.max(50, expenseT.p95)) leads.push(officialLead("expense_heavy", official, `Expenses are ${expense.toFixed(1)}% of total reported payments and exceed the $${MATERIAL_CHANGE.expenses.toLocaleString("en-CA")} materiality floor.`, strength(expense, expenseT.p95, expenseT.p99), {expensesPercentage: expense, expenses: official.amounts.expenses, materialityFloor: MATERIAL_CHANGE.expenses, fiscalYearP95: expenseT.p95, cohortSize: expenseT.count}));
    const other = official.amounts.otherPayments, remuneration = official.amounts.remuneration, otherT = cohort.otherRatio;
    if (other != null && other >= MATERIAL_CHANGE.otherPayments && remuneration != null && remuneration !== 0 && otherT) { const value = other / remuneration * 100; if (value >= Math.max(50, otherT.p95)) leads.push(officialLead("other_payment_heavy", official, `Other reported payments are ${value.toFixed(1)}% of remuneration and exceed the $${MATERIAL_CHANGE.otherPayments.toLocaleString("en-CA")} materiality floor.`, strength(value, otherT.p95, otherT.p99), {otherToRemunerationPercentage: value, otherPayments: other, materialityFloor: MATERIAL_CHANGE.otherPayments, fiscalYearP95: otherT.p95, cohortSize: otherT.count})); }
    const total = official.amounts.totalReported, totalT = cohort.totalReported;
    if (total != null && totalT && total >= totalT.p95) leads.push(officialLead("high_total", official, `Total reported payments are at or above the fiscal-year 95th percentile ($${Math.round(totalT.p95).toLocaleString("en-CA")}).`, strength(total, totalT.p95, totalT.p99), {totalReported: total, fiscalYearP95: totalT.p95, cohortSize: totalT.count}));
    for (const field of ["remuneration", "expenses", "otherPayments"] as const) { const value = official.amounts[field], threshold = cohort[field], verb = field === "remuneration" ? "is" : "are"; if (value != null && threshold && value >= threshold.p99) leads.push(officialLead("extreme_one_year_value", official, `${fieldLabel(field).replace(/^./, letter => letter.toLocaleUpperCase("en-CA"))} ${verb} at or above the fiscal-year 99th percentile.`, "very_high", {field, value, fiscalYearP99: threshold.p99, cohortSize: threshold.count})); }
    for (const field of FIELDS) { const yoy = official.yoy[field] as Change | null, threshold = cohort[`yoy_${field}`], magnitude = Math.abs(yoy?.percent || 0), floor = MATERIAL_CHANGE[field] || 5000; if (yoy?.percent != null && Math.abs(yoy.amount) >= floor && threshold && magnitude >= Math.max(50, threshold.p95)) leads.push(officialLead("large_yoy_change", official, `${field.replace(/([A-Z])/g, " $1")} ${yoy.percent > 0 ? "increased" : "decreased"} ${magnitude.toFixed(1)}% ($${Math.round(Math.abs(yoy.amount)).toLocaleString("en-CA")}) from the previous consecutive fiscal year.`, strength(magnitude, threshold.p95, threshold.p99), {field, change: yoy, absoluteMaterialityFloor: floor, previousFiscalYear: official.yoy.previousFiscalYear, fiscalYearP95: threshold.p95, cohortSize: threshold.count})); }
    for (const [field, trend] of Object.entries(official.trends)) { const trendChange = change(trend.values[2], trend.values[0]), floor = MATERIAL_CHANGE[field] || 5000; if (trendChange?.percent != null && Math.abs(trendChange.percent) >= 20 && Math.abs(trendChange.amount) >= floor) leads.push(officialLead("multi_year_trend", official, `${field.replace(/([A-Z])/g, " $1")} moved ${trend.direction} for three consecutive fiscal years, changing ${Math.abs(trendChange.percent).toFixed(1)}% ($${Math.round(Math.abs(trendChange.amount)).toLocaleString("en-CA")}) overall.`, "moderate", {field, ...trend, threeYearChange: trendChange, minimumPercentChange: 20, absoluteMaterialityFloor: floor})); }
    const negative = Object.entries(official.amounts).filter(([, value]) => value != null && value < 0).map(([field]) => field);
    const missingCore = (["remuneration", "totalReported"] as const).filter(field => official.amounts[field] == null);
    const impossiblePercentages = Object.entries({expenses: official.metrics.expensesPercentage, remuneration: official.metrics.remunerationPercentage, otherPayments: official.metrics.otherPaymentsPercentage}).filter(([, value]) => value != null && (value < 0 || value > 100.01)).map(([field, value]) => ({field, value}));
    const duplicateCount = duplicateCounts.get(`${official.provenance.filingId}:${official.officialKey}:${canonical(official.role)}`) || 1;
    const mismatch = official.metrics.totalComponentDifference;
    const totalMismatch = mismatch != null && official.metrics.componentSum != null && Math.abs(mismatch) > Math.max(5, Math.abs(official.metrics.componentSum) * .02);
    const issues = [negative.length && "negative amount", missingCore.length && "missing core component", impossiblePercentages.length && "impossible percentage", duplicateCount > 1 && "duplicate official", totalMismatch && "total mismatch"].filter(Boolean);
    if (issues.length) leads.push(officialLead("data_anomaly", official, `Manual data-quality review required: ${issues.join(", ")}.`, "high", {negativeFields: negative, missingCore, impossiblePercentages, duplicateCount, reportedMinusComponents: mismatch, componentSum: official.metrics.componentSum}));
  }
  const nationCohorts = new Map<string, number[]>();
  for (const nation of nations) { const value = nation.perOfficialAverages.expenses; if (value != null) { if (!nationCohorts.has(nation.fiscalYear)) nationCohorts.set(nation.fiscalYear, []); nationCohorts.get(nation.fiscalYear)!.push(value); } }
  for (const nation of nations) {
    const values = nationCohorts.get(nation.fiscalYear) || [], threshold = values.length >= 5 ? percentile(values, .95) : null, average = nation.perOfficialAverages.expenses;
    if (average != null && threshold != null && average >= threshold) leads.push({leadId: `nation_expense_average:${nation.nationId}:${nation.fiscalYear}`, type: "nation_expense_average", scope: "nation", nation: nation.nation, nationId: nation.nationId, official: null, fiscalYear: nation.fiscalYear, signalStrength: "high", reason: `Average reported expenses per official ($${Math.round(average).toLocaleString("en-CA")}) are at or above the fiscal-year 95th percentile.`, evidence: {averageExpenses: average, fiscalYearP95: threshold, cohortSize: values.length, officialCount: nation.officialCount}, requiresManualVerification: true, interpretationGuardrail: DISCLAIMER, provenance: {recordIds: nation.recordIds, sourceUrls: nation.sourceUrls}});
    for (const [field, trend] of Object.entries(nation.trends)) { const trendChange = change(trend.values[2], trend.values[0]), floor = MATERIAL_CHANGE[field] || 5000; if (trendChange?.percent != null && Math.abs(trendChange.percent) >= 20 && Math.abs(trendChange.amount) >= floor) leads.push({leadId: `multi_year_trend:${nation.nationId}:${nation.fiscalYear}:${field}`, type: "multi_year_trend", scope: "nation", nation: nation.nation, nationId: nation.nationId, official: null, fiscalYear: nation.fiscalYear, signalStrength: "moderate", reason: `Per-official average ${field.replace(/([A-Z])/g, " $1")} moved ${trend.direction} for three consecutive fiscal years, changing ${Math.abs(trendChange.percent).toFixed(1)}% overall.`, evidence: {field, ...trend, threeYearChange: trendChange, minimumPercentChange: 20, absoluteMaterialityFloor: floor}, requiresManualVerification: true, interpretationGuardrail: DISCLAIMER, provenance: {recordIds: nation.recordIds, sourceUrls: nation.sourceUrls}}); }
  }
  for (const filing of filings) if (filing.isRemunerationFiling && filing.posted && !filing.parsedRecordCount) leads.push({leadId: `unparsed_filing:${filing.filingId}`, type: "data_anomaly", scope: "filing", nation: text(filing.nation), nationId: text(filing.nationId), official: null, fiscalYear: text(filing.fiscalYear), signalStrength: "moderate", reason: `Posted remuneration filing has no parsed official records (status: ${text(filing.parseStatus)}).`, evidence: {issue: "posted_unparsed_filing", parseStatus: filing.parseStatus, technicalStatus: filing.technicalStatus, warnings: filing.warnings}, requiresManualVerification: true, interpretationGuardrail: DISCLAIMER, provenance: filing});
  return consolidateLeads(leads);
}

export function buildIntelligence(raw: SourceData): IntelligenceReport {
  const {officials, filings} = normalize(raw);
  addOfficialHistory(officials);
  const nations = nationMetrics(officials), storyLeads = signals(officials, nations, filings);
  const fiscalYears = [...new Set(officials.map(item => item.provenance.fiscalYear).filter(Boolean))].sort();
  const nationNames = [...new Set(officials.map(item => item.provenance.nation).filter(Boolean))].sort((left, right) => left.localeCompare(right));
  const signalTypes = [...new Set(storyLeads.flatMap(item => item.signalTypes || [item.type]))].sort();
  const signalsByType = Object.fromEntries(signalTypes.map(type => [type, storyLeads.filter(lead => (lead.signalTypes || [lead.type]).includes(type)).length]));
  const componentAvailability = Object.fromEntries(Object.keys(officials[0]?.amounts || {}).map(field => [field, {knownRecords: officials.filter(item => item.amounts[field as keyof Amounts] != null).length, missingRecords: officials.filter(item => item.amounts[field as keyof Amounts] == null).length}]));
  return {
    generatedAt: new Date().toISOString(), sourceGeneratedAt: text(raw.generated),
    overview: {nationsAnalyzed: new Set(officials.map(item => item.provenance.nationId)).size, officialRecordsAnalyzed: officials.length, uniqueOfficialsWithinNation: new Set(officials.map(item => `${item.provenance.nationId}:${item.officialKey}`)).size, fiscalYears, nationNames, signalTypes, signalCount: storyLeads.length, signalsByType},
    dataQuality: {componentAvailability, postedUnparsedFilings: filings.filter(filing => filing.isRemunerationFiling && filing.posted && !filing.parsedRecordCount).length, note: "Optional columns can be absent because filing layouts differ. Absence remains null and limits comparisons; it is not treated as an anomaly without additional evidence."},
    storyLeads, officialAnalysis: officials, nationAnalysis: nations
  };
}
