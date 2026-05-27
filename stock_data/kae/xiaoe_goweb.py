"""
小鹅通 — 找到 goWeb 方法 + 触发课程详情 + 拦截视频API
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

        # Capture ALL XHR/Fetch
        api_calls = []
        page.on("response", lambda resp: (
            api_calls.append({"url": resp.url, "status": resp.status, "body": resp.text()[:2000] if resp.status == 200 else ""})
            if resp.request.resource_type in ("xhr", "fetch") or "admin.xiaoe-tech.com" in resp.url
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

        # === Step 1: Find goWeb method ===
        log("=== Finding goWeb method ===")
        goWeb_info = page.evaluate("""() => {
            const result = {};

            // Search on the card component and all ancestors
            const card = document.querySelector('.course-card-list');
            if (!card || !card.__vue__) return {error: 'no vue'};
            const vm = card.__vue__;

            // Check card component
            if (vm.goWeb) {
                result.card = {found: true, src: vm.goWeb.toString().slice(0, 1500)};
            }

            // Check all parents
            let parent = vm.$parent;
            let depth = 1;
            while (parent && depth < 20) {
                if (parent.goWeb) {
                    result[`parent_${depth}_goWeb`] = parent.goWeb.toString().slice(0, 1500);
                    const tag = parent.$options && (parent.$options._componentTag || parent.$options.name);
                    result[`parent_${depth}_tag`] = tag || 'unknown';
                }
                // Check methods
                if (parent.$options && parent.$options.methods) {
                    for (const [name, fn] of Object.entries(parent.$options.methods)) {
                        if (name.includes('go') || name.includes('web') || name.includes('nav') || name.includes('open')) {
                            result[`parent_${depth}_${name}`] = fn.toString().slice(0, 1500);
                        }
                    }
                }
                parent = parent.$parent;
                depth++;
            }

            // Check mixins
            if (vm.$options && vm.$options.mixins) {
                result.mixinCount = vm.$options.mixins.length;
                vm.$options.mixins.forEach((m, i) => {
                    if (m.methods) {
                        for (const [name, fn] of Object.entries(m.methods)) {
                            if (name.includes('go') || name.includes('web') || name.includes('nav')) {
                                result[`mixin_${i}_${name}`] = fn.toString().slice(0, 1500);
                            }
                        }
                    }
                });
            }

            return result;
        }""")
        for k, v in goWeb_info.items():
            log(f"  {k}:")
            if isinstance(v, str):
                for line in v.split('\n'):
                    log(f"    {line}")
            else:
                log(f"    {json.dumps(v, ensure_ascii=False)[:500]}")

        # === Step 2: Try calling goWeb(2) directly ===
        # But first, check if it navigates away or opens a modal
        log("\n=== Calling goWeb(2) on first card ===")
        api_before = len(api_calls)

        result = page.evaluate("""() => {
            const card = document.querySelector('.course-card-list');
            if (!card || !card.__vue__) return {error: 'no vue'};

            // Call goWeb on the card (found in render function)
            const vm = card.__vue__;

            // Try multiple targets
            const targets = [vm];
            let p = vm.$parent;
            while (p) { targets.push(p); p = p.$parent; }

            const results = [];
            for (const target of targets) {
                if (typeof target.goWeb === 'function') {
                    try {
                        const r = target.goWeb(2);
                        results.push({target: 'goWeb(2)', result: r !== undefined ? String(r) : 'void'});
                    } catch(e) {
                        results.push({target: 'goWeb(2)', error: e.message});
                    }
                }
            }
            return results;
        }""")
        log(f"  goWeb results: {json.dumps(result, ensure_ascii=False)}")
        time.sleep(5)

        new_calls = api_calls[api_before:]
        log(f"  New API calls: {len(new_calls)}")
        for c in new_calls:
            log(f"    [{c['status']}] {c['url'][:200]}")

        # === Step 3: Check if goWeb navigates or shows a modal ===
        log(f"\n  URL: {page.url}")

        # Check if a video overlay/modal appeared
        overlay = page.evaluate("""() => {
            const result = {};
            const all = document.querySelectorAll('*');
            const overlays = [];
            for (const el of all) {
                const cls = el.className || '';
                if (typeof cls !== 'string') continue;
                if ((cls.includes('overlay') || cls.includes('Overlay') || cls.includes('mask') || cls.includes('Mask') || cls.includes('video') || cls.includes('modal') || cls.includes('dialog') || cls.includes('player')) && el.offsetParent !== null) {
                    const rect = el.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {
                        overlays.push({
                            class: cls.slice(0, 60),
                            size: {w: Math.round(rect.width), h: Math.round(rect.height)},
                            hasVue: !!el.__vue__,
                        });
                    }
                }
            }
            result.overlays = overlays;

            // Check for new iframe
            result.iframes = document.querySelectorAll('iframe').length;

            // Check if a new element appeared
            const container = document.getElementById('common_template_mounted_el_container');
            if (container) {
                result.containerChildren = container.children.length;
                result.containerHTML = container.innerHTML.slice(0, 1000);
            }
            return result;
        }""")
        log(f"  Overlay: {json.dumps(overlay, ensure_ascii=False)[:500]}")

        # === Step 4: Try different goWeb args ===
        log("\n=== Trying goWeb with different args ===")
        for arg in [1, 2, 3, 0, 'alive', 'play', 'detail']:
            api_before = len(api_calls)
            result = page.evaluate(f"""() => {{
                const card = document.querySelector('.course-card-list');
                if (!card || !card.__vue__) return {{error: 'no vue'}};
                const vm = card.__vue__;
                if (typeof vm.goWeb === 'function') {{
                    return String(vm.goWeb({json.dumps(arg)}));
                }}
                return 'no goWeb';
            }}""")
            log(f"  goWeb({arg}): {result}")
            new_calls = api_calls[api_before:]
            if new_calls:
                log(f"    New API calls:")
                for c in new_calls:
                    log(f"      [{c['status']}] {c['url'][:200]}")
            time.sleep(2)

        # === Step 5: Try calling the enterLive on the parent WITH cardData ===
        log("\n=== Calling enterLive on parent with cardData ===")
        api_before = len(api_calls)

        enter_result = page.evaluate("""() => {
            const card = document.querySelector('.course-card-list');
            if (!card || !card.__vue__) return {error: 'no vue'};
            const vm = card.__vue__;

            // Get cardData
            const cardData = vm.$options.propsData.cardData;
            if (!cardData) return {error: 'no cardData'};

            // Find parent with enterLive
            let p = vm.$parent;
            while (p) {
                if (typeof p.enterLive === 'function') {
                    try {
                        const r = p.enterLive(cardData);
                        return {called: true, depth: 0, result: r !== undefined ? String(r) : 'void'};
                    } catch(e) {
                        return {called: false, error: e.message};
                    }
                }
                p = p.$parent;
            }
            return {error: 'enterLive not found'};
        }""")
        log(f"  enterLive: {json.dumps(enter_result, ensure_ascii=False)}")
        time.sleep(5)

        new_calls = api_calls[api_before:]
        log(f"  New API calls: {len(new_calls)}")
        for c in new_calls:
            log(f"    [{c['status']}] {c['url'][:200]}")

        # === Step 6: Try the cardShow method which references oplShow ===
        log("\n=== Trying cardShow on the card ===")
        api_before = len(api_calls)

        card_show = page.evaluate("""() => {
            const card = document.querySelector('.course-card-list');
            if (!card || !card.__vue__) return {error: 'no vue'};
            const vm = card.__vue__;

            // cardShow uses this.cardData — it references oplShow
            // Let's see what oplShow does
            if (typeof vm.oplShow === 'function') {
                try {
                    vm.oplShow();
                    return {oplShow: 'called'};
                } catch(e) {
                    return {oplShow: e.message};
                }
            }

            // Check for cardShow
            if (typeof vm.cardShow === 'function') {
                try {
                    vm.cardShow();
                    return {cardShow: 'called'};
                } catch(e) {
                    return {cardShow: e.message};
                }
            }

            return {error: 'no method found'};
        }""")
        log(f"  {json.dumps(card_show, ensure_ascii=False)}")
        time.sleep(3)
        new_calls = api_calls[api_before:]
        log(f"  New API calls: {len(new_calls)}")
        for c in new_calls:
            log(f"    [{c['status']}] {c['url'][:200]}")

        # === Step 7: Print all admin/study XHR calls for analysis ===
        log(f"\n{'='*60}")
        log("ALL API calls for reference:")
        for c in api_calls:
            url = c['url']
            if 'study.xiaoe-tech.com' in url or 'admin.xiaoe-tech.com' in url:
                if 'js' not in url and 'css' not in url:
                    log(f"  [{c['status']}] {url}")

        time.sleep(5)
        browser.close()

if __name__ == "__main__":
    main()
