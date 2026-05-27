"""
小鹅通 — 测试 v4 地址 + l_program=xe_know_pc 参数
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

    all_video_reqs = []

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=False)
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        context.add_cookies(cookies)

        page = context.new_page()

        # Capture network
        page.on("request", lambda req: (
            all_video_reqs.append({"url": req.url, "method": req.method})
            if any(x in req.url for x in ['.m3u8', '.mp4', '.flv', 'txvideo', 'vod'])
            and not any(x in req.url for x in ['.js', '.css', '.png', '.jpg'])
            else None
        ))
        page.on("response", lambda resp: (
            all_video_reqs.append({"url": resp.url, "status": resp.status})
            if any(x in resp.url for x in ['.m3u8', '.mp4', '.flv', 'txvideo'])
            and not any(x in resp.url for x in ['.js', '.css', '.png', '.jpg'])
            else None
        ))

        # Load PC page first to restore localStorage
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

        # Extract course data for v4 URLs
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
                });
            });
            return courses;
        }""")
        log(f"Found {len(course_data)} courses")

        # Try the v4 URL for one course
        course = course_data[0]  # 0525
        rid = course["resource_id"]
        app_id = course["app_id"]

        # v4 URL with l_program=xe_know_pc (this is what the user provided)
        v4_url = f"https://appzsnu8fxf7905.h5.xiaoeknow.com/v4/course/alive/{rid}?app_id={app_id}&l_program=xe_know_pc"
        log(f"\nTrying v4 URL: {v4_url}")

        try:
            page.goto(v4_url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(3)
            log(f"  URL: {page.url}")
            log(f"  Title: {page.title()}")

            if "login" in page.url.lower() or "auth" in page.url.lower() or "Loading" in page.title():
                log(f"  *** Login redirect (even with PC auth)")
                log(f"  Page content: {page.content()[:1000]}")
            else:
                log(f"  *** SUCCESS! Page loaded!")
                time.sleep(15)
                body = page.inner_text("body")
                log(f"  Body: {body[:500]}")

                # Check video
                vinfo = page.evaluate("""() => {
                    const info = {};
                    const vids = document.querySelectorAll('video');
                    info.videoCount = vids.length;
                    info.sources = [];
                    vids.forEach(v => {
                        info.sources.push({
                            src: v.src || v.currentSrc || '',
                            poster: v.poster || '',
                        });
                    });
                    return info;
                }""")
                log(f"  Video: {json.dumps(vinfo, ensure_ascii=False)[:500]}")

                # Try to play
                page.evaluate("""() => {
                    document.querySelectorAll('video').forEach(v => {
                        try { v.play(); } catch(e) {}
                    });
                }""")
                time.sleep(10)

            log(f"\nVideo requests: {len(all_video_reqs)}")
            for r in all_video_reqs:
                log(f"  {r.get('url','')[:200]}")

        except Exception as e:
            log(f"  Error: {e}")

        # Try all remaining courses with v4 URL
        log(f"\n{'='*60}")
        log(f"Trying ALL courses with v4 URL...")

        for i, course in enumerate(course_data):
            rid = course["resource_id"]
            app_id = course["app_id"]
            title = course["title"]
            v4_url = f"https://appzsnu8fxf7905.h5.xiaoeknow.com/v4/course/alive/{rid}?app_id={app_id}&l_program=xe_know_pc"

            log(f"\n[{i+1}] {title}")
            log(f"  v4 URL: {v4_url}")

            page2 = context.new_page()

            vreqs = []
            def capture(req):
                url = req.url
                if any(x in url for x in ['.m3u8', '.mp4', '.flv', 'txvideo', 'vod']):
                    log(f"  >>> VIDEO: {url[:200]}")
                    vreqs.append(url)

            page2.on("request", capture)

            try:
                page2.goto(v4_url, wait_until="domcontentloaded", timeout=30000)
                time.sleep(3)
                log(f"  URL: {page2.url}")
                log(f"  Title: {page2.title()}")

                if "login" not in page2.url.lower() and "auth" not in page2.url.lower() and "Loading" not in page2.title():
                    log(f"  *** LOADED SUCCESSFULLY!")
                    time.sleep(15)

                    # Auto-play
                    page2.evaluate("""() => {
                        document.querySelectorAll('video').forEach(v => {
                            try { v.play(); } catch(e) {}
                        });
                    }""")
                    time.sleep(10)

                    # Check video
                    vinfo = page2.evaluate("""() => {
                        const vids = document.querySelectorAll('video');
                        return {count: vids.length, src: (vids[0] && (vids[0].src || vids[0].currentSrc)) || ''};
                    }""")
                    log(f"  Video info: {json.dumps(vinfo, ensure_ascii=False)}")

                else:
                    log(f"  -> Login redirect")

                if vreqs:
                    log(f"  Video requests: {len(vreqs)}")

            except Exception as e:
                log(f"  Error: {e}")

            page2.close()
            time.sleep(2)

        time.sleep(5)
        browser.close()

    with open(os.path.join(CAPTURE_DIR, "xiaoe_v4_results.json"), "w", encoding="utf-8") as f:
        json.dump({"video_requests": all_video_reqs}, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
