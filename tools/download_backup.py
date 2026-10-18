"""Download selected release parts, verify SHA256, and restore original filenames."""
import argparse
import hashlib
import json
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BLOCK = 8 * 1024 ** 2


def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(BLOCK), b''):
            h.update(block)
    return h.hexdigest()


def matches(path, record):
    return path.is_file() and path.stat().st_size == record['size'] and sha256(path) == record['sha256']


def download(record, dest):
    target = dest / record['name']
    if matches(target, record):
        print('Already verified: ' + target.name, flush=True)
        return target
    if target.exists():
        raise RuntimeError('Existing part has unexpected contents; move it aside: ' + str(target))
    temporary = target.with_suffix(target.suffix + '.download')
    for attempt in range(1, 4):
        try:
            offset = temporary.stat().st_size if temporary.exists() else 0
            if offset > record['size']:
                raise RuntimeError('Partial file exceeds expected size: ' + str(temporary))
            if offset == record['size']:
                if sha256(temporary) == record['sha256']:
                    temporary.replace(target)
                    return target
                temporary.unlink()
                offset = 0
            headers = {'User-Agent': 'modelsave-backup-downloader'}
            if offset:
                headers['Range'] = f'bytes={offset}-'
            request = urllib.request.Request(record['url'], headers=headers)
            with urllib.request.urlopen(request, timeout=120) as response:
                resume = response.status == 206 and response.headers.get('Content-Range', '').startswith(f'bytes {offset}-')
                if response.status == 206 and not resume:
                    raise RuntimeError('Server returned an unexpected byte range')
                with temporary.open('ab' if resume else 'wb') as stream:
                    for block in iter(lambda: response.read(BLOCK), b''):
                        stream.write(block)
            if temporary.stat().st_size < record['size']:
                raise IOError('Connection ended early; keeping downloaded bytes for resume')
            if not matches(temporary, record):
                temporary.unlink()
                raise RuntimeError('Downloaded part failed SHA256 verification')
            temporary.replace(target)
            print('Downloaded and verified: ' + target.name, flush=True)
            return target
        except Exception:
            if attempt == 3:
                raise
            print(f'Retrying {record["name"]}, attempt {attempt + 1}/3', flush=True)
            time.sleep(2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--only', choices=['handoff', 'model', 'all'], default='all')
    parser.add_argument('--dest', type=Path, default=ROOT / 'downloads')
    parser.add_argument('--local-parts', type=Path, help='Use existing parts without downloading')
    parser.add_argument('--verify-only', action='store_true', help='Verify parts and complete-file hashes without merging')
    args = parser.parse_args()
    manifest = json.loads((ROOT / 'backup_manifest.json').read_text(encoding='utf-8'))
    if args.verify_only and not args.local_parts:
        parser.error('--verify-only requires --local-parts')
    if not args.verify_only:
        args.dest.mkdir(parents=True, exist_ok=True)
    for artifact in manifest['artifacts']:
        if args.only not in ('all', artifact['id']):
            continue
        target = args.dest / artifact['filename']
        if Path(artifact['filename']).name != artifact['filename']:
            raise RuntimeError('Unsafe output filename')
        if not args.verify_only and target.exists():
            if matches(target, artifact):
                print('Original file already verified: ' + target.name, flush=True)
                continue
            raise RuntimeError('Refusing to overwrite an existing original file: ' + str(target))
        parts = []
        for record in artifact['parts']:
            if Path(record['name']).name != record['name']:
                raise RuntimeError('Unsafe part filename')
            if args.local_parts:
                part = args.local_parts / record['name']
                if not matches(part, record):
                    raise RuntimeError('Local part failed verification: ' + str(part))
                parts.append(part)
            else:
                parts.append(download(record, args.dest))
        combined = hashlib.sha256()
        total = 0
        temporary = target.with_suffix(target.suffix + '.merging')
        out = None if args.verify_only else temporary.open('wb')
        try:
            for part in parts:
                with part.open('rb') as stream:
                    for block in iter(lambda: stream.read(BLOCK), b''):
                        combined.update(block)
                        total += len(block)
                        if out:
                            out.write(block)
        finally:
            if out:
                out.close()
        if total != artifact['size'] or combined.hexdigest() != artifact['sha256']:
            raise RuntimeError('Complete-file verification failed: ' + artifact['filename'])
        if not args.verify_only:
            temporary.replace(target)
        print(f'Complete SHA256 verified: {artifact["filename"]} ({total} bytes)', flush=True)


if __name__ == '__main__':
    main()
