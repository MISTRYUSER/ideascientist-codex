import concurrent.futures
import hashlib
import json
import subprocess
import time
from pathlib import Path

root = Path(__file__).resolve().parent.parent
target = root / 'data/SvalbardIdeaVault'
manifest = json.loads((root / 'config/public-vault-manifest.json').read_text())
revision = '64ab36be959afab06066f8c1e7ea292dba9362e5'

def sha256_file(path):
    digest = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()

def download(item):
    path = target / item['path']
    path.parent.mkdir(parents=True, exist_ok=True)
    expected = item['lfs']['oid']
    if path.exists() and path.stat().st_size == item['size']:
        if sha256_file(path) == expected:
            print('VERIFIED ' + item['path'], flush=True)
            return
    partial = path.with_suffix(path.suffix + '.partial')
    url = f'https://huggingface.co/datasets/Jerry999/SvalbardIdeaVault/resolve/{revision}/{item["path"]}'
    print('START ' + item['path'], flush=True)
    for attempt in range(30):
        if partial.exists() and partial.stat().st_size == item['size']:
            break
        result = subprocess.run(['curl', '--http1.1', '-L', '--fail', '--silent', '--show-error', '--connect-timeout', '30', '--max-time', '600', '--continue-at', '-', '-o', str(partial), url])
        if result.returncode == 0:
            break
        print(f'RESUME {item["path"]}: {partial.stat().st_size if partial.exists() else 0} bytes, attempt {attempt + 1}', flush=True)
        time.sleep(2)
    else:
        raise RuntimeError('download retries exhausted: ' + item['path'])
    assert partial.stat().st_size == item['size'], str(partial)
    assert sha256_file(partial) == expected, str(partial)
    partial.replace(path)
    print('DONE ' + item['path'], flush=True)

if __name__ == '__main__':
    files = sorted((i for i in manifest if i['type'] == 'file'), key=lambda i: i['size'])
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(download, files))
    print('DOWNLOAD COMPLETE: all 30 data shards verified', flush=True)
