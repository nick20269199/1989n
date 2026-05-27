"""
小鹅通 — 触发 Vue 组件方法 (getAntiTheft/jumpLive/enterLive) 并捕获网络请求
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

        all_requests = []
        all_responses = []

        def on_request(req):
            url = req.url
            if 'study.xiaoe-tech.com' in url and ('pc_client' in url or 'xe.' in url):
                all_requests.append({
                    "url": url, "method": req.method,
                    "headers": dict(req.headers),
                    "post_data": req.post_data,
                })

        def on_response(resp):
            url = resp.url
            if 'study.xiaoe-tech.com' in url and ('pc_client' in url or 'xe.' in url):
                try:
                    body = resp.text()[:3000]
                except:
                    body = "(no body)"
                all_responses.append({
                    "url": url, "status": resp.status, "body": body,
                })

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
        app_id = "appzsnu8fxf7905"

        # Get user_id from check_token
        log("\n=== Getting user info ===")
        user_info = page.evaluate("""async () => {
            const r = await fetch('/xe.learn-pc.user/check_token');
            const d = await r.json();
            if (d.code === 0) {
                const data = d.data;
                return JSON.stringify({
                    b_user_id: data.b_user_id || '',
                    nickname: data.nickname || '',
                    user_id: data.user_id || '',
                    token_info: data.token_info || {},
                });
            }
            return JSON.stringify(d);
        }""")
        log(f"User info: {user_info[:300]}")
        ui = json.loads(user_info)
        b_user_id = ui.get('b_user_id', '')

        # Read WebSocket messages if any
        ws_messages = []
        def on_ws(ws):
            ws.on('framesent', lambda f: ws_messages.append(('sent', f.payload[:500])))
            ws.on('framereceived', lambda f: ws_messages.append(('recv', f.payload[:500])))
        page.on('websocket', on_ws)

        # === TEST 1: Call getAntiTheft method ===
        log("\n=== Test 1: Call getAntiTheft method ===")
        anti_result = page.evaluate("""async ({rid, app_id}) => {
            const card = document.querySelector('.course-card-list');
            if (!card || !card.__vue__) return 'no vue';
            let p = card.__vue__.$parent;
            while (p) {
                if (p.getAntiTheft) {
                    try {
                        const result = await p.getAntiTheft({alive_id: rid, app_id: app_id});
                        return 'result: ' + JSON.stringify(result).substring(0, 1000);
                    } catch(e) {
                        return 'error: ' + e.message;
                    }
                }
                p = p.$parent;
            }
            return 'no getAntiTheft method';
        }""", {"rid": rid, "app_id": app_id})
        log(f"getAntiTheft result: {anti_result[:500]}")

        # === TEST 2: Call checkCourseInterest method ===
        log("\n=== Test 2: Call checkCourseInterest method ===")
        interest_result = page.evaluate("""async ({user_id, rid, app_id}) => {
            const card = document.querySelector('.course-card-list');
            if (!card || !card.__vue__) return 'no vue';
            let p = card.__vue__.$parent;
            while (p) {
                if (p.checkCourseInterest) {
                    try {
                        const result = await p.checkCourseInterest({user_id: user_id, alive_id: rid, app_id: app_id});
                        return 'result: ' + JSON.stringify(result).substring(0, 1000);
                    } catch(e) {
                        return 'error: ' + e.message;
                    }
                }
                p = p.$parent;
            }
            return 'no checkCourseInterest method';
        }""", {"user_id": b_user_id, "rid": rid, "app_id": app_id})
        log(f"checkCourseInterest result: {interest_result[:500]}")

        # === TEST 3: Call jumpLive method ===
        log("\n=== Test 3: Call jumpLive method ===")
        jump_result = page.evaluate("""async ({user_id, rid, app_id}) => {
            const card = document.querySelector('.course-card-list');
            if (!card || !card.__vue__) return 'no vue';
            let p = card.__vue__.$parent;
            while (p) {
                if (p.jumpLive) {
                    try {
                        const result = await p.jumpLive({user_id: user_id, alive_id: rid, app_id: app_id});
                        return 'result: ' + JSON.stringify(result).substring(0, 1000);
                    } catch(e) {
                        return 'error: ' + e.message;
                    }
                }
                p = p.$parent;
            }
            return 'no jumpLive method';
        }""", {"user_id": b_user_id, "rid": rid, "app_id": app_id})
        log(f"jumpLive result: {jump_result[:500]}")

        # === Show intercepted network traffic ===
        log(f"\n=== Intercepted API traffic ({len(all_requests)} requests, {len(all_responses)} responses) ===")
        for i, req in enumerate(all_requests):
            log(f"\n  [{i}] {req['method']} {req['url']}")
            log(f"     Headers: app-token={req['headers'].get('app-token', 'NOT SET')[:20]}...")
            if req['post_data']:
                log(f"     Body: {req['post_data'][:200]}")

        for i, resp in enumerate(all_responses):
            if resp['status'] == 200:
                log(f"\n  [{i}] RESP [{resp['status']}] {resp['url'][:120]}")
                log(f"     {resp['body'][:300]}")

        # === Show WebSocket messages ===
        if ws_messages:
            log(f"\n=== WebSocket messages ({len(ws_messages)}) ===")
            for direction, payload in ws_messages[:5]:
                log(f"  [{direction}] {payload[:200]}")

        browser.close()
        log("\nDone.")

if __name__ == "__main__":
    main()
