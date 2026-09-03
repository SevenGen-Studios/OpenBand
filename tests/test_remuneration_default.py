"""Execute the real tab/year selection functions with a minimal UI adapter."""
import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which('node')


@unittest.skipUnless(NODE, 'Node.js is needed for browser-logic regression tests')
class RemunerationDefaultTests(unittest.TestCase):
    def test_year_selection_and_route_restoration(self):
        source = (ROOT / 'assets/openband.js').read_text()
        names = ['remFilings', 'isManualReview', 'getFilingStatus', 'isReliableParsed',
                 'filingScore', 'remFilingsByYear', 'bestYear', 'switchProfileTab']
        functions = '\n'.join(line for line in source.splitlines()
                              if any(line.startswith(f'function {name}(') or
                                     line.startswith(f'async function {name}(') for name in names))
        script = r'''
const assert = require('node:assert/strict');
const vm = require('node:vm');
const calls = [];
const select = {value:''};
const filing = (year, overrides={}) => ({year, posted:true,
  docType:'Schedule of Remuneration and Expenses', people:[{name:'Official'}], ...overrides});
const band = {filings:[filing('2021-2022'), filing('2025-2026', {people:[]}),
  filing('2024-2025'), filing('2023-2024')]};
const context = vm.createContext({
  VALID_TABS:['overview','remuneration','capital','sources'], activeProfileTab:'overview',
  curYear:'2021-2022', curCapitalYear:'2022-2023', band,
  hasRows:f => Boolean(f?.people?.length), selectedBand:() => band,
  el:() => select, document:{querySelectorAll:() => []}, window:{},
  renderYear:() => calls.push('renderYear'), ensureProfileData:async()=>{},
  getCapitalDisplayYear:()=>'2022-2023', renderActiveProfilePanel:()=>{},
  updateProfileMeta:()=>{}, updateHeaderSource:()=>calls.push('source'),
  updateProfileRoute:mode=>calls.push(mode)
});
vm.runInContext(FUNCTIONS, context);
(async()=>{
  // An old Recently Updated card must not set the default remuneration year.
  await context.switchProfileTab('remuneration');
  assert.equal(context.curYear,'2024-2025');
  assert.equal(select.value,'2024-2025');
  assert.ok(calls.includes('renderYear'));
  assert.ok(calls.includes('source'));
  assert.equal(calls.at(-1),'push');
  // Clicking the already-active tab must not undo a deliberate year selection.
  context.curYear='2021-2022';
  await context.switchProfileTab('remuneration');
  assert.equal(context.curYear,'2021-2022');
  // A capital year must not leak into remuneration on tab entry.
  context.activeProfileTab='capital';
  await context.switchProfileTab('remuneration');
  assert.equal(context.curYear,'2024-2025');
  assert.equal(context.curCapitalYear,'2022-2023');
  // Direct links, refresh and back/forward restoration preserve their year.
  context.activeProfileTab='overview'; context.curYear='2021-2022'; calls.length=0;
  await context.switchProfileTab('remuneration',{history:true});
  assert.equal(context.curYear,'2021-2022');
  assert.ok(!calls.includes('renderYear'));
  assert.ok(!calls.includes('push'));
  // Newer manual-review rows cannot displace the latest reliable parsed year.
  band.filings.push(filing('2026-2027',{manual_review_required:true}));
  assert.equal(context.bestYear(band),'2024-2025');
  // Duplicate filing selection and input order do not change the default.
  band.filings.unshift(filing('2024-2025',{people:[]}));
  assert.equal(context.bestYear(band),'2024-2025');
  // With no parsed year, retain a real available year (or a clean empty state).
  band.filings=[filing('2025-2026',{people:[]})];
  context.activeProfileTab='overview';
  await context.switchProfileTab('remuneration');
  assert.equal(context.curYear,'2025-2026');
  band.filings=[]; context.activeProfileTab='overview';
  await context.switchProfileTab('remuneration');
  assert.equal(context.curYear,null);
  assert.equal(select.value,'');
})().catch(error=>{console.error(error);process.exitCode=1});
'''.replace('FUNCTIONS', json.dumps(functions))
        result = subprocess.run([NODE, '-e', script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
