const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('assets/openband.js','utf8');
const context=vm.createContext({parseMoney:v=>Number(v)||0,esc:String,escAttr:String,
  formatMoney:v=>`$${v}`,expenseCategoryDetailMarkup:()=>''});
vm.runInContext(source.split('\n').find(l=>l.startsWith('const EXPENSE_CHART_COLORS='))+'\n'+
  source.slice(source.indexOf('function expenseSlicePath('),source.indexOf('function capitalMemberChip(')),context);
const full=context.expenseSlicePath(0,360);
assert.equal((full.match(/A 151 151/g)||[]).length,2,'Single-category rings need two outer arcs');
assert.equal((full.match(/A 109 109/g)||[]).length,2,'Single-category rings need two inner arcs');
for(const rows of [[{category:'Only',amount:10}], [{category:'Large',amount:999999},{category:'Tiny',amount:1}],
  [{category:'Positive',amount:20},{category:'Adjustment',amount:-5},{category:'Zero',amount:0}]]) {
  const html=context.capitalExpenseCategoriesMarkup({expenseBreakdown:rows},rows.reduce((n,r)=>n+r.amount,0),'');
  assert.equal((html.match(/class="expense-slice"/g)||[]).length,rows.filter(r=>r.amount>0).length);
  assert.equal((html.match(/class="expense-legend-item"/g)||[]).length,rows.filter(r=>r.amount>0).length);
  assert(!html.includes('stroke-dasharray'),'Segments must not wrap as dashed circles');
  assert(!html.includes('NaN'));
  assert(html.indexOf('expense-chart-legend')<html.indexOf('expense-chart-layout'));
  for(const [index,r] of rows.entries())assert(html.includes(`data-expense-category="${index}" data-label="${r.category}" data-amount="$${r.amount}"`));
}
const data=JSON.parse(fs.readFileSync('capital-data.json','utf8'));
let checked=0;
for(const band of Object.values(data.bands))for(const summary of Object.values(band.years||{})) {
  const rows=summary.expenseBreakdown||summary.expenses||[];
  if(!rows.length)continue;
  const html=context.capitalExpenseCategoriesMarkup(summary,summary.totalExpenses,'');
  assert(!html.includes('NaN'));
  assert.equal((html.match(/class="expense-slice"/g)||[]).length,rows.filter(r=>Number(r.amount)>0).length);
  checked++;
}
console.log(`Expense ring geometry, legend matching, adjustments, and ${checked} stored breakdowns passed.`);
