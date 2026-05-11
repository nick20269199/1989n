"""Download and verify key source files for authenticity"""
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
    return data

tree = api('/git/trees/master?recursive=1')

# Build a lookup
blobs = {}
for item in tree['tree']:
    if item['type'] == 'blob':
        blobs[item['path']] = item

# Download and verify key files
VERIFY_FILES = [
    'src/entrypoints/cli.tsx',
    'src/constants/prompts.ts',
    'src/voice/voiceModeEnabled.ts',
    'src/coordinator/coordinatorMode.ts',
    'src/commands.ts',
    'src/tools.ts',
    'src/buddy/CompanionSprite.tsx',
]

print("=== Verifying Key Source Files ===\n")
for path in VERIFY_FILES:
    if path not in blobs:
        print(f"[MISSING] {path}")
        continue

    f = blobs[path]
    data = download_blob(f['sha'], os.path.join(OUT, path))
    content = data.decode('utf-8', errors='replace')
    lines = content.split('\n')

    # Check for modifications
    has_chinese_comments = any('一' <= c <= '鿿' for c in content[:5000])
    has_dataeyes = 'dataeyes' in content.lower()
    has_ponponon = 'ponponon' in content.lower()

    # Check for known feature patterns
    has_buddy = 'buddy' in content.lower()
    has_kairos = 'kairos' in content.lower() or 'KAIROS' in content
    has_voice = 'voice' in content.lower()
    has_coordinator = 'coordinator' in content.lower()
    has_feature_flags = 'FEATURE' in content or 'featureFlag' in content or 'feature_flag' in content

    print(f"[{path}] ({len(lines)} lines, {len(content):,} chars)")
    print(f"  Chinese comments: {has_chinese_comments}")
    print(f"  DataEyesAI refs: {has_dataeyes}")
    print(f"  ponponon refs:   {has_ponponon}")
    print(f"  Feature patterns: BUDDY={has_buddy} KAIROS={has_kairos} VOICE={has_voice} COORD={has_coordinator}")

    # Show first few meaningful lines
    print(f"  First lines:")
    for line in lines[:8]:
        if line.strip():
            print(f"    | {line[:120]}")
    print()

# Now scan ALL src files for Chinese characters and DataEyes injections
print("=== Scanning for modifications across ALL src files ===\n")
modified_files = []
for path, f in blobs.items():
    if not path.endswith('.ts') and not path.endswith('.tsx') and not path.endswith('.js') and not path.endswith('.mjs'):
        continue
    if not path.startswith('src/'):
        continue
    # Quick check on the path name itself
    if any(kw in path.lower() for kw in ['dataeyes', 'ponponon', 'promo']):
        modified_files.append((path, 'SUSPICIOUS_FILENAME'))

print(f"Scanning {sum(1 for p in blobs if p.startswith('src/') and (p.endswith('.ts') or p.endswith('.tsx') or p.endswith('.js') or p.endswith('.mjs')))} source files...")

# Sample check: download and scan top 50 largest files + random sample
import random
src_files = [(p, blobs[p]) for p in blobs if p.startswith('src/') and (p.endswith('.ts') or p.endswith('.tsx') or p.endswith('.js') or p.endswith('.mjs'))]
largest = sorted(src_files, key=lambda x: x[1]['size'], reverse=True)[:30]
random.seed(42)
samples = random.sample([x for x in src_files if x not in largest], min(30, len(src_files) - len(largest)))
check_files = largest + samples

scan_count = 0
for path, f in check_files:
    try:
        data = download_blob(f['sha'], os.path.join(OUT, path))
        content = data.decode('utf-8', errors='replace')
        scan_count += 1

        # Check for Chinese characters (potential injections)
        chinese_chars = sum(1 for c in content if '一' <= c <= '鿿')
        dataeyes_hit = 'dataeyes' in content.lower()
        ponponon_hit = 'ponponon' in content.lower()

        if chinese_chars > 0 or dataeyes_hit or ponponon_hit:
            modified_files.append((path, f'CN={chinese_chars} DE={dataeyes_hit} PP={ponponon_hit}'))
            print(f"  [MODIFIED?] {path}: {chinese_chars} Chinese chars, dataeyes={dataeyes_hit}, ponponon={ponponon_hit}")
    except Exception as e:
        pass

if not modified_files:
    print("  No modifications found in sampled files!")
else:
    print(f"\n  {len(modified_files)} potentially modified files found")

print(f"\nScanned {scan_count} files for modifications")
print("\n=== Verification Complete ===")
PYEOF