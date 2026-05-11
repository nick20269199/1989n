"""Extract source files from cli.js.map"""
import json
import os

MAP_PATH = r'D:\1989n\claude-code-package\package\cli.js.map'
OUT_DIR = r'D:\1989n\claude-code-source'

print(f"Reading source map ({os.path.getsize(MAP_PATH)/1024/1024:.1f} MB)...")
with open(MAP_PATH, 'r', encoding='utf-8') as f:
    sm = json.load(f)

print(f"Version: {sm.get('version')}")
print(f"Sources: {len(sm.get('sources', []))}")
print(f"SourcesContent: {len(sm.get('sourcesContent', []))}")

sources = sm.get('sources', [])
contents = sm.get('sourcesContent', [])
print(f"Mappings length: {len(sm.get('mappings', '')):,} chars")

if len(sources) != len(contents):
    print(f"WARNING: sources ({len(sources)}) != sourcesContent ({len(contents)})")

os.makedirs(OUT_DIR, exist_ok=True)

# Count by directory
dirs = {}
total_bytes = 0
extracted = 0
skipped = 0

for i, (src, content) in enumerate(zip(sources, contents)):
    if content is None:
        skipped += 1
        continue

    # Normalize path
    src = src.replace('../../', '').replace('../', '')
    filepath = os.path.join(OUT_DIR, src)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        extracted += 1
        total_bytes += len(content)

        # Track dirs
        d = os.path.dirname(src).split('/')[0] if '/' in src else '(root)'
        dirs[d] = dirs.get(d, 0) + 1
    except Exception as e:
        print(f"Error writing {src}: {e}")

print(f"\nExtracted: {extracted} files")
print(f"Skipped (null content): {skipped}")
print(f"Total: {total_bytes:,} bytes ({total_bytes/1024/1024:.1f} MB)")
print(f"Output: {OUT_DIR}")
print(f"\nTop directories:")
for d, count in sorted(dirs.items(), key=lambda x: -x[1])[:20]:
    print(f"  {d:30s} {count:>4d} files")

# Save a file manifest
manifest_path = os.path.join(OUT_DIR, 'MANIFEST.txt')
with open(manifest_path, 'w') as f:
    for src in sources:
        f.write(src + '\n')
print(f"\nManifest saved to {manifest_path}")
PYEOF