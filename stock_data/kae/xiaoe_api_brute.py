"""
小鹅通 — 暴力搜索 $request API 名 + 尝试 kotoken 解密跨域
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

        # Get resource_id for API calls
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
                    user_id: data.user_id,
                });
            });
            return courses;
        }""")
        first = course_data[0]
        rid = first["resource_id"]
        app_id = first["app_id"]
        user_id = first.get("user_id", "")

        # === Approach 1: Brute force try API names ===
        log("=== Brute-forcing $request API names ===")

        # Generate possible API names based on patterns seen
        bases = ["alive", "live", "play", "video", "course", "resource", "record", "replay", "media", "player", "vod", "asset"]
        suffixes = ["_get", "_detail", "_info", "_play", "_url", "_data", "_resource", ".get", ".create", ".detail"]
        prefixes = ["get_", "index_", "xe_", ""]

        api_attempts = []
        for base in bases:
            for suffix in suffixes:
                api_attempts.append(f"{base}{suffix}")
                api_attempts.append(f"index_{base}{suffix}")
                api_attempts.append(f"get_{base}{suffix}")
                api_attempts.append(f"{base}_info")
                api_attempts.append(f"{base}_detail")

        # Add known APIs for reference
        known_apis = [
            "index_getPendingLiveList",
            "index_getOpenLivingList",
            "living_live_list_get",
            "my_attend_normal_list_get",
            "check_unfinished_live",
            "check_token",
            "recent_learn_set",
            "get_new_gateway",
            "shop_is_company_get",
            "nation_code",
            "check_password",
        ]
        api_attempts.extend(known_apis)

        # Add more patterns
        api_attempts.extend([
            "alive_get", "alive_detail_get", "alive_resource_get",
            "alive_play_get", "alive_player_url_get",
            "live_detail", "live_info", "live_play",
            "course_detail", "course_info", "course_play",
            "video_get", "video_info", "video_play", "video_url",
            "resource_get", "resource_detail", "resource_play",
            "asset_get", "asset_detail",
            "player_info_get", "player_url_get",
            "vod_get", "vod_info", "vod_play",
            "media_get", "media_info", "media_play",
            "record_get", "record_detail", "record_replay",
            "replay_get", "replay_detail", "replay_url",
            "alive_player", "get_alive_detail",
            "alive_play_info", "alive_video_url",
            "play_auth_get", "play_token_get",
            "alive.learn-pc.get", "alive.resource.get",
            "alive_detail", "alive_detail_info",
            "alive_replay_get", "alive_record_get",
            "get_alive_resource", "get_alive_play",
            "get_alive_info", "get_alive_detail_info",
        ])

        # Remove duplicates
        api_attempts = list(set(api_attempts))
        log(f"Will try {len(api_attempts)} API names")

        # Try each API name
        found_apis = {}
        params = {"alive_id": rid, "resource_id": rid, "app_id": app_id}

        for api_name in api_attempts[:80]:  # Try first 80
            result = page.evaluate(f"""async () => {{
                const card = document.querySelector('.course-card-list');
                if (!card || !card.__vue__) return {{}};
                let p = card.__vue__.$parent;
                while (p) {{
                    if (p.$request) {{
                        try {{
                            const r = await p.$request('{api_name}', {{alive_id: '{rid}'}});
                            if (r && r.code === 0) return {{success: true, code: 0, msg: r.msg, data: JSON.stringify(r.data).slice(0, 500)}};
                            if (r && r.code) return {{code: r.code, msg: r.msg}};
                            return r;
                        }} catch(e) {{
                            return {{error: e.message}};
                        }}
                    }}
                    p = p.$parent;
                }}
                return null;
            }}""")
            if result and isinstance(result, dict):
                if result.get("success"):
                    found_apis[api_name] = result
                    log(f"  *** FOUND: {api_name} -> {json.dumps(result, ensure_ascii=False)[:300]}")
                elif result.get("code") and result.get("code") != 404:
                    log(f"  *** INTERESTING: {api_name} -> code={result.get('code')} msg={result.get('msg','')}")

        log(f"\nFound {len(found_apis)} working APIs:")
        for name, data in found_apis.items():
            log(f"  {name}: {json.dumps(data, ensure_ascii=False)[:200]}")

        # === Approach 2: Try the kotoken approach again, using the encrypted_cookies ===
        # Set the encrypted_cookies value as the p_token on the h5 domain
        log(f"\n{'='*60}")
        log("=== Trying encrypted_cookies as h5 auth ===")

        result = page.evaluate(f"""async () => {{
            const resp = await fetch('/xe.learn-pc.client.user/kotoken.create/1.0.0?app_id={app_id}', {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify({{app_id: '{app_id}', user_id: '{user_id}'}})
            }});
            const data = await resp.json();
            return JSON.stringify(data);
        }}""")
        log(f"  kotoken full response: {result[:500]}")

        try:
            kt_data = json.loads(result)
            encrypted = kt_data.get("data", {}).get("encrypted_cookies", "")
            log(f"  encrypted_cookies length: {len(encrypted)}")

            # Try setting this as p_token on xiaoeknow.com
            if encrypted:
                log("  Setting encrypted_cookies on .xiaoeknow.com and reloading h5...")
                h5_page = context.new_page()

                # Set the encrypted_cookies as p_token
                context.add_cookies([{
                    "name": "p_token",
                    "value": encrypted,
                    "domain": ".xiaoeknow.com",
                    "path": "/",
                    "httpOnly": False,
                    "secure": False,
                }])

                h5_url = f"https://appzsnu8fxf7905.h5.xiaoeknow.com/v3/course/alive/{rid}?type=2"
                try:
                    h5_page.goto(h5_url, wait_until="domcontentloaded", timeout=15000)
                    time.sleep(5)
                    log(f"  URL: {h5_page.url}")
                    log(f"  Title: {h5_page.title()}")
                    if "login" not in h5_page.url.lower() and "Loading" not in h5_page.title():
                        log(f"  *** LOADED! Checking video...")
                        time.sleep(15)
                        body = h5_page.inner_text("body")
                        log(f"  Body: {body[:500]}")
                    else:
                        log(f"  -> Still login redirect")
                except Exception as e:
                    log(f"  Error: {e}")
                h5_page.close()
        except json.JSONDecodeError:
            log(f"  Could not parse kotoken response")

        # === Approach 3: Try calling the kotoken.create from a h5 context ===
        log(f"\n{'='*60}")
        log("=== Kotoken from h5 context ===")

        h5_context = browser.new_context(viewport={"width": 1280, "height": 900})
        h5_context.add_cookies(cookies)
        # Also set p_token for xiaoeknow.com
        p_token = None
        for c in cookies:
            if c.get("name") == "p_token":
                p_token = c["value"]
                break
        if p_token:
            h5_context.add_cookies([{
                "name": "p_token", "value": p_token,
                "domain": ".xiaoeknow.com", "path": "/",
                "httpOnly": False, "secure": False,
            }])

        h5_page2 = h5_context.new_page()

        # Load the h5 page and intercept auth
        api_responses = {}
        def capture(resp):
            url = resp.url
            if any(x in url for x in ['xe.', '_alive', 'login', 'auth', 'token']):
                try:
                    text = resp.text()[:2000]
                    api_responses[url.split('?')[0][:150]] = text
                except:
                    pass

        h5_page2.on("response", capture)

        try:
            h5_page2.goto(f"https://appzsnu8fxf7905.h5.xiaoeknow.com/v3/course/alive/{rid}?type=2",
                         wait_until="domcontentloaded", timeout=15000)
            time.sleep(3)
        except:
            pass

        # Show captured auth-related responses
        log("Auth responses:")
        for url, body in api_responses.items():
            log(f"  {url}")
            if body and not any(x in url for x in ['.js', '.css', '.png', '.gif', '.svg']):
                log(f"    {body[:300]}")

        h5_page2.close()

        time.sleep(5)
        browser.close()

if __name__ == "__main__":
    main()
