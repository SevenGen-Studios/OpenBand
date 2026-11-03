"""Bounded, resumable public-source research shared by all four content pipelines.

Fetched pages are evidence, never automatically verified projects or active jobs.
Changed pages enter the research report for review rather than replacing curation.
"""
import argparse
import gzip
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
try:
    from tools.news_discovery import Fetcher, write_json
    from tools.community_updates import SourcePage, error_status
except ImportError:
    from news_discovery import Fetcher, write_json
    from community_updates import SourcePage, error_status

ROOT = Path(__file__).resolve().parents[1]


def research(root, sources, refresh=False, limit=40):
    folder = root / 'research/community-intelligence/phase2-2026-11-02/evidence'
    folder.mkdir(parents=True, exist_ok=True)
    path = folder.parent / 'source-checks.json'
    previous = json.loads(path.read_text()) if path.exists() else {}
    fetcher = Fetcher(delay=.4, timeout=12)
    def check(source):
        url = source['url']; old = previous.get(url, {})
        if old.get('status') == 'checked' and not refresh: return url, old
        now = datetime.now(timezone.utc).isoformat(timespec='seconds')
        if (urlsplit(url).hostname or '').endswith(('facebook.com', 'instagram.com')):
            return url, {**old, 'url': url, 'status': 'authorized_api_required', 'lastAttempted': now}
        try:
            body, final, content_type = fetcher.get(url)
            sha = hashlib.sha256(body).hexdigest()
            filename = hashlib.sha256(url.encode()).hexdigest()[:20] + '-' + sha[:16] + '.gz'
            (folder / filename).write_bytes(gzip.compress(body, mtime=0))
            return url, {'url': url, 'finalUrl': final, 'contentType': content_type, 'status': 'checked',
                         'lastAttempted': now, 'lastSuccess': now, 'sha256': sha,
                         'changed': bool(old.get('sha256') and old['sha256'] != sha),
                         'evidencePath': str((folder / filename).relative_to(root))}
        except Exception as e:
            return url, {**old, 'url': url, 'status': error_status(e), 'lastAttempted': now, 'error': str(e)}
    unique = list({s['url']: s for s in sources}.values())[:limit]
    with ThreadPoolExecutor(max_workers=4) as pool:
        for url, result in pool.map(check, unique):
            previous[url] = result
            print(result['status'], url, flush=True)
    write_json(path, previous)
    return previous


def evidence_text(root, result):
    body = gzip.decompress((root / result['evidencePath']).read_bytes())
    if result.get('contentType', '').startswith('image/'):
        import subprocess
        import tempfile
        suffix = Path(urlsplit(result['url']).path).suffix or '.png'
        with tempfile.NamedTemporaryFile(suffix=suffix) as handle:
            handle.write(body); handle.flush()
            return subprocess.check_output(['tesseract', handle.name, 'stdout'], stderr=subprocess.DEVNULL, timeout=45).decode()
    if result.get('contentType') == 'application/pdf' or body.startswith(b'%PDF-'):
        import io
        import pdfplumber
        with pdfplumber.open(io.BytesIO(body)) as pdf:
            return '\n'.join(p.extract_text() or '' for p in pdf.pages)
    parser = SourcePage(result.get('finalUrl') or result['url']); parser.feed(body.decode('utf-8', errors='replace'))
    return ' '.join(parser.text)


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--url', action='append', default=[])
    p.add_argument('--refresh', action='store_true'); p.add_argument('--limit', type=int, default=40)
    a = p.parse_args()
    registry = ROOT / 'community-research-sources.json'
    sources = [{'url': u} for u in a.url] if a.url else json.loads(registry.read_text())['sources']
    research(ROOT, sources, a.refresh, a.limit)
