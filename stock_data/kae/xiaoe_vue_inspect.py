"""
小鹅通 — 通过 Vue 组件直接导航到课程详情页
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
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        context.add_cookies(cookies)
        page = context.new_page()

        page.route("**/*", lambda route: route.continue_())

        # Capture network requests
        xhr_calls = []
        page.on("response", lambda resp: (
            xhr_calls.append({"url": resp.url, "status": resp.status})
            if not any(ext in resp.url for ext in [".js", ".css", ".png", ".jpg", ".gif", ".svg", ".ico", ".woff", ".woff2", ".ttf", ".eot"])
            and ("admin.xiaoe-tech.com" in resp.url or "xiaoeknow.com" in resp.url or ".m3u8" in resp.url or ".mp4" in resp.url)
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

        # STEP 1: Get course card data from Vue component
        log("\n--- Inspecting Vue component on first course card ---")
        vue_info = page.evaluate("""() => {
            const card = document.querySelector('.course-card-list');
            if (!card || !card.__vue__) return {error: 'No Vue component'};

            const vm = card.__vue__;
            const info = {};

            // Get props
            if (vm.$props) info.props = Object.keys(vm.$props);
            if (vm.$options && vm.$options.propsData) info.propsData = vm.$options.propsData;

            // Get data
            if (vm._data) {
                const dataKeys = Object.keys(vm._data);
                info.dataKeys = dataKeys;
                // Get first few data values (non-circular only)
                const sample = {};
                for (const k of dataKeys.slice(0, 10)) {
                    try {
                        const val = vm._data[k];
                        if (typeof val !== 'object' || val === null) sample[k] = val;
                        else if (Array.isArray(val)) sample[k] = `Array(${val.length})`;
                        else sample[k] = `Object`;
                    } catch(e) { sample[k] = '<error>'; }
                }
                info.dataSample = sample;
            }

            // Get computed
            if (vm._computedWatchers) info.computedKeys = Object.keys(vm._computedWatchers);

            // Get methods
            if (vm.$options && vm.$options.methods) info.methods = Object.keys(vm.$options.methods);

            // Check for $router
            info.hasRouter = !!vm.$router;
            info.hasRoute = !!vm.$route;

            // Get parent component info
            let parent = vm.$parent;
            let depth = 0;
            while (parent && depth < 5) {
                const tag = parent.$options && parent.$options._componentTag;
                if (tag) info[`parent_${depth}_tag`] = tag;
                parent = parent.$parent;
                depth++;
            }

            return info;
        }""")
        log(f"Vue info:")
        for k, v in vue_info.items():
            log(f"  {k}: {v}")

        # STEP 2: Get the course list data from the Vuex store or parent component
        log("\n--- Getting course list from Vuex/root ---")
        store_info = page.evaluate("""() => {
            const card = document.querySelector('.course-card-list');
            if (!card || !card.__vue__) return {error: 'No Vue component'};

            const vm = card.__vue__;
            const result = {};

            // Navigate up to find the my-participate-page component or store
            let parent = vm.$parent;
            let count = 0;
            while (parent && count < 10) {
                const tag = parent.$options && parent.$options._componentTag;
                if (tag) result[`level_${count}`] = tag;

                // Check for course list data
                if (parent._data) {
                    for (const k of Object.keys(parent._data)) {
                        const val = parent._data[k];
                        if (Array.isArray(val) && val.length > 0 && val[0] && typeof val[0] === 'object') {
                            result[`data_array_${k}`] = `Array(${val.length})`;
                            // Get first item sample
                            try {
                                const first = JSON.parse(JSON.stringify(val[0]));
                                result[`data_sample_${k}`] = JSON.stringify(first).slice(0, 300);
                            } catch(e) {}
                        }
                    }
                }

                parent = parent.$parent;
                count++;
            }

            // Check for Vuex store
            if (vm.$store) {
                result.hasStore = true;
                try {
                    const state = JSON.parse(JSON.stringify(vm.$store.state));
                    result.storeKeys = Object.keys(state);
                    for (const k of Object.keys(state)) {
                        const v = state[k];
                        if (Array.isArray(v)) result[`store_${k}`] = `Array(${v.length})`;
                        else if (typeof v === 'object' && v !== null) result[`store_${k}`] = `Object: ${Object.keys(v).slice(0, 5).join(',')}`;
                        else result[`store_${k}`] = String(v).slice(0, 100);
                    }
                } catch(e) {
                    result.storeError = String(e);
                }
            }

            return result;
        }""")
        for k, v in store_info.items():
            log(f"  {k}: {v}")

        # STEP 3: Try to get the course resource IDs from the DOM or store
        log("\n--- Extracting course IDs ---")
        course_ids = page.evaluate("""() => {
            const cards = document.querySelectorAll('.course-card-list');
            const ids = [];
            cards.forEach((card, idx) => {
                const vm = card.__vue__;
                if (!vm) return;
                // Try props
                if (vm.$options && vm.$options.propsData) {
                    ids.push({idx, props: JSON.parse(JSON.stringify(vm.$options.propsData))});
                }
            });
            return ids;
        }""")
        for ci in course_ids:
            log(f"  Card props: {ci}")

        # STEP 4: Alternative approach — look for router-link elements
        log("\n--- Looking for navigation elements ---")
        nav_info = page.evaluate("""() => {
            // Find all router-link or a tags that navigate
            const links = document.querySelectorAll('a[href], [href]');
            const routers = [];
            document.querySelectorAll('*').forEach(el => {
                if (el.__vue__ && el.__vue__.$options && el.__vue__.$options._componentTag === 'router-link') {
                    routers.push({
                        tag: el.tagName,
                        to: el.__vue__.to || 'unknown',
                        text: el.textContent?.slice(0, 50),
                    });
                }
            });
            return {
                aLinks: Array.from(links).slice(0, 10).map(l => ({href: l.href, text: (l.textContent || '').slice(0, 30)})),
                routerLinks: routers,
            };
        }""")
        log(f"  Links: {json.dumps(nav_info, ensure_ascii=False, indent=2)[:1000]}")

        # STEP 5: Try to navigate via Vue router directly
        log("\n--- Trying direct route navigation ---")
        route_result = page.evaluate("""() => {
            const card = document.querySelector('.course-card-list');
            if (!card || !card.__vue__) return {error: 'No Vue'};
            const vm = card.__vue__;

            // Try getting router info
            const result = {};
            if (vm.$router) {
                result.routerOptions = vm.$router.options ? Object.keys(vm.$router.options) : [];
                if (vm.$router.options && vm.$router.options.routes) {
                    const routes = vm.$router.options.routes;
                    result.routes = routes.map(r => ({
                        path: r.path,
                        name: r.name,
                        component: r.component ? (r.component.name || r.component.__name || 'unnamed') : null
                    }));
                }
                // Try navigating to a course detail page
                // 小鹅通 often uses /live/{id} for live replays
                // Let's see what routes exist
            }
            if (vm.$route) {
                result.currentRoute = {
                    path: vm.$route.path,
                    fullPath: vm.$route.fullPath,
                    name: vm.$route.name,
                    params: vm.$route.params,
                    query: vm.$route.query,
                    hash: vm.$route.hash,
                };
            }
            return result;
        }""")
        log(f"  Route info: {json.dumps(route_result, ensure_ascii=False, indent=2)[:2000]}")

        # Capture any network calls made during above operations
        log(f"\nNetwork calls captured: {len(xhr_calls)}")
        for c in xhr_calls:
            log(f"  {c['status']} {c['url'][:150]}")

        time.sleep(10)
        browser.close()


if __name__ == "__main__":
    main()
