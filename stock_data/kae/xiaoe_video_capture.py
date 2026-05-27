"""
小鹅通 — h5_url 加载 + 移动端 UA + p_token 跨域注入 + 拦截 m3u8
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

    # Extract p_token
    p_token = None
    for c in cookies:
        if c.get("name") == "p_token":
            p_token = c["value"]
            break
    log(f"p_token: {p_token[:20] if p_token else 'N/A'}...")

    from playwright.sync_api import sync_playwright

    all_results = {}
    all_video_requests = []

    with sync_playwright() as p:
        # Step 1: Load PC page to extract course data
        browser = p.chromium.launch(channel="msedge", headless=False)
        pc_context = browser.new_context(viewport={"width": 1280, "height": 800})
        pc_context.add_cookies(cookies)
        pc_page = pc_context.new_page()
        pc_page.route("**/*", lambda route: route.continue_())

        pc_page.goto("https://study.xiaoe-tech.com/t_l/learnIndex?type=wx#/muti_index",
                      wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)
        pc_page.evaluate(f"""
        var st = {json.dumps(storage)};
        for (var key in st) {{ localStorage.setItem(key, st[key]); }}
        """)
        pc_page.reload(wait_until="domcontentloaded")
        time.sleep(5)

        # Extract course data
        course_data = pc_page.evaluate("""() => {
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
                    h5_url: data.h5_url,
                    start_at: data.start_at,
                });
            });
            return courses;
        }""")
        log(f"Found {len(course_data)} courses")

        pc_context.close()

        # Step 2: Create mobile-like context for h5 pages
        # p_token cookies for all relevant domains
        h5_cookies = []
        for d in [".xiaoeknow.com", ".xet.tech", "appzsnu8fxf7905.h5.xiaoeknow.com"]:
            h5_cookies.append({
                "name": "p_token",
                "value": p_token,
                "domain": d,
                "path": "/",
                "httpOnly": False,
                "secure": False,
            })

        # Use a mobile user agent to avoid desktop-only redirects
        mobile_ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"

        h5_context = browser.new_context(
            viewport={"width": 390, "height": 844},  # iPhone 14 Pro
            user_agent=mobile_ua,
        )
        h5_context.add_cookies(h5_cookies)

        # Process each course
        for i, course in enumerate(course_data):
            rid = course["resource_id"]
            title = course["title"]
            h5_url = course.get("h5_url", "")

            if not h5_url:
                log(f"\n[{i+1}] {title}: No h5_url, skipping")
                continue

            log(f"\n{'='*60}")
            log(f"[{i+1}/{len(course_data)}] {title}")
            log(f"  h5_url: {h5_url}")

            # Create page in the h5 context
            page = h5_context.new_page()

            video_reqs = []

            def on_req(request):
                url = request.url
                if '.m3u8' in url or '.mp4' in url or '.flv' in url or 'txvideo' in url or 'vod' in url:
                    log(f"  >>> VIDEO REQUEST: {url[:200]}")
                    video_reqs.append({"url": url, "method": request.method, "type": "request"})

            def on_resp(response):
                url = response.url
                if '.m3u8' in url:
                    try:
                        body = response.text()[:2000]
                    except:
                        body = ""
                    video_reqs.append({"url": url, "status": response.status, "body": body[:500]})
                    log(f"  >>> M3U8: {url[:200]}")
                elif '.ts' in url:
                    video_reqs.append({"url": url, "status": response.status})
                    log(f"  >>> TS: {url[:150]}")

            page.on("request", on_req)
            page.on("response", on_resp)
            page.route("**/*", lambda route: route.continue_())

            try:
                # Navigate to h5_url
                page.goto(h5_url, wait_until="domcontentloaded", timeout=30000)
                time.sleep(3)

                # Check if we're on the login page or the actual content
                current_url = page.url
                log(f"  URL: {current_url}")

                is_login = "login" in current_url or "auth" in current_url

                if is_login:
                    log(f"  *** On login page, trying to inject auth...")

                    # Try to find and interact with the login page
                    # Some login pages auto-redirect if cookies are valid
                    time.sleep(3)
                    current_url = page.url
                    log(f"  URL after 3s: {current_url}")
                    is_login = "login" in current_url or "auth" in current_url

                    if is_login:
                        log(f"  Still on login, skipping (no auth available)")
                        # Save a screenshot for reference
                        try:
                            page.screenshot(path=os.path.join(CAPTURE_DIR, f"login_{rid[:20]}.png"))
                            log(f"  Screenshot saved")
                        except:
                            pass
                        page.close()
                        all_results[title] = {"resource_id": rid, "status": "login_required"}
                        continue

                # Page loaded successfully!
                log(f"  Page loaded! Title: {page.title()}")

                # Wait for video player
                time.sleep(8)

                # Get page content
                try:
                    body = page.inner_text("body")
                    log(f"  Body: {body[:300]}")
                except:
                    pass

                # Check video elements
                vinfo = page.evaluate("""() => {
                    const info = {};
                    const vids = document.querySelectorAll('video');
                    info.videoCount = vids.length;
                    info.sources = [];
                    vids.forEach(v => {
                        info.sources.push({
                            src: v.src || v.currentSrc || '',
                            poster: v.poster || '',
                            duration: v.duration,
                            readyState: v.readyState,
                        });
                        // Try to get source children
                        const srcEls = v.querySelectorAll('source');
                        srcEls.forEach(s => info.sources.push({type: 'source', src: s.src}));
                    });
                    info.players = {};
                    if (typeof AliPlayer !== 'undefined') info.players.aliplayer = true;
                    if (typeof TCPlayer !== 'undefined') info.players.tcplayer = true;
                    if (typeof videojs !== 'undefined') info.players.videojs = true;
                    return info;
                }""")
                log(f"  Video: {json.dumps(vinfo, ensure_ascii=False)[:500]}")

                # Wait more for network activity
                time.sleep(10)

                # Try to interact with any play button
                page.evaluate("""() => {
                    // Try clicking play buttons
                    document.querySelectorAll('[class*="play"], [class*="Play"], button, [class*="start"]').forEach(el => {
                        try { el.click(); } catch(e) {}
                    });
                    // Try autoplaying all video elements
                    document.querySelectorAll('video').forEach(v => {
                        try { v.play(); } catch(e) {}
                    });
                }""")
                time.sleep(5)

                # Save the page for analysis
                html_path = os.path.join(CAPTURE_DIR, f"xe_detail_{rid[:20]}.html")
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(page.content())
                log(f"  HTML saved ({len(page.content())} bytes)")

                # Collect results
                all_results[title] = {
                    "resource_id": rid,
                    "url": page.url,
                    "video_requests": video_reqs,
                    "video_elements": vinfo,
                    "loaded": True,
                }
                all_video_requests.extend(video_reqs)

            except Exception as e:
                log(f"  Error: {e}")
                all_results[title] = {"resource_id": rid, "error": str(e)}
            finally:
                page.close()
                time.sleep(2)

        # Summary
        log(f"\n{'='*60}")
        log(f"FINAL SUMMARY:")
        loaded = sum(1 for v in all_results.values() if v.get("loaded"))
        login = sum(1 for v in all_results.values() if v.get("status") == "login_required")
        log(f"  Loaded successfully: {loaded}")
        log(f"  Login required: {login}")
        log(f"  Total video requests: {len(all_video_requests)}")

        for title, data in all_results.items():
            if data.get("video_requests"):
                log(f"\n  {title}:")
                for r in data["video_requests"]:
                    log(f"    {r.get('url','')[:200]}")

        with open(os.path.join(CAPTURE_DIR, "xiaoe_video_results.json"), "w", encoding="utf-8") as f:
            json.dump(all_results, f, ensure_ascii=False, indent=2)

        log(f"\nResults saved to xiaoe_video_results.json")
        time.sleep(10)
        browser.close()


if __name__ == "__main__":
    main()
