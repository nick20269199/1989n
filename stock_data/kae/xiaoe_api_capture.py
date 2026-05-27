"""
小鹅通 API 抓取 — 使用已获取的 cookie 直接抓取课程数据
"""
import os, json, time, re, sys
from datetime import datetime

CAPTURE_DIR = "D:/1989n/stock_data/kae"

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def main():
    # Load cookies from previous capture
    with open(os.path.join(CAPTURE_DIR, "xiaoe_cookies.json"), encoding="utf-8") as f:
        cookies = json.load(f)

    # Load localStorage
    with open(os.path.join(CAPTURE_DIR, "xiaoe_storage.json"), encoding="utf-8") as f:
        storage = json.load(f)

    # Extract p_token
    p_token = None
    for c in cookies:
        if c.get("name") == "p_token":
            p_token = c["value"]
            break

    user_info = json.loads(storage.get("userInfo", "{}"))
    b_user_id = user_info.get("b_user_id", "")

    log(f"p_token: {p_token[:20] if p_token else 'N/A'}...")
    log(f"User: {user_info.get('nickname', 'N/A')}")
    log(f"b_user_id: {b_user_id}")

    from playwright.sync_api import sync_playwright

    all_network_data = []

    with sync_playwright() as p:
        log("Launching Edge with saved cookies...")
        browser = p.chromium.launch(channel="msedge", headless=False)

        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            storage_state=None,
        )

        # Add cookies
        context.add_cookies(cookies)

        # Inject localStorage before navigation
        page = context.new_page()
        page.add_init_script(f"""
        // Restore localStorage before page loads
        window.__STORAGE__ = {json.dumps(storage)};
        """)

        # Intercept ALL XHR/fetch requests
        api_log = []

        def on_request(request):
            url = request.url
            if any(d in url for d in ["admin.xiaoe-tech.com", "xiaoeknow.com"]):
                if not any(ext in url for ext in [".js", ".css", ".png", ".jpg", ".gif", ".svg", ".ico", ".woff"]):
                    api_log.append({
                        "type": "request",
                        "url": url,
                        "method": request.method,
                        "headers": dict(request.headers),
                        "time": datetime.now().isoformat(),
                    })

        def on_response(response):
            url = response.url
            if any(d in url for d in ["admin.xiaoe-tech.com", "xiaoeknow.com"]):
                if not any(ext in url for ext in [".js", ".css", ".png", ".jpg", ".gif", ".svg", ".ico", ".woff"]):
                    try:
                        body = response.text()
                    except:
                        body = "<binary>"
                    api_log.append({
                        "type": "response",
                        "url": url,
                        "status": response.status,
                        "body": body[:10000],
                        "time": datetime.now().isoformat(),
                    })

        page.on("request", on_request)
        page.on("response", on_response)

        # Navigate to the main page
        log("Navigating to 小鹅通 main page...")
        page.goto(
            "https://study.xiaoe-tech.com/t_l/learnIndex?type=wx#/muti_index",
            wait_until="domcontentloaded",
            timeout=30000,
        )

        # Wait for page to settle and restore storage
        time.sleep(3)

        # Restore localStorage via page evaluate
        try:
            page.evaluate(f"""
            var st = {json.dumps(storage)};
            for (var key in st) {{
                localStorage.setItem(key, st[key]);
            }}
            """)
            log("localStorage restored")
        except Exception as e:
            log(f"localStorage restore: {e}")

        # Now refresh to let the app read the auth state
        log("Refreshing with auth data...")
        page.reload(wait_until="domcontentloaded")
        time.sleep(5)

        # Check current state
        log(f"URL: {page.url}")
        log(f"Title: {page.title()}")

        # Try to see the page content
        try:
            text = page.inner_text("body")
            log(f"Body text: {text[:500]}")
        except:
            pass

        # Trigger navigation to course page by trying common URLs
        course_pages = [
            "https://study.xiaoe-tech.com/t_l/learnIndex?type=wx#/muti_index",
            "https://study.xiaoe-tech.com/t_l/courseList?type=wx",
            "https://study.xiaoe-tech.com/t_l/myCourse?type=wx",
            "https://study.xiaoe-tech.com/t_l/learnIndex?type=wx#/myCourse",
        ]

        for course_url in course_pages:
            log(f"Navigating to: {course_url}")
            try:
                page.goto(course_url, wait_until="domcontentloaded", timeout=15000)
                time.sleep(3)

                # Check page content
                try:
                    text = page.inner_text("body")
                    log(f"  Content: {text[:300]}")
                except:
                    pass
            except Exception as e:
                log(f"  Error: {e}")

        # Save all captured network data
        with open(os.path.join(CAPTURE_DIR, "xiaoe_network_log.json"), "w", encoding="utf-8") as f:
            json.dump(api_log, f, ensure_ascii=False, indent=2)
        log(f"Captured {len(api_log)} network events")

        # Save HTML for analysis
        html = page.content()
        with open(os.path.join(CAPTURE_DIR, "xiaoe_final.html"), "w", encoding="utf-8") as f:
            f.write(html)
        log(f"Final HTML saved ({len(html)} bytes)")

        log("=" * 60)
        log("Done! Check stock_data/kae/ for results.")
        log("=" * 60)

        browser.close()


if __name__ == "__main__":
    main()
