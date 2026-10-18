"""Publish verified release parts using a Git Credential Manager login; never log credentials."""
import argparse
import hashlib
import json
import os
import socket
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
import truststore
from requests.adapters import HTTPAdapter
from urllib3.connection import HTTPConnection

truststore.inject_into_ssl()
ROOT = Path(__file__).resolve().parents[1]
API = 'https://api.github.com'
REPO = 'fak123456/modelsave'
BLOCK = 8 * 1024 ** 2


class PhysicalUploadAdapter(HTTPAdapter):
    def __init__(self, interface, source_ip):
        self.interface = interface
        self.source_ip = source_ip
        super().__init__()

    def init_poolmanager(self, connections, maxsize, block=False, **kwargs):
        # Windows IP_UNICAST_IF applies only to these upload sockets, not system routes.
        kwargs['socket_options'] = HTTPConnection.default_socket_options + [
            (socket.IPPROTO_IP, 31, socket.htonl(self.interface)),
            (socket.SOL_SOCKET, socket.SO_SNDBUF, 4 * 1024 ** 2)]
        kwargs['source_address'] = (self.source_ip, 0)
        return super().init_poolmanager(connections, maxsize, block=block, **kwargs)


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(BLOCK), b''):
            h.update(block)
    return h.hexdigest()


def credential():
    env = dict(os.environ, GIT_TERMINAL_PROMPT='0', GCM_INTERACTIVE='never')
    result = subprocess.run(['git', 'credential', 'fill'],
                            input='protocol=https\nhost=github.com\nusername=fak123456\n\n',
                            text=True, capture_output=True, env=env, cwd=ROOT)
    if result.returncode:
        raise RuntimeError('No local GitHub credential. Sign in through Git Credential Manager first.')
    values = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    token = values.get('password')
    if not token:
        raise RuntimeError('Git Credential Manager returned no usable credential.')
    return token


