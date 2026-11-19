"""Private companion API for the existing static administration interface."""
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import hmac
import json
import os
from pathlib import Path
import threading
from datetime import datetime,timezone
from urllib.parse import urlsplit,parse_qs
from tools.filing_review.store import Store,ROOT,dump,read
from tools.filing_review.pipeline import Pipeline,writer_lock

class ReviewServer(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,address,directory,root=ROOT):
        self.directory=Path(directory).resolve();self.root=Path(root).resolve()
        self.token=os.environ.get('ANALYTICS_ADMIN_TOKEN','')
        if len(self.token)<24:raise ValueError('Set ANALYTICS_ADMIN_TOKEN to the existing high-entropy admin secret (24+ characters)')
        self.origins=set(os.environ.get('FILING_REVIEW_ALLOWED_ORIGINS','http://127.0.0.1:8765,https://openband.ca').split(','))
        self.executor=ThreadPoolExecutor(max_workers=1)
        self.active=None;self.job_lock=threading.Lock()
        super().__init__(address,Handler)

    def enqueue(self,action,years=None,limit=25):
        with self.job_lock:
            if self.active and not self.active.done():return False
            def work():
                s=Store(self.directory)
                try:
                    p=Pipeline(s,self.root)
                    if action=='scan':s.inventory(self.root,years)
                    else:p.run(action,limit)
                finally:s.db.close()
            self.active=self.executor.submit(work)
            return True

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass # Never log headers or bearer credentials.

    def response(self,status,value,content_type='application/json'):
        data=(dump(value).encode() if content_type=='application/json' else value)
        self.send_response(status);self.send_header('Content-Type',content_type);self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        origin=self.headers.get('Origin','')
        if origin in self.server.origins:
            self.send_header('Access-Control-Allow-Origin',origin);self.send_header('Vary','Origin')
            self.send_header('Access-Control-Allow-Headers','Authorization,Content-Type');self.send_header('Access-Control-Allow-Methods','GET,POST,OPTIONS')
        self.end_headers();self.wfile.write(data)

    def do_OPTIONS(self):
        self.response(200,{})

    def do_GET(self):self.handle_request(False)
    def do_POST(self):self.handle_request(True)

    def handle_request(self,write):
        path=urlsplit(self.path).path
        static={'/admin/financial-filings/':'admin/financial-filings/index.html',
                '/':'admin/financial-filings/index.html',
                '/assets/filing-review.js':'assets/filing-review.js',
                '/assets/filing-review.css':'assets/filing-review.css',
                '/assets/openband.css':'assets/openband.css',
                '/assets/analytics-admin.css':'assets/analytics-admin.css',
                '/assets/favicon.svg':'assets/favicon.svg'}
        if not write and path in static:
            target=self.server.root/static[path]
            import mimetypes
            return self.response(200,target.read_bytes(),mimetypes.guess_type(target)[0] or 'text/plain')
        if not path.startswith('/v1/filing-review'):return self.response(404,{'error':'not_found'})
        auth=self.headers.get('Authorization','')
        if not hmac.compare_digest(auth,'Bearer '+self.server.token):return self.response(401,{'error':'Administrator authentication required'})
        origin=self.headers.get('Origin')
        if origin and origin not in self.server.origins:return self.response(403,{'error':'Origin not allowed'})
        store=Store(self.server.directory)
        try:
            endpoint=path[len('/v1/filing-review'):]
            if not write:
                if endpoint in ('','/'):
                    report=store.report();report['jobs']=store.rows('jobs');report['running']=bool(self.server.active and not self.server.active.done()) or any(j['state']=='running' and (datetime.now(timezone.utc)-datetime.fromisoformat(j['updated_at'])).total_seconds()<900 for j in report['jobs'])
                    if self.server.active and self.server.active.done() and self.server.active.exception():report['lastJobError']=str(self.server.active.exception())
                    return self.response(200,report)
                if endpoint=='/evidence':
                    cid=parse_qs(urlsplit(self.path).query).get('id',[''])[0]
                    row=store.db.execute('SELECT * FROM candidates WHERE id=?',(cid,)).fetchone()
                    if not row:return self.response(404,{'error':'Not found'})
                    return self.response(200,dict(candidate=dict(row,payload=json.loads(row['payload'])),searches=[dict(r) for r in store.db.execute('SELECT * FROM searches WHERE slot_id=?',(row['slot_id'],))],history=[dict(r) for r in store.db.execute('SELECT * FROM history WHERE candidate_id=?',(cid,))]))
                if endpoint in ('/pdf','/page'):
                    sha=parse_qs(urlsplit(self.path).query).get('sha',[''])[0]
                    import re
                    if not re.fullmatch('[a-f0-9]{64}',sha):raise ValueError('Invalid checksum')
                    pdf=store.pdfs/(sha+'.pdf')
                    if not pdf.exists():return self.response(404,{'error':'PDF not stored'})
                    if endpoint=='/page':
                        import subprocess,sys
                        page=int(parse_qs(urlsplit(self.path).query).get('page',['1'])[0])
                        if not 1<=page<=300:raise ValueError('Page out of range')
                        rendered=subprocess.run([sys.executable,'-m','tools.filing_review.worker'],input=dump(dict(path=str(pdf),renderPage=page)).encode(),capture_output=True,timeout=60,cwd=ROOT)
                        if rendered.returncode:raise ValueError('Source page could not be rendered')
                        return self.response(200,rendered.stdout,'image/png')
                    return self.response(200,pdf.read_bytes(),'application/pdf')
                return self.response(404,{'error':'Not found'})
            length=int(self.headers.get('Content-Length','0'))
            if length>256000:return self.response(413,{'error':'Request too large'})
            body=json.loads(self.rfile.read(length) or b'{}')
            if not isinstance(body,dict):raise ValueError('JSON object required')
            pipeline=Pipeline(store,self.server.root)
            if endpoint=='/jobs':
                action=body.get('action')
                if action not in ('scan','discover','process'):raise ValueError('Invalid job action')
                years=body.get('years')
                if years is not None:
                    import re
                    if not isinstance(years,list) or not years or len(years)>20 or any(not isinstance(y,str) or not re.fullmatch(r'20\d{2}-20\d{2}',y) or int(y[-4:])!=int(y[:4])+1 for y in years):raise ValueError('Invalid years')
                started=self.server.enqueue(action,years,max(1,min(900,int(body.get('limit',25)))))
                return self.response(202 if started else 409,{'status':'queued' if started else 'A batch is already running'})
            if endpoint=='/sources':
                url=body['url'];p=urlsplit(url)
                if p.scheme!='https' or not p.hostname or p.username or p.password or p.port not in (None,443):raise ValueError('HTTPS source required')
                if body.get('termsReviewed') is not True or len(body.get('ownershipEvidence','').strip())<12:raise ValueError('Confirm terms, permissions, and source ownership evidence')
                if not store.db.execute('SELECT 1 FROM slots WHERE band_id=?',(str(body['bandId']),)).fetchone():raise ValueError('Unknown Nation')
                registry=read(store.directory/'sources.json',{'sources':[]})
                source={k:body[k] for k in ('url','bandId','termsReviewed','ownershipEvidence')}
                with writer_lock(store.directory):
                    registry=read(store.directory/'sources.json',{'sources':[]})
                    if source not in registry['sources']:registry['sources'].append(source)
                    tmp=store.directory/'sources.tmp';tmp.write_text(dump(registry));os.replace(tmp,store.directory/'sources.json')
                    store.event(None,'source_registered','administrator',None,source,source);store.db.commit()
                return self.response(200,{'status':'registered'})
            if endpoint=='/figure':
                with writer_lock(store.directory):
                    pipeline.correct_figure(body['id'],body['metric'],body['raw'],body['scale'],body['page'],body['title'],body['explanation'],'administrator')
                return self.response(200,{'status':'figure_proposed'})
            if endpoint=='/review':
                with writer_lock(store.directory):pipeline.review(body['id'],body['action'],'administrator',body.get('evidence',{}))
                return self.response(200,{'status':'saved'})
            if endpoint=='/import':
                return self.response(200,pipeline.import_approved(body['id'],'administrator',body.get('replaceExisting') is True))
            if endpoint=='/candidate':
                sid=body['slotId']
                if not store.db.execute('SELECT 1 FROM slots WHERE id=?',(sid,)).fetchone():raise ValueError('Unknown filing slot')
                pipeline.http.validate(body['url']);pipeline.http.validate(body['source'])
                return self.response(200,{'id':store.candidate(sid,body['url'],body['source'])})
            if endpoint=='/reset-search':
                store.db.execute("DELETE FROM searches WHERE slot_id=? AND status IN ('search_complete','search_incomplete')",(body['slotId'],));store.db.commit()
                return self.response(200,{'status':'ready_for_rediscovery'})
            return self.response(404,{'error':'Not found'})
        except (ValueError,KeyError,TypeError) as error:self.response(400,{'error':str(error)})
        except Exception as error:self.response(500,{'error':type(error).__name__+': '+str(error)[:500]})
        finally:store.db.close()
