/** Financial maintenance API. GitHub is the only persistence layer. */
export interface FinancialEntryEnv {
  FINANCIAL_ADMINS?: string; // JSON {identity: {token, role: editor|verifier}}
  FINANCIAL_GITHUB_TOKEN?: string;
  FINANCIAL_ENTRY_ENABLED?: string;
  ALLOWED_ORIGINS: string;
}
type Row = Record<string, any>;
type Draft = Record<string, any>;
const repo = '/repos/SevenGen-Studios/OpenBand';
const branch = 'financial-drafts';
const schema = 'openband-remuneration-v1';
const clone = <T>(v: T): T => structuredClone(v);
const fail = (message: string, status = 422): never => { throw Object.assign(new Error(message), {status}); };
const equal = (a: any, b: any) => JSON.stringify(a) === JSON.stringify(b);
const secureEqual = (a: string, b: string) => {
  let difference = a.length ^ b.length;
  for (let i = 0; i < Math.max(a.length, b.length); i++) difference |= (a.charCodeAt(i) || 0) ^ (b.charCodeAt(i) || 0);
  return difference === 0;
};
const safeSource = (value: string) => {
  let url: URL;
  try { url = new URL(value); } catch { return fail('Official HTTPS PDF URL required'); }
  if (url.protocol !== 'https:' || url.port || url.username || url.password ||
      !['services.sac-isc.gc.ca', 'fnp-ppn.aadnc-aandc.gc.ca'].includes(url.hostname)) fail('Use an official ISC financial disclosure PDF URL');
  return url.href;
};
const numeric = (v: any) => {
  if (v === null || v === undefined) return null;
  if (typeof v !== 'number' || !Number.isFinite(v) || Math.abs(v) > 1e10) fail('Amounts must be finite numbers or blank');
  return v;
};
export const parts = (r: Row) => {
  const raw = [r.travel, r.expenses, r.creditCard];
  const travel = raw.every(v => v == null) ? (r.travelExpenses ?? null) : raw.reduce((a, v) => a + (v ?? 0), 0);
  return [r.remuneration ?? null, travel, r.otherPayments === undefined ? (r.other ?? null) : r.otherPayments];
};
export function select(data: any, id: string, year: string) {
  const bands = data.bands.filter((b: any) => String(b.id) === id);
  if (bands.length !== 1) fail('Nation ID is missing or ambiguous');
  const band = bands[0];
  const all = (band.filings || []).filter((f: any) => f.year === year && /remuneration/i.test(f.docType));
  const posted = all.filter((f: any) => f.href && f.posted !== false);
  const candidates = posted.length ? posted : all;
  if (candidates.length > 1) fail('Multiple source schedules: resolve source identity first');
  return {band, filing: candidates[0] || null};
}
/** Indexes refer to the immutable before-image. Full snapshots are made here,
 * never from the browser, so omitted officials/fields cannot erase data. */
