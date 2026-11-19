"""Dependency-free BC financial index settings for builders and extractors."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / '.openband-ocr/british-columbia'
INDEX = ROOT / 'bc-financial-index.json'
YEARS = [f'{year}-{year+1}' for year in range(2014, 2026)]

def read(path, default=None):
    path = Path(path)
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default
