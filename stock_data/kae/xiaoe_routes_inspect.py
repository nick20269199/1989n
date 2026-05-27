"""
小鹅通 — 检查嵌套路由 + 尝试正确路径导航
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
        page.route("**/*", lambda route: route.continue_())

        # Load main page
        page.goto("https://study.xiaoe-tech.com/t_l/learnIndex?type=wx#/muti_index",
                   wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)
        page.evaluate(f"""
        var st = {json.dumps(storage)};
        for (var key in st) {{ localStorage.setItem(key, st[key]); }}
        """)
        page.reload(wait_until="domcontentloaded")
        time.sleep(5)

        # Check nested routes on /muti_index
        log("=== Checking nested routes on /muti_index ===")
        nested = page.evaluate("""() => {
            const card = document.querySelector('.course-card-list');
            if (!card || !card.__vue__) return {};
            const router = card.__vue__.$router;
            const result = {};

            // Find muti_index route and check its children
            if (router && router.options && router.options.routes) {
                const mutiRoute = router.options.routes.find(r => r.path === '/muti_index');
                if (mutiRoute) {
                    result.mutiRoute = {
                        path: mutiRoute.path,
                        name: mutiRoute.name || '',
                        hasChildren: !!mutiRoute.children,
                        childrenCount: mutiRoute.children ? mutiRoute.children.length : 0,
                    };
                    if (mutiRoute.children) {
                        result.children = mutiRoute.children.map(c => ({
                            path: c.path,
                            name: c.name || '',
                        }));
                    }
                }
            }

            // Also check the full route matched
            const matched = router.currentRoute._parent ? 'parent exists' : 'no parent';
            result.matched = matched;

            // Check $route.matched for nested routes
            if (card.__vue__.$route) {
                const matchedLen = card.__vue__.$route.matched ? card.__vue__.$route.matched.length : 0;
                result.matchedLen = matchedLen;
                if (card.__vue__.$route.matched) {
                    result.matchedRoutes = card.__vue__.$route.matched.map(m => ({
                        path: m.path,
                        name: m.name || '',
                    }));
                }
            }

            return result;
        }""")
        for k, v in nested.items():
            log(f"  {k}: {json.dumps(v, ensure_ascii=False)[:500]}")

        # Try navigating to nested route paths
        rid = "l_6a0eb015e4b0694c350c7d09"
        route_variants = [
            f"/muti_index/resource/{rid}",
            f"/muti_index/course/{rid}",
            f"/muti_index/alive/{rid}",
            f"/resource/{rid}",
            f"/course/{rid}",
        ]

        log("\n=== Trying route variants ===")
        for route_path in route_variants:
            log(f"\n  Pushing route: {route_path}")
            page.evaluate(f"""() => {{
                const card = document.querySelector('.course-card-list');
                if (card && card.__vue__ && card.__vue__.$router) {{
                    card.__vue__.$router.push('{route_path}');
                }}
            }}""")
            time.sleep(3)
            log(f"  URL: {page.url}")

            # Check body content
            try:
                body = page.inner_text("body")
                log(f"  Body (first 200): {body[:200]}")
            except:
                pass

            # Check if new components appeared
            container_info = page.evaluate("""() => {
                const container = document.getElementById('common_template_mounted_el_container');
                if (!container) return {};
                const info = {};
                for (let i = 0; i < container.children.length; i++) {
                    const child = container.children[i];
                    info['child_' + i] = {
                        class: (child.className || '').slice(0, 80),
                        visible: child.offsetParent !== null,
                        innerText: (child.innerText || '').slice(0, 100),
                    };
                }
                return info;
            }""")
            for k, v in container_info.items():
                log(f"    {k}: {json.dumps(v, ensure_ascii=False)[:200]}")

        time.sleep(10)
        browser.close()


if __name__ == "__main__":
    main()
