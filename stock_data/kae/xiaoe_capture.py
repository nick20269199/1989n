"""
小鹅通网页版自动登录 + 课程抓取
全自动，只需用户扫一次微信二维码
"""
import os
import json
import time
import sys
from datetime import datetime

CAPTURE_DIR = "D:/1989n/stock_data/kae"
COOKIE_FILE = os.path.join(CAPTURE_DIR, "xiaoe_cookies.json")
COURSE_FILE = os.path.join(CAPTURE_DIR, "xiaoe_courses.json")
os.makedirs(CAPTURE_DIR, exist_ok=True)

XIAOE_URL = "https://study.xiaoe-tech.com/t_l/learnIndex?type=wx#/muti_index"


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)


def capture():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        log("Launching Edge browser...")
        browser = p.chromium.launch(
            channel="msedge",
            headless=False,
        )

        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
        )

        page = context.new_page()

        # Track all admin API responses
        api_responses = []
        def on_response(response):
            url = response.url
            if "admin.xiaoe-tech.com" in url or "xiaoeknow" in url:
                try:
                    body = response.text()
                    api_responses.append({"url": url, "status": response.status, "body": body[:5000]})
                except:
                    pass
        page.on("response", on_response)

        # Track cookie changes
        auth_detected = False
        def on_cookie(cookie):
            nonlocal auth_detected
            if any(k in cookie.get('name', '').lower() for k in ['token', 'session', 'auth', 'sid', 'login', 'user', 'access']):
                auth_detected = True
        context.on('cookie', on_cookie)

        log("Navigating to 小鹅通...")
        page.goto(XIAOE_URL, wait_until="domcontentloaded", timeout=30000)

        log("=" * 60)
        log("浏览器窗口已打开，请用微信扫码登录")
        log("扫码登录后页面会自动跳转，我自动抓取数据")
        log("=" * 60)

        # Step 1: Wait for login page to fully load (redirect from learnIndex to learnLogin)
        has_login_url = False
        for i in range(30):
            time.sleep(1)
            try:
                url = page.url
                if 'login' in url.lower():
                    has_login_url = True
                    log("Login page detected, waiting for QR scan...")
                    break
            except:
                pass

        # Step 2: Wait for user to scan QR code and be redirected back to main page
        logged_in = False
        for i in range(180):
            time.sleep(1)

            # Check URL - after login it should redirect back to main page (not login)
            current_url = page.url
            is_login_page = 'login' in current_url.lower()

            # Check for auth cookies
            cookies = context.cookies()
            has_auth_cookie = False
            for c in cookies:
                cname = c.get('name', '').lower()
                cvalue = c.get('value', '')
                if any(k in cname for k in ['ke_sig', 'token', 'session', 'auth', 'sid', 'xs_token', 'access_token']):
                    has_auth_cookie = True
                    if not logged_in:
                        log(f"Auth cookie found: {c['name']}={cvalue[:30]}...")
                    break

            # Also check localStorage for auth tokens
            if not has_auth_cookie:
                try:
                    storage_json = page.evaluate("() => JSON.stringify(window.localStorage)")
                    storage = json.loads(storage_json)
                    for key in storage:
                        if any(k in key.lower() for k in ['token', 'auth', 'session', 'user', 'xs']):
                            has_auth_cookie = True
                            if not logged_in:
                                log(f"Auth localStorage key found: {key}")
                            break
                except:
                    pass

            # Signal: Not on login page AND (has auth cookie OR URL has content indicators)
            if not is_login_page and (has_auth_cookie or 'muti_index' in current_url or 'course' in current_url):
                if not logged_in:
                    logged_in = True
                    log("Login detected!")
                    break

            if logged_in:
                break

            if i % 15 == 0:
                log(f"等待扫码... ({i}s)")

        if not logged_in:
            log("Login detection timeout, proceeding anyway...")

        # Save cookies
        cookies = context.cookies()
        with open(COOKIE_FILE, "w", encoding="utf-8") as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)
        log(f"Cookies saved ({len(cookies)} cookies)")

        # Save localStorage
        try:
            storage = page.evaluate("() => JSON.stringify(window.localStorage)")
            with open(os.path.join(CAPTURE_DIR, "xiaoe_storage.json"), "w", encoding="utf-8") as f:
                f.write(storage)
            log(f"localStorage saved ({len(storage)} bytes)")
        except Exception as e:
            log(f"localStorage error: {e}")

        # Save current page state
        log(f"Current URL: {page.url}")
        log(f"Page title: {page.title()}")

        try:
            html = page.content()
            with open(os.path.join(CAPTURE_DIR, "xiaoe_page.html"), "w", encoding="utf-8") as f:
                f.write(html)
            log(f"HTML saved ({len(html)} bytes)")

            # Try to get visible text
            text = page.inner_text("body")
            with open(os.path.join(CAPTURE_DIR, "xiaoe_page_text.txt"), "w", encoding="utf-8") as f:
                f.write(text[:10000])
            log(f"Page text saved ({len(text)} chars)")
        except Exception as e:
            log(f"Page content error: {e}")

        # Save API responses
        with open(os.path.join(CAPTURE_DIR, "xiaoe_api.json"), "w", encoding="utf-8") as f:
            json.dump(api_responses, f, ensure_ascii=False, indent=2)
        log(f"API responses saved ({len(api_responses)})")

        # Also capture HAR (network log) for complete analysis
        # Wait a moment for any pending requests
        time.sleep(3)

        log("=" * 60)
        log("抓取完成！可以关闭浏览器了")
        log("=" * 60)

        # Keep browser open with a simple loop instead of input()
        for _ in range(120):
            time.sleep(1)
            try:
                # Check if browser still open
                page.title()
            except:
                break

        browser.close()
        log("Done.")


if __name__ == "__main__":
    capture()
