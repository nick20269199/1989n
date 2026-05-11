"""
大V雷达 - 抖音登录态刷新
打开浏览器 → 扫码登录 → 自动检测登录成功 → 保存状态

用法:
  python vv_login.py
"""

import asyncio
import sys
from pathlib import Path
from playwright.async_api import async_playwright

STATE_DIR = Path("D:/1989n/stock_data/vv_browser_state")
STATE_FILE = STATE_DIR / "state.json"


async def check_logged_in(page):
    """检测是否已登录 —— 检查页面是否有用户信息"""
    try:
        # 方法1: 检查 localStorage 中是否有登录 token
        has_token = await page.evaluate("""() => {
            const keys = Object.keys(localStorage);
            return keys.some(k => k.includes('uid') || k.includes('user') || k.includes('login') || k.includes('token'));
        }""")
        if has_token:
            return True

        # 方法2: 检查 cookies 中是否有登录相关 cookie
        cookies = await page.context.cookies()
        for c in cookies:
            if 'passport' in c.get('name', '') or 'odin_tt' in c.get('name', '') or 'session' in c.get('name', ''):
                return True

        return False
    except Exception:
        return False


async def main():
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(STATE_DIR / "user_data"),
            headless=False,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
            ],
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
        )

        page = await context.new_page()
        await page.goto('https://www.douyin.com/', wait_until='load', timeout=60000)
        await page.wait_for_timeout(5000)

        print("=" * 60)
        print("浏览器已打开，请扫码登录抖音")
        print("等待登录中... (自动检测，无需手动回车)")
        print("=" * 60)

        # 轮询检测登录状态，最多等 120 秒
        logged_in = await check_logged_in(page)
        waited = 0
        while not logged_in and waited < 120:
            await asyncio.sleep(2)
            waited += 2
            logged_in = await check_logged_in(page)
            if waited % 10 == 0:
                print(f"  等待中... ({waited}s)")

        if logged_in:
            print("检测到登录成功!")
        else:
            print("超时未检测到登录。如果你已登录，按 Enter 继续保存状态...")
            print("如果未登录，请关闭浏览器后重新运行。")

        await asyncio.sleep(1)

        # 保存 storage state
        await context.storage_state(path=str(STATE_FILE))
        print(f"登录态已保存: {STATE_FILE}")
        await context.close()


if __name__ == '__main__':
    asyncio.run(main())
