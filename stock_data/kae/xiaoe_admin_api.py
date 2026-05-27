"""
小鹅通 — 从 Python 直接调 admin/study API，绕过 CORS
"""
import os, json, time, requests
from datetime import datetime

CAPTURE_DIR = "D:/1989n/stock_data/kae"

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def load_cookies():
    """Load cookies from saved file and convert to requests format"""
    with open(os.path.join(CAPTURE_DIR, "xiaoe_cookies.json"), encoding="utf-8") as f:
        cj = json.load(f)
    jar = requests.cookies.RequestsCookieJar()
    for c in cj:
        if c.get("name") and c.get("value"):
            jar.set(c["name"], c["value"], domain=c.get("domain", ""), path=c.get("path", "/"))
    return jar

def test_api(name, method, url, cookies, data=None):
    """Test an API endpoint"""
    try:
        if method == "GET":
            resp = requests.get(url, cookies=cookies, timeout=15, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Origin": "https://study.xiaoe-tech.com",
                "Referer": "https://study.xiaoe-tech.com/",
            })
        else:
            resp = requests.post(url, cookies=cookies, timeout=15, json=data, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Origin": "https://study.xiaoe-tech.com",
                "Referer": "https://study.xiaoe-tech.com/",
                "Content-Type": "application/json",
            })
        log(f"  [{resp.status_code}] {name}")
        if resp.status_code == 200:
            try:
                body = resp.json()
                if body.get("code") == 0:
                    log(f"    SUCCESS! {json.dumps(body, ensure_ascii=False)[:500]}")
                else:
                    log(f"    code={body.get('code')} msg={body.get('msg','')}")
            except:
                log(f"    (non-JSON response)")
        return resp
    except Exception as e:
        log(f"  [ERROR] {name}: {e}")
        return None

