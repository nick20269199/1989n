"""Test: Launch Playwright with Douyin app's user data directory"""
import shutil, time, os
from pathlib import Path
from playwright.sync_api import sync_playwright

# Source: Douyin app's roaming profile
src = Path(os.environ['APPDATA']) / 'douyin'
# Destination: working copy
dst = Path('/tmp/douyin_profile_copy')

# Remove old copy if exists
if dst.exists():
    shutil.rmtree(dst)
shutil.copytree(src, dst)
print(f'Copied profile to {dst}')

# Also copy Local State (needed for decryption key)
local_state_src = src / 'Local State'
if local_state_src.exists():
    shutil.copy2(local_state_src, dst / 'Local State')

with sync_playwright() as pw:
    context = pw.chromium.launch_persistent_context(
        user_data_dir=str(dst),
        headless=False,
        args=[
            '--disable-blink-features=AutomationControlled',
            '--no-sandbox',
        ],
        viewport={'width': 1280, 'height': 800},
        locale='zh-CN',
        timezone_id='Asia/Shanghai',
    )

    page = context.pages[0] if context.pages else context.new_page()
    page.goto('https://www.douyin.com', wait_until='domcontentloaded')
    time.sleep(3)

    # Check if logged in
    body = page.inner_text('body')[:1000]
    if '登录' in body[:200]:
        print('❌ Not logged in - login button still visible')
    else:
        print('✅ Logged in!')

    print(f'\nBody preview: {body[:300]}')

    # Try to navigate to a test page
    page2 = context.new_page()
    page2.goto('https://www.douyin.com/video/7642148370153762234', wait_until='domcontentloaded')
    time.sleep(3)
    body2 = page2.inner_text('body')[:2000]
    print(f'\nVideo page: {body2[:300]}')

    context.close()
