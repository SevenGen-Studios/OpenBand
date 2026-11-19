// Optional isolated browser QA: NODE_PATH points to the bundled Playwright.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.OPENBAND_BROWSER_EXE||'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'});
 const page=await browser.newPage({viewport:{width:1365,height:900}});const errors=[];
 page.on('pageerror',error=>errors.push(error.message));
 await page.goto('http://127.0.0.1:8767/first-nations/bonaparte-first-nation/?tab=capital&year=2025-2026');
 await page.waitForFunction(()=>document.querySelector('#capitalPanel')?.textContent.includes('19,803,109'),{timeout:30000});
 assert.match(await page.locator('#capitalPanel').innerText(),/11,975,742/);
 await page.screenshot({path:'.openband-ocr/british-columbia/visual/bonaparte-desktop.png',fullPage:true});
 await page.goto('http://127.0.0.1:8767/first-nations/aitchelitz/?tab=remuneration&year=2025-2026');
 await page.waitForFunction(()=>document.querySelector('#tb')?.textContent.includes('Bailey, Angie'));
 assert.match(await page.locator('#tb').innerText(),/85,078/);
 assert.equal(await page.locator('#tb tr').count(),2);
 await page.setViewportSize({width:390,height:844});
 await page.locator('#tb tr').first().click();
 assert.ok(await page.locator('#tb tr').first().locator('[data-label="Months"]').isVisible());
 await page.screenshot({path:'.openband-ocr/british-columbia/visual/aitchelitz-mobile.png',fullPage:true});
 const width=await page.evaluate(()=>({page:document.documentElement.scrollWidth,viewport:innerWidth}));
 assert.ok(width.page<=width.viewport+1,JSON.stringify(width));
 await page.evaluate(()=>pick('Keeseekoose First Nation'));
 await page.waitForFunction(()=>document.querySelector('#rName')?.textContent.includes('Keeseekoose'));
 if(await page.locator('#tb tr').count())assert.equal(await page.locator('#tb').evaluate(el=>el.closest('table').querySelectorAll('thead th').length),7);
 assert.deepEqual(errors,[]);
 console.log('Desktop audit, exact remuneration fields, mobile overflow, province navigation and console checks passed');
 await browser.close();
})().catch(error=>{console.error(error);process.exit(1)});
