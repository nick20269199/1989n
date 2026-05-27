"""
小鹅通 — 在浏览器上下文调用 pc_client API，拦截真实请求/响应
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
        context.add_cookies(cookies)
        page = context.new_page()

        captured_requests = []
        captured_responses = []

        def on_request(request):
            if 'jump_url' in request.url or 'big_class' in request.url or 'get_anti_theft' in request.url:
                captured_requests.append({
                    "url": request.url,
                    "method": request.method,
                    "headers": dict(request.headers),
                    "post_data": request.post_data,
                })
                log(f"  REQUEST: {request.method} {request.url}")

        def on_response(response):
            if 'jump_url' in response.url or 'big_class' in response.url or 'get_anti_theft' in response.url:
                try:
                    body = response.text()[:2000]
                except:
                    body = "(no body)"
                captured_responses.append({
                    "url": response.url,
                    "status": response.status,
                    "body": body,
                })
                log(f"  RESPONSE [{response.status}]: {body[:500]}")

        page.on("request", on_request)
        page.on("response", on_response)

        log("Loading page...")
        page.goto("https://study.xiaoe-tech.com/t_l/learnIndex?type=wx#/muti_index",
                   wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)
        page.evaluate("""
        var st = """ + json.dumps(storage) + """;
        for (var key in st) { localStorage.setItem(key, st[key]); }
        """)
        page.reload(wait_until="domcontentloaded")
        time.sleep(5)

        rid = "l_6a15546fe4b0694c5bca44b0"

        log("\n=== Direct fetch to pc_client ===")
        result = page.evaluate("""async (rid) => {
            const m = document.cookie.match(/(^| )p_token=([^;]*)(;|$)/);
            const p_token = m ? m[2] : '';
            const app_id = localStorage.getItem('app_id') || 'appzsnu8fxf7905';

            // Call jump_url
            const resp = await fetch('/pc_client/xe.big_class.course.jump_url', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'app-token': p_token,
                    'app_id': app_id,
                },
                body: JSON.stringify({
                    user_id: btoa(p_token).substring(0,10),
                    app_id: app_id,
                    alive_id: rid
                })
            });
            const data = await resp.json();
            return JSON.stringify(data);
        }""", rid)
        log(f"fetch result: {result[:500]}")

        log("\n=== Show intercepted requests/responses ===")
        for r in captured_requests:
            log(f"\n  REQUEST: {r['method']} {r['url']}")
            auth_headers = {k: v for k, v in r['headers'].items()
                          if any(x in k.lower() for x in ['auth', 'token', 'app', 'cookie'])}
            log(f"  Auth headers: {json.dumps(auth_headers, ensure_ascii=False)[:500]}")
            if r['post_data']:
                log(f"  Body: {r['post_data'][:500]}")

        for r in captured_responses:
            log(f"\n  RESPONSE: [{r['status']}] {r['url']}")
            log(f"  Body: {r['body'][:500]}")

        browser.close()
        log("\nDone.")

if __name__ == "__main__":
    main()
