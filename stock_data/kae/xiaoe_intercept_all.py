"""
小鹅通 — 拦截所有网络请求 + 找到De API映射 + 点击课程卡片
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
        page = context.new_page()

        # Intercept ALL responses
        all_requests = []
        js_contents = {}

        def capture_response(response):
            url = response.url
            all_requests.append({"url": url, "status": response.status, "method": response.request.method})
            # Capture JS files
            if url.endswith('.js') and response.status == 200:
                try:
                    body = response.text()
                    if any(x in body for x in ['De[', 'check_token', 'living_live', 'kotoken', 'xe.learn-pc']):
                        js_contents[url.split('/')[-1][:60]] = body
                        log(f"  CAPTURED JS: {url.split('/')[-1][:60]} ({len(body)} chars)")
                except:
                    pass

        page.on("response", capture_response)

        # Load the study page
        log("Loading study page...")
        page.goto("https://study.xiaoe-tech.com/t_l/learnIndex?type=wx#/muti_index",
                   wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)

        # Restore localStorage
        page.evaluate(f"""
        var st = {json.dumps(storage)};
        for (var key in st) {{ localStorage.setItem(key, st[key]); }}
        """)
        page.reload(wait_until="domcontentloaded")
        time.sleep(5)

        log(f"Total requests captured: {len(all_requests)}")
        log(f"JS files captured: {len(js_contents)}")

        # Search for De mapping in captured JS
        log("\n=== Searching for De API mapping in JS ===")
        for js_name, js_body in js_contents.items():
            # Search for the De dictionary definition
            # Pattern: De is an object mapping API names to {url, method}
            for pattern in ['De=', 'De =', 'De[', 'apiMap', 'API_MAP']:
                idx = js_body.find(pattern)
                if idx >= 0:
                    start = max(0, idx - 200)
                    end = min(len(js_body), idx + 500)
                    log(f"  Found '{pattern}' in {js_name}:")
                    log(f"  {js_body[start:end]}")
                    log("  ---")

        # Look for API path patterns
        log("\n=== Looking for xe.learn-pc API paths ===")
        api_paths = re.findall(r'xe\.learn-pc[^"\'\\s,)]+', js_body if js_contents else '')
        for path in set(api_paths):
            log(f"  {path}")

        # Now try to click a course card and see what happens
        log("\n=== Clicking course card ===")
        card = page.query_selector('.course-card-list')
        if card:
            # Clear previous API calls
            all_requests.clear()
            log("  Clicking...")
            try:
                card.click()
                time.sleep(5)
                log(f"  After click - {len(all_requests)} new requests:")
                for req in all_requests:
                    if 'xe.' in req['url'] or 'api' in req['url']:
                        log(f"    [{req['method']}] [{req['status']}] {req['url'][:200]}")
            except Exception as e:
                log(f"  Click error: {e}")

        # Try to enumerate Vue component methods
        log("\n=== Enumerating Vue component ===")
        vue_info = page.evaluate("""() => {
            const result = {};

            // Find Vue component
            const card = document.querySelector('.course-card-list');
            if (!card || !card.__vue__) return {error: 'no vue'};
            const vm = card.__vue__;

            // Walk up to parent
            let p = vm.$parent;
            let depth = 0;
            while (p && depth < 10) {
                const key = 'parent_' + depth;
                result[key] = {};

                // List methods
                if (p.$options && p.$options.methods) {
                    result[key].methods = Object.keys(p.$options.methods);
                }

                // List computed
                if (p.$options && p.$options.computed) {
                    result[key].computed = Object.keys(p.$options.computed);
                }

                // Check for $request
                if (p.$request) {
                    result[key].hasRequest = true;
                    // Try to get De from $request's closure
                    const reqStr = p.$request.toString();
                    result[key].requestSource = reqStr.slice(0, 300);
                }

                // Check api config
                if (p.apiConfig || p.API_CONFIG || p.__api_config__) {
                    result[key].hasApiConfig = true;
                }

                // Check for Ht (axios instance)
                if (p.Ht) {
                    result[key].hasHt = true;
                }

                p = p.$parent;
                depth++;
            }

            // Also capture ALL function names on the component chain
            result.ownMethods = Object.getOwnPropertyNames(vm).filter(n => typeof vm[n] === 'function').slice(0, 30);
            result.parentKeys = Object.keys(vm.$parent || {}).filter(k => k.startsWith('$') === false).slice(0, 50);

            return result;
        }""")
        log(f"Vue info: {json.dumps(vue_info, ensure_ascii=False)[:3000]}")

        # Try to call known working APIs via $request to get course detail
        rid = None
        try:
            courses = page.evaluate("""() => {
                const cards = document.querySelectorAll('.course-card-list');
                const result = [];
                cards.forEach(c => {
                    const vm = c.__vue__;
                    if (!vm || !vm.$options || !vm.$options.propsData) return;
                    const d = vm.$options.propsData.cardData;
                    if (d) result.push({title: d.title, alive_id: d.alive_id, resource_id: d.resource_id});
                });
                return result;
            }""")
            if courses:
                log(f"Found {len(courses)} courses")
                rid = courses[0].get('alive_id') or courses[0].get('resource_id')
                log(f"Sample: {json.dumps(courses[0], ensure_ascii=False)[:300]}")
        except Exception as e:
            log(f"Error getting courses: {e}")

        # Try to call $request with various course detail APIs
        if rid:
            log(f"\n=== Trying $request APIs for course detail (rid={rid}) ===")
            apis_to_try = [
                "check_token",
                "living_live_list_get",
                "my_attend_normal_list_get",
                "alive_get",
                "alive_detail",
                "alive_detail_get",
                "alive_info",
                "course_detail",
                "course_info",
                "resource_get",
                "resource_detail",
                "alive_resource",
                "alive_play",
                "alive_play_url",
                "alive_video",
                "alive_replay",
                "alive_player",
                "alive_learn_detail",
                "get_alive_detail",
                "get_alive_resource",
                "get_alive_play_info",
                "get_course_detail",
                "get_resource_detail",
                "learn_alive_detail",
                "learn_alive_info",
                "learn_course_detail",
                "learn_resource_detail",
                "play_info",
                "play_url",
                "player_info",
                "player_url",
                "video_get",
                "video_info",
                "video_play",
                "video_play_info",
                "media_get",
                "media_info",
                "media_play",
            ]

            for api_name in apis_to_try:
                result = page.evaluate(f"""async () => {{
                    const card = document.querySelector('.course-card-list');
                    if (!card || !card.__vue__) return null;
                    let p = card.__vue__.$parent;
                    while (p) {{
                        if (p.$request) {{
                            for (const params of [
                                {{alive_id: '{rid}'}},
                                {{resource_id: '{rid}'}},
                                {{alive_id: '{rid}', resource_id: '{rid}'}},
                                {{alive_id: '{rid}', app_id: 'appzsnu8fxf7905'}},
                            ]) {{
                                try {{
                                    const r = await p.$request('{api_name}', params);
                                    if (r && r.code === 0) {{
                                        return {{success: true, api: '{api_name}', params: params, code: 0, data: JSON.stringify(r.data).slice(0, 1000)}};
                                    }}
                                }} catch(e) {{}}
                            }}
                            return null;
                        }}
                        p = p.$parent;
                    }}
                    return null;
                }}""")
                if result and isinstance(result, dict) and result.get('success'):
                    log(f"  *** FOUND: {result['api']} -> {json.dumps(result, ensure_ascii=False)[:800]}")

        # Save captured JS files for offline analysis
        if js_contents:
            log(f"\nSaving {len(js_contents)} JS files for analysis...")
            for js_name, js_body in js_contents.items():
                safe_name = re.sub(r'[^a-zA-Z0-9._-]', '_', js_name)[:60]
                path = os.path.join(CAPTURE_DIR, safe_name)
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(js_body[:50000])  # Save first 50KB
                log(f"  Saved {safe_name}")

        time.sleep(5)
        browser.close()
        log("\nDone.")

if __name__ == "__main__":
    main()
