"""
Capture 鹅直播 (wx13a74d0d3ab0942e) mini-program traffic.
Captures HLS video streams, API endpoints, and media content.
"""
import json
import logging
import os
import re
from datetime import datetime

CAPTURE_LOG = "D:/1989n/stock_data/kae/e_live_capture.log"
HLS_DIR = "D:/1989n/stock_data/kae/e_live_videos"
API_LOG = "D:/1989n/stock_data/kae/e_live_api.json"

os.makedirs(HLS_DIR, exist_ok=True)


class ELiveCapture:
    def request(self, flow):
        url = flow.request.pretty_url

        # Only capture relevant traffic
        keywords = [
            "wx13a74d0d3ab0942e", "qq.com", "m3u8", ".ts",
            ".flv", ".mp4", "live", "video", "stream",
            "applet", "miniapp", ".wxapkg"
        ]
        if not any(kw in url for kw in keywords):
            return

        with open(CAPTURE_LOG, "a", encoding="utf-8") as f:
            f.write("[%s] REQ %s %s\n" % (datetime.now().isoformat(), flow.request.method, url))
            if flow.request.headers:
                f.write("  Headers: %s\n" % dict(flow.request.headers))
            if flow.request.text and len(flow.request.text) < 2000:
                f.write("  Body: %s\n" % flow.request.text)
            f.write("\n")

    def response(self, flow):
        url = flow.request.pretty_url
        ct = flow.response.headers.get("content-type", "")

        keywords = [
            "wx13a74d0d3ab0942e", "m3u8", ".ts", ".flv", ".mp4",
            "qq.com", "live", "video", "stream", "applet", "miniapp"
        ]
        if not any(kw in url for kw in keywords):
            return

        with open(CAPTURE_LOG, "a", encoding="utf-8") as f:
            f.write("[%s] RES %s %s\n" % (datetime.now().isoformat(), flow.response.status_code, url))
            f.write("  Content-Type: %s\n" % ct)
            f.write("  Size: %d bytes\n" % len(flow.response.content))

            # Save m3u8 playlists
            if "m3u8" in ct or "m3u8" in url:
                f.write("  === HLS PLAYLIST ===\n%s\n  === END ===\n" % flow.response.text)
                safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', url.split("?")[0][-60:])
                with open("%s/%s.m3u8" % (HLS_DIR, safe_name), "w", encoding="utf-8") as pf:
                    pf.write(flow.response.text)

            # Save JSON API responses
            if "json" in ct or url.endswith(".json"):
                body = flow.response.text[:5000]
                f.write("  Body: %s\n" % body)
                # Also save structured
                api_rec = {
                    "time": datetime.now().isoformat(),
                    "url": url,
                    "method": flow.request.method,
                    "body": flow.response.text[:5000]
                }
                with open(API_LOG, "a", encoding="utf-8") as af:
                    af.write(json.dumps(api_rec, ensure_ascii=False) + "\n")

            # Save video segments
            if ".ts" in url and ("video" in ct or ct == "" or "octet" in ct):
                safe_name = url.split("/")[-1].split("?")[0]
                if safe_name:
                    with open("%s/%s" % (HLS_DIR, safe_name), "wb") as vf:
                        vf.write(flow.response.content)
                    f.write("  Saved to %s/%s\n" % (HLS_DIR, safe_name))

            f.write("\n")


addons = [ELiveCapture()]
