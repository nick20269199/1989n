"""
小鹅通 — 拦截 h5 API 响应 + 提取实际 API 端点
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

        page.goto("https://study.xiaoe-tech.com/t_l/learnIndex?type=wx#/muti_index",
                   wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)
        page.evaluate(f"""
        var st = {json.dumps(storage)};
        for (var key in st) {{ localStorage.setItem(key, st[key]); }}
        """)
        page.reload(wait_until="domcontentloaded")
        time.sleep(5)

        # Get course data
        course_data = page.evaluate("""() => {
            const cards = document.querySelectorAll('.course-card-list');
            const courses = [];
            cards.forEach((card, idx) => {
                const vm = card.__vue__;
                if (!vm || !vm.$options || !vm.$options.propsData) return;
                const data = vm.$options.propsData.cardData;
                if (!data) return;
                courses.push({
                    index: idx,
                    title: data.title,
                    resource_id: data.resource_id,
                    app_id: data.app_id,
                });
            });
            return courses;
        }""")
        first = course_data[0]
        rid = first["resource_id"]
        app_id = first["app_id"]

        # === Approach 1: Intercept h5 API responses ===
        log("=== Intercepting h5 API responses ===")

        h5_api_responses = {}

        def capture_response(response):
            url = response.url
            # Only catch data APIs, not static files
            if any(x in url for x in ['xe.', '_alive', 'api']) and \
               not any(x in url for x in ['.js', '.css', '.png', '.jpg', '.gif', '.svg', '.ico', '.woff', '.ttf', '.eot']):
                try:
                    body = response.text()[:3000]
                    h5_api_responses[url.split('?')[0][:150]] = {"status": response.status, "body": body}
                except:
                    pass

        # Load h5 page and capture APIs
        h5_page = context.new_page()
        h5_page.on("response", capture_response)

        h5_url = f"https://appzsnu8fxf7905.h5.xiaoeknow.com/v3/course/alive/{rid}?type=2"
        try:
            h5_page.goto(h5_url, wait_until="domcontentloaded", timeout=15000)
            time.sleep(5)
        except:
            pass

        h5_page.close()

        # Show captured API responses
        log(f"\nCaptured {len(h5_api_responses)} API responses:")
        for url_key, resp_data in h5_api_responses.items():
            log(f"\n  [{resp_data['status']}] {url_key}")
            body = resp_data['body']
            if body and len(body) < 2000:
                log(f"    Body: {body[:500]}")

        # === Approach 2: Try to get the alive data directly via PC API ===
        # The PC page has its own API endpoints. Let me try more endpoint names.
        log(f"\n{'='*60}")
        log("=== Trying more PC API endpoints ===")

        # These are the $request API names used by the parent component
        pc_endpoints = [
            ("index_getPendingLiveList", {}),
            ("index_getOpenLivingList", {"page_size": 16, "page_params": "1-0-0"}),
            ("living_live_list_get", {"page_size": 16, "page_params": "1-0-0"}),
            ("my_attend_normal_list_get", {"page_index": 1, "page_size": 100}),
        ]

        for api_name, params in pc_endpoints:
            result = page.evaluate(f"""async () => {{
                const card = document.querySelector('.course-card-list');
                if (!card || !card.__vue__) return null;
                let p = card.__vue__.$parent;
                while (p) {{
                    if (p.$request) {{
                        try {{
                            const r = await p.$request('{api_name}', {json.dumps(params)});
                            if (r && r.code === 0) return {{success: true, data: JSON.stringify(r).slice(0, 800)}};
                            if (r) return {{code: r.code, msg: r.msg, data: JSON.stringify(r.data).slice(0, 300)}};
                        }} catch(e) {{
                            return {{error: e.message}};
                        }}
                    }}
                    p = p.$parent;
                }}
                return null;
            }}""")
            if result:
                log(f"  {api_name}: {json.dumps(result, ensure_ascii=False)[:600]}")

        # === Approach 3: Get the actual request mapping from the JS ===
        log(f"\n{'='*60}")
        log("=== Extracting request mapping from Vue ===")

        request_map = page.evaluate("""() => {
            const result = {};

            // Check for request map on the window or its prototypes
            // The $request method maps friendly names to API paths

            // Check if there's an API list on Vue.prototype
            const card = document.querySelector('.course-card-list');
            if (!card || !card.__vue__) return {};
            const vm = card.__vue__;

            // Check $request internals
            if (vm.$request) {
                // Check for a list or config on $request
                // In many Vue apps, $request has a base URL or API list
                for (const key in vm.$request) {
                    if (vm.$request.hasOwnProperty(key)) {
                        try {
                            const val = vm.$request[key];
                            if (typeof val === 'string') result['request_' + key] = val.slice(0, 200);
                            if (typeof val === 'object') result['request_' + key] = JSON.stringify(val).slice(0, 200);
                        } catch(e) {}
                    }
                }
            }

            // Check Vue.prototype.$request internals
            const proto = Object.getPrototypeOf(vm);
            if (proto.$request) {
                for (const key in proto.$request) {
                    if (proto.$request.hasOwnProperty(key)) {
                        try { result['proto_request_' + key] = String(proto.$request[key]).slice(0, 200); } catch(e) {}
                    }
                }
            }

            // Check vm.$http or similar
            if (vm.$http) result.hasHttp = true;
            if (vm.$api) result.hasApi = true;
            if (vm.$axios) result.hasAxios = true;

            // Check the actual request function source
            if (vm.$request && typeof vm.$request === 'function') {
                result.requestSource = vm.$request.toString().slice(0, 500);
            }

            return result;
        }""")
        for k, v in request_map.items():
            log(f"  {k}: {v}")

        # === Approach 4: Get the full course list (with all 16 courses) from the $request ===
        # This tells us which APIs work
        log(f"\n{'='*60}")
        log("=== Full course list API call ===")

        # Get all courses from the list
        all_list = page.evaluate(f"""async () => {{
            const card = document.querySelector('.course-card-list');
            if (!card || !card.__vue__) return null;
            let p = card.__vue__.$parent;
            while (p) {{
                if (p.$request) {{
                    try {{
                        // Try the same API that loads the course list
                        const r = await p.$request('my_attend_normal_list_get', {page_size: 50, page_index: 1});
                        if (r && r.code === 0) return JSON.stringify(r).slice(0, 3000);
                        return JSON.stringify(r || 'no response').slice(0, 500);
                    }} catch(e) {{
                        return 'Error: ' + e.message;
                    }}
                }}
                p = p.$parent;
            }}
            return 'no $request';
        }}""")
        log(f"  {all_list[:2000]}")

        # === Approach 5: Look at PC JavaScript files for API mappings ===
        log(f"\n{'='*60}")
        log("=== Checking PC page JS for API base URLs ===")

        js_apis = page.evaluate("""() => {
            const result = {};

            // Check all script tags for API_URL or XIAOE_API patterns
            const scripts = document.querySelectorAll('script');
            for (const s of scripts) {
                const text = s.textContent || '';
                if (text.includes('api') || text.includes('API') || text.includes('xe.')) {
                    // Extract API URLs
                    const matches = text.match(/https?:\/\/[^'"\\s]+(?:xe\.|api\.)[^'"\\s]+/g);
                    if (matches) result[s.id || 'inline'] = matches.slice(0, 5);

                    // Extract $request mappings like 'xxx': 'xe.xxx.xxx'
                    const mappings = text.match(/'[a-z_]+':\s*'xe\.[^']+'/g);
                    if (mappings) result['mappings_' + (s.id || 'inline')] = mappings.slice(0, 20);
                }
            }

            // Check window for API config
            if (window.API_BASE_URL) result.apiBaseUrl = window.API_BASE_URL;
            if (window.XIAOE_API) result.xiaoeApi = JSON.stringify(window.XIAOE_API).slice(0, 500);

            return result;
        }""")
        for k, v in js_apis.items():
            if isinstance(v, list):
                log(f"  {k}:")
                for item in v:
                    log(f"    {item[:150]}")
            else:
                log(f"  {k}: {str(v)[:300]}")

        time.sleep(5)
        browser.close()

if __name__ == "__main__":
    main()
