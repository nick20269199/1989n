"""
小鹅通 — SSO 弹窗拦截 + h5 认证 + 视频提取
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
        js_storage = json.dumps(storage)
        page.evaluate("var st = " + js_storage + "; for (var key in st) { localStorage.setItem(key, st[key]); }")
        page.reload(wait_until="networkidle")
        time.sleep(5)

        # Click a card and WAIT for popup properly
        log("Clicking course card...")
        card = page.query_selector('.course-card-list')
        if not card:
            log("No card found!")
            return

        card.click()

        # Wait for popup with timeout
        log("Waiting for popup...")
        try:
            popup = page.wait_for_event("popup", timeout=15000)
            log("Popup URL: " + popup.url)
        except:
            log("No popup after 15s, retrying click on different card...")
            # Try clicking second card
            time.sleep(3)
            cards = page.query_selector_all('.course-card-list')
            if len(cards) > 1:
                cards[1].click()
                try:
                    popup = page.wait_for_event("popup", timeout=15000)
                    log("Popup URL (2nd try): " + popup.url)
                except:
                    log("Still no popup")
                    return
            else:
                return

        # We have a popup! Let's monitor it
        h5_api = []

        def capture_h5(response):
            url = response.url
            if 'xiaoeknow.com' in url and not any(x in url for x in ['.js', '.css', '.png', '.jpg', '.gif', '.ico']):
                try:
                    h5_api.append({"url": url.split('?')[0][:150], "body": response.text()[:500]})
                except:
                    pass

        context.on("response", capture_h5)

        # Wait for popup to fully load
        try:
            popup.wait_for_load_state("load", timeout=10000)
        except:
            pass
        time.sleep(5)

        log("Popup title: '" + popup.title() + "'")
        log("Popup URL: " + popup.url)

        # Check for navigation/redirect in popup
        for i in range(10):
            current_url = popup.url
            if 'login' not in current_url:
                log("Popup redirected to: " + current_url + " (after " + str(i+1) + "s)")
            time.sleep(1)

        # Check all cookies including h5 domain
        all_cookies = context.cookies()
        h5_cookies = [c for c in all_cookies if 'xiaoeknow' in c.get('domain', '') or 'xiaoeke' in c.get('domain', '')]

        if h5_cookies:
            log("\nh5 cookies: " + json.dumps({c['name']: c['value'][:30] for c in h5_cookies}, ensure_ascii=False))
        else:
            log("\nNo h5 cookies set")

        # Check auth status on popup
        auth = popup.evaluate("""() => {
            return {
                userId: window.USERID || '',
                anony: window.__anony_logon || '',
                url: window.location.href,
            };
        }""")
        log("Auth on popup: " + json.dumps(auth, ensure_ascii=False))

        # Show h5 API calls during auth
        log("\nh5 API calls during auth (" + str(len(h5_api)) + "):")
        for call in h5_api:
            log("  " + call['url'] + " -> " + call['body'][:200])

        # Try to navigate to course page on h5
        rid = "l_6a15546fe4b0694c5bca44b0"
        log("\nNavigating to course page...")
        try:
            popup.goto(
                "https://appzsnu8fxf7905.h5.xiaoeknow.com/v4/course/alive/" + rid + "?app_id=appzsnu8fxf7905",
                wait_until="domcontentloaded", timeout=15000
            )
            time.sleep(5)

            auth2 = popup.evaluate("""() => {
                return {
                    userId: window.USERID || '',
                    anony: window.__anony_logon || '',
                    url: window.location.href,
                };
            }""")
            log("Auth after nav: " + json.dumps(auth2, ensure_ascii=False))

            if auth2.get('userId'):
                log("*** AUTHENTICATED ON h5! ***")
                # Extract video URL
                video_data = popup.evaluate("""() => {
                    var html = document.documentElement.innerHTML;
                    var urls = [];
                    var m = html.match(/https?:[^\"'\\s<>]+\\.(?:m3u8|mp4|flv)[^\"'\\s<>]*/gi);
                    if (m) urls = urls.concat(m.slice(0,5));
                    var dataScript = document.querySelector('script[id*=\"NUXT\"], script[type=\"application/json\"]');
                    return {
                        urls: urls,
                        hasDataScript: !!dataScript,
                        pageSize: html.length,
                        title: document.title,
                    };
                }""")
                log("Video: " + json.dumps(video_data, ensure_ascii=False)[:1000])
        except Exception as e:
            log("Course nav error: " + str(e))

        popup.close()
        context.close()
        browser.close()
        log("\nDone.")

if __name__ == "__main__":
    main()
