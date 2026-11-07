"""Bound PDF parsing/OCR outside the API process (no network access needed)."""
from contextlib import redirect_stdout
import json
import sys
from pathlib import Path

def main():
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_CPU,(300,300))
        if sys.platform.startswith('linux'):
            resource.setrlimit(resource.RLIMIT_AS,(4*1024**3,4*1024**3))
    except (ImportError,ValueError):pass
    spec=json.loads(sys.stdin.read(100000))
    from tools.capital_parser import pdfplumber
    with pdfplumber.open(spec['path']) as pdf:
        if len(pdf.pages)>300:raise ValueError('PDF exceeds 300-page processing limit')
        if spec.get('renderPage'):
            page_number=spec['renderPage']
            if not 1<=page_number<=len(pdf.pages):raise ValueError('Page out of range')
            page=pdf.pages[page_number-1]
            if page.width*page.height*(180/72)**2>25_000_000:raise ValueError('Oversize PDF page')
            import io
            image=page.to_image(resolution=180).original
            buffer=io.BytesIO();image.save(buffer,format='PNG');sys.stdout.buffer.write(buffer.getvalue());return
    from tools.filing_review.extraction import extract
    from tools.filing_review.store import dump
    with redirect_stdout(sys.stderr):
        result=extract(Path(spec['path']).read_bytes(),spec['slot'],spec['url'],spec['sha256'])
    print(dump(result))

if __name__=='__main__':main()
