"""Prepare the two explicitly selected artifacts without modifying either source."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TAG = 'v16-handoff-20261019'
CHUNK = 1024 ** 3
BLOCK = 8 * 1024 ** 2
ARTIFACTS = [
    ('handoff', 'v16-handoff-20261018.zip',
     ROOT.parent / '生图测试结果/FLUX3蒸馏版_27B扩写_交接包_20261018.zip',
     3145801121, 'c6b17c4a7e612d633ea50b0cfc83bb8e0867e37f2f35fef6e80e8da4b89facfb'),
    ('model', 'flux3-distilled-int8.safetensors',
     Path('C:/QwenSceneTestsV16/runtime/v16_comfy/models/diffusion_models/flux3_image_klein_sd_int8_convrot.safetensors'),
     5827874779, '847d8933548afd93df4af2cac2498e70891bf28d9dae06d695f536992e168fe2'),
]


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(BLOCK), b''):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', type=Path, default=ROOT / 'release_assets')
    args = parser.parse_args()
    args.stage.mkdir(parents=True, exist_ok=True)
    manifest = {'schema_version': 1, 'repository': 'fak123456/modelsave',
                'release_tag': TAG, 'part_size_bytes': CHUNK, 'artifacts': []}
    checksums = []
    for kind, prefix, source, expected_size, expected_sha in ARTIFACTS:
        before = source.stat()
        if before.st_size != expected_size:
            raise RuntimeError(f'Source size differs: {source.name}')
        whole = hashlib.sha256()
        parts = []
        with source.open('rb') as stream:
            remaining = expected_size
            index = 1
            while remaining:
                name = f'{prefix}.part{index:03d}'
                target = args.stage / name
                temporary = target.with_suffix(target.suffix + '.preparing')
                size = min(CHUNK, remaining)
                part_hash = hashlib.sha256()
                left = size
                with temporary.open('wb') as out:
                    while left:
                        block = stream.read(min(BLOCK, left))
                        if not block:
                            raise RuntimeError('Source ended before its declared size')
                        out.write(block)
                        part_hash.update(block)
                        whole.update(block)
                        left -= len(block)
                temporary.replace(target)
                sha = part_hash.hexdigest()
                parts.append({'name': name, 'size': size, 'sha256': sha,
                              'url': f'https://github.com/fak123456/modelsave/releases/download/{TAG}/{name}'})
                checksums.append(f'{sha}  {name}')
                print(f'Prepared {name}: {size} bytes, sha256={sha}', flush=True)
                remaining -= size
                index += 1
        after = source.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise RuntimeError(f'Source changed during preparation: {source.name}')
        if whole.hexdigest() != expected_sha:
            raise RuntimeError(f'Source SHA256 differs: {source.name}')
        record = {'id': kind, 'filename': source.name, 'size': expected_size,
                  'sha256': expected_sha, 'parts': parts}
        if kind == 'model':
            record.update(repository='black-forest-labs/flux-3-image-klein-comfy',
                          revision='5c9b714851dc072b04a23ef6d2d36421f5ccb3a0',
                          remote_path='diffusion_models/flux3_image_klein_sd_int8_convrot.safetensors',
                          recommended_relative_path='runtime/v16_comfy/models/diffusion_models/' + source.name,
                          license='flux-kommunity-license')
        manifest['artifacts'].append(record)
        checksums.append(f'{expected_sha}  {source.name}')
    manifest['total_bytes'] = sum(a['size'] for a in manifest['artifacts'])
    (ROOT / 'backup_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (ROOT / 'SHA256SUMS.txt').write_text('\n'.join(checksums) + '\n', encoding='utf-8')
    print(f'Ready: {manifest["total_bytes"]} bytes in {sum(len(a["parts"]) for a in manifest["artifacts"])} parts.', flush=True)


if __name__ == '__main__':
    main()
