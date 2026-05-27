"""
小鹅通 — 通过 pc_client API 获取视频URL (用 p_token 鉴权)
"""
import os, json, time, requests
from datetime import datetime

CAPTURE_DIR = "D:/1989n/stock_data/kae"

BASE = "https://study.xiaoe-tech.com"
APP_ID = "appzsnu8fxf7905"

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def load_cookies():
    with open(os.path.join(CAPTURE_DIR, "xiaoe_cookies.json"), encoding="utf-8") as f:
        cj = json.load(f)
    jar = requests.cookies.RequestsCookieJar()
    for c in cj:
        if c.get("name") and c.get("value"):
            jar.set(c["name"], c["value"], domain=c.get("domain", ""), path=c.get("path", "/"))
    return jar

def get_p_token(cookies_jar=None):
    """Extract p_token from cookies"""
    with open(os.path.join(CAPTURE_DIR, "xiaoe_cookies.json"), encoding="utf-8") as f:
        cj = json.load(f)
    for c in cj:
        if c.get("name") == "p_token":
            return c["value"]
    return None

def call_api(name, path, data, p_token, cookies, extra_headers=None):
    """Call a pc_client API with app-token auth"""
    url = f"{BASE}{path}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Content-Type": "application/json",
        "Origin": BASE,
        "Referer": f"{BASE}/",
        "app-token": p_token,
        "app_id": APP_ID,
    }
    if extra_headers:
        headers.update(extra_headers)

    try:
        resp = requests.post(url, cookies=cookies, json=data, timeout=15, headers=headers)
        log(f"  [{resp.status_code}] {name}")
        if resp.status_code == 200:
            try:
                body = resp.json()
                log(f"    Response: {json.dumps(body, ensure_ascii=False)[:1000]}")
                return body
            except:
                log(f"    Raw: {resp.text[:500]}")
                return resp.text
        else:
            log(f"    Status: {resp.status_code}, Body: {resp.text[:300]}")
        return resp
    except Exception as e:
        log(f"  [ERROR] {name}: {e}")
        return None

def main():
    cookies = load_cookies()
    p_token = get_p_token(cookies)
    log(f"p_token: {p_token[:20]}...")

    rid = "l_6a15546fe4b0694c5bca44b0"

    # Step 1: Get user_id from check_token
    log("\n=== Step 1: Get user_id from check_token ===")
    check_resp = requests.get(
        f"{BASE}/xe.learn-pc.user/check_token",
        cookies=cookies,
        timeout=15,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Origin": BASE,
        }
    )
    if check_resp.status_code == 200:
        token_data = check_resp.json()
        log(f"  {json.dumps(token_data, ensure_ascii=False)[:500]}")
        user_id = token_data.get("data", {}).get("user_id", "")
        log(f"  user_id: {user_id}")
    else:
        log(f"  check_token failed: {check_resp.status_code}")
        # Try to get from course list
        user_id = ""

    # If no user_id, try to get from localStorage via Playwright
    if not user_id:
        log("\n=== Getting user_id from Playwright ===")
        from playwright.sync_api import sync_playwright

        with open(os.path.join(CAPTURE_DIR, "xiaoe_storage.json"), encoding="utf-8") as f:
            storage = json.load(f)

        with sync_playwright() as p:
            browser = p.chromium.launch(channel="msedge", headless=False)
            context = browser.new_context(viewport={"width": 1280, "height": 900})
            context.add_cookies(json.load(open(os.path.join(CAPTURE_DIR, "xiaoe_cookies.json"), encoding="utf-8")))
            page = context.new_page()

            page.goto(f"{BASE}/t_l/learnIndex?type=wx#/muti_index",
                       wait_until="domcontentloaded", timeout=30000)
            time.sleep(2)
            page.evaluate(f"""
            var st = {json.dumps(storage)};
            for (var key in st) {{ localStorage.setItem(key, st[key]); }}
            """)
            page.reload(wait_until="domcontentloaded")
            time.sleep(5)

            # Get user_id from Vue component
            user_id = page.evaluate("""() => {
                const card = document.querySelector('.course-card-list');
                if (!card || !card.__vue__) return '';
                let p = card.__vue__.$parent;
                while (p) {
                    if (p.accountInfo && p.accountInfo.user_id) return p.accountInfo.user_id;
                    p = p.$parent;
                }
                return '';
            }""")
            log(f"  user_id from Vue: {user_id}")

            # Also try to get from localStorage
            ls_user = page.evaluate("() => { const u = localStorage.getItem('userInfo'); if (u) { try { return JSON.parse(u).user_id || ''; } catch(e) { return u; } } return ''; }")
            log(f"  user_id from localStorage: {ls_user}")

            browser.close()

    if not user_id:
        log("ERROR: Cannot find user_id!")
        return

    # Step 2: Try pc_client APIs
    log(f"\n=== Step 2: Try pc_client APIs (user_id={user_id}) ===")

    # Test 1: alive_info_by_link (get course info first)
    log("\n-- Test 1: alive_info_by_link --")
    alive_data = call_api(
        "alive_info_by_link",
        "/pc_client/xe.big_class.course.alive_info_by_link",
        {"app_id": APP_ID, "query_content": rid},
        p_token, cookies,
        {"login_client": "pc", "login_app": "el"}
    )

    # Test 2: jump_url (direct video URL)
    log("\n-- Test 2: jump_url --")
    jump_data = call_api(
        "jump_url",
        "/pc_client/xe.big_class.course.jump_url",
        {"user_id": user_id, "app_id": APP_ID, "alive_id": rid},
        p_token, cookies
    )

    # Test 3: get_anti_theft
    log("\n-- Test 3: get_anti_theft --")
    anti_data = call_api(
        "get_anti_theft",
        "/pc_client/xe.big_class.course.get_anti_theft",
        {"app_id": APP_ID, "alive_id": rid},
        p_token, cookies
    )

    # Step 3: If alive_info_by_link needs a URL instead of ID, try with full URL
    log("\n-- Test 4: alive_info_by_link with full URL --")
    alive_url_data = call_api(
        "alive_info_by_link_url",
        "/pc_client/xe.big_class.course.alive_info_by_link",
        {"app_id": APP_ID, "query_content": f"https://study.xiaoe-tech.com/t_l/learnIndex?type=wx#/alive_detail?alive_id={rid}"},
        p_token, cookies,
        {"login_client": "pc", "login_app": "el"}
    )

    log("\nDone.")

if __name__ == "__main__":
    main()
