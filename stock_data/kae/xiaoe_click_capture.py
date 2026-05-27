"""
小鹅通 — 点击课程卡片 + 拦截所有网络/弹出/WS，捕获完整流程
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

        api_calls = []
        new_pages = []
        ws_messages = []

        def on_response(resp):
            url = resp.url
            if any(x in url for x in ['pc_client', 'xe.', 'kotoken', 'encrypted', 'alive']):
                try:
                    body = resp.text()[:2000]
                    api_calls.append({
                        "url": url.split('?')[0][:150],
                        "status": resp.status,
                        "body": body
                    })
                except:
                    pass

        page.on("response", on_response)

        def on_page(page):
            new_pages.append(page.url)
            log(f"  NEW PAGE: {page.url}")
            try:
                page.wait_for_load_state("domcontentloaded", timeout=5000)
                log(f"  NEW PAGE title: {page.title()}")
                log(f"  NEW PAGE content: {page.content()[:500]}")
            except:
                pass

        context.on("page", on_page)

        # Load page
        log("Loading...")
        page.goto("https://study.xiaoe-tech.com/t_l/learnIndex?type=wx#/muti_index",
                   wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)
        page.evaluate("""
        var st = """ + json.dumps(storage) + """;
        for (var key in st) { localStorage.setItem(key, st[key]); }
        """)
        page.reload(wait_until="domcontentloaded")
        time.sleep(5)

        log("Clicking course card...")
        api_calls.clear()

        # Click the first course card
        card = page.query_selector('.course-card-list')
        if card:
            try:
                card.click()
                time.sleep(8)  # Wait for all async operations
            except Exception as e:
                log(f"  Click error: {e}")

        # Also directly trigger enterLive with proper data
        log("\n=== Directly triggering enterLive ===")
        rid = "l_6a15546fe4b0694c5bca44b0"
        app_id = "appzsnu8fxf7905"

        # First get user_id from attend list
        attend_info = page.evaluate("""async () => {
            const r = await fetch('/xe.learn-pc.user/check_token');
            const d = await r.json();
            if (d.code === 0) return JSON.stringify(d.data);
            const r2 = await fetch('/xe.learn-pc/my_attend_normal_list.get/1.0.1', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({"page_size":16,"page":1,"agent_type":7,"resource_type":["0"]})
            });
            const d2 = await r2.json();
            return JSON.stringify(d2);
        }""")
        log(f"Attend info: {attend_info[:500]}")

        # Now trigger enterLive with full params via the component
        log("\n=== Calling enterLive on Vue component ===")
        enter_result = page.evaluate("""async ({rid, app_id}) => {
            const card = document.querySelector('.course-card-list');
            if (!card || !card.__vue__) return 'no vue';
            let p = card.__vue__.$parent;
            while (p) {
                if (p.enterLive) {
                    try {
                        // First get user_id from check_token
                        const tr = await fetch('/xe.learn-pc.user/check_token');
                        const td = await tr.json();
                        const b_user_id = td.data && td.data.b_user_id ? td.data.b_user_id : '';

                        // Get user_id from attend list
                        const ar = await fetch('/xe.learn-pc/my_attend_normal_list.get/1.0.1', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({"page_size":1,"page":1,"agent_type":7,"resource_type":["0"]})
                        });
                        const ad = await ar.json();
                        const user_id = ad.data && ad.data.list && ad.data.list[0] ? ad.data.list[0].user_id : '';

                        const result = await p.enterLive({
                            user_id: user_id,
                            alive_id: rid,
                            app_id: app_id,
                            jump_url: ''
                        });
                        return 'enterLive result: ' + JSON.stringify(result).substring(0, 1000);
                    } catch(e) {
                        return 'enterLive error: ' + (e.message || JSON.stringify(e));
                    }
                }
                p = p.$parent;
            }
            return 'no enterLive method';
        }""", {"rid": rid, "app_id": app_id})
        log(f"{enter_result[:500]}")

        # Show API responses
        log(f"\n=== API calls during click ({len(api_calls)}) ===")
        for call in api_calls:
            log(f"\n  [{call['status']}] {call['url']}")
            if call['status'] == 200:
                log(f"    {call['body'][:500]}")

        # Show new pages
        if new_pages:
            log(f"\n=== New popup pages ({len(new_pages)}) ===")
            for url in new_pages:
                log(f"  {url}")

        browser.close()
        log("\nDone.")

if __name__ == "__main__":
    main()
