"""
小鹅通 — 从PC页面内部触发课程详情，拦截API调用获取视频地址
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

        # === Load PC page ===
        page = context.new_page()

        # Capture ALL XHR/fetch to admin or relevant APIs
        api_calls = []
        page.on("response", lambda resp: (
            api_calls.append({"url": resp.url, "status": resp.status, "headers": dict(resp.headers)})
            if ("admin.xiaoe-tech.com" in resp.url or ".m3u8" in resp.url or ".mp4" in resp.url or "txvideo" in resp.url or "vod" in resp.url)
            and ("js" not in resp.url and "css" not in resp.url and "png" not in resp.url)
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

        # === Get course card data ===
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

        # Get course cards reference
        cards_el = page.query_selector_all(".course-card-list")
        log(f"Card elements: {len(cards_el)}")

        # === Try to trigger course detail via Vue method ===
        # Instead of clicking, call the internal method directly
        # The card should have methods like enterLive or jumpClass
        for i, course in enumerate(course_data[:5]):  # Try first 5
            rid = course["resource_id"]
            title = course["title"]
            log(f"\n[{i+1}] {title}")

            api_before = len(api_calls)

            # Method 1: Call enterLive via Vue component
            log(f"  Calling enterLive on card {i}...")
            result = page.evaluate(f"""() => {{
                const cards = document.querySelectorAll('.course-card-list');
                const card = cards[{i}];
                if (!card || !card.__vue__) return {{error: 'no vue'}};
                const vm = card.__vue__;
                return vm.$emit('enterLive', {{}});
            }}""")
            log(f"  enterLive emit: {result}")
            time.sleep(3)

            # Check if any new API calls appeared
            new_calls = api_calls[api_before:]
            if new_calls:
                log(f"  API calls after enterLive:")
                for c in new_calls:
                    log(f"    [{c['status']}] {c['url'][:200]}")
            else:
                log(f"  No new API calls")

            api_before = len(api_calls)

            # Method 2: Try calling jumpClass with the resource data
            log(f"  Trying jumpClass on card {i}...")
            result = page.evaluate(f"""() => {{
                const cards = document.querySelectorAll('.course-card-list');
                const card = cards[{i}];
                if (!card || !card.__vue__) return {{error: 'no vue'}};
                const vm = card.__vue__;
                // Check if jumpClass exists
                if (typeof vm.jumpClass === 'function') {{
                    vm.jumpClass();
                    return {{called: true}};
                }}
                // Check parent
                let parent = vm.$parent;
                let depth = 0;
                while (parent && depth < 10) {{
                    if (typeof parent.jumpClass === 'function') {{
                        parent.jumpClass();
                        return {{called: true, parent: true, depth: depth}};
                    }}
                    // Check methods
                    if (parent.$options && parent.$options.methods && parent.$options.methods.jumpClass) {{
                        return {{hasMethod: true, depth: depth}};
                    }}
                    parent = parent.$parent;
                    depth++;
                }}
                return {{notFound: true}};
            }}""")
            log(f"  jumpClass: {result}")
            time.sleep(3)

            new_calls = api_calls[api_before:]
            if new_calls:
                log(f"  API calls after jumpClass:")
                for c in new_calls:
                    log(f"    [{c['status']}] {c['url'][:200]}")
                    # If there's a video URL in response, capture it
                    try:
                        if 'm3u8' in c['url'] or 'mp4' in c['url']:
                            log(f"    *** VIDEO URL FOUND!")
                    except:
                        pass
            else:
                log(f"  No new API calls after jumpClass")

        # === Method 3: Try the admin API directly ===
        # Based on common 小鹅通 API patterns
        log(f"\n{'='*60}")
        log(f"Trying direct admin API calls...")

        # We need cookies for admin.xiaoe-tech.com
        # Check if we have them
        admin_cookies = [c for c in context.cookies() if 'admin.xiaoe-tech.com' in c['domain']]
        log(f"admin.xiaoe-tech.com cookies: {len(admin_cookies)}")

        # Try to discover API endpoints from the page's JS or data
        api_discovery = page.evaluate("""() => {
            // Check window for API base URL config
            const result = {};
            if (window.XiaoEConfig) result.XiaoEConfig = JSON.stringify(window.XiaoEConfig).slice(0, 500);
            if (window.GLOBAL_CONFIG) result.GLOBAL_CONFIG = JSON.stringify(window.GLOBAL_CONFIG).slice(0, 500);
            if (window.xiaoeConfig) result.xiaoeConfig = JSON.stringify(window.xiaoeConfig).slice(0, 500);
            // Check __NEXT_DATA__ or SSR data
            if (window.__NUXT__) result.__NUXT__ = JSON.stringify(window.__NUXT__).slice(0, 500);
            if (window.__INITIAL_STATE__) result.__INITIAL_STATE__ = JSON.stringify(window.__INITIAL_STATE__).slice(0, 500);
            // Check for __NEXT_DATA__
            try {
                const el = document.getElementById('__NEXT_DATA__');
                if (el) result.__NEXT_DATA__ = el.textContent.slice(0, 500);
            } catch(e) {}
            try {
                const el = document.getElementById('__APP_DATA__');
                if (el) result.__APP_DATA__ = el.textContent.slice(0, 500);
            } catch(e) {}
            return result;
        }""")
        for k, v in api_discovery.items():
            log(f"  {k}: {v}")

        # === Method 4: Try to make the card actually navigate ===
        # Click the card using force=True (bypasses overlay detection)
        log(f"\n{'='*60}")
        log(f"Trying force-click on first card...")
        if cards_el:
            api_before = len(api_calls)
            cards_el[0].click(force=True)
            time.sleep(5)

            log(f"  URL: {page.url}")
            new_calls = api_calls[api_before:]
            if new_calls:
                log(f"  API calls after force-click:")
                for c in new_calls:
                    log(f"    [{c['status']}] {c['url'][:200]}")
            else:
                log(f"  No new API calls after force-click")

        # Print all API calls for analysis
        log(f"\n{'='*60}")
        log(f"ALL admin API calls captured: {len([c for c in api_calls if 'admin.xiaoe-tech.com' in c['url']])}")
        for c in api_calls:
            if 'admin.xiaoe-tech.com' in c['url']:
                log(f"  [{c['status']}] {c['url'][:200]}")

        time.sleep(5)
        browser.close()

if __name__ == "__main__":
    main()