def main():
    cookies = load_cookies()
    log(f"Cookies loaded: {len(cookies)} entries")

    rid = "l_6a15546fe4b0694c5bca44b0"  # 0526
    app_id = "appzsnu8fxf7905"

    # === Test: study.xiaoe-tech.com APIs ===
    log("\n=== study.xiaoe-tech.com APIs ===")
    base = "https://study.xiaoe-tech.com"

    study_apis = [
        ("check_token", "GET", f"{base}/xe.learn-pc.user/check_token"),
        ("living_live_list_get", "GET", f"{base}/xe.learn-pc/living_live_list.get/1.0.0?page_size=16&page_params=1-0-0"),
        ("my_attend_normal_list_get", "POST", f"{base}/xe.learn-pc/my_attend_normal_list.get/1.0.1", {"page_index": 1, "page_size": 16}),
        ("kotoken_create", "POST", f"{base}/xe.learn-pc.client.user/kotoken.create/1.0.0?app_id={app_id}", {"app_id": app_id}),
    ]

    for api_def in study_apis:
        name = api_def[0]
        method = api_def[1]
        url = api_def[2]
        data = api_def[3] if len(api_def) > 3 else None
        test_api(name, method, url, cookies, data)

    # === Test: admin.xiaoe-tech.com APIs ===
    log("\n=== admin.xiaoe-tech.com APIs ===")
    admin_base = "https://admin.xiaoe-tech.com"

    admin_apis = [
        ("xe.asset.alive.get", "POST", f"{admin_base}/xe/asset/alive/get/1.0.0", {"alive_id": rid, "app_id": app_id}),
        ("xe.asset.alive.get_resource", "POST", f"{admin_base}/xe/asset/alive/get_alive_resource/1.0.0", {"alive_id": rid, "app_id": app_id}),
        ("xe.asset.resource.get_by_id", "POST", f"{admin_base}/xe/asset/resource/get_by_id/1.0.0", {"resource_id": rid, "app_id": app_id}),
        ("xe.learn-pc.user.kotoken.create", "POST", f"{admin_base}/xe.learn-pc.client.user/kotoken.create/1.0.0?app_id={app_id}", {"app_id": app_id}),
    ]

    for api_def in admin_apis:
        test_api(*api_def)

    # === Test: More admin API URL patterns ===
    log("\n=== More admin API patterns ===")
    more_patterns = [
        # Asset APIs
        ("asset_course_get", "POST", f"{admin_base}/xe/asset/course/get/1.0.0", {"course_id": rid, "app_id": app_id}),
        ("asset_resource_detail", "POST", f"{admin_base}/xe/asset/resource_detail/1.0.0", {"resource_id": rid, "app_id": app_id}),
        # Learn API
        ("learn_course_detail", "POST", f"{admin_base}/xe.learn-pc/course_detail/1.0.0", {"resource_id": rid}),
        ("learn_living_live_detail", "POST", f"{admin_base}/xe.learn-pc/living_live_detail.get/1.0.0", {"alive_id": rid}),
        # Different host pattern
        ("xe_api_alive", "POST", f"https://api.xiaoe-tech.com/xe/asset/alive/get/1.0.0", {"alive_id": rid, "app_id": app_id}),
    ]

    for api_def in more_patterns:
        test_api(*api_def)

    # === Try: Get video URL via asset API with different params ===
    log("\n=== Trying to find video URL APIs ===")
    video_apis = [
        ("asset_video_get", "POST", f"{admin_base}/xe/asset/video/get/1.0.0", {"resource_id": rid, "app_id": app_id}),
        ("asset_video_play_info", "POST", f"{admin_base}/xe/asset/video/play_info/1.0.0", {"resource_id": rid, "app_id": app_id}),
        ("asset_alive_replay", "POST", f"{admin_base}/xe/asset/alive/replay/1.0.0", {"alive_id": rid, "app_id": app_id}),
        ("asset_alive_play_url", "POST", f"{admin_base}/xe/asset/alive/play_url/1.0.0", {"alive_id": rid, "app_id": app_id}),
        ("asset_alive_video", "POST", f"{admin_base}/xe/asset/alive/video/1.0.0", {"alive_id": rid, "app_id": app_id}),
        ("learn_video_play", "POST", f"{base}/xe.learn-pc/video_play/1.0.0", {"resource_id": rid}),
        ("learn_alive_play", "POST", f"{base}/xe.learn-pc/alive_play/1.0.0", {"alive_id": rid}),
        ("learn_res_play", "POST", f"{base}/xe.learn-pc/resource_play/1.0.0", {"resource_id": rid}),
        ("learn_media_play", "POST", f"{base}/xe.learn-pc/media_play/1.0.0", {"resource_id": rid}),
        ("learn_get_alive", "POST", f"{base}/xe.learn-pc/alive_get/1.0.0", {"alive_id": rid}),
        ("learn_alive_detail", "POST", f"{base}/xe.learn-pc/alive_detail/1.0.0", {"alive_id": rid}),
        ("learn_alive_info", "POST", f"{base}/xe.learn-pc/alive_info/1.0.0", {"alive_id": rid}),
    ]

    for api_def in video_apis:
        test_api(*api_def)

    # === Try: open API without auth ===
    log("\n=== Trying public APIs (no auth needed) ===")
    public_apis = [
        ("h5_file_tag", "GET", f"https://appzsnu8fxf7905.h5.xiaoeknow.com/_alive/file_tag_info?system_name=live_h5&from_client=live_h5&gray_app_id={app_id}&deploy_env=pro&version=v3"),
        ("h5_micro_page", "POST", f"https://appzsnu8fxf7905.h5.xiaoeknow.com/xe.micro_page.common.public.data.get/1.0.0"),
        ("h5_pc_config", "GET", f"https://appzsnu8fxf7905.h5.xiaoeknow.com/xe.account-platform.pc.config.search/1.0.0?appId={app_id}&t=test"),
    ]

    for api_def in public_apis:
        test_api(*api_def, cookies)
    # Also check admin response bodies
    log("\n=== Checking admin API response body ===")
    try:
        resp = requests.post(
            f"{admin_base}/xe/asset/alive/get/1.0.0",
            cookies=cookies,
            json={"alive_id": rid, "app_id": app_id},
            timeout=15,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Content-Type": "application/json",
            }
        )
        log(f"  Status: {resp.status_code}")
        log(f"  Headers: {dict(resp.headers)}")
        log(f"  Body (first 500): {resp.text[:500]}")
    except Exception as e:
        log(f"  Error: {e}")

    log(f"\n{'='*60}")
    log("Done.")

if __name__ == "__main__":
    main()