export function editRows(before: Row[], edits: any[], additions: Row[], removals: number[]) {
  if (!Array.isArray(edits) || !Array.isArray(additions) || !Array.isArray(removals)) fail('Invalid edits');
  const rows = clone(before), touched = new Set<number>();
  const fields = ['name', 'role', 'months', 'remuneration', 'travelExpenses', 'other', 'total'];
  for (const edit of edits) {
    if (!Number.isInteger(edit.index) || !rows[edit.index] || touched.has(edit.index)) fail('Invalid or duplicate row edit');
    touched.add(edit.index);
    if (!edit.values || Object.keys(edit.values).some(k => !fields.includes(k))) fail('Unsupported row field');
    const row = rows[edit.index];
    for (const [key, value] of Object.entries(edit.values)) {
      if (key === 'name' || key === 'role') {
        if (typeof value !== 'string' || !value.trim() || value.length > 150) fail('Name and position required');
        row[key] = (value as string).trim();
      } else row[key] = numeric(value);
    }
    if ('travelExpenses' in edit.values) {
      // An explicitly corrected aggregate replaces, rather than adds to, its
      // components. Unedited component breakdowns remain byte-for-byte intact.
      row.travel = row.travelExpenses; row.expenses = null; row.creditCard = null;
    }
    if ('other' in edit.values) row.otherPayments = row.other;
    const changedMoney = ['remuneration', 'travelExpenses', 'other'].some(k => k in edit.values);
    if (changedMoney && !('total' in edit.values)) {
      const old = before[edit.index], oldParts = parts(old);
      if (old.total != null && (oldParts.some(v => v == null) || Math.abs(oldParts.reduce((a, v) => a + v, 0) - old.total) > 1.01)) fail('Review and explicitly correct this reported total');
      const p = parts(row); row.total = p.some(v => v == null) ? null : p.reduce((a, v) => a + v, 0);
    }
  }
  if (new Set(removals).size !== removals.length || removals.some(i => !Number.isInteger(i) || !rows[i])) fail('Invalid removed official');
  const result = rows.filter((_, i) => !removals.includes(i));
  for (const addition of additions) {
    if (Object.keys(addition).some(k => !fields.includes(k))) fail('Unsupported new official field');
    const row: Row = {...addition, travel: addition.travelExpenses ?? null, expenses: null, creditCard: null, otherPayments: addition.other ?? null};
    if (row.total == null) { const p = parts(row); row.total = p.some(v => v == null) ? null : p.reduce((a, v) => a + v, 0); }
    result.push(row);
  }
  return result;
}
export function validateRows(rows: Row[], source: any) {
  if (!rows.length || rows.length > 100) fail('One to 100 officials required');
  const identities = new Set<string>();
  for (const row of rows) {
    if (typeof row.name !== 'string' || !row.name.trim() || typeof row.role !== 'string' || !row.role.trim()) fail('Official name and position required');
    const identity = `${row.name.trim().toLowerCase()}|${row.role.trim().toLowerCase()}`;
    if (identities.has(identity) || /^(grand\s+)?(sub)?total\b/i.test(row.name)) fail('Duplicate official or total row');
    identities.add(identity);
    for (const key of ['months','remuneration','travel','expenses','creditCard','travelExpenses','other','otherPayments','total']) numeric(row[key]);
    if (row.months != null && (row.months < 0 || row.months > 12)) fail('Months must be between zero and 12');
    const p = parts(row);
    if (p.every(v => v != null) && row.total != null && Math.abs(p.reduce((a, v) => a + v, 0) - row.total) > 1.01) fail('Reported official total does not reconcile');
  }
  const printed = numeric(source.scheduleTotal);
  if (printed != null && (rows.some(r => r.total == null) || Math.abs(rows.reduce((a, r) => a + r.total, 0) - printed) > 1.01)) fail('Printed schedule total does not reconcile');
}
async function pdfHash(url: string) {
  const response = await fetch(safeSource(url), {redirect: 'manual', signal: AbortSignal.timeout(25000)});
  if (!response.ok) fail('Official PDF could not be retrieved (redirects require a direct official URL)');
  if (Number(response.headers.get('content-length')) > 25000000) fail('PDF exceeds 25 MB limit');
  const reader = response.body!.getReader(), chunks: Uint8Array[] = []; let size = 0;
  while (true) {
    const {done, value} = await reader.read(); if (done) break;
    size += value.length; if (size > 25000000) { await reader.cancel(); fail('PDF exceeds 25 MB limit'); }
    chunks.push(value);
  }
  const bytes = new Uint8Array(size); let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length; }
  if (!new TextDecoder().decode(bytes.slice(0, 5)).startsWith('%PDF-')) fail('Official URL did not return a PDF');
  return [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))].map(b => b.toString(16).padStart(2, '0')).join('');
}
const decode = (v: string) => JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(v.replace(/\s/g, '')), c => c.charCodeAt(0))));
async function github(env: FinancialEntryEnv, path: string, method = 'GET', body?: any, raw = false, optional = false): Promise<any> {
  const response = await fetch(`https://api.github.com${repo}${path}`, {
    method, headers: {Authorization: `Bearer ${env.FINANCIAL_GITHUB_TOKEN}`, Accept: raw ? 'application/vnd.github.raw+json' : 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'OpenBand-financial-admin', 'Content-Type': 'application/json'},
    ...(body ? {body: JSON.stringify(body)} : {})
  });
  if (optional && response.status === 404) return null;
  if (!response.ok) fail(response.status === 409 || response.status === 422 ? 'GitHub conflict: reload this record before retrying' : 'GitHub service unavailable or insufficient server permissions', response.status === 409 || response.status === 422 ? 409 : 503);
  return response.status === 204 ? {} : response.json();
}
const read = async (env: FinancialEntryEnv, path: string, ref: string) => {
  const file = await github(env, `/contents/${path}?ref=${encodeURIComponent(ref)}`, 'GET', undefined, false, true);
  return file ? {value: decode(file.content), sha: file.sha} : {value: null, sha: null};
};
async function ensureBranch(env: FinancialEntryEnv) {
  if (await github(env, `/git/ref/heads/${branch}`, 'GET', undefined, false, true)) return;
  const main = await github(env, '/git/ref/heads/main');
  await github(env, '/git/refs', 'POST', {ref: `refs/heads/${branch}`, sha: main.object.sha});
}
export async function handleFinancialEntry(request: Request, env: FinancialEntryEnv): Promise<Response> {
  const origin = request.headers.get('Origin') || '';
  const allowed = env.ALLOWED_ORIGINS.split(',').map(v => v.trim()).includes(origin);
  const headers: Record<string,string> = {'Content-Type':'application/json', 'Cache-Control':'no-store', 'Vary':'Origin'};
  if (allowed) headers['Access-Control-Allow-Origin'] = origin;
  const respond = (v: any, status = 200) => new Response(JSON.stringify(v), {status, headers});
  try {
    if (!allowed) fail('Origin not allowed', 403);
    if (env.FINANCIAL_ENTRY_ENABLED !== 'true' || !env.FINANCIAL_GITHUB_TOKEN || !env.FINANCIAL_ADMINS) fail('Financial entry backend is not configured', 503);
    const token = request.headers.get('Authorization')?.replace(/^Bearer\s+/i, '') || '';
    const admins = JSON.parse(env.FINANCIAL_ADMINS!);
    const identity = Object.keys(admins).find(k => typeof admins[k].token === 'string' && admins[k].token.length >= 32 && secureEqual(token, admins[k].token)) || fail('Unauthorized',401);
    if (!identity || !['editor','verifier'].includes(admins[identity].role)) fail('Unauthorized', 401);
    const url = new URL(request.url), action = url.pathname.slice('/v1/financial-entry'.length);
    if (request.method === 'GET' && action === '/catalog') {
      const data = await github(env, '/contents/data.json?ref=main', 'GET', undefined, true);
      const bands = data.bands.filter((b: any) => ['SK','AB','MB'].includes(b.province)).map((b: any) => ({id:b.id,name:b.name,province:b.province,
        filings:b.filings.filter((f: any) => /remuneration/i.test(f.docType)).map((f: any) => ({year:f.year,status:f.parse_status,source:f.href,hasPeople:!!f.people?.length,review:!!f.manual_review_required,revision:f.financialEntryRevision}))}));
      const index = (await read(env,'admin_drafts/index.json',branch)).value || {};
      const drafts = Object.values(index).map((d: any) => {
        const live = bands.find((b: any) => String(b.id) === d.bandId)?.filings.find((f: any) => f.year === d.year);
        return {...d,state:live?.revision===d.revision?'published':d.state};
      });
      return respond({identity,role:admins[identity].role,bands,drafts});
    }
    const id = url.searchParams.get('band') || '', year = url.searchParams.get('year') || '';
    if (!/^[A-Za-z0-9_-]{1,64}$/.test(id) || !/^\d{4}-\d{4}$/.test(year) || Number(year.slice(5)) !== Number(year.slice(0,4))+1) fail('Invalid Nation ID or fiscal year');
    const path = `admin_drafts/${id}-${year}.json`;
    if (request.method === 'GET' && action === '/record') {
      const data = await github(env, '/contents/data.json?ref=main', 'GET', undefined, true);
      const {band,filing} = select(data,id,year), saved = await read(env,path,branch);
      return respond({band:{id:band.id,name:band.name,province:band.province},filing,draft:saved.value,draftSha:saved.sha});
    }
    if (request.method === 'GET' && action === '/status') {
      const saved = await read(env,path,branch);
      if (!saved.value) fail('Draft not found',404);
      const runs = await github(env,'/actions/workflows/publish-financial-entry.yml/runs?event=workflow_dispatch&per_page=100');
      const run = runs.workflow_runs.find((r: any) => r.display_title === `Financial entry ${saved.value.revision}`);
      const overridePath = `manual_overrides/zz-admin-${id}-${year}.json`;
      const live = await read(env,overridePath,'main');
      let deployed = false, commit: string | null = null;
      if (live.value?.revision === saved.value.revision) {
        const commits = await github(env,`/commits?path=${overridePath}&per_page=1`); commit = commits[0]?.sha;
        const builds = await github(env,'/pages/builds?per_page=100');
        if (commit && run?.conclusion === 'success') {
          for (const build of builds.filter((b: any) => b.status === 'built').slice(0,5)) {
            const comparison = await github(env,`/compare/${commit}...${build.commit}`);
            if (!['ahead','identical'].includes(comparison.status)) continue;
            const publicResponse = await fetch('https://openband.ca/data.json', {cache:'no-store'});
            if (publicResponse.ok) {
              const publicData = await publicResponse.json();
              const current = select(publicData,id,year).filing;
              deployed = current?.financialEntryRevision === saved.value.revision;
            }
            break;
          }
        }
      }
      return respond({revision:saved.value.revision,workflow:run?{status:run.status,conclusion:run.conclusion,url:run.html_url}:null,commit,deployed});
    }
    if (request.method !== 'POST') fail('Method not allowed',405);
    if (Number(request.headers.get('Content-Length')) > 200000) fail('Request too large',413);
    const text = await request.text(); if (new TextEncoder().encode(text).length > 200000) fail('Request too large',413);
    const body = JSON.parse(text);
    await ensureBranch(env);
    const saved = await read(env,path,branch);
    if ((body.draftSha || null) !== saved.sha) fail('Draft changed: reload before saving or approving',409);
    if (action === '/publish') {
      if (admins[identity].role !== 'verifier' || saved.value?.state !== 'approved' || saved.value.approvedBy !== identity) fail('Verifier approval required',403);
      const head = await github(env,`/git/ref/heads/${branch}`);
      // Dispatch a SHA-bound draft; branch edits after dispatch cannot change it.
      const exact = await read(env,path,head.object.sha);
      if (exact.sha !== saved.sha) fail('Draft changed; reload',409);
      await github(env,'/actions/workflows/publish-financial-entry.yml/dispatches','POST',{ref:'main',inputs:{draft_sha:head.object.sha,draft_path:path,revision:saved.value.revision}});
      return respond({state:'queued',revision:saved.value.revision},202);
    }
    let draft: Draft;
    if (action === '/reverse') {
      const previous = (await read(env,`manual_overrides/zz-admin-${id}-${year}.json`,'main')).value;
      if (!previous?.before?.people?.length) fail('No previous populated schedule to restore');
      const data = await github(env,'/contents/data.json?ref=main','GET',undefined,true);
      const {band,filing} = select(data,id,year);
      if (filing?.financialEntryRevision !== previous.revision) fail('Published correction changed; reload',409);
      if (previous.before.href !== filing.href) fail('Reversal requires review of a different official source');
      const source = {...previous.source,sha256:await pdfHash(filing.href),identityAndYearConfirmed:false,completeSchedule:false};
      const people = clone(previous.before.people);
      validateRows(people,source);
      draft = {schema,bandId:id,band:band.name,province:band.province,year,before:filing,people,source,
        reason:String(body.reason || '').trim().slice(0,2000),editedBy:identity,editedAt:new Date().toISOString(),
        revision:crypto.randomUUID(),state:'awaiting_verification',reverses:previous.revision};
      if (!draft.reason) fail('Reversal reason required');
    } else if (action === '/approve') {
      if (admins[identity].role !== 'verifier' || saved.value?.state !== 'awaiting_verification' || saved.value.editedBy === identity) fail('Independent verifier required',403);
      if (body.identityAndYearConfirmed !== true || body.completeSchedule !== true) fail('Explicit PDF verification required');
      draft = clone(saved.value);
      validateRows(draft.people,draft.source);
      if (await pdfHash(draft.source.url) !== draft.source.sha256) fail('Official source changed; reopen and review',409);
      draft.source.identityAndYearConfirmed = true; draft.source.completeSchedule = true;
      draft.state = 'approved'; draft.approvedBy = identity; draft.approvedAt = new Date().toISOString();
    } else if (action === '/draft' || action === '/submit') {
      const data = await github(env,'/contents/data.json?ref=main','GET',undefined,true);
      const {band,filing} = select(data,id,year);
      if (!['SK','AB','MB'].includes(band.province)) fail('Unsupported province');
      // Existing drafts use their before-image. Browser can neither replace it
      // nor forge source verification or approval metadata.
      const before = body.restart === true ? filing : (saved.value ? saved.value.before : filing);
      if (!equal(before,filing)) fail('Published schedule changed; reload and start a new revision',409);
      const people = editRows(before?.people || [], body.edits, body.additions, body.removals);
      const sourceUrl = safeSource(body.source?.url || filing?.href || '');
      if (filing?.href && sourceUrl !== safeSource(filing.href)) fail('Source must match selected filing');
      const source = {url:sourceUrl, pages:String(body.source?.pages || '').slice(0,200), scheduleTotal:numeric(body.source?.scheduleTotal), sha256:'',identityAndYearConfirmed:false,completeSchedule:false};
      if (action === '/submit') {
        if (!source.pages.trim()) fail('Source page references required');
        validateRows(people,source); source.sha256 = await pdfHash(sourceUrl);
      }
      draft = {schema,bandId:id,band:band.name,province:band.province,year,before,people,source,
        reason:String(body.reason || '').trim().slice(0,2000),editedBy:identity,editedAt:new Date().toISOString(),
        revision:crypto.randomUUID(),editor:{edits:body.edits,additions:body.additions,removals:body.removals},state:action==='/submit'?'awaiting_verification':'draft'};
      if (!draft.reason && action === '/submit') fail('Correction reason required');
    } else return respond({error:'Not found'},404);
    // One atomic Git commit updates both the record and queue index. A
    // non-fast-forward ref update rejects any concurrent branch writer.
    const head = await github(env,`/git/ref/heads/${branch}`);
    const exact = await read(env,path,head.object.sha);
    if (exact.sha !== saved.sha) fail('Draft changed; reload',409);
    const index = (await read(env,'admin_drafts/index.json',head.object.sha)).value || {};
    index[`${id}-${year}`] = {bandId:id,year,state:draft.state,revision:draft.revision};
    const parent = await github(env,`/git/commits/${head.object.sha}`);
    const tree = await github(env,'/git/trees','POST',{base_tree:parent.tree.sha,tree:[
      {path,mode:'100644',type:'blob',content:JSON.stringify(draft,null,2)+'\n'},
      {path:'admin_drafts/index.json',mode:'100644',type:'blob',content:JSON.stringify(index,null,2)+'\n'}
    ]});
    const commit = await github(env,'/git/commits','POST',{message:`Financial entry ${draft.state}: ${id} ${year}`,tree:tree.sha,parents:[head.object.sha]});
    await github(env,`/git/refs/heads/${branch}`,'PATCH',{sha:commit.sha,force:false});
    const stored = await read(env,path,commit.sha);
    return respond({draft,draftSha:stored.sha});

  } catch (error: any) { return respond({error:error instanceof SyntaxError?'Invalid JSON':error.message || 'Financial service unavailable'},error.status || (error instanceof SyntaxError?400:503)); }
}