class ProgressFile:
    def __init__(self, path):
        self.stream = path.open('rb')
        self.path = path
        self.started = self.last = time.monotonic()

    def __getattr__(self, name):
        return getattr(self.stream, name)

    def read(self, size=-1):
        block = self.stream.read(size)
        now = time.monotonic()
        if now - self.last >= 20:
            sent = self.stream.tell()
            print(f'{self.path.name}: sent {sent / 1024**2:.1f} MiB, '
                  f'{sent / max(now-self.started, .001) / 1024**2:.2f} MiB/s', flush=True)
            self.last = now
        return block


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-auth', action='store_true')
    parser.add_argument('--parts', nargs='+', help='Upload only these declared assets; keep the release draft')
    parser.add_argument('--upload-interface', type=int, help='Windows physical IPv4 interface index')
    parser.add_argument('--upload-source-ip', help='IPv4 address belonging to that interface')
    args = parser.parse_args()
    if bool(args.upload_interface) != bool(args.upload_source_ip):
        parser.error('--upload-interface and --upload-source-ip must be used together')
    session = requests.Session()
    if args.upload_interface:
        if os.name != 'nt':
            parser.error('Physical interface selection is implemented for Windows only')
        session.trust_env = False
        session.mount('https://uploads.github.com/', PhysicalUploadAdapter(args.upload_interface, args.upload_source_ip))
        print(f'Large uploads bound to physical interface {args.upload_interface}.', flush=True)
    session.headers.update({'Authorization': 'Bearer ' + credential(),
                            'Accept': 'application/vnd.github+json',
                            'X-GitHub-Api-Version': '2022-11-28',
                            'User-Agent': 'modelsave-backup'})

    def api(method, path, allow_missing=False, **kwargs):
        url = path if path.startswith('https://') else API + path
        if urlparse(url).hostname not in ('api.github.com', 'uploads.github.com'):
            raise RuntimeError('Unexpected authenticated API host')
        response = session.request(method, url, timeout=(30, 180), **kwargs)
        if allow_missing and response.status_code == 404:
            return None
        if not response.ok:
            try:
                message = response.json().get('message', 'API request rejected')
            except ValueError:
                message = 'API request rejected'
            if response.status_code in (502, 503, 504):
                raise requests.HTTPError(f'Temporary GitHub API HTTP {response.status_code}')
            raise RuntimeError(f'GitHub API HTTP {response.status_code}: {message}')
        return response.json() if response.content else None

    user = api('GET', '/user')
    repo = api('GET', '/repos/' + REPO)
    print('Authenticated account: ' + user['login'], flush=True)
    if not repo.get('permissions', {}).get('push'):
        raise RuntimeError('The local account does not have repository write permission.')
    print('Repository write permission verified.', flush=True)
    if args.check_auth:
        return
    manifest = json.loads((ROOT / 'backup_manifest.json').read_text(encoding='utf-8'))
    tag = manifest['release_tag']
    assets = []
    for artifact in manifest['artifacts']:
        for part in artifact['parts']:
            assets.append((ROOT / 'release_assets' / part['name'], part['sha256'], part['size']))
    for name in ('backup_manifest.json', 'SHA256SUMS.txt', 'README.md',
                 'licenses/FLUX_LICENSE.md', 'licenses/FLUX_NOTICE.txt'):
        path = ROOT / name
        assets.append((path, digest(path), path.stat().st_size))
    if args.parts:
        selected = set(args.parts)
        assets = [row for row in assets if row[0].name in selected]
        if {row[0].name for row in assets} != selected:
            raise RuntimeError('Selected asset is not declared by this backup')
    print('Verifying local upload files...', flush=True)
    for path, expected, size in assets:
        if path.stat().st_size != size or digest(path) != expected:
            raise RuntimeError('Local upload file verification failed: ' + path.name)
    if not args.parts:
        subprocess.run(['git', '-c', 'credential.username=fak123456', 'push', '-u', 'origin', 'main'], cwd=ROOT, check=True)
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    release = api('GET', f'/repos/{REPO}/releases/tags/{tag}', allow_missing=True)
    if release is None:
        candidates = [r for r in api('GET', f'/repos/{REPO}/releases?per_page=100') if r['tag_name'] == tag]
        if len(candidates) > 1:
            raise RuntimeError('More than one release uses this backup tag; refusing to create another')
        release = candidates[0] if candidates else None
    if release is None:
        if args.parts:
            raise RuntimeError('The main publisher must create the draft release first')
        release = api('POST', f'/repos/{REPO}/releases', json={
            'tag_name': tag, 'target_commitish': commit, 'draft': True,
            'name': 'V16 交接包 + FLUX3 蒸馏模型（2026-10-19）',
            'body': '原样保存指定交接 ZIP（3.15GB）及 FLUX3 蒸馏 INT8 权重（5.83GB）。'
                    '9 个分片，共 8,973,675,900 字节。下载与合并方法见仓库 README；'
                    'backup_manifest.json 和 SHA256SUMS.txt 包含完整校验。'
                    '\n\n交接包本身不包含已安装环境、27B 或其他模型；安装与恢复说明在包内。'
                    '\n\nFLUX 模型须遵守随附的原始许可及归属声明。'})
    upload_url = release['upload_url'].split('{', 1)[0]

    def remote_assets():
        return api('GET', f'/repos/{REPO}/releases/{release["id"]}/assets?per_page=100')

    def verified(remote, size, sha):
        return remote.get('state') == 'uploaded' and remote.get('size') == size and remote.get('digest') == 'sha256:' + sha

    for index, (path, sha, size) in enumerate(assets, 1):
        for attempt in range(1, 4):
            existing = next((a for a in remote_assets() if a['name'] == path.name), None)
            if existing:
                if verified(existing, size, sha):
                    print(f'Verified remote {index}/{len(assets)}: {path.name}', flush=True)
                    break
                if existing.get('state') != 'starter' or not release.get('draft'):
                    raise RuntimeError('Existing remote asset differs; refusing to replace it: ' + path.name)
                api('DELETE', f'/repos/{REPO}/releases/assets/{existing["id"]}')
            print(f'Uploading {index}/{len(assets)}: {path.name}, {size} bytes, attempt {attempt}', flush=True)
            stream = ProgressFile(path)
            try:
                remote = api('POST', upload_url, params={'name': path.name}, data=stream,
                             headers={'Content-Type': 'application/octet-stream', 'Content-Length': str(size)})
                if not verified(remote, size, sha):
                    raise RuntimeError('GitHub did not confirm the expected asset digest: ' + path.name)
                print('Uploaded and SHA256 confirmed: ' + path.name, flush=True)
                break
            except requests.RequestException as exc:
                print(f'Transport interrupted ({type(exc).__name__}); checking remote before retry.', flush=True)
                if attempt == 3:
                    raise RuntimeError('Upload transport failed; rerun to resume completed parts.') from None
                time.sleep(3)
            finally:
                stream.close()
        else:
            raise RuntimeError('Asset upload did not finish: ' + path.name)
    remote = {a['name']: a for a in remote_assets()}
    for path, sha, size in assets:
        if not verified(remote.get(path.name, {}), size, sha):
            raise RuntimeError('Final remote verification failed: ' + path.name)
    if args.parts:
        print('Selected assets verified; release publication is left to the main publisher.', flush=True)
        return
    if release.get('draft'):
        release = api('PATCH', f'/repos/{REPO}/releases/{release["id"]}', json={'draft': False})
    receipt = {'repository': REPO, 'commit': commit, 'release_url': release['html_url'],
               'total_original_bytes': manifest['total_bytes'],
               'assets': [{'name': p.name, 'size': n, 'sha256': s} for p, s, n in assets],
               'all_remote_digests_match': True, 'published': not release.get('draft')}
    (ROOT / '.publish-state.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Published and verified: ' + release['html_url'], flush=True)


if __name__ == '__main__':
    main()
