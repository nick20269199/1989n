"""
小鹅通 — 深挖Vue组件方法源码 + 在PC页面内触发课程详情
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

        # Capture XHR/fetch requests (not static assets)
        api_calls = []
        page.on("response", lambda resp: (
            api_calls.append({"url": resp.url, "status": resp.status})
            if resp.request.resource_type in ("xhr", "fetch")
            or "admin.xiaoe-tech.com" in resp.url
            or ".m3u8" in resp.url or ".mp4" in resp.url
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

        # === Step 1: Deep inspect Vue component methods ===
        log("\n=== DEEP Vue method inspection (first card) ===")
        methods_src = page.evaluate("""() => {
            const card = document.querySelector('.course-card-list');
            if (!card || !card.__vue__) return {error: 'no vue'};
            const vm = card.__vue__;

            const result = {};

            // Get the component's options (includes methods source)
            if (vm.$options) {
                if (vm.$options.methods) {
                    result.methods = {};
                    for (const [name, fn] of Object.entries(vm.$options.methods)) {
                        result.methods[name] = fn.toString().slice(0, 1000);
                    }
                }
                if (vm.$options.computed) {
                    result.computed = Object.keys(vm.$options.computed);
                }
                // Check for template or render function
                if (vm.$options.template) result.template = vm.$options.template.slice(0, 500);
                if (vm.$options.render) result.hasRender = vm.$options.render.toString().slice(0, 200);
            }

            // Check parent component's methods too
            let parent = vm.$parent;
            let depth = 0;
            while (parent && depth < 20) {
                const tag = parent.$options && (parent.$options._componentTag || parent.$options.name || '');
                if (parent.$options && parent.$options.methods) {
                    const pMethods = Object.keys(parent.$options.methods);
                    if (pMethods.length > 0) {
                        result[`parent_${depth}_methods`] = pMethods;
                        // Get source of jumpClass or enterLive-like methods
                        for (const m of pMethods) {
                            if (m.includes('jump') || m.includes('enter') || m.includes('click') || m.includes('open') || m.includes('live') || m.includes('play') || m.includes('nav')) {
                                const fn = parent.$options.methods[m];
                                result[`parent_${depth}_${m}`] = fn.toString().slice(0, 1500);
                            }
                        }
                    }
                }
                // Check for event listeners
                if (parent._events) {
                    const events = Object.keys(parent._events);
                    if (events.length > 0) result[`parent_${depth}_events`] = events;
                }
                if (tag) result[`parent_${depth}_tag`] = tag;
                parent = parent.$parent;
                depth++;
            }

            // Check root for methods
            if (vm.$root && vm.$root !== vm) {
                const root = vm.$root;
                if (root.$options && root.$options.methods) {
                    const rootMethods = Object.keys(root.$options.methods);
                    if (rootMethods.length > 0) result.root_methods = rootMethods;
                }
            }

            return result;
        }""")
        for k, v in methods_src.items():
            log(f"  {k}:")
            if isinstance(v, str):
                for line in v.split('\n'):
                    log(f"    {line}")
            else:
                log(f"    {json.dumps(v, ensure_ascii=False)[:500]}")

        # === Step 2: Find the component that handles enterLive ===
        log("\n=== Finding enterLive handler ===")
        enter_live = page.evaluate("""() => {
            const card = document.querySelector('.course-card-list');
            if (!card || !card.__vue__) return {};
            const vm = card.__vue__;

            // Walk up and find who listens to 'enterLive'
            let parent = vm.$parent;
            let depth = 0;
            while (parent && depth < 30) {
                if (parent._events && parent._events.enterLive) {
                    return {
                        found: true,
                        depth: depth,
                        tag: (parent.$options && (parent.$options._componentTag || parent.$options.name)) || 'unknown',
                        handlers: parent._events.enterLive.length
                    };
                }
                parent = parent.$parent;
                depth++;
            }
            return {found: false, depth: depth};
        }""")
        log(f"  {json.dumps(enter_live, ensure_ascii=False)}")

        # === Step 3: Try calling jumpClass with all possible approaches ===
        log("\n=== Trying to trigger course detail via multiple methods ===")

        for method_name in ['jumpClass', 'enterLive', 'handleClick', 'goDetail', 'openCourse']:
            result = page.evaluate(f"""() => {{
                const card = document.querySelector('.course-card-list');
                if (!card || !card.__vue__) return {{error: 'no vue'}};
                const vm = card.__vue__;

                // Search up the tree for this method
                let target = vm;
                let depth = 0;
                while (target && depth < 20) {{
                    if (typeof target.{method_name} === 'function') {{
                        try {{
                            const r = target.{method_name}();
                            return {{found: true, depth: depth, result: r, tag: (target.$options && target.$options._componentTag) || ''}};
                        }} catch(e) {{
                            return {{found: true, depth: depth, error: e.message, tag: (target.$options && target.$options._componentTag) || ''}};
                        }}
                    }}
                    target = target.$parent;
                    depth++;
                }}
                return {{found: false}};
            }}""")
            log(f"  {method_name}: {json.dumps(result, ensure_ascii=False)[:500]}")

        # === Step 4: Check for any popup/modal/overlay mechanism ===
        log("\n=== Checking for modal/overlay mechanism ===")
        modal_info = page.evaluate("""() => {
            const result = {};

            // Check for Vue modal components
            const all = document.querySelectorAll('*');
            const masks = [];
            const modals = [];
            for (const el of all) {
                const cls = el.className || '';
                if (typeof cls !== 'string') continue;
                if (cls.includes('mask') || cls.includes('Mask') || cls.includes('overlay') || cls.includes('Overlay')) {
                    const rect = el.getBoundingClientRect();
                    masks.push({
                        class: cls.slice(0, 60),
                        visible: rect.width > 0 && rect.height > 0 && el.offsetParent !== null,
                        hasVue: !!el.__vue__,
                    });
                }
                if (cls.includes('modal') || cls.includes('Modal') || cls.includes('dialog') || cls.includes('Dialog') || cls.includes('popup') || cls.includes('Popup')) {
                    const rect = el.getBoundingClientRect();
                    modals.push({
                        class: cls.slice(0, 60),
                        visible: rect.width > 0 && rect.height > 0 && el.offsetParent !== null,
                        size: {w: rect.width, h: rect.height},
                    });
                }
            }
            result.masks = masks.slice(0, 10);
            result.modals = modals.slice(0, 10);

            // Check iframe
            result.iframes = document.querySelectorAll('iframe').length;

            // Check for a video container div
            const containers = document.querySelectorAll('[class*="container"], [class*="video"], [class*="player"], [class*="live"]');
            result.containers = Array.from(containers).slice(0, 5).map(el => ({
                class: (el.className || '').slice(0, 60),
                visible: el.offsetParent !== null,
            }));

            return result;
        }""")
        for k, v in modal_info.items():
            log(f"  {k}: {json.dumps(v, ensure_ascii=False)[:500]}")

        # === Step 5: Try directly dispatching enterLive with cardData ===
        log("\n=== Dispatching enterLive with cardData ===")
        result = page.evaluate("""() => {
            const card = document.querySelector('.course-card-list');
            if (!card || !card.__vue__) return {error: 'no vue'};
            const vm = card.__vue__;

            // Get cardData from props
            const cardData = vm.$options.propsData.cardData;
            if (!cardData) return {error: 'no cardData'};

            // Walk up and find enterLive listener
            let parent = vm.$parent;
            let depth = 0;
            while (parent && depth < 30) {
                if (parent._events && parent._events.enterLive) {
                    // Call all enterLive handlers with cardData as arg
                    parent._events.enterLive.forEach(handler => {
                        try {
                            handler(cardData);
                        } catch(e) {}
                    });
                    return {
                        called: true,
                        depth: depth,
                        handlerCount: parent._events.enterLive.length,
                        tag: (parent.$options && (parent.$options._componentTag || parent.$options.name)) || ''
                    };
                }
                parent = parent.$parent;
                depth++;
            }
            return {found: false, depth: depth};
        }""")
        log(f"  {json.dumps(result, ensure_ascii=False)}")
        time.sleep(5)

        # Check for new API calls after enterLive dispatch
        new_calls = [c for c in api_calls if c not in api_calls[:len(api_calls)-len([1 for _ in api_calls if True])]]
        # Actually, let's just check if there are NEW calls
        log(f"\nTotal API calls so far: {len(api_calls)}")
        for c in api_calls:
            if 'admin.xiaoe-tech.com' in c['url']:
                log(f"  [{c['status']}] {c['url'][:200]}")

        # === Step 6: Try opening the h5 URL inside an iframe on the PC page ===
        log("\n=== Trying to load h5 in iframe ===")
        iframe_result = page.evaluate("""() => {
            const iframe = document.createElement('iframe');
            iframe.style.display = 'none';
            iframe.src = 'https://appzsnu8fxf7905.h5.xiaoeknow.com/v3/course/alive/l_6a15546fe4b0694c5bca44b0?type=2';
            document.body.appendChild(iframe);
            return 'iframe added';
        }""")
        log(f"  {iframe_result}")
        time.sleep(5)

        # Check if the iframe loaded differently
        iframe_count = page.evaluate("document.querySelectorAll('iframe').length")
        log(f"  Iframes in page: {iframe_count}")

        # List all API calls one more time
        log(f"\n=== ALL XHR/Fetch API calls ===")
        for c in api_calls:
            log(f"  [{c['status']}] {c['url'][:200]}")

        time.sleep(5)
        browser.close()

if __name__ == "__main__":
    main()
