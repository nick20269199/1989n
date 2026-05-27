"""
小鹅通 — 全自动提取所有课程视频URL
流程:
1. 加载cookies + localStorage 认证 study.xiaoe-tech.com
2. 获取完整课程列表 (living_live_list.get)
3. 点击第一个课程卡片触发 SSO popup → 完成跨域认证
4. 遍历每个课程: 导航到 h5 课程页面 → 拦截 get_lookback_list API → 提取视频URL
5. 输出所有视频URL到 JSON
"""
import os, json, time
from datetime import datetime

CAPTURE_DIR = "D:/1989n/stock_data/kae"

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def capture_video_from_page(page, rid, app_id="appzsnu8fxf7905", wait_seconds=12):
    """Navigate to h5 course page and intercept get_lookback_list response.

    Returns the video data dict, or None if not found.
    Each function call uses its own closure scope via factory pattern.
    """
    result = {}

    def on_response(response):
        url = response.url
        if 'get_lookback_list' in url:
            try:
                body = response.json()
                if body.get('code') == 0 and body.get('data'):
                    result['video'] = body['data']
                    log(f"    CAPTURED get_lookback_list for {rid}")
            except Exception:
                pass

    page.on("response", on_response)
    page.goto(
        f"https://appzsnu8fxf7905.h5.xiaoeknow.com/v4/course/alive/{rid}?app_id={app_id}",
        wait_until="domcontentloaded", timeout=20000
    )

    for _ in range(wait_seconds):
        if result.get('video'):
            break
        time.sleep(1)

    auth = page.evaluate("""() => {
        return {userId: window.USERID || '', anony: window.__anony_logon || ''};
    }""")
    log(f"    Auth: userId={auth.get('userId','')[:25] or 'empty'}")
    return result.get('video'), auth.get('userId')


def extract_video_summary(video_data):
    """Flatten video_data into a list of {line, resolution, url}."""
    entries = []
    if not video_data:
        return entries
    for stream in video_data:
        line_name = stream.get('line_name', 'unknown')
        for s in stream.get('line_sharpness', []):
            entries.append({
                'line': line_name,
                'name': s.get('name', ''),
                'resolution': s.get('resolution', ''),
                'url': s.get('url', ''),
            })
    return entries


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

        results = {}  # rid -> {title, video_entries, auth_userId}

        # Step 1: Load PC study page
        log("Step 1: Loading PC study page...")
        page.goto("https://study.xiaoe-tech.com/t_l/learnIndex?type=wx#/muti_index",
                   wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)
        js_storage = json.dumps(storage)
        page.evaluate("var st = " + js_storage + "; for (var key in st) { localStorage.setItem(key, st[key]); }")
        page.reload(wait_until="networkidle")
        time.sleep(5)

        # Step 2: Get full course list
        log("Step 2: Getting course list...")
        courses_json = page.evaluate("""async () => {
            var r = await fetch('/xe.learn-pc/living_live_list.get/1.0.0');
            var d = await r.json();
            if (d.code !== 0) return '[]';
            return JSON.stringify(d.data.list || []);
        }""")
        courses = json.loads(courses_json)
        log(f"Found {len(courses)} courses:")
        for c in courses:
            rid = c.get('resource_id') or c.get('alive_id', '?')
            title = str(c.get('title', ''))[:60]
            log(f"  {rid} | {title}")

        if not courses:
            log("No courses found!")
            return

        # Step 3: Trigger SSO by clicking first course card
        log("\nStep 3: Triggering SSO popup...")
        popup_ref = [None]
        page.on("popup", lambda p: popup_ref.__setitem__(0, p) or log(f"  POPUP: {p.url[:100]}"))

        cards = page.query_selector_all('.course-card-list')
        if not cards:
            log("No course cards!")
            return

        cards[0].click()
        log("  Waiting for popup...")
        for i in range(20):
            time.sleep(1)
            if popup_ref[0]:
                break

        if popup_ref[0]:
            h5_popup = popup_ref[0]
            try:
                h5_popup.wait_for_load_state("load", timeout=15000)
            except:
                pass
            time.sleep(8)  # Let SSO redirect complete
            log(f"  Popup URL after SSO: {h5_popup.url[:150]}")

            auth = h5_popup.evaluate("""() => {
                return {userId: window.USERID || '', anony: window.__anony_logon || ''};
            }""")
            log(f"  Auth on popup: userId={auth.get('userId','')[:25] or 'empty'}")

            if not auth.get('userId'):
                log("  SSO may not have completed, navigating to course...")
                rid0 = courses[0].get('resource_id') or courses[0].get('alive_id', '')
                try:
                    h5_popup.goto(
                        f"https://appzsnu8fxf7905.h5.xiaoeknow.com/v4/course/alive/{rid0}?app_id=appzsnu8fxf7905",
                        wait_until="domcontentloaded", timeout=15000
                    )
                    time.sleep(5)
                except:
                    pass

            h5_popup.close()
        else:
            log("  No popup, checking if already have h5 cookies...")

        # Show SSO cookies
        h5_cookies = [c for c in context.cookies()
                      if 'xiaoeknow' in c.get('domain', '') or 'xiaoeke' in c.get('domain', '')]
        log(f"\n  h5 cookies after SSO: {len(h5_cookies)}")
        for c in h5_cookies:
            log(f"    {c['name']}: {c['value'][:30]} domain={c['domain']}")

        # Step 4: Iterate each course, extract video URL
        log("\nStep 4: Extracting videos from all courses...")

        for idx, course in enumerate(courses):
            rid = course.get('resource_id') or course.get('alive_id', '')
            title = str(course.get('title', ''))[:60]
            log(f"\n  [{idx+1}/{len(courses)}] {rid} {title}")

            h5_page = context.new_page()
            video_data, user_id = capture_video_from_page(h5_page, rid)
            entries = extract_video_summary(video_data)

            result_entry = {
                'title': title,
                'auth_userId': user_id or '',
                'video_entries': entries,
                'raw_video_data': video_data,
            }

            if entries:
                log(f"    ✅ {len(entries)} video entries found")
                for e in entries:
                    log(f"      [{e['line']}] {e['name']} ({e['resolution']})")
                    log(f"        {e['url'][:150]}")
            else:
                log(f"    ❌ No video data")
                result_entry['error'] = 'no_video_data'

            results[rid] = result_entry
            h5_page.close()
            time.sleep(2)

        # Step 5: Save results
        log("\nStep 5: Saving results...")
        output = {
            'timestamp': datetime.now().isoformat(),
            'total_courses': len(courses),
            'results': results,
        }

        output_path = os.path.join(CAPTURE_DIR, "xiaoe_video_urls.json")
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        log(f"Saved to {output_path}")

        # Print summary
        log("\n" + "=" * 60)
        log("SUMMARY")
        log("=" * 60)
        success = 0
        for rid, data in results.items():
            if data.get('video_entries'):
                log(f"  ✅ {data['title'][:45]}")
                success += 1
            elif data.get('error'):
                log(f"  ❌ {data['title'][:45]} - {data['error']}")
            else:
                log(f"  ⬜ {data['title'][:45]} - unknown")

        log(f"\n{success}/{len(courses)} courses with video data")

        context.close()
        browser.close()
        log("\nDone.")


if __name__ == "__main__":
    main()
