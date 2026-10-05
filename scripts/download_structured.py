"""Download only the authorized structured sources; cache and hash every artifact."""

import argparse
import hashlib
import json
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/raw'
URLS = {
    'kg.csv': 'https://dataverse.harvard.edu/api/access/datafile/6180620',
    'mondo.obo': 'https://purl.obolibrary.org/obo/mondo.obo',
    'hp.obo': 'https://purl.obolibrary.org/obo/hp.obo',
}


def sha256(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def download(url: str, path: Path) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    meta = path.with_suffix(path.suffix + '.meta.json')
    if path.exists() and meta.exists():
        record = json.loads(meta.read_text(encoding='utf8'))
        if record['sha256'] != sha256(path):
            raise ValueError(f'Cached checksum mismatch: {path.name}')
        return record
    part = path.with_suffix(path.suffix + '.part')
    request = urllib.request.Request(url, headers={'User-Agent': 'medkg-research/0.1'})
    for attempt in range(2):
        try:
            with urllib.request.urlopen(request, timeout=90) as response, part.open('wb') as out:
                while block := response.read(1024 * 1024):
                    out.write(block)
                expected = response.headers.get('Content-Length')
                if expected and part.stat().st_size != int(expected):
                    raise ValueError('Truncated download')
            if part.stat().st_size < 100:
                raise ValueError('Empty download')
            part.replace(path)
            record = {'url': url, 'bytes': path.stat().st_size, 'sha256': sha256(path),
                      'retrieved_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
            meta.write_text(json.dumps(record, indent=2), encoding='utf8')
            return record
        except (OSError, ValueError):
            if attempt == 1:
                raise
            time.sleep(2)
    raise RuntimeError('Unreachable')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--only', choices=list(URLS))
    args = parser.parse_args()
    for name, url in URLS.items():
        if not args.only or args.only == name:
            print(json.dumps({'file': name, **download(url, RAW / name)}), flush=True)


if __name__ == '__main__':
    main()
