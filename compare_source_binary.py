import os

src_dir = r'D:\1989n\claude-code-source\src'
cli_js = r'D:\1989n\claude-code-package\package\cli.js'

with open(cli_js, 'rb') as f:
    bundle = f.read()

eliminated = []
retained = []

for root, dirs, files in os.walk(src_dir):
    for fn in files:
        if not fn.endswith(('.ts', '.tsx')):
            continue
        rel = os.path.relpath(os.path.join(root, fn), src_dir)
        rel = rel.replace('\\', '/')
        name_hint = fn.replace('.tsx', '').replace('.ts', '').encode()
        if name_hint in bundle:
            retained.append(rel)
        else:
            eliminated.append(rel)

print(f"Modules with trace in binary: {len(retained)}")
print(f"Modules COMPLETELY eliminated: {len(eliminated)}")
print()

elim_by_dir = {}
for m in eliminated:
    d = m.split('/')[0]
    elim_by_dir[d] = elim_by_dir.get(d, 0) + 1

print("=== Eliminated by directory ===")
for d, n in sorted(elim_by_dir.items(), key=lambda x: -x[1]):
    print(f"  {d:30s} {n:>4d} files")

print()
print("=== All eliminated modules ===")
for m in sorted(eliminated):
    print(f"  {m}")
PYEOF