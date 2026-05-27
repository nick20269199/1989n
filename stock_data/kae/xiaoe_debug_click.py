"""
小鹅通 — 调试点击问题 + 直接导航到课程详情的备选方案
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

    all_requests = []

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=False)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        context.add_cookies(cookies)
        page = context.new_page()

        # Capture ALL network requests
        page.on("request", lambda req: (
            all_requests.append({"url": req.url, "method": req.method, "type": req.resource_type, "time": datetime.now().isoformat()})
            if req.resource_type in ("xhr", "fetch") or "admin.xiaoe-tech.com" in req.url or ".m3u8" in req.url
            else None
        ))

        page.route("**/*", lambda route: route.continue_())

        # Load page
        page.goto("https://study.xiaoe-tech.com/t_l/learnIndex?type=wx#/muti_index",
                   wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)

        # Restore localStorage
        page.evaluate(f"""
        var st = {json.dumps(storage)};
        for (var key in st) {{ localStorage.setItem(key, st[key]); }}
        """)

        page.reload(wait_until="domcontentloaded")
        time.sleep(5)

        log(f"URL: {page.url}")
        log(f"Title: {page.title()}")

        # DEBUG: Check click handling on course cards
        debug = page.evaluate("""() => {
            const results = {};
            const card = document.querySelector('.course-card-list');
            if (!card) return {error: 'no card found'};

            // Check for Vue instance
            results.vueAttached = !!card.__vue__;
            results.vueParentComponent = !!card.__vueParentComponent;

            // Check computed styles for pointer-events
            const style = window.getComputedStyle(card);
            results.pointerEvents = style.pointerEvents;
            results.cursor = style.cursor;
            results.position = style.position;
            results.zIndex = style.zIndex;

            // Check for child elements with click handlers
            const allChildren = card.querySelectorAll('*');
            let clickableChild = null;
            for (const child of allChildren) {
                if (child.onclick || child.__vue__ || child.__vueParentComponent) {
                    clickableChild = child.className || child.tagName;
                    break;
                }
                const childStyle = window.getComputedStyle(child);
                if (childStyle.cursor === 'pointer') {
                    clickableChild = child.className || child.tagName;
                    break;
                }
            }
            results.firstClickableChild = clickableChild;

            // Check for overlay
            const overlays = document.querySelectorAll('*');
            let overlayFound = null;
            for (const el of overlays) {
                const rect = el.getBoundingClientRect();
                const cardRect = card.getBoundingClientRect();
                if (el !== card && !card.contains(el) &&
                    rect.left <= cardRect.left && rect.right >= cardRect.right &&
                    rect.top <= cardRect.top && rect.bottom >= cardRect.bottom &&
                    window.getComputedStyle(el).pointerEvents !== 'none') {
                    overlayFound = el.className || el.tagName;
                    break;
                }
            }
            results.overlayFound = overlayFound;

            // Get card bounding rect
            const cardRect = card.getBoundingClientRect();
            results.cardRect = {
                left: cardRect.left, top: cardRect.top,
                width: cardRect.width, height: cardRect.height,
                centerX: cardRect.left + cardRect.width/2,
                centerY: cardRect.top + cardRect.height/2
            };

            // Check what element is at center of card
            const centerEl = document.elementFromPoint(cardRect.left + cardRect.width/2, cardRect.top + cardRect.height/2);
            results.centerElement = centerEl ? (centerEl.className || centerEl.tagName) : 'none';

            // Check for clickable elements inside card (a, button, [role=button], [onclick])
            const clickable = card.querySelectorAll('a, button, [onclick], [role="button"], [data-click]');
            results.clickableInside = Array.from(clickable).map(el => el.className || el.tagName);

            // Check if img-box or card-shop have click handlers via Vue
            const imgBox = card.querySelector('.card-img-box');
            results.imgBoxClickable = imgBox ? !!(imgBox.__vue__ || imgBox.onclick) : false;

            // Try to find Vue router
            const appEl = document.querySelector('#common_template_mounted_el_container');
            results.appComponent = appEl ? !!(appEl.__vue__ || appEl.__vueParentComponent) : false;

            return results;
        }""")
        log(f"Debug info:")
        for k, v in debug.items():
            log(f"  {k}: {v}")

        # Try different click approaches
        card = page.query_selector(".course-card-list")
        if card:
            # Approach 1: Click center of card-img-box
            img_box = card.query_selector(".card-img-box")
            if img_box:
                log("Trying click on card-img-box...")
                img_box.click()
                time.sleep(3)
                log(f"  URL after: {page.url}")

            if page.url == "https://study.xiaoe-tech.com/t_l/learnIndex?type=wx#/muti_index":
                # Approach 2: Click on card-shop (right side icon)
                card_shop = card.query_selector(".card-shop")
                if card_shop:
                    log("Trying click on card-shop...")
                    card_shop.click()
                    time.sleep(3)
                    log(f"  URL after: {page.url}")

            if page.url == "https://study.xiaoe-tech.com/t_l/learnIndex?type=wx#/muti_index":
                # Approach 3: DispatchEvent with bubbles
                log("Trying dispatchEvent(click)...")
                page.evaluate("""() => {
                    const card = document.querySelector('.course-card-list');
                    if (card) {
                        const event = new MouseEvent('click', {
                            bubbles: true,
                            cancelable: true,
                            view: window,
                            clientX: card.getBoundingClientRect().left + card.offsetWidth/2,
                            clientY: card.getBoundingClientRect().top + card.offsetHeight/2
                        });
                        card.dispatchEvent(event);
                    }
                }""")
                time.sleep(3)
                log(f"  URL after: {page.url}")

        # Save requests
        with open(os.path.join(CAPTURE_DIR, "xiaoe_requests.json"), "w", encoding="utf-8") as f:
            json.dump(all_requests, f, ensure_ascii=False, indent=2)
        log(f"Requests saved: {len(all_requests)}")

        time.sleep(10)
        browser.close()


if __name__ == "__main__":
    main()
