"""Restore only the exact audited output; refuse rollback over subsequent edits."""
import argparse
import hashlib
import json
from pathlib import Path


def restore_bytes(current, undo):
    if hashlib.sha256(current).hexdigest() != undo['outputSha256']:
        raise ValueError('Dataset changed since correction; refusing to overwrite later work')
    data = json.loads(current)
    for key, before in undo['beforeSummaries'].items():
        band, year = key.split(':')
        data['bands'][band]['years'][year] = before
    compact = current.count(b'\n') <= 1
    restored = (json.dumps(data, ensure_ascii=False, **({'separators': (',', ':')} if compact else {'indent': 2})) + '\n').encode()
    if hashlib.sha256(restored).hexdigest() != undo['inputSha256']:
        raise ValueError('Restored bytes do not match original input; refusing write')
    return restored


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', default='capital-data.json')
    parser.add_argument('--undo', required=True)
    parser.add_argument('--output', required=True, help='New destination; original dataset is never overwritten')
    args = parser.parse_args()
    restored = restore_bytes(Path(args.data).read_bytes(), json.loads(Path(args.undo).read_text()))
    with Path(args.output).open('xb') as stream:
        stream.write(restored)
    print('Restored bytes match original input SHA-256')


if __name__ == '__main__':
    main()
