"""
小鹅通 — 精准处理 SSO 弹窗 + 测试 h5 认证
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
        h5_api_calls = []

        def on_response(response):
            url = response.url
            if 'xiaoeknow.com' in url and not any(x in url for x in ['.js', '.css', '.png', '.jpg']):
                try:
                    body = response.text()[:2000]
                    h5_api_calls.append({"url": url.split('?')[0][:150], "body": body[:300]})
                except:
                    pass

        context.on("response", on_response)

        log("Loading page...")
        page.goto("https://study.xiaoe-tech.com/t_l/learnIndex?type=wx#/muti_index",
                   wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)
        js_storage = json.dumps(storage)
        page.evaluate("var st = " + js_storage + "; for (var key in st) { localStorage.setItem(key, st[key]); }")
        page.reload(wait_until="networkidle")
        time.sleep(5)

        # Get course list from living_live_list
        log("Getting courses...")
        courses_json = page.evaluate("""async () => {
            var r = await fetch('/xe.learn-pc/living_live_list.get/1.0.0');
            var d = await r.json();
            if (d.code !== 0) return '[]';
            return JSON.stringify(d.data.list || []);
        }""")
        course_list = json.loads(courses_json)
        log("Found " + str(len(course_list)) + " courses")

        # Click first course and handle popup
        rid = course_list[0].get('resource_id') or course_list[0].get('alive_id', '?')
        log("Clicking first course: " + rid)

        # Set up popup handler BEFORE clicking
        popup_page = [None]
        popup_opened = [False]

        def handle_popup(p):
            popup_page[0] = p
            popup_opened[0] = True
            log("POPUP OPENED: " + p.url)

        page.on("popup", handle_popup)

        # Click the card
        card = page.query_selector('.course-card-list')
        if card:
            card.click()

        # Wait for popup
        for i in range(15):
            time.sleep(1)
            if popup_opened[0]:
                break

        if popup_opened[0] and popup_page[0]:
            h5 = popup_page[0]
            log("Handling popup...")

            # Wait for popup to load
            try:
                h5.wait_for_load_state("domcontentloaded", timeout=10000)
            except:
                pass
            time.sleep(3)

            log("Popup URL: " + h5.url)
            log("Popup title: '" + h5.title() + "'")

            # Wait for SSO to process - check cookies periodically
            for i in range(10):
                xiaoeknow_cookies = [c for c in context.cookies() if 'xiaoeknow' in c.get('domain', '')]
                if xiaoeknow_cookies:
                    log("h5 cookies after SSO (" + str(i+1) + "s): " + str({c['name']: c['value'][:20] for c in xiaoeknow_cookies}))
                time.sleep(1)

            # Now open course page on h5 domain
            log("\nOpening course page on h5 domain...")
            try:
                h5.goto(
                    "https://appzsnu8fxf7905.h5.xiaoeknow.com/v4/course/alive/" + rid + "?app_id=appzsnu8fxf7905",
                    wait_until="domcontentloaded", timeout=15000
                )
                time.sleep(5)
                log("Course URL: " + h5.url)
                log("Course title: " + h5.title())

                # Auth status
                auth = h5.evaluate("""() => {
                    return {
                        userId: window.USERID,
                        anony: window.__anony_logon,
                        pageUrl: window.location.href,
                    };
                }""")
                log("Auth: " + json.dumps(auth, ensure_ascii=False))

                if auth.get('userId') or auth.get('anony') == '1':
                    log("*** AUTHENTICATED on h5! ***")
                    # Look for video
                    video_info = h5.evaluate("""() => {
                        var html = document.documentElement.innerHTML;
                        var urls = [];
                        // m3u8 URLs
                        var m3u8matches = html.match(/https?:[^\"'\\s<>]+\\.m3u8[^\"'\\s<>]*/gi);
                        if (m3u8matches) urls = urls.concat(m3u8matches.slice(0,5));
                        // mp4 URLs
                        var mp4matches = html.match(/https?:[^\"'\\s<>]+\\.mp4[^\"'\\s<>]*/gi);
                        if (mp4matches) urls = urls.concat(mp4matches.slice(0,5));
                        // check __NUXT__ or similar data
                        var dataScript = document.querySelector('script[type=\"application/json\"], script#__NUXT__, script.__NUXT__');
                        var nuxtData = dataScript ? dataScript.textContent.substring(0, 2000) : '';
                        return {urls: urls, nuxtData: nuxtData, htmlLength: html.length};
                    }""")
                    log("Video info: " + json.dumps(video_info, ensure_ascii=False)[:1000])
                else:
                    log("NOT authenticated on h5")

            except Exception as e:
                log("Course page error: " + str(e))

            h5.close()
        else:
            log("No popup appeared")

        # Show h5 API calls
        if h5_api_calls:
            log("\n=== h5 API calls ===")
            for call in h5_api_calls:
                log("[" + call['url'][:120] + "] " + call['body'][:200])

        context.close()
        browser.close()
        log("\nDone.")

if __name__ == "__main__":
    main()
