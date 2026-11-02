const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'assets/openband.js'), 'utf8');
const names = ['normalizeRevenueParent', 'revenueSubcategory', 'revenueEntriesForSummary'];
const functions = source.split('\n').filter(line =>
  line.startsWith('const REVENUE_CATEGORY_ORDER=') || names.some(name => line.startsWith(`function ${name}(`))
).join('\n');
const context = vm.createContext({parseMoney: Number, capitalRevenueSourceNote: () => null});
vm.runInContext(functions, context);
for (const [label, category] of [
  ['Trust', 'Business and enterprise revenue'],
  ['Income from government business enterprises - other', 'Business and enterprise revenue'],
  ['Government contributions', 'Government funding and transfers'],
  ['Health Canada', 'Government funding and transfers'],
  ['Tribal council', 'Unclassified'],
  ['Land Claim Settlement Trust', 'Unclassified'],
  ['Contributions', 'Unclassified'],
  ['Other', 'Other revenue'],
]) assert.equal(context.normalizeRevenueParent(label, category), category, label);
assert.equal(context.normalizeRevenueParent('Government contributions'), 'Unclassified', 'Browser must not invent a category');
assert.equal(context.revenueSubcategory('Business Trust', 'Business and enterprise revenue'), 'Business earnings');
assert.equal(context.revenueSubcategory('Trust', 'Business and enterprise revenue'), null);
assert.equal(context.revenueSubcategory('Trust', 'Unclassified'), null);
const reviewed = context.revenueEntriesForSummary({id: 1, name: 'Nation'}, '2024-2025', {
  sourceRevenueRows: [{label: 'Trust', category: 'Business and enterprise revenue', normalizedCategory: 'Investment income', amount: 100}],
});
assert.equal(reviewed[0].normalizedCategory, 'Business and enterprise revenue', 'Stored category must win over a stale normalizedCategory');
const data = JSON.parse(fs.readFileSync(path.join(root, 'capital-data.json'), 'utf8'));
let checked = 0;
for (const [id, band] of Object.entries(data.bands)) {
  for (const [year, summary] of Object.entries(band.years || {})) {
    if (summary.parseStatus !== 'parsed' || summary.publishable === false) continue;
    const rows = summary.sourceRevenueRows?.length ? summary.sourceRevenueRows : summary.revenueBreakdown || [];
    const entries = context.revenueEntriesForSummary({...band, id}, year, summary);
    assert.equal(entries.length, rows.length);
    rows.forEach((row, index) => {
      assert.equal(entries[index].amount, Number(row.amount));
      assert.equal(entries[index].normalizedCategory, context.normalizeRevenueParent(row.label || row.category, row.category || row.normalizedCategory));
      checked++;
    });
  }
}
console.log(`Frontend classification precedence and ${checked} published revenue mappings passed.`);
