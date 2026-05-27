"""
小鹅通 — SSO跨域认证 + 自动获取所有16个视频URL
流程:
1. 从PC域 study.xiaoe-tech.com 获取 SSO code (get_new_gateway)
2. 用 code 在 h5 域登录
3. 访问课程页面获取视频URL
"""
import os, json, time, re
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
        context.add_cookies(cookies)

        pc_page = context.new_page()
        h5_api_calls = []

        def on_response(response):
            url = response.url
            if any(x in url for x in ['xe.', '_alive', 'login', 'auth']) and \
               not any(x in url for x in ['.js', '.css', '.png', '.jpg', '.gif', '.ico']):
                try:
                    body = response.text()[:2000]
                    h5_api_calls.append({
                        "url": url.split('?')[0][:150],
                        "status": response.status,
                        "body": body,
                    })
                except:
                    pass

        context.on("response", on_response)

        # Step 1: Load PC page
        log("Step 1: Loading PC study page...")
        pc_page.goto("https://study.xiaoe-tech.com/t_l/learnIndex?type=wx#/muti_index",
                      wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)
        js_storage = json.dumps(storage)
        pc_page.evaluate("var st = " + js_storage + "; for (var key in st) { localStorage.setItem(key, st[key]); }")
        pc_page.reload(wait_until="domcontentloaded")
        time.sleep(5)

        # Step 2: Get course list using living_live_list
        log("Step 2: Getting course list...")
        course_list = pc_page.evaluate("""async () => {
            var r = await fetch('/xe.learn-pc/living_live_list.get/1.0.0');
            var d = await r.json();
            if (d.code !== 0) return '[]';
            return JSON.stringify(d.data.list || []);
        }""")
        courses = json.loads(course_list)
        log("Found " + str(len(courses)) + " courses:")
        for c in courses:
            rid = c.get('resource_id', c.get('alive_id', '?'))
            title = str(c.get('title', ''))[:50]
            log("  " + rid + " | " + title)

        # Step 3: Get SSO code
        log("\nStep 3: Getting SSO code from get_new_gateway...")
        sso_json = pc_page.evaluate("""async () => {
            var r = await fetch('/xe.learn-pc/get_new_gateway/1.0.0', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: '{}'
            });
            var d = await r.json();
            return JSON.stringify(d);
        }""")
        log("SSO raw: " + sso_json[:500])
        sso_data = json.loads(sso_json)
        if isinstance(sso_data, dict) and isinstance(sso_data.get("data"), dict):
            sso_url = sso_data["data"].get("url", "")
            log("SSO URL: " + sso_url)
        else:
            log("SSO returned non-dict data, trying through $request...")
            # Try through Vue's $request function
            sso_json2 = pc_page.evaluate("""async () => {
                var card = document.querySelector('.course-card-list');
                if (!card || !card.__vue__) return '{"error":"no vue"}';
                var p = card.__vue__.$parent;
                while (p) {
                    if (p.$request) {
                        try {
                            var r = await p.$request('index_getNewGateway', {});
                            return JSON.stringify(r);
                        } catch(e) {
                            return '{"error":"' + e.message + '"}';
                        }
                    }
                    p = p.$parent;
                }
                return '{"error":"no $request"}';
            }""")
            log("SSO via $request: " + sso_json2[:500])
            sso_data2 = json.loads(sso_json2)
            if isinstance(sso_data2, dict) and isinstance(sso_data2.get("data"), dict):
                sso_url = sso_data2["data"].get("url", "")
            else:
                sso_url = ""

        # Step 4: Authenticate on h5 domain
        if sso_url:
            log("\nStep 4: Authenticating on h5 domain via SSO...")
            h5_page = context.new_page()

            h5_api_calls.clear()
            h5_page.goto(sso_url, wait_until="domcontentloaded", timeout=15000)
            log("Auth page title: " + h5_page.title())
            log("Auth page URL: " + h5_page.url)
            time.sleep(5)

            # Navigate to first course
            if courses:
                rid = courses[0].get('resource_id') or courses[0].get('alive_id', '')
                log("\nNavigating to course: " + rid)
                try:
                    h5_page.goto(
                        "https://appzsnu8fxf7905.h5.xiaoeknow.com/v4/course/alive/" + rid + "?app_id=appzsnu8fxf7905",
                        wait_until="domcontentloaded", timeout=15000
                    )
                    time.sleep(5)
                    log("Course page title: " + h5_page.title())
                    log("Course page URL: " + h5_page.url)

                    # Check auth status
                    logged_in = h5_page.evaluate("""() => {
                        return {userId: window.USERID || '', anony: window.__anony_logon || ''};
                    }""")
                    log("Login check: " + json.dumps(logged_in, ensure_ascii=False))

                    if logged_in.get('userId') or logged_in.get('anony') == '1':
                        log("*** SSO AUTHENTICATION SUCCESSFUL! ***")
                        # Check page for video
                        page_html = h5_page.evaluate("""() => {
                            return document.querySelector('title') ? document.querySelector('title').innerText : '';
                        }""")
                        log("Title: " + page_html)
                    else:
                        log("SSO did not set auth - USERID still empty")

                except Exception as e:
                    log("Error: " + str(e))

            h5_page.close()
        else:
            log("No SSO URL returned!")

        # Step 5: Show all h5 API traffic
        log("\n=== h5 login/auth API calls ===")
        for call in h5_api_calls:
            url_short = call['url']
            if 'login' in url_short or 'auth' in url_short or 'token' in url_short or 'code' in url_short or 'session' in url_short:
                log("\n[" + str(call['status']) + "] " + url_short)
                log("  " + call['body'][:400])

        # Show h5 cookies
        h5_cookies = [c for c in context.cookies() if 'xiaoeknow' in c.get('domain', '') or 'xiaoeke' in c.get('domain', '')]
        log("\n=== h5 domain cookies (" + str(len(h5_cookies)) + ") ===")
        for c in h5_cookies:
            log("  " + str(c.get('name')) + ": " + str(c.get('value', ''))[:40] + " domain=" + str(c.get('domain')))

        pc_page.close()
        browser.close()
        log("\nDone.")

if __name__ == "__main__":
    main()
