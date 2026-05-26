"""
Brute-force ByteDance v10_tt cookie encryption.
Known plaintext: enter_pc_once = "1"
"""
import json, os, sqlite3, base64
from pathlib import Path
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

roaming = Path(os.environ['APPDATA']) / 'douyin'

# Get AES key
ls = json.loads((roaming / 'Local State').read_text(encoding='utf-8'))
import win32crypt
aes_key = win32crypt.CryptUnprotectData(base64.b64decode(ls['os_crypt']['encrypted_key'])[5:], None, None, None, 0)[1]
print(f'AES key: {aes_key.hex()[:32]}...')

# Read the enter_pc_once encrypted value
conn = sqlite3.connect(f'file:{roaming / "tt_Cookies"}?mode=ro', uri=True)
row = conn.execute(
    "SELECT host_key, name, encrypted_value, value FROM cookies WHERE name='enter_pc_once'"
).fetchone()
conn.close()

ev = row[2]  # encrypted_value (bytes)
print(f'Encrypted ({len(ev)} bytes): {ev.hex()}')

# Try ALL possible combinations
def try_decrypt(enc, key, nonce_start, nonce_size, tag_size, prefix_size=6, aad=None):
    """Try GCM decryption with specified parameters"""
    if len(enc) < prefix_size + nonce_size + tag_size:
        return None
    nonce = enc[prefix_size + nonce_start:prefix_size + nonce_start + nonce_size]
    ct_start = prefix_size + nonce_start + nonce_size
    ct = enc[ct_start:-tag_size]
    tag = enc[-tag_size:]

    try:
        if aad:
            cipher = Cipher(algorithms.AES(key), modes.GCM(nonce, tag))
            decryptor = cipher.decryptor()
            decryptor.authenticate_additional_data(aad)
            plain = decryptor.update(ct) + decryptor.finalize()
        else:
            cipher = Cipher(algorithms.AES(key), modes.GCM(nonce, tag))
            decryptor = cipher.decryptor()
            plain = decryptor.update(ct) + decryptor.finalize()
        return plain
    except Exception:
        return None

def try_raw_ctr(enc, key, nonce_start, nonce_size, prefix_size=6):
    """Try AES-CTR (no auth tag)"""
    if len(enc) < prefix_size + nonce_size:
        return None
    nonce = enc[prefix_size + nonce_start:prefix_size + nonce_start + nonce_size]
    ct = enc[prefix_size + nonce_start + nonce_size:]
    try:
        cipher = Cipher(algorithms.AES(key), modes.CTR(nonce))
        decryptor = cipher.decryptor()
        plain = decryptor.update(ct) + decryptor.finalize()
        return plain
    except Exception as e:
        return None

results = []

# Strategy 1: Standard GCM with different offsets
for prefix in [3, 6]:
    for nonce_s in range(0, 8):
        for nonce_sz in [8, 11, 12, 16]:
            for tag_sz in [8, 12, 16]:
                r = try_decrypt(ev, aes_key, nonce_s, nonce_sz, tag_sz, prefix)
                if r:
                    results.append(('GCM', prefix, nonce_s, nonce_sz, tag_sz, r.hex(), r))

# Strategy 2: GCM with AAD (cookie domain context)
for prefix in [6]:
    for aad_val in [b'douyin', b'.douyin.com', b'enter_pc_once', b'']:
        for nonce_sz in [12]:
            r = try_decrypt(ev, aes_key, 0, nonce_sz, 16, prefix, aad=aad_val)
            if r:
                results.append(('GCM+AAD', prefix, 0, nonce_sz, 16, r.hex(), r, aad_val))

# Strategy 3: AES-CTR (no tag verification)
for prefix in [3, 6]:
    for nonce_s in range(0, 8):
        for nonce_sz in [8, 12, 16]:
            r = try_raw_ctr(ev, aes_key, nonce_s, nonce_sz, prefix)
            if r:
                results.append(('CTR', prefix, nonce_s, nonce_sz, 0, r.hex(), r))

for r in results:
    tag = r[-1] if len(r) > 6 else ''
    r_type = r[0]
    plain_hex = r[5]
    print(f'{r_type} prefix={r[1]} ns={r[2]} nsz={r[3]} tsz={r[4]} => {plain_hex}')
    # Try to decode as text
    try:
        plain_bytes = bytes.fromhex(plain_hex)
        txt = plain_bytes.decode('utf-8', errors='replace')
        if len(txt) < 50:
            print(f'  TEXT: {txt}')
    except:
        pass

if not results:
    print('No decryption worked')
