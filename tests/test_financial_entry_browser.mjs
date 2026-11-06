// Run with Node 22+, PLAYWRIGHT_MODULE, and optionally CHROME_EXECUTABLE.
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {handleFinancialEntry} from '../analytics-worker/src/financial-entry.ts';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE||'playwright');
const env={ALLOWED_ORIGINS:'https://openband.ca',FINANCIAL_ENTRY_ENABLED:'true',FINANCIAL_GITHUB_TOKEN:'fixture-server-only',FINANCIAL_ADMINS:JSON.stringify({editor:{token:'e'.repeat(40),role:'editor'},verifier:{token:'v'.repeat(40),role:'verifier'}})};
const filing={year:'2024-2025',docType:'Remuneration',href:'https://services.sac-isc.gc.ca/source.pdf',parse_status:'parsed',people:[{name:'Example Chief',role:'Chief',months:12,remuneration:105000,travel:200,expenses:50,creditCard:10,travelExpenses:260,otherPayments:0,other:0,total:105260},{name:'Example Councillor',role:'Councillor',months:null,remuneration:100,travel:null,expenses:null,creditCard:null,travelExpenses:null,otherPayments:null,other:null,total:null}]};
const data={bands:[{id:1,name:'Example Nation',province:'SK',filings:[filing]}]};
let draft=null,sha=null,index={},pending=null,sequence=0,dispatched=false;
const nativeFetch=globalThis.fetch;
globalThis.fetch=async(url,options={})=>{const u=new URL(url);if(u.hostname==='services.sac-isc.gc.ca')return new Response('%PDF-1.7 official fixture');assert.equal(u.hostname,'api.github.com');assert.equal(options.headers.Authorization,'Bearer fixture-server-only');const p=u.pathname;
 if(p.endsWith('/contents/data.json'))return Response.json(data);
 if(p.includes('/git/ref/heads/'))return Response.json({object:{sha:'a'.repeat(40)}});
 if(p.includes('/git/commits/'))return Response.json({tree:{sha:'base'}});
 if(p.endsWith('/git/trees')){pending=JSON.parse(options.body).tree;return Response.json({sha:'tree'})}
 if(p.endsWith('/git/commits'))return Response.json({sha:'b'.repeat(40)});
 if(p.includes('/git/refs/heads/')){for(const f of pending){if(f.path.endsWith('index.json'))index=JSON.parse(f.content);else{draft=JSON.parse(f.content);sha='blob'+(++sequence)}}return Response.json({})}
 if(p.endsWith('/contents/admin_drafts/index.json'))return Response.json({content:Buffer.from(JSON.stringify(index)).toString('base64'),sha:'index'});
 if(p.includes('/contents/admin_drafts/'))return draft?Response.json({content:Buffer.from(JSON.stringify(draft)).toString('base64'),sha}):Response.json({},{status:404});
 if(p.endsWith('/dispatches')){dispatched=true;return new Response(null,{status:204})}
 throw Error('Unexpected GitHub request '+url);
};
const browser=await chromium.launch({headless:true,...(process.env.CHROME_EXECUTABLE?{executablePath:process.env.CHROME_EXECUTABLE}:{})});
try{
 const context=await browser.newContext({viewport:{width:1440,height:1000}});const page=await context.newPage();const errors=[];page.on('pageerror',e=>{errors.push(e.message);console.log('PAGE ERROR',e.message)});page.on('console',m=>{if(m.type()==='error')console.log('CONSOLE',m.text())});
 await page.route('**/*',async route=>{const r=route.request(),u=new URL(r.url());if(u.hostname==='worker.example'){
  const headers=new Headers(r.headers());headers.set('Origin','https://openband.ca');const response=await handleFinancialEntry(new Request(r.url(),{method:r.method(),headers,...(r.postData()?{body:r.postData()}:{})}),env);
  await route.fulfill({status:response.status,headers:Object.fromEntries(response.headers),body:await response.text()});return;
 }
 if(u.hostname!=='openband.ca'){await route.abort();return}
 if(u.pathname==='/assets/analytics-config.js'){await route.fulfill({contentType:'application/javascript',body:'window.OPENBAND_ANALYTICS_CONFIG={apiEndpoint:"https://worker.example/v1/events"}'});return}
 const filename=resolve(u.pathname.endsWith('/')?'.'+u.pathname+'index.html':'.'+u.pathname);
 const body=await readFile(filename);await route.fulfill({contentType:filename.endsWith('.js')?'application/javascript':filename.endsWith('.css')?'text/css':'text/html',body});
 });
 await page.goto('https://openband.ca/admin/manual-entry/?band=1&year=2024-2025');
 await page.locator('#entryToken').fill('e'.repeat(40));await page.locator('#entryLogin button').click();await page.locator('#entryRows input[data-field=remuneration]').first().waitFor();
 await page.locator('#entryRows input[data-field=remuneration]').first().fill('15000');await page.locator('#entryPages').fill('3');await page.locator('#entryReason').fill('Correct OCR figure from official PDF');await page.locator('#entryPreview').click();
 assert.match(await page.locator('#entryDiff').innerText(),/105000/);assert.match(await page.locator('#entryDiff').innerText(),/15000/);
 await page.locator('#entrySave').click();await page.waitForFunction(()=>document.querySelector('#entryStatus').textContent.includes('Draft saved'));
 assert.equal(draft.people[0].remuneration,15000);assert.equal(draft.people[0].total,15260);assert.equal(draft.people[0].expenses,50);assert.equal(draft.people[1].other,null);
 await page.locator('#entrySubmit').click();await page.waitForFunction(()=>document.querySelector('#entryStatus').textContent.includes('Submitted.'));
 assert.equal(draft.state,'awaiting_verification');await page.locator('#entryLogout').click();
 await page.locator('#entryToken').fill('v'.repeat(40));await page.locator('#entryLogin button').click();await page.locator('#entryApprove').waitFor();
 await page.locator('#entryConfirmed').check();await page.locator('#entryComplete').check();await page.locator('#entryApprove').click();await page.waitForFunction(()=>document.querySelector('#entryStatus').textContent.includes('Revision approved'));
 await page.locator('#entryPublish').click();await page.waitForFunction(()=>document.querySelector('#entryStatus').textContent.includes('Publication queued'));assert.equal(dispatched,true);
 assert.equal(await page.evaluate(()=>localStorage.length+sessionStorage.length),0);
 if(process.env.ENTRY_SCREENSHOT)await page.screenshot({path:process.env.ENTRY_SCREENSHOT,fullPage:true});
 await page.setViewportSize({width:390,height:844});assert.equal(await page.locator('#entryHeading').isVisible(),true);assert.deepEqual(errors,[]);
 console.log('PASS: browser editor → GitHub draft → submit → independent approval → queued publishing; desktop/mobile, no browser credential storage.');
}finally{await browser.close();globalThis.fetch=nativeFetch}
