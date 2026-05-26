"""
Copy Douyin app user data directory (skip locked files),
then launch Playwright Chromium with the copy.
"""
import shutil, os, time, json
from pathlib import Path
from playwright.sync_api import sync_playwright

src = Path(os.environ['APPDATA']) / 'douyin'
dst = Path('/tmp/douyin_profile_v2')

# Clean up previous
if dst.exists():
    shutil.rmtree(dst)

# Copy with error handling for locked files
def ignore_locked(src, names):
    ignored = set()
    for n in names:
        p = os.path.join(src, n)
        try:
            if os.path.isfile(p):
                with open(p, 'rb') as f:
                    f.read(1)
        except (PermissionError, OSError):
            ignored.add(n)
            print(f'  skipping locked: {n}')
    return ignored

print('Copying profile (skipping locked files)...')
shutil.copytree(src, dst, ignore=ignore_locked, dirs_exist_ok=True)
print(f'Profile copied to {dst}')

# Ensure Local State exists (needed for os_crypt)
ls_src = src / 'Local State'
ls_dst = dst / 'Local State'
if ls_src.exists() and not ls_dst.exists():
    try:
        shutil.copy2(ls_src, ls_dst)
    except:
        pass

# Now try to use it with Playwright
print('\nLaunching Playwright with copied profile...')

with sync_playwright() as pw:
    context = pw.chromium.launch_persistent_context(
        user_data_dir=str(dst),
        headless=True,  # can change to False for debugging
        args=[
            '--disable-blink-features=AutomationControlled',
            '--no-sandbox',
            '--disable-features=IsolateOrigins,site-per-process',
        ],
        viewport={'width': 1920, 'height': 1080},
        locale='zh-CN',
        timezone_id='Asia/Shanghai',
        user_agent=(
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/124.0.0.0 Safari/537.36'
        ),
    )

    # Add anti-detection
    context.add_init_script('''
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
        Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh'] });
        window.chrome = { runtime: {} };
    ''')

    page = context.pages[0] if context.pages else context.new_page()
    page.goto('https://www.douyin.com', wait_until='domcontentloaded', timeout=30000)
    page.wait_for_timeout(5000)

    body = page.inner_text('body')[:500]
    has_login = '登录' in body[:200]
    has_user = '消息' in body[:2000] or '私信' in body[:2000]
    print(f'Login button: {has_login}')
    print(f'User content: {has_user}')
    print(f'Status: {"✅ LOGGED IN" if not has_login or has_user else "❌ NOT LOGGED IN"}')
    print(f'Body: {body[:300]}')

    if not has_login or has_user:
        # Save the working session
        out_path = Path('D:/1989n/stock_data/douyin/cookies.json')
        context.storage_state(path=str(out_path))
        print(f'Session saved to {out_path}')

    context.close()
