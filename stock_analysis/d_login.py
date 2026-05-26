"""
d_login.py — 抖音桌面端登录助手
一次扫码，永久复用。启动后在浏览器扫码登录，检测到登录后自动保存 session。
"""
import json, logging, time, sys
from pathlib import Path
from playwright.sync_api import sync_playwright

OUTPUT_DIR = Path("D:/1989n/stock_data/douyin")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

COOKIES_PATH = OUTPUT_DIR / "cookies.json"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("d_login")


def login():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )
        context = browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 800},
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
        )
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh'] });
            window.chrome = { runtime: {} };
        """)

        page = context.new_page()
        page.goto("https://www.douyin.com", wait_until="domcontentloaded")

        print("\n" + "=" * 60)
        print("  浏览器已打开 → 请扫码登录抖音")
        print("  登录成功后会自动保存 session...")
        print("=" * 60 + "\n")

        # Poll for login state (max 5 min)
        max_wait = 300
        for i in range(max_wait):
            try:
                body = page.inner_text("body")

                # Login detected: "登录" button gone + user-specific content present
                has_login_btn = "登录" in body[:300]
                has_user_content = any(
                    kw in body for kw in ["消息", "私信"]
                )

                if has_user_content or not has_login_btn:
                    # Double-check with a navigation
                    time.sleep(2)

                    # Save session
                    context.storage_state(path=str(COOKIES_PATH))
                    print(f"\n  ✅ 登录成功！session 已保存到 {COOKIES_PATH}")
                    print(f"    后续所有提取自动复用此 session\n")
                    browser.close()
                    return True

            except Exception:
                pass

            if i % 30 == 0 and i > 0:
                print(f"  等待登录中... ({i}s)")

            time.sleep(1)

        print("\n  ⏰ 超时未检测到登录\n")
        browser.close()
        return False


if __name__ == "__main__":
    success = login()
    sys.exit(0 if success else 1)
