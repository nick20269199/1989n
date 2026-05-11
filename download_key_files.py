"""Download key source files from ponponon/claude_code_src for verification"""
import urllib.request
import json
import base64
import os

API = 'https://api.github.com/repos/ponponon/claude_code_src'
HEADERS = {'Accept': 'application/vnd.github.v3+json', 'User-Agent': 'python-verify'}
OUT = r'D:\1989n\ponponon_claude_code_src'

def api(path):
    req = urllib.request.Request(f'{API}{path}', headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

def download_blob(sha, local_path):
    url = f'https://api.github.com/repos/ponponon/claude_code_src/git/blobs/{sha}'
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as r:
        blob = json.loads(r.read())
    data = base64.b64decode(blob['content'])
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    with open(local_path, 'wb') as f:
        f.write(data)
    return len(data)

# Step 1: Get full file tree (already know we have 4758 files)
# Let's get the listing in chunks by top-level directories
print("=== Getting directory listing ===")
tree = api('/git/trees/master?recursive=1')

# Group files by top-level dir
src_files = {}
for item in tree['tree']:
    if item['type'] == 'blob':
        parts = item['path'].split('/')
        top = parts[0]
        if top not in src_files:
            src_files[top] = []
        src_files[top].append(item)

print("Top-level directories:")
for d in sorted(src_files.keys()):
    total_size = sum(f.get('size', 0) for f in src_files[d])
    print(f"  {d:30s} {len(src_files[d]):>6d} files  {total_size:>12,} bytes")

# Step 2: Download key files for verification
KEY_FILES = [
    # Check if any Chinese comments or non-original code was injected
    'src/constants/features.ts',       # Feature flags - should contain BUDDY, KAIROS etc
    'src/constants/product.ts',       # Product constants
    'src/constants/flags.ts',         # Launch flags
    'src/entrypoints/cli.ts',         # Main CLI entry
    'src/commands/index.ts',          # Command index
    'src/tools/index.ts',             # Tools index
    'src/utils/auth.ts',              # Auth utilities
    'src/utils/security.ts',          # Security utils
    'src/components/App.tsx',         # Main app component
    'vendor/ink/build.js',            # Ink rendering
]

print("\n=== Downloading key files ===")
downloaded = {}
for pattern in KEY_FILES:
    found = None
    for f in tree['tree']:
        if f['type'] == 'blob' and f['path'].endswith(pattern.split('/')[-1]) or f['path'] == pattern:
            # Try exact match first
            pass

    # Find best match
    for f in tree['tree']:
        if f['type'] == 'blob':
            if f['path'] == pattern or f['path'].endswith('/' + pattern.split('/')[-1]):
                if pattern.count('/') == f['path'].count('/'):
                    found = f
                    break

    if found:
        size = download_blob(found['sha'], os.path.join(OUT, found['path']))
        downloaded[found['path']] = size
        print(f"  [OK] {found['path']} ({size:,} bytes)")
    else:
        print(f"  [MISS] {pattern}")

# Step 3: Also search for specific patterns across the tree
print("\n=== Searching for known feature flags ===")
# Download some more files that likely contain feature flags
flag_files = []
for f in tree['tree']:
    if f['type'] == 'blob':
        name = f['path'].lower()
        if any(kw in name for kw in ['feature', 'flag', 'launch', 'const', 'config', 'env']):
            if f['size'] < 100000:  # skip huge files
                flag_files.append(f)

print(f"Found {len(flag_files)} potential feature/config files")
for f in flag_files[:30]:
    print(f"  {f['path']:60s} {f['size']:>8,} bytes")

# Download some of these
for f in flag_files[:15]:
    try:
        local = os.path.join(OUT, f['path'])
        if not os.path.exists(local):
            download_blob(f['sha'], local)
        with open(local, 'r', encoding='utf-8', errors='replace') as fh:
            content = fh.read()
        # Check for key patterns
        has_buddy = 'BUDDY' in content or 'buddy' in content.lower()
        has_kairos = 'KAIROS' in content or 'kairos' in content.lower()
        has_voice = 'VOICE' in content
        has_web = 'WEB_BROWSER' in content
        flags_found = []
        if has_buddy: flags_found.append('BUDDY')
        if has_kairos: flags_found.append('KAIROS')
        if has_voice: flags_found.append('VOICE')
        if has_web: flags_found.append('WEB_BROWSER')
        if flags_found:
            print(f"  [FLAGS] {f['path']}: {', '.join(flags_found)}")
    except Exception as e:
        pass

print("\n=== Done ===")
PYEOF