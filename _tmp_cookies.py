"""Check Network/Cookies for different encryption or plaintext values"""
import json, os, sqlite3, base64
from pathlib import Path

roaming = Path(os.environ['APPDATA']) / 'douyin'

# Check Network/Cookies
net_cookies = roaming / 'Network' / 'Cookies'
print(f'Network/Cookies exists: {net_cookies.exists()}')
if net_cookies.exists():
    print(f'Size: {net_cookies.stat().st_size}')

    conn = sqlite3.connect(f'file:{net_cookies}?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    print(f'Tables: {[t[0] for t in tables]}')

    rows = conn.execute('''
        SELECT host_key, name, value, length(encrypted_value) as ev_len
        FROM cookies
        WHERE host_key LIKE '%douyin%' AND (length(value) > 0 OR length(encrypted_value) > 5)
        ORDER BY host_key
        LIMIT 20
    ''').fetchall()

    print(f'\nDouyin cookies with data: {len(rows)}')
    for r in rows:
        val = r['value'] if r['value'] else ''
        print(f'  {r["host_key"]:25s} {r["name"]:25s} plain={val[:40]!r:45s} ev_len={r["ev_len"]}')

    conn.close()

# Also check what processes are using tt_Cookies
print(f'\nChecking if tt_Cookies is locked...')
try:
    import msvcrt
    f = open(roaming / 'tt_Cookies', 'rb')
    f.close()
    print('tt_Cookies: accessible')
except Exception as e:
    print(f'tt_Cookies: locked ({e})')
