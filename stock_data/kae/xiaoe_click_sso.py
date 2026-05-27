"""
小鹅通 — 点击卡片触发SSO + 拦截h5弹窗 + 提取视频
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

        # Track popups/pages
        popup = [None]
        api_calls = []

        def on_response(response):
            url = response.url
            if any(x in url for x in ['xe.', '_alive', 'login', 'token', 'code']):
                if not any(x in url for x in ['.js', '.css', '.png', '.jpg', '.gif', '.ico', '.woff', '.svg']):
                    try:
                        body = response.text()[:2000]
                        api_calls.append({"url": url.split('?')[0][:150], "status": response.status, "body": body})
                    except:
                        pass

        context.on("response", on_response)

        def on_popup(new_page):
            popup[0] = new_page
            log("  POPUP: " + new_page.url)

        page.on("popup", on_popup)

        # Load page
        log("Loading page...")
        page.goto("https://study.xiaoe-tech.com/t_l/learnIndex?type=wx#/muti_index",
                   wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)
        js_storage = json.dumps(storage)
        page.evaluate("var st = " + js_storage + "; for (var key in st) { localStorage.setItem(key, st[key]); }")
        page.reload(wait_until="domcontentloaded")
        time.sleep(5)

        # Get course list
        log("Getting courses...")
        courses = page.evaluate("""async () => {
            var r = await fetch('/xe.learn-pc/living_live_list.get/1.0.0');
            var d = await r.json();
            if (d.code !== 0) return '[]';
            return JSON.stringify(d.data.list || []);
        }""")
        course_list = json.loads(courses)
        log("Found " + str(len(course_list)) + " courses")

        # Click each course card and handle popup
        for idx, course in enumerate(course_list):
            rid = course.get('resource_id') or course.get('alive_id', '?')
            title = str(course.get('title', ''))[:40]
            log("\n--- Course " + str(idx+1) + ": " + rid + " " + title + " ---")

            # Click the card
            cards = page.query_selector_all('.course-card-list')
            if idx < len(cards):
                api_calls.clear()
                popup[0] = None

                try:
                    cards[idx].click()
                    time.sleep(8)

                    # Check for popup
                    if popup[0]:
                        h5_page = popup[0]
                        try:
                            h5_page.wait_for_load_state("domcontentloaded", timeout=5000)
                        except:
                            pass
                        time.sleep(3)
                        log("Popup URL: " + h5_page.url)
                        log("Popup title: " + h5_page.title())

                        # Check cookies set on xiaoeknow
                        h5_cookies = [c for c in context.cookies() if 'xiaoeknow' in c.get('domain', '')]
                        xiaoeknow_cookies = {c['name']: c['value'] for c in h5_cookies}
                        if xiaoeknow_cookies:
                            log("h5 cookies: " + json.dumps(xiaoeknow_cookies, ensure_ascii=False)[:200])

                        # Try navigate to course now (SSO should have set cookies)
                        try:
                            log("Navigating to course page...")
                            h5_page.goto(
                                "https://appzsnu8fxf7905.h5.xiaoeknow.com/v4/course/alive/" + rid + "?app_id=appzsnu8fxf7905",
                                wait_until="domcontentloaded", timeout=15000
                            )
                            time.sleep(5)
                            log("Course URL: " + h5_page.url)
                            log("Course title: " + h5_page.title())

                            # Check auth
                            auth_check = h5_page.evaluate("""() => {
                                return {
                                    userId: window.USERID || '__empty__',
                                    anony: window.__anony_logon || '__empty__',
                                };
                            }""")
                            log("Auth: " + json.dumps(auth_check, ensure_ascii=False))

                            # Look for video elements
                            video_check = h5_page.evaluate("""() => {
                                var videos = document.querySelectorAll('video');
                                var sources = document.querySelectorAll('source');
                                var iframes = document.querySelectorAll('iframe');
                                return {
                                    videoCount: videos.length,
                                    sourceCount: sources.length,
                                    iframeCount: iframes.length,
                                    videoSrcs: Array.from(videos).map(v => v.src || v.currentSrc || '').filter(Boolean),
                                    sourceSrcs: Array.from(sources).map(s => s.src || '').filter(Boolean),
                                    iframeSrcs: Array.from(iframes).map(i => i.src || '').filter(Boolean),
                                };
                            }""")
                            log("Video elements: " + json.dumps(video_check, ensure_ascii=False)[:500])

                            # Check for video URLs in page source
                            page_source = h5_page.evaluate("""() => {
                                var html = document.documentElement.innerHTML;
                                var matches = html.match(/https?:[^\"'\\s]+(?:m3u8|mp4|flv)[^\"'\\s]*/gi);
                                return matches ? matches.slice(0, 5) : [];
                            }""")
                            if page_source:
                                for url in page_source:
                                    log("VIDEO URL: " + url)

                        except Exception as e:
                            log("Course nav error: " + str(e))

                        h5_page.close()
                    else:
                        log("No popup opened")

                except Exception as e:
                    log("Click error: " + str(e))
            else:
                log("Card not found at index " + str(idx))

            time.sleep(2)

        context.close()
        browser.close()
        log("\nDone.")

if __name__ == "__main__":
    main()
