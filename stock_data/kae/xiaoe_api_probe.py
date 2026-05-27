"""
小鹅通 — 通过 $request API 发现模式 + 拦截 h5 auth 检查
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

    all_video_urls = {}
    found_m3u8 = []

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
                    user_id: data.user_id,
                });
            });
            return courses;
        }""")

        # === Approach 1: Try various $request API endpoints ===
        log("=== Probing $request API endpoints ===")
        api_names = [
            # Alive/course detail APIs
            "alive_detail_get",
            "alive_resource_get",
            "alive_player_url_get",
            "alive_get",
            "alive_info_get",
            "alive_play_info_get",
            "index_getAliveDetail",
            "index_alive_detail",
            "get_alive_detail",
            "get_alive_info",
        ]

        first = course_data[0]
        rid = first["resource_id"]

        for api_name in api_names:
            result = page.evaluate(f"""async () => {{
                const card = document.querySelector('.course-card-list');
                if (!card || !card.__vue__) return null;
                let p = card.__vue__.$parent;
                while (p) {{
                    if (p.$request) {{
                        try {{
                            const r = await p.$request('{api_name}', {{alive_id: '{rid}'}});
                            if (r && r.code === 0) return {{success: true, data: JSON.stringify(r).slice(0, 500)}};
                            return {{notFound: r && r.code === 404 ? true : false, code: r ? r.code : null}};
                        }} catch(e) {{
                            return {{error: e.message}};
                        }}
                    }}
                    p = p.$parent;
                }}
                return null;
            }}""")
            if result and result.get('success'):
                log(f"  *** FOUND: {api_name} -> {json.dumps(result, ensure_ascii=False)[:500]}")
            elif result:
                log(f"  {api_name}: {json.dumps(result, ensure_ascii=False)[:200]}")

        # === Approach 2: Profile the actual $request API list ===
        # The Vue app has a mapping of API names to actual URLs
        log("\n=== Finding $request API mappings ===")
        api_mappings = page.evaluate("""() => {
            const card = document.querySelector('.course-card-list');
            if (!card || !card.__vue__) return null;
            const vm = card.__vue__;

            // $request is added to Vue prototype
            // Check Vue.prototype
            const proto = Object.getPrototypeOf(vm);
            const result = {};

            // Check for API_URL or API mappings on the vm or its prototype
            for (const key of Object.getOwnPropertyNames(proto)) {
                if (key.includes('api') || key.includes('API') || key.includes('request') || key.includes('url') || key.includes('URL')) {
                    try { result[key] = String(proto[key]).slice(0, 500); } catch(e) {}
                }
            }

            // Check for request interceptors or API configs
            if (vm.$request) {
                result.hasRequest = true;
                // $request might have a list or config attached
                for (const key of Object.getOwnPropertyNames(vm.$request)) {
                    if (key.includes('api') || key.includes('API')) {
                        try { result['request_' + key] = JSON.stringify(vm.$request[key]).slice(0, 500); } catch(e) {}
                    }
                }
            }

            // Check window for API configs
            if (window.__API_CONFIG__) result.apiConfig = JSON.stringify(window.__API_CONFIG__).slice(0, 1000);
            if (window.__api_list__) result.apiList = JSON.stringify(window.__api_list__).slice(0, 1000);

            return result;
        }""")
        if api_mappings:
            for k, v in api_mappings.items():
                log(f"  {k}: {v}")
        else:
            log(f"  No mappings found")

        # === Approach 3: Intercept h5 auth and try to "force" pass it ===
        log("\n=== Attempt: intercept h5 auth to force-bypass ===")

        # Create a new page that intercepts auth-related API responses
        h5_page = context.new_page()

        # Intercept login/auth XHR
        def intercept_response(response):
            url = response.url
            if "get_do_verification_h5" in url:
                log(f"  Intercepted verification! Returning success.")
                # We can't actually modify the response body, but we can log it
                try:
                    body = response.text()[:500]
                    log(f"  Original verification response: {body}")
                except:
                    pass

        h5_page.on("response", intercept_response)

        # Intercept the route to prevent redirect
        def handle_route(route):
            url = route.request.url
            if "login/auth" in url:
                log(f"  Blocked login redirect: {url[:150]}")
                route.abort()
            else:
                route.continue_()

        h5_page.route("**/*", handle_route)

        try:
            h5_url = f"https://appzsnu8fxf7905.h5.xiaoeknow.com/v3/course/alive/{rid}?type=2"
            log(f"Navigating (with redirect blocking): {h5_url}")
            h5_page.goto(h5_url, wait_until="domcontentloaded", timeout=15000)
            time.sleep(5)
            log(f"  URL: {h5_page.url}")
            log(f"  Title: {h5_page.title()}")
            body = h5_page.content()
            log(f"  Content length: {len(body)}")

            # Check if the blocked redirect caused a different state
            # The page might have rendered some content before the redirect was attempted
            text = h5_page.inner_text("body")
            log(f"  Body text: {text[:500]}")
        except Exception as e:
            log(f"  Error: {e}")

        h5_page.close()

        # === Approach 4: Open h5 in same context WITHOUT userAgent override
        # and check what the actual page HTML looks like
        log("\n=== h5 page raw load (inspect initial HTML) ===")
        h5_page2 = context.new_page()

        # Don't intercept anything initially - just capture the raw HTML
        h5_page2.on("response", lambda resp: (
            log(f"  INIT: {resp.status} {resp.url[:200]}")
            if "login/auth" in resp.url or "alive" in resp.url
            else None
        ))

        h5_url = f"https://appzsnu8fxf7905.h5.xiaoeknow.com/v3/course/alive/{rid}?type=2"
        log(f"Loading: {h5_url}")
        try:
            h5_page2.goto(h5_url, wait_until="domcontentloaded", timeout=15000)
            time.sleep(3)
            initial_html = h5_page2.content()
            log(f"Initial content length: {len(initial_html)}")

            # Save the initial page HTML for analysis
            with open(os.path.join(CAPTURE_DIR, f"xe_page_init.html"), "w", encoding="utf-8") as f:
                f.write(initial_html)

            # Extract any embedded data
            embedded = h5_page2.evaluate("""() => {
                const result = {};
                // Check for SSR data
                const scripts = document.querySelectorAll('script');
                for (const s of scripts) {
                    const text = s.textContent || '';
                    if (text.includes('resource_id') || text.includes('alive') || text.includes('video') || text.includes('m3u8') || text.includes('mp4')) {
                        result[s.id || 'script_' + scripts.length] = text.slice(0, 500);
                    }
                    if (text.includes('window.__') || text.includes('window._') || text.includes('window.xiaoe')) {
                        const match = text.match(/window\.(__[^=]+|_[^=]+|xiaoe[^=]+)/);
                        if (match) result[match[1]] = text.slice(0, 500);
                    }
                }
                // Check for meta tags with course data
                const metas = document.querySelectorAll('meta[name]');
                for (const m of metas) {
                    result['meta_' + m.getAttribute('name')] = m.getAttribute('content') || '';
                }
                return result;
            }""")
            for k, v in embedded.items():
                log(f"  Embedded: {k} = {str(v)[:200]}")

        except Exception as e:
            log(f"  Error: {e}")

        h5_page2.close()

        # === Approach 5: Try the h5 page WITHOUT redirect blocking and check the actual login redirect page HTML ===
        log("\n=== Redirect page HTML analysis ===")
        h5_page3 = context.new_page()
        h5_page3.on("response", lambda resp: (
            log(f"  RESP {resp.status}: {resp.url[:200]}")
        ))

        try:
            h5_page3.goto(h5_url, wait_until="domcontentloaded", timeout=15000)
            time.sleep(5)
            # By now we should be on the login page
            redirect_html = h5_page3.content()
            with open(os.path.join(CAPTURE_DIR, f"xe_page_login.html"), "w", encoding="utf-8") as f:
                f.write(redirect_html)
            log(f"Redirect page saved: {len(redirect_html)} bytes")
        except Exception as e:
            log(f"  Error: {e}")
        h5_page3.close()

        # Summary
        log(f"\n{'='*60}")
        log("SUMMARY:")
        log(f"  Video URLs found: {len(all_video_urls)}")
        log(f"  M3U8 requests: {len(found_m3u8)}")
        for u in found_m3u8:
            log(f"    {u}")

        time.sleep(5)
        browser.close()

if __name__ == "__main__":
    main()
