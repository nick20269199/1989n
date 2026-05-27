"""
小鹅通 — 通过 kotoken API 获取跨域 Token，访问 h5 视频
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

        # Load PC page
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
                    h5_url: data.h5_url,
                    room_id: data.room_id,
                    user_id: data.user_id,
                });
            });
            return courses;
        }""")
        log(f"Found {len(course_data)} courses")

        first = course_data[0]
        rid = first["resource_id"]
        app_id = first["app_id"]
        user_id = first["user_id"]

        # === Step 1: Try kotoken.create API ===
        log("\n=== Calling kotoken.create API ===")

        kotoken_result = page.evaluate(f"""async () => {{
            try {{
                const resp = await fetch('/xe.learn-pc.client.user/kotoken.create/1.0.0?app_id={app_id}', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{app_id: '{app_id}', user_id: '{user_id}'}})
                }});
                const data = await resp.json();
                return JSON.stringify(data);
            }} catch(e) {{
                return 'Error: ' + e.message;
            }}
        }}""")
        log(f"  kotoken response: {kotoken_result[:500]}")
        kotoken_data = None
        try:
            kotoken_data = json.loads(kotoken_result) if kotoken_result.startswith('{') else None
        except:
            log(f"  Could not parse kotoken response (likely truncated)")
        if kotoken_data and kotoken_data.get('code') == 0:
            encrypted = kotoken_data.get('data', {}).get('encrypted_cookies', '')
            log(f"  encrypted_cookies length: {len(encrypted)}")
            token_value = encrypted
        else:
            log(f"  kotoken failed or no data")
            token_value = ""

        # === Step 2: Try accessing h5 with kotoken as cookie ===
        log("\n=== Trying h5 with kotoken as cookie on .xiaoeknow.com ===")
        # Already have token_value from above

        if token_value:
            h5_context_pc = browser.new_context(
                viewport={"width": 1280, "height": 900},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            # Add ALL cookies from PC context + kotoken for h5 domain
            all_pc_cookies = context.cookies()
            h5_context_pc.add_cookies(all_pc_cookies)

            # Also add kotoken as additional auth for xiaoeknow.com
            h5_context_pc.add_cookies([{
                "name": "kotoken",
                "value": token_value,
                "domain": ".xiaoeknow.com",
                "path": "/",
                "httpOnly": False,
                "secure": False,
            }])

            h5_page = h5_context_pc.new_page()
            h5_page.on("request", lambda req: log(f"  REQ: {req.url[:200]}") if '.m3u8' in req.url or '.mp4' in req.url else None)

            h5_url = f"https://appzsnu8fxf7905.h5.xiaoeknow.com/v3/course/alive/{rid}?type=2"
            log(f"  Navigating to: {h5_url}")
            try:
                h5_page.goto(h5_url, wait_until="domcontentloaded", timeout=30000)
                time.sleep(5)
                log(f"  URL: {h5_page.url}")
                log(f"  Title: {h5_page.title()}")
                if "login" not in h5_page.url.lower() and "auth" not in h5_page.url.lower():
                    log(f"  *** LOADED!")
                else:
                    log(f"  -> Still login redirect (kotoken didn't help)")
            except Exception as e:
                log(f"  Error: {e}")
            h5_page.close()
            h5_context_pc.close()

        # === Step 3: Try XHR-based h5 API calls ===
        # The h5 page loads data via APIs. Maybe we can call these directly from the PC domain.
        log("\n=== Trying h5 APIs from PC context ===")

        # Try the alive detail API
        api_tests = [
            f"https://admin.xiaoe-tech.com/xe/asset/alive/get/1.0.0?alive_id={rid}&app_id={app_id}",
            f"https://admin.xiaoe-tech.com/xe/asset/alive/get_alive_resource/1.0.0?alive_id={rid}&app_id={app_id}",
            f"https://admin.xiaoe-tech.com/xe/asset/resource/get_by_id/1.0.0?resource_id={rid}&app_id={app_id}",
        ]

        for api_url in api_tests:
            log(f"\n  Trying: {api_url}")
            try:
                resp = page.evaluate(f"""async () => {{
                    try {{
                        const resp = await fetch('{api_url}', {{credentials: 'include'}});
                        const text = await resp.text();
                        return {{status: resp.status, body: text.slice(0, 1000)}};
                    }} catch(e) {{
                        return {{error: e.message}};
                    }}
                }}""")
                log(f"    Response: {json.dumps(resp, ensure_ascii=False)[:500]}")
            except Exception as e:
                log(f"    Error: {e}")

        # === Step 4: Try study.xiaoe-tech.com API endpoints ===
        # The PC page has its own APIs under xe.learn-pc
        log("\n=== Trying PC API endpoints ===")
        study_apis = [
            f"/xe.learn-pc/living_live_detail.get/1.0.0?alive_id={rid}",
            f"/xe.learn-pc/alive_resource.get/1.0.0?alive_id={rid}",
            f"/xe.learn-pc/course_detail.get/1.0.0?resource_id={rid}",
            f"/xe.learn-pc/course_player_info.get/1.0.0?resource_id={rid}",
        ]

        for api_path in study_apis:
            log(f"\n  Trying: {api_path}")
            try:
                resp = page.evaluate(f"""async () => {{
                    try {{
                        const resp = await fetch('{api_path}', {{credentials: 'include'}});
                        const text = await resp.text();
                        return {{status: resp.status, body: text.slice(0, 1000)}};
                    }} catch(e) {{
                        return {{error: e.message}};
                    }}
                }}""")
                log(f"    Response: {json.dumps(resp, ensure_ascii=False)[:500]}")
            except Exception as e:
                log(f"    Error: {e}")

        # === Step 5: Try the h5 API from the PC domain ===
        log("\n=== Trying h5 APIs from PC context (same domain) ===")
        h5_apis = [
            f"https://appzsnu8fxf7905.h5.xiaoeknow.com/xe.micro_page.common.public.data.get/1.0.0",
            f"https://appzsnu8fxf7905.h5.xiaoeknow.com/_alive/file_tag_info?system_name=live_h5&page_name=live_h5&from_client=live_h5&gray_app_id={app_id}&deploy_env=pro&version=v3",
        ]

        for api_url in h5_apis:
            log(f"\n  Trying: {api_url}")
            try:
                resp = page.evaluate(f"""async () => {{
                    try {{
                        const resp = await fetch('{api_url}', {{credentials: 'include'}});
                        const text = await resp.text();
                        return {{status: resp.status, body: text.slice(0, 1000)}};
                    }} catch(e) {{
                        return {{error: e.message}};
                    }}
                }}""")
                log(f"    Response: {json.dumps(resp, ensure_ascii=False)[:500]}")
            except Exception as e:
                log(f"    Error: {e}")

        # === Step 6: Try page.evaluate to call the $request method ===
        # The Vue components use `this.$request('api_name', params)`
        log("\n=== Trying $request API pattern ===")
        request_result = page.evaluate(f"""async () => {{
            const card = document.querySelector('.course-card-list');
            if (!card || !card.__vue__) return 'no vue';

            const vm = card.__vue__;

            // Find parent with $request
            let p = vm.$parent;
            while (p) {{
                if (p.$request) {{
                    try {{
                        const result = await p.$request('living_live_detail_get', {{
                            alive_id: '{rid}',
                        }});
                        return JSON.stringify(result).slice(0, 2000);
                    }} catch(e) {{
                        return 'Error: ' + e.message;
                    }}
                }}
                p = p.$parent;
            }}
            return 'no $request found';
        }}""")
        log(f"  $request result: {request_result[:500]}")
        time.sleep(2)

        # === Step 7: One more approach — try the getAntiTheft API ===
        # The parent has getAntiTheft method
        log("\n=== Checking getAntiTheft method ===")
        anti_theft = page.evaluate("""() => {
            const card = document.querySelector('.course-card-list');
            if (!card || !card.__vue__) return 'no vue';

            let p = card.__vue__.$parent;
            while (p) {
                if (p.getAntiTheft) {
                    return {haveIt: true, src: p.getAntiTheft.toString().slice(0, 1000)};
                }
                p = p.$parent;
            }
            return 'not found';
        }""")
        log(f"  getAntiTheft: {json.dumps(anti_theft, ensure_ascii=False)[:500]}")

        # === Step 8: Check the checkCourseInterest method ===
        course_interest = page.evaluate("""() => {
            const card = document.querySelector('.course-card-list');
            if (!card || !card.__vue__) return 'no vue';

            let p = card.__vue__.$parent;
            while (p) {
                if (p.checkCourseInterest) {
                    return {haveIt: true, src: p.checkCourseInterest.toString().slice(0, 1000)};
                }
                p = p.$parent;
            }
            return 'not found';
        }""")
        log(f"  checkCourseInterest: {json.dumps(course_interest, ensure_ascii=False)[:500]}")

        time.sleep(10)
        browser.close()

if __name__ == "__main__":
    main()
