"""
小鹅通 — 提取 De API 映射字典，找到视频相关 API
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

        # === Step 1: Extract De (API mapping dictionary) ===
        log("=== Extracting De API mapping ===")
        de_data = page.evaluate("""() => {
            // Find the 'De' object used by $request
            // It's a globally accessible variable or attached to Vue prototype
            let De = null;

            // Check window
            if (window.De) De = window.De;
            if (window.__De) De = window.__De;
            if (window.API_MAP) De = window.API_MAP;

            // Try to find it through Vue
            if (!De) {
                const card = document.querySelector('.course-card-list');
                if (card && card.__vue__) {
                    const vm = card.__vue__;
                    // Walk prototypes
                    let proto = Object.getPrototypeOf(vm);
                    while (proto) {
                        for (const key of Object.getOwnPropertyNames(proto)) {
                            if (key === 'De' || key === 'apiMap' || key === 'API_MAP') {
                                De = proto[key];
                                break;
                            }
                        }
                        if (De) break;
                        proto = Object.getPrototypeOf(proto);
                    }
                }
            }

            if (!De) return {error: 'De not found'};

            // Extract all API names and their URLs
            const result = {};
            for (const [key, val] of Object.entries(De)) {
                result[key] = {
                    url: val.url || '',
                    method: val.method || 'post',
                };
            }
            return result;
        }""")
        if "error" in de_data:
            log(f"  {de_data['error']}")
            # If De wasn't found directly, try to get it from the closure
            log("  Trying alternative extraction...")
            de_alt = page.evaluate("""() => {
                // $request references De from closure. Let's try to get it differently.
                const card = document.querySelector('.course-card-list');
                if (!card || !card.__vue__) return {};
                const vm = card.__vue__;

                // Walk up to find the closure containing De
                let p = vm.$parent;
                while (p) {
                    // Check for _de, apiDe, __api_map__ etc
                    for (const key of Object.getOwnPropertyNames(p)) {
                        if (key.toLowerCase().includes('api') || key.toLowerCase().includes('de_') || key === 'De') {
                            const val = p[key];
                            if (typeof val === 'object' && val !== null) {
                                return {[key]: 'found'};
                            }
                        }
                    }
                    p = p.$parent;
                }

                // Try to capture De by overriding $request
                const origRequest = vm.$request;
                if (origRequest) {
                    // Check if De is in the closure of $request
                    const reqStr = origRequest.toString();
                    const match = reqStr.match(/De\[['"]([^'"]+)['"]\]/);
                    if (match) return {hint: match[1]};
                }

                return {error: 'still not found'};
            }""")
            log(f"  {json.dumps(de_alt, ensure_ascii=False)}")
        else:
            log(f"  Found {len(de_data)} APIs!")
            # Print all APIs sorted by name
            for name in sorted(de_data.keys()):
                info = de_data[name]
                log(f"    {name:45s} -> {info['url'][:100]}")

            # Find video/alive related APIs
            video_apis = {k: v for k, v in de_data.items() if any(x in k.lower() for x in ['alive', 'live', 'video', 'play', 'resource', 'course'])}
            log(f"\n  Video-related APIs ({len(video_apis)}):")
            for name, info in sorted(video_apis.items()):
                log(f"    {name:45s} -> {info['url'][:100]}")

            # Save full mapping for reference
            with open(os.path.join(CAPTURE_DIR, "xiaoe_api_map.json"), "w", encoding="utf-8") as f:
                json.dump(de_data, f, ensure_ascii=False, indent=2)

        time.sleep(5)
        browser.close()

if __name__ == "__main__":
    main()
