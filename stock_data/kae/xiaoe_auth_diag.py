"""
小鹅通 — 鉴权诊断：对比PC cookies vs h5需要的auth
"""
import os, json, time
from datetime import datetime

CAPTURE_DIR = "D:/1989n/stock_data/kae"

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def main():
    with open(os.path.join(CAPTURE_DIR, "xiaoe_cookies.json"), encoding="utf-8") as f:
        cookies = json.load(f)
    with open(os.path.join(CAPTURE_DIR, "xiaoe_storage.json"), encoding="utf-8") as f:
        storage = json.load(f)

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=False)
        context = browser.new_context(viewport={"width": 1280, "height": 900})

        # === Step 1: Add cookies and load PC page ===
        context.add_cookies(cookies)
        page = context.new_page()

        xhr_log = []
        page.on("response", lambda resp: (
            xhr_log.append({"url": resp.url, "status": resp.status, "headers": dict(resp.headers)})
            if "admin.xiaoe-tech.com" in resp.url or "xiaoeknow.com" in resp.url
            else None
        ))

        page.goto("https://study.xiaoe-tech.com/t_l/learnIndex?type=wx#/muti_index",
                   wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)
        page.evaluate(f"""
        var st = {json.dumps(storage)};
        for (var key in st) {{ localStorage.setItem(key, st[key]); }}
        """)
        page.reload(wait_until="domcontentloaded")
        time.sleep(5)

        log(f"URL: {page.url}")
        log(f"Title: {page.title()}")

        # === Step 2: Dump ALL cookies from authenticated context ===
        log("\n=== ALL COOKIES in authenticated context ===")
        all_cookies = context.cookies()
        for c in all_cookies:
            log(f"  {c['name']:30s} domain={c['domain']:30s} path={c['path']:20s} httpOnly={c['httpOnly']} secure={c['secure']}")

        # === Step 3: Dump localStorage ===
        log("\n=== localStorage keys ===")
        ls_keys = page.evaluate("() => Object.keys(localStorage)")
        for k in ls_keys:
            v = page.evaluate(f"localStorage.getItem('{k}')")
            if len(v) > 150:
                log(f"  {k}: {v[:150]}...")
            else:
                log(f"  {k}: {v}")

        # === Step 4: Check what the course list API returns ===
        log("\n=== Course list API calls ===")
        for x in xhr_log:
            log(f"  [{x['status']}] {x['url'][:200]}")
            if 'set-cookie' in {k.lower(): v for k, v in x['headers'].items()}:
                log(f"    >>> Has Set-Cookie header!")

        # === Step 5: Try loading h5 page IN the same context (not separate) ===
        # to see if the cookies work when set properly
        log("\n=== Trying h5 page in SAME context (full cookie set) ===")
        h5_page = context.new_page()
        h5_page.route("**/*", lambda route: route.continue_())

        alive_requests = []

        def on_req(request):
            if 'alive' in request.url or 'm3u8' in request.url or '.mp4' in request.url:
                log(f"  >>> REQ: {request.url[:250]}")
                alive_requests.append(request.url)

        h5_page.on("request", on_req)

        rid = "l_6a15546fe4b0694c5bca44b0"  # 0526
        h5_url = f"https://appzsnu8fxf7905.h5.xiaoeknow.com/v3/course/alive/{rid}?type=2"
        log(f"Navigating to: {h5_url}")

        try:
            h5_page.goto(h5_url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(2)
            log(f"  URL: {h5_page.url}")
            log(f"  Title: {h5_page.title()}")

            if "login" in h5_page.url.lower() or "auth" in h5_page.url.lower() or "Loading" in h5_page.title():
                log(f"  *** Login redirect detected!")
                # Try waiting more
                time.sleep(5)
                log(f"  URL after wait: {h5_page.url}")
                log(f"  Title after wait: {h5_page.title()}")

                # Check response headers for one request to understand auth
                log(f"\n  Checking redirect chain...")
                try:
                    body = h5_page.content()
                    log(f"  Page content length: {len(body)}")
                    # Check for embedded auth forms
                    if "login" in body.lower()[:5000]:
                        log(f"  First 500 chars: {body[:500]}")
                except:
                    pass
            else:
                log(f"  *** Page loaded! No redirect!")
                time.sleep(10)
                body = h5_page.inner_text("body")
                log(f"  Body: {body[:300]}")
        except Exception as e:
            log(f"  Error: {e}")

        h5_page.close()

        # === Step 6: Try loading with ALL cookies including study.xiaoe-tech.com ===
        # The h5 server might check for a session cookie that originates from the PC domain
        log("\n=== Trying with restricted cookie domains ===")
        # Filter to just include relevant cookies
        xe_cookies = [c for c in all_cookies if 'xiaoeknow' in c['domain'] or 'xet' in c['domain']]
        log(f"xiaoeknow/xet cookies: {len(xe_cookies)}")

        # Try approach: call the h5 auth endpoint with p_token as param
        log("\n=== Trying auth via URL param ===")
        p_token = None
        for c in cookies:
            if c.get("name") == "p_token":
                p_token = c["value"]
                break

        if p_token:
            auth_url = f"{h5_url}&p_token={p_token}"
            log(f"Trying: {auth_url[:150]}")
            test_page = context.new_page()
            try:
                test_page.goto(auth_url, wait_until="domcontentloaded", timeout=15000)
                time.sleep(3)
                log(f"  URL: {test_page.url}")
                log(f"  Title: {test_page.title()}")
            except Exception as e:
                log(f"  Error: {e}")
            test_page.close()

        # === Step 7: Check what cookies are on study domain that might be the real auth ===
        log("\n=== Checking for OAuth/cross-domain cookies ===")
        for c in all_cookies:
            if 'oauth' in c['name'].lower() or 'sid' in c['name'].lower() or 'session' in c['name'].lower() or 'token' in c['name'].lower() or 'x_a' in c['name'].lower():
                log(f"  Auth-relevant cookie: {c['name']} = {c['value'][:50]} domain={c['domain']}")

        time.sleep(5)
        browser.close()

    # Save auth diag results
    with open(os.path.join(CAPTURE_DIR, "xiaoe_auth_diag.json"), "w", encoding="utf-8") as f:
        json.dump({
            "cookies_count": len(all_cookies),
            "h5_requests": alive_requests,
        }, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
