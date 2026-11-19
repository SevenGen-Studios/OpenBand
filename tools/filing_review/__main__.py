import argparse
import json
from pathlib import Path
from tools.filing_review.store import Store,ROOT,DEFAULT_YEARS,dump
from tools.filing_review.pipeline import Pipeline

def main():
    p=argparse.ArgumentParser(description='OpenBand private financial filing review; no automatic publication')
    p.add_argument('action',choices=['scan','discover','process','report','serve'])
    p.add_argument('--state',type=Path,default=ROOT/'.openband-ocr'/'filing-review')
    p.add_argument('--root',type=Path,default=ROOT)
    p.add_argument('--years',nargs='+',default=None)
    p.add_argument('--limit',type=int,default=25)
    p.add_argument('--port',type=int,default=8765)
    p.add_argument('--output',type=Path)
    args=p.parse_args()
    s=Store(args.state)
    if args.action=='serve':
        from tools.filing_review.server import ReviewServer
        server=ReviewServer(('127.0.0.1',args.port),args.state,args.root)
        print(f'Financial Filing Review: http://127.0.0.1:{args.port}/admin/financial-filings/',flush=True)
        try:server.serve_forever()
        finally:server.server_close();server.executor.shutdown(wait=True)
        return
    if args.action=='scan':result=s.inventory(args.root,args.years)
    elif args.action=='report':result=s.report(args.years)
    else:
        if args.limit<1 or args.limit>900:p.error('--limit must be between 1 and 900')
        result={'jobId':Pipeline(s,args.root).run(args.action,args.limit)}
    if args.output:args.output.write_text(dump(result)+'\n')
    print(json.dumps(result.get('counts',result),indent=2))
    s.db.close()

if __name__=='__main__':main()
