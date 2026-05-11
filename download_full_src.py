"""Download ALL src/ files from ponponon/claude_code_src via GitHub API"""
import urllib.request
import json
import base64
import os
import time
import sys

API = 'https://api.github.com/repos/ponponon/claude_code_src'
HEADERS = {'Accept': 'application/vnd.github.v3+json', 'User-Agent': 'python-dl'}
OUT = r'D:\1989n\ponponon_claude_code_src'

def api(path):
    req = urllib.request.Request(f'{API}{path}', headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

def download_blob(sha, local_path, expected_size):
    """Download a single file via blob API, skip if exists with correct size"""
    if os.path.exists(local_path):
        actual = os.path.getsize(local_path)
        if actual == expected_size:
            return 'skip'
        # else: file exists but wrong size, re-download

    url = f'https://api.github.com/repos/ponponon/claude_code_src/git/blobs/{sha}'
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=60) as r:
                blob = json.loads(r.read())
            data = base64.b64decode(blob['content'])
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            with open(local_path, 'wb') as f:
                f.write(data)
            return 'ok'
        except Exception as e:
            if attempt == 2:
                return f'fail: {e}'
            time.sleep(2)

print("=== Fetching full repo tree ===")
tree = api('/git/trees/master?recursive=1')

# Filter: only src/ files
src_blobs = [(item['path'], item['sha'], item['size'])
             for item in tree['tree']
             if item['type'] == 'blob' and item['path'].startswith('src/')]

total = len(src_blobs)
total_size = sum(s for _, _, s in src_blobs)
print(f"Files to download: {total}")
print(f"Total size: {total_size:,} bytes ({total_size/1024/1024:.1f} MB)")
print()

# Download with progress
ok = skip = fail = 0
downloaded_bytes = 0
start_time = time.time()
batch_start = time.time()

for i, (path, sha, size) in enumerate(src_blobs):
    local = os.path.join(OUT, path)
    result = download_blob(sha, local, size)

    if result == 'ok':
        ok += 1
        downloaded_bytes += size
    elif result == 'skip':
        skip += 1
    else:
        fail += 1
        print(f"  FAIL: {path} - {result}")

    # Progress every 50 files or every 10 seconds
    if (i + 1) % 50 == 0 or i == total - 1:
        elapsed = time.time() - start_time
        batch_elapsed = time.time() - batch_start
        rate = (ok * 1.0) / elapsed if elapsed > 0 else 0
        eta = (total - ok - skip) / rate if rate > 0 else 0
        print(f"  [{i+1}/{total}] ok={ok} skip={skip} fail={fail} | "
              f"{downloaded_bytes/1024/1024:.1f}MB | "
              f"{rate:.1f} files/s | ETA {eta/60:.0f}m | "
              f"elapsed {elapsed/60:.1f}m")
        batch_start = time.time()

    # Rate limiting: max ~10 req/s to be safe
    if i % 10 == 9:
        time.sleep(0.1)

elapsed = time.time() - start_time
print(f"\n=== Download Complete ===")
print(f"Total: {total} files, {total_size/1024/1024:.1f} MB")
print(f"OK: {ok}  Skipped: {skip}  Failed: {fail}")
print(f"Time: {elapsed/60:.1f} minutes")
print(f"Downloaded: {downloaded_bytes/1024/1024:.1f} MB")
PYEOF