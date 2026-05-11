"""Download src/ files in batches with rate limiting"""
import urllib.request
import json
import base64
import os
import time

API = 'https://api.github.com/repos/ponponon/claude_code_src'
HEADERS = {'Accept': 'application/vnd.github.v3+json', 'User-Agent': 'python-dl-batched'}
OUT = r'D:\1989n\ponponon_claude_code_src'

def api(path):
    req = urllib.request.Request(f'{API}{path}', headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

# Get tree listing (already have it cached from earlier runs)
tree = api('/git/trees/master?recursive=1')

src_blobs = [(item['path'], item['sha'], item['size'])
             for item in tree['tree']
             if item['type'] == 'blob' and item['path'].startswith('src/')]

# Check what's already downloaded
existing = set()
for root, dirs, files in os.walk(os.path.join(OUT, 'src')):
    for f in files:
        existing.add(os.path.relpath(os.path.join(root, f), OUT).replace('\\', '/'))

to_download = [(p, s, sz) for p, s, sz in src_blobs if p not in existing]
print(f"Total src files: {len(src_blobs)}")
print(f"Already downloaded: {len(existing)}")
print(f"Remaining: {len(to_download)}")

if not to_download:
    print("All files already downloaded!")
    exit()

# Download in batches of 50, with 65s delay between batches to stay under rate limit
BATCH = 50
total = len(to_download)
ok = skip = fail = 0

for batch_start in range(0, total, BATCH):
    batch = to_download[batch_start:batch_start + BATCH]
    batch_num = batch_start // BATCH + 1
    total_batches = (total + BATCH - 1) // BATCH

    for path, sha, size in batch:
        local = os.path.join(OUT, path)
        try:
            url = f'https://api.github.com/repos/ponponon/claude_code_src/git/blobs/{sha}'
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=30) as r:
                blob = json.loads(r.read())
            data = base64.b64decode(blob['content'])
            os.makedirs(os.path.dirname(local), exist_ok=True)
            with open(local, 'wb') as f:
                f.write(data)
            ok += 1
        except Exception as e:
            fail += 1
            print(f"  FAIL: {path} - {e}")

        time.sleep(0.3)  # Small delay to avoid bursts

    done = batch_start + len(batch)
    print(f"  Batch {batch_num}/{total_batches}: {done}/{total} done, ok={ok}, fail={fail}")

    if done < total:
        print(f"  Waiting 65s for rate limit reset...")
        time.sleep(65)

print(f"\nDone! ok={ok}, fail={fail}")
PYEOF