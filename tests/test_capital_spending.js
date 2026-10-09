const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'assets/openband.js'), 'utf8');
const names = ['capitalYearsForBand', 'getCapitalSummary', 'getCapitalSpending'];
const functions = source.split('\n').filter(line => names.some(name => line.startsWith(`function ${name}(`))).join('\n');
const context = vm.createContext({capitalData: {bands: {'1': {years: {
  '2024-2025': {capitalSpending: null, capitalAssets: 50011530},
  '2023-2024': {capitalSpending: 0, capitalAssets: 49000000},
  '2022-2023': {capitalSpending: {total: 1234}, capitalAssets: 48000000},
  '2021-2022': {capitalSpending: 4567, capitalAssets: 47000000},
}}}}});
vm.runInContext(functions, context);
assert.equal(context.getCapitalSpending('1', '2024-2025'), null, 'Missing spending must not become an asset balance');
assert.equal(context.getCapitalSpending('1', '2023-2024'), 0, 'Reported zero must stay zero');
assert.equal(context.getCapitalSpending('1', '2022-2023').total, 1234);
assert.equal(context.getCapitalSpending('1', '2021-2022'), 4567);
assert.equal(context.getCapitalSpending('unknown', '2024-2025'), null);
context.capitalData = JSON.parse(fs.readFileSync(path.join(root, 'capital-data.json'), 'utf8'));
let checked = 0;
for (const [id, band] of Object.entries(context.capitalData.bands)) {
  for (const [year, summary] of Object.entries(band.years || {})) {
    const actual = context.getCapitalSpending(id, year);
    assert.equal(actual, summary.capitalSpending ?? null, `${id}/${year}: spending must come only from the spending field`);
    checked++;
  }
}
console.log(`Capital spending regression and ${checked} stored Nation-year mappings passed.`);
