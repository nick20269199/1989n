"""
小鹅通 — Capture ALL JS files with full content, extract De API mapping
"""
import os, json, time, re
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

        # Capture ALL JS responses fully
        js_files = {}

        def capture_js(response):
            url = response.url
            if url.endswith('.js') and response.status == 200:
                try:
                    body = response.text()
                    # Save with tracking
                    key = url.split('/')[-1].split('?')[0][:60]
                    if key not in js_files:
                        js_files[key] = {"url": url, "body": body, "size": len(body)}
                        log(f"  JS: {key} ({len(body)} chars)")
                    # Check for De mapping
                    if 'xe.learn-pc' in body or 'De[' in body:
                        log(f"  *** CONTAINS API: {key}")
                except Exception as e:
                    log(f"  Error capturing {url.split('/')[-1][:40]}: {e}")

        page.on("response", capture_js)

        log("Loading study page...")
        page.goto("https://study.xiaoe-tech.com/t_l/learnIndex?type=wx#/muti_index",
                   wait_until="networkidle", timeout=30000)
        time.sleep(2)

        # Restore localStorage and reload
        page.evaluate(f"""
        var st = {json.dumps(storage)};
        for (var key in st) {{ localStorage.setItem(key, st[key]); }}
        """)
        page.reload(wait_until="networkidle")
        time.sleep(5)

        # Save ALL JS files with full content
        log(f"\nSaving {len(js_files)} JS files...")
        for js_name, js_info in js_files.items():
            safe_name = re.sub(r'[^a-zA-Z0-9._-]', '_', js_name)
            save_path = os.path.join(CAPTURE_DIR, f"js_{safe_name}")
            with open(save_path, 'w', encoding='utf-8') as f:
                f.write(js_info["body"])
            log(f"  Saved: js_{safe_name} ({js_info['size']} chars)")

        # Now extract De from the JS that contains it
        log("\n=== Extracting De API mappings ===")
        for js_name, js_info in js_files.items():
            body = js_info["body"]
            if 'De[' not in body and 'xe.learn-pc' not in body:
                continue

            # Find all API name → URL mappings in the De style
            # Pattern: name:{url:'xe.learn-pc/...',method:'post'}
            api_mappings = re.findall(
                r"([a-zA-Z_]\w*)\s*:\s*\{[^}]*?url\s*:\s*'([^']+)'[^}]*?method\s*:\s*'([^']+)'",
                body
            )
            if api_mappings:
                log(f"  Found {len(api_mappings)} API definitions in {js_name}")
                for name, url, method in sorted(api_mappings, key=lambda x: x[0]):
                    log(f"    {name:45s} -> {method:6s} {url}")

            # Also find entries with param
            api_with_param = re.findall(
                r"([a-zA-Z_]\w*)\s*:\s*\{[^}]*?url\s*:\s*'([^']+)'[^}]*?method\s*:\s*'([^']+)'[^}]*?param\s*:\s*\{",
                body
            )
            if api_with_param:
                log(f"\n  APIs WITH param in {js_name}:")
                for name, url, method in sorted(api_with_param, key=lambda x: x[0]):
                    log(f"    {name:45s} -> {method:6s} {url}")

        browser.close()
        log("\nDone.")

if __name__ == "__main__":
    main()
