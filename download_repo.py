"""Download ponponon/claude_code_src via GitHub API"""
import urllib.request
import json
import base64
import os
import sys
import time

API = 'https://api.github.com/repos/ponponon/claude_code_src'
HEADERS = {'Accept': 'application/vnd.github.v3+json', 'User-Agent': 'python-dl'}
OUT = r'D:\1989n\ponponon_claude_code_src'
os.makedirs(OUT, exist_ok=True)

def api(path):
    req = urllib.request.Request(f'{API}{path}', headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

def download_file(path, sha, size):
    """Download a single file via blob API"""
    local = os.path.join(OUT, path)
    os.makedirs(os.path.dirname(local), exist_ok=True)
    if os.path.exists(local) and os.path.getsize(local) == size:
        return 'skip'

    url = f'https://api.github.com/repos/ponponon/claude_code_src/git/blobs/{sha}'
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as r:
        blob = json.loads(r.read())

    if blob.get('encoding') == 'base64':
        data = base64.b64decode(blob['content'])
    else:
        data = blob['content'].encode('utf-8')

    with open(local, 'wb') as f:
        f.write(data)
    return 'ok'

def walk_tree(sha, prefix=''):
    """Recursively walk git tree"""
    tree = api(f'/git/trees/{sha}?recursive=1')
    files = []
    for item in tree.get('tree', []):
        if item['type'] == 'blob':
            files.append((f"{prefix}{item['path']}", item['sha'], item['size']))
    return files

# 1. Get README
print("=== Downloading README ===")
readme = api('/readme')
content = base64.b64decode(readme['content']).decode('utf-8')
with open(os.path.join(OUT, 'README.md'), 'w', encoding='utf-8') as f:
    f.write(content)
print(f"README.md saved ({len(content)} chars)")

# 2. Get repo structure
print("\n=== Getting repo tree ===")
repo = api('')
default_branch = repo['default_branch']
print(f"Default branch: {default_branch}")
print(f"Description: {repo['description']}")
print(f"Stars: {repo['stargazers_count']}  Forks: {repo['forks_count']}")
print(f"Created: {repo['created_at']}  Pushed: {repo['pushed_at']}")

# 3. Get full tree (src/ and vendor/ dirs, skip node_modules and the big tgz)
print("\n=== Getting src/ tree ===")
src_tree = api(f'/git/trees/{default_branch}?recursive=1')
all_files = []
total_dirs = set()
for item in src_tree.get('tree', []):
    if item['type'] == 'blob':
        all_files.append(item)
    elif item['type'] == 'tree':
        total_dirs.add(item['path'])

print(f"Total files: {len(all_files)}")
print(f"Total dirs: {len(total_dirs)}")

# Show top-level structure
for item in src_tree.get('tree', []):
    if item['type'] == 'tree':
        print(f"  📁 {item['path']}/")

# Show file list summary
print("\n=== File list ===")
for f in sorted(all_files, key=lambda x: x['path']):
    print(f"  {f['path']:60s} {f.get('size',0):>10,} bytes")
PYEOF