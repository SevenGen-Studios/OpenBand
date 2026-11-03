"""Cache attributable logo candidates for manual review; never approves assets."""
import argparse
import hashlib
import json
import subprocess
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urljoin

from lxml import html
from tools.collect_first_nation_logos import ROOT, request_bytes


def fetch(url):
    try:
        return request_bytes(url)
    except Exception as error:
        # Some hosts close Python TLS connections. Curl still verifies TLS.
        if 'Remote end closed' not in str(error): raise
        client = shutil.which('curl.exe') or shutil.which('curl')
        if not client: raise
        result = subprocess.run([client, '--location', '--fail', '--max-time', '25',
                                 '--silent', '--show-error', url], capture_output=True, check=True)
        payload = result.stdout
        if len(payload) > 12_000_000: raise ValueError('Download exceeds research limit')
        content_type = 'text/html'
        if payload.startswith(b'\x89PNG'): content_type = 'image/png'
        elif payload.startswith(b'\xff\xd8'): content_type = 'image/jpeg'
        elif payload.startswith(b'RIFF'): content_type = 'image/webp'
        elif b'<svg' in payload[:500]: content_type = 'image/svg+xml'
        return payload, content_type, url


def research(item, output):
    key, url = item
    folder = output / str(key)
    folder.mkdir(parents=True, exist_ok=True)
    result = {'key': key, 'requested_url': url, 'candidates': []}
    try:
        payload, _, final = fetch(url)
        result.update(final_url=final, page_sha256=hashlib.sha256(payload).hexdigest())
        (folder / 'page.html').write_bytes(payload)
        doc = html.fromstring(payload)
        result['title'] = ' '.join(doc.xpath('//title/text()'))
        candidates = {}
        for img in doc.xpath('//img'):
            src = img.get('data-src') or img.get('data-lazy-src') or img.get('src')
            if not src or src.startswith('data:'): continue
            address = urljoin(final, src)
            candidates[address] = {'asset_url': address, 'alt': img.get('alt', '')}
        for n, candidate in enumerate(candidates.values()):
            try:
                asset, content_type, asset_url = fetch(candidate['asset_url'])
                path = folder / f'{n}.source'
                path.write_bytes(asset)
                candidate.update(path=str(path.relative_to(ROOT)), content_type=content_type,
                                 source_sha256=hashlib.sha256(asset).hexdigest(), final_url=asset_url)
            except Exception as error:
                candidate['error'] = str(error)
            result['candidates'].append(candidate)
    except Exception as error:
        result['error'] = str(error)
    (folder / 'research.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'{key}: {result.get("title", result.get("error"))}; {len(result["candidates"])} images', flush=True)
    return result


if __name__ == '__main__':
    sys.stdout.reconfigure(errors='replace')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sources', type=Path, help='JSON object mapping research keys to source URLs')
    parser.add_argument('--output', type=Path, default=ROOT / 'tmp/manitoba-logo-research')
    args = parser.parse_args()
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda item: research(item, args.output), json.loads(args.sources.read_text()).items()))
