"""
小鹅通 — 通过 Ht.Http (vue-resource) 调用 pc_client API，看拦截器和完整响应
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

        # Step 1: Get course detail from $request (knows how to auth properly)
        log("\n=== Get course list from $request ===")
        course_data = page.evaluate("""async () => {
            const card = document.querySelector('.course-card-list');
            if (!card || !card.__vue__) return 'no vue';
            let p = card.__vue__.$parent;
            while (p) {
                if (p.$request) {
                    const r = await p.$request('living_live_list_get', {page_size: 16, page_params: '1-0-0'});
                    if (r && r.code === 0) {
                        // Return first course detail
                        const list = r.data && r.data.list ? r.data.list.slice(0, 3) : [];
                        return JSON.stringify(list).substring(0, 3000);
                    }
                    return JSON.stringify(r);
                }
                p = p.$parent;
            }
            return 'no $request';
        }""")
        log(f"Course list sample: {course_data[:2000]}")

        # Step 2: Get full living_live_list response looking for media URLs
        log("\n=== Full living_live_list response (looking for video URLs) ===")
        full_list = page.evaluate("""async () => {
            const card = document.querySelector('.course-card-list');
            if (!card || !card.__vue__) return 'no vue';
            let p = card.__vue__.$parent;
            while (p) {
                if (p.$request) {
                    const r = await p.$request('living_live_list_get', {page_size: 16, page_params: '1-0-0'});
                    if (r && r.code === 0) {
                        return JSON.stringify(r.data).substring(0, 5000);
                    }
                    return JSON.stringify(r);
                }
                p = p.$parent;
            }
            return 'no $request';
        }""")
        # Search for media/URL fields in the response
        log("Searching for URL fields...")
        if 'http' in full_list.lower() or 'm3u8' in full_list.lower() or 'video' in full_list.lower() or 'url' in full_list.lower():
            # Find http/m3u8/video in the output
            for keyword in ['http', 'm3u8', 'video', 'url', 'play', 'media']:
                idx = full_list.lower().find(keyword)
                if idx >= 0:
                    start = max(0, idx - 50)
                    end = min(len(full_list), idx + 150)
                    log(f"  '{keyword}' at {idx}: ...{full_list[start:end]}...")
        else:
            log(f"  No media URLs found in response")
            log(f"  Full response: {full_list[:2000]}")

        # Step 3: Use vue-resource (Ht.Http) to call pc_client - the proper way
        log("\n=== Using vue-resource (Ht.Http) to call pc_client ===")
        vue_result = page.evaluate("""async (rid) => {
            try {
                // Check if vue-resource is accessible
                const card = document.querySelector('.course-card-list');
                if (!card || !card.__vue__) return 'no vue';

                // Get b_user_id from check_token
                const tokenResp = await fetch('/xe.learn-pc.user/check_token');
                const tokenData = await tokenResp.json();
                const b_user_id = tokenData.data && tokenData.data.b_user_id ? tokenData.data.b_user_id : '';

                let p = card.__vue__.$parent;
                while (p) {
                    // Check if parent has Ht (vue-resource)
                    if (p.Ht && p.Ht.Http) {
                        // Use the app's vue-resource to make the call
                        const {Http} = p.Ht;

                        // Get p_token from cookie
                        const m = document.cookie.match(/(^| )p_token=([^;]*)(;|$)/);
                        const p_token = m ? m[2] : '';
                        const app_id = 'appzsnu8fxf7905';

                        try {
                            const response = await Http.post(
                                '/pc_client/xe.big_class.course.jump_url',
                                {user_id: b_user_id, app_id: app_id, alive_id: rid},
                                {headers: {'app-token': p_token}}
                            );
                            return 'Ht.Http OK: ' + JSON.stringify(response).substring(0, 1000);
                        } catch(e) {
                            return 'Ht.Http error: ' + e.message;
                        }
                    }
                    p = p.$parent;
                }

                // If no Ht, try $http (vue-resource's global registration)
                try {
                    // Vue.http might be available
                    const vm = card.__vue__;
                    const app_id = 'appzsnu8fxf7905';
                    const m = document.cookie.match(/(^| )p_token=([^;]*)(;|$)/);
                    const p_token = m ? m[2] : '';

                    if (vm.$http) {
                        const response = await vm.$http.post(
                            '/pc_client/xe.big_class.course.jump_url',
                            {user_id: b_user_id, app_id: app_id, alive_id: rid},
                            {headers: {'app-token': p_token}}
                        );
                        return '$http OK: ' + JSON.stringify(response).substring(0, 1000);
                    }
                } catch(e) {
                    // ignore
                }

                return 'no Ht or $http found';
            } catch(e) {
                return 'error: ' + e.message;
            }
        }""", rid)
        log(f"vue-resource result: {vue_result[:500]}")

        # Step 4: Also try the living_live_list_get to check if course has detail API
        log("\n=== Try my_attend_normal_list_get (for resource_type info) ===")
        attend_list = page.evaluate("""async () => {
            const card = document.querySelector('.course-card-list');
            if (!card || !card.__vue__) return 'no vue';
            let p = card.__vue__.$parent;
            while (p) {
                if (p.$request) {
                    const r = await p.$request('my_attend_normal_list_get', {page_size: 50, page_index: 1});
                    if (r && r.code === 0) {
                        return JSON.stringify(r.data).substring(0, 4000);
                    }
                    return JSON.stringify(r);
                }
                p = p.$parent;
            }
            return 'no $request';
        }""")
        log(f"Attend list: {attend_list[:2000]}")

        # Step 5: List all Vue parent keys to find any API-related methods
        log("\n=== Finding API-related methods on Vue parent ===")
        all_keys = page.evaluate("""() => {
            const card = document.querySelector('.course-card-list');
            if (!card || !card.__vue__) return [];
            let p = card.__vue__.$parent;
            const keys = new Set();
            while (p) {
                Object.keys(p).forEach(k => {
                    if (!k.startsWith('$') && !k.startsWith('_')) keys.add(k);
                });
                p = p.$parent;
            }
            return Array.from(keys);
        }""")
        log(f"All Vue parent keys: {json.dumps(all_keys, ensure_ascii=False)[:1000]}")

        browser.close()
        log("\nDone.")

if __name__ == "__main__":
    main()
