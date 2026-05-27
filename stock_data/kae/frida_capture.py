"""
Frida-based capture for 鹅直播 (WeChat mini-program) network traffic.
Hooks mmcronet.dll's Cronet C API to dump all URL requests and responses.

Usage:
  1. Open 鹅直播 in WeChat PC client
  2. Run: python frida_capture.py
  3. The script will capture all HTTP traffic from the mini-program
"""
import os
import sys
import json
import time
import logging
from datetime import datetime

CAPTURE_DIR = "D:/1989n/stock_data/kae"
LOG_FILE = os.path.join(CAPTURE_DIR, "frida_capture.log")
URLS_FILE = os.path.join(CAPTURE_DIR, "frida_urls.json")
HLS_DIR = os.path.join(CAPTURE_DIR, "e_live_videos")
os.makedirs(HLS_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)

FRIDA_SCRIPT = """
'use strict';

// Module handles
var mmcronet = null;
var Cronet_Buffer_GetData = null;
var Cronet_Buffer_GetSize = null;
var Cronet_UrlResponseInfo_url_get = null;
var Cronet_UrlResponseInfo_http_status_code_get = null;

// Track active requests: ptr -> {url: string, body_parts: [bytes], response_started: bool}
var active_requests = {};

// Interesting URL patterns (video/live related)
var INTERESTING_PATTERNS = [
    "m3u8", ".ts", ".flv", ".mp4", "live", "video", "stream",
    "wx13a74d0d3ab0942e", "qq.com", "miniapp", "applet"
];

function isInteresting(url) {
    var lower = url.toLowerCase();
    for (var i = 0; i < INTERESTING_PATTERNS.length; i++) {
        if (lower.indexOf(INTERESTING_PATTERNS[i]) !== -1) {
            return true;
        }
    }
    return false;
}

function initHelpers() {
    mmcronet = Module.findBaseAddress("mmcronet.dll");
    if (!mmcronet) {
        console.log("ERROR: mmcronet.dll not found in process");
        return false;
    }
    console.log("mmcronet.dll at: " + mmcronet);

    // Resolve helper functions
    var getDataAddr = Module.findExportByName("mmcronet.dll", "Cronet_Buffer_GetData");
    var getSizeAddr = Module.findExportByName("mmcronet.dll", "Cronet_Buffer_GetSize");
    var urlGetAddr = Module.findExportByName("mmcronet.dll", "Cronet_UrlResponseInfo_url_get");
    var statusGetAddr = Module.findExportByName("mmcronet.dll", "Cronet_UrlResponseInfo_http_status_code_get");

    if (!getDataAddr || !getSizeAddr || !urlGetAddr || !statusGetAddr) {
        console.log("ERROR: Could not resolve helper functions");
        return false;
    }

    Cronet_Buffer_GetData = new NativeFunction(getDataAddr, "pointer", ["pointer"]);
    Cronet_Buffer_GetSize = new NativeFunction(getSizeAddr, "uint64", ["pointer"]);
    Cronet_UrlResponseInfo_url_get = new NativeFunction(urlGetAddr, "pointer", ["pointer"]);
    Cronet_UrlResponseInfo_http_status_code_get = new NativeFunction(statusGetAddr, "int32", ["pointer"]);

    return true;
}

function readCString(ptr) {
    if (!ptr || ptr.isNull()) return null;
    try {
        return ptr.readCString();
    } catch (e) {
        return "<error reading string>";
    }
}

function hookUrlRequestInit() {
    var initFn = Module.findExportByName("mmcronet.dll", "Cronet_UrlRequest_InitWithParams");
    if (!initFn) {
        console.log("ERROR: Cronet_UrlRequest_InitWithParams not found");
        return;
    }

    Interceptor.attach(initFn, {
        onEnter: function(args) {
            // Signature: (Cronet_UrlRequestPtr request, Cronet_EnginePtr engine, Cronet_String url, Cronet_UrlRequestParamsPtr params, Cronet_UrlRequestCallbackPtr callback, Cronet_ExecutorPtr executor)
            var requestPtr = args[0];
            var urlPtr = args[2];
            var url = readCString(urlPtr);

            if (url) {
                active_requests[requestPtr] = {
                    url: url,
                    body_parts: [],
                    response_started: false,
                };
            }
        }
    });
    console.log("Hooked Cronet_UrlRequest_InitWithParams");
}

function hookCallbacks() {
    // Hook OnReadCompleted - captures response body data
    var onReadFn = Module.findExportByName("mmcronet.dll", "Cronet_UrlRequestCallback_OnReadCompleted");
    if (!onReadFn) {
        console.log("ERROR: Cronet_UrlRequestCallback_OnReadCompleted not found");
        return;
    }

    Interceptor.attach(onReadFn, {
        onEnter: function(args) {
            // Signature: (self, request, info, buffer, executor)
            var requestPtr = args[1];
            var bufferPtr = args[3];
            var infoPtr = args[2];

            var reqInfo = active_requests[requestPtr];
            if (!reqInfo) {
                // Try to get URL from response info
                var urlFromInfo = readCString(Cronet_UrlResponseInfo_url_get(infoPtr));
                if (urlFromInfo) {
                    reqInfo = {url: urlFromInfo, body_parts: [], response_started: true};
                    active_requests[requestPtr] = reqInfo;
                } else {
                    return;
                }
            }

            if (!isInteresting(reqInfo.url)) return;

            // Read buffer data
            var dataPtr = Cronet_Buffer_GetData(bufferPtr);
            var dataSize = Cronet_Buffer_GetSize(bufferPtr);
            if (dataPtr && !dataPtr.isNull() && dataSize > 0) {
                var chunk = dataPtr.readByteArray(Number(dataSize));
                if (chunk) {
                    reqInfo.body_parts.push(chunk);
                }
            }
        }
    });
    console.log("Hooked Cronet_UrlRequestCallback_OnReadCompleted");

    // Hook OnResponseStarted - capture response headers
    var onRespFn = Module.findExportByName("mmcronet.dll", "Cronet_UrlRequestCallback_OnResponseStarted");
    if (onRespFn) {
        Interceptor.attach(onRespFn, {
            onEnter: function(args) {
                var requestPtr = args[1];
                var infoPtr = args[2];
                var reqInfo = active_requests[requestPtr];
                if (!reqInfo) {
                    var urlFromInfo = readCString(Cronet_UrlResponseInfo_url_get(infoPtr));
                    if (urlFromInfo) {
                        reqInfo = {url: urlFromInfo, body_parts: [], response_started: true};
                        active_requests[requestPtr] = reqInfo;
                    }
                }
                if (reqInfo) {
                    reqInfo.response_started = true;
                    if (isInteresting(reqInfo.url)) {
                        var statusCode = Cronet_UrlResponseInfo_http_status_code_get(infoPtr);
                        console.log("[RESP] " + statusCode + " " + reqInfo.url);
                    }
                }
            }
        });
        console.log("Hooked Cronet_UrlRequestCallback_OnResponseStarted");
    }

    // Hook OnSucceeded - finalize request
    var onSucFn = Module.findExportByName("mmcronet.dll", "Cronet_UrlRequestCallback_OnSucceeded");
    if (onSucFn) {
        Interceptor.attach(onSucFn, {
            onEnter: function(args) {
                var requestPtr = args[1];
                var infoPtr = args[2];
                var reqInfo = active_requests[requestPtr];
                if (!reqInfo) {
                    var urlFromInfo = readCString(Cronet_UrlResponseInfo_url_get(infoPtr));
                    if (urlFromInfo) {
                        reqInfo = {url: urlFromInfo, body_parts: [], response_started: true};
                    }
                }
                if (!reqInfo) return;

                var url = reqInfo.url;
                if (!isInteresting(url)) {
                    delete active_requests[requestPtr];
                    return;
                }

                // Reassemble body
                var body_size = 0;
                for (var i = 0; i < reqInfo.body_parts.length; i++) {
                    body_size += reqInfo.body_parts[i].length;
                }

                // Check if bytes look like text
                var firstChunk = reqInfo.body_parts.length > 0 ? reqInfo.body_parts[0] : null;
                var isText = firstChunk ? isTextData(firstChunk) : false;

                if (isText) {
                    // Concatenate all chunks
                    var full = null;
                    for (var i = 0; i < reqInfo.body_parts.length; i++) {
                        if (full === null) {
                            full = reqInfo.body_parts[i];
                        } else {
                            full = Buffer.concat(full, reqInfo.body_parts[i]);
                        }
                    }
                    if (full) {
                        var text = bytesToString(full);
                        console.log("[DONE] " + url + " (" + body_size + " bytes, text)");

                        // Save to file
                        saveCaptured(url, text, body_size);
                    }
                } else {
                    console.log("[DONE] " + url + " (" + body_size + " bytes, binary)");
                    if (body_size > 0 && reqInfo.body_parts.length > 0) {
                        var full = null;
                        for (var i = 0; i < reqInfo.body_parts.length; i++) {
                            if (full === null) full = reqInfo.body_parts[i];
                            else full = Buffer.concat(full, reqInfo.body_parts[i]);
                        }
                        saveCapturedBinary(url, full, body_size);
                    }
                }

                delete active_requests[requestPtr];
            }
        });
        console.log("Hooked Cronet_UrlRequestCallback_OnSucceeded");
    }

    // Hook OnFailed
    var onFailFn = Module.findExportByName("mmcronet.dll", "Cronet_UrlRequestCallback_OnFailed");
    if (onFailFn) {
        Interceptor.attach(onFailFn, {
            onEnter: function(args) {
                var requestPtr = args[1];
                var reqInfo = active_requests[requestPtr];
                if (reqInfo && isInteresting(reqInfo.url)) {
                    console.log("[FAIL] " + reqInfo.url);
                }
                delete active_requests[requestPtr];
            }
        });
        console.log("Hooked Cronet_UrlRequestCallback_OnFailed");
    }
}

function isTextData(bytes) {
    // Check if first 512 bytes look like text
    var len = Math.min(bytes.length, 512);
    var textChars = 0;
    for (var i = 0; i < len; i++) {
        var b = bytes[i];
        if ((b >= 32 && b <= 126) || b == 10 || b == 13 || b == 9) {
            textChars++;
        }
    }
    return (textChars > len * 0.7);
}

function bytesToString(bytes) {
    // Convert byte array to UTF-8 string
    var result = "";
    var i = 0;
    while (i < bytes.length) {
        var b = bytes[i];
        if (b < 0x80) {
            result += String.fromCharCode(b);
            i++;
        } else if (b < 0xE0) {
            if (i + 1 < bytes.length) {
                result += String.fromCharCode(((b & 0x1F) << 6) | (bytes[i+1] & 0x3F));
                i += 2;
            } else i++;
        } else if (b < 0xF0) {
            if (i + 2 < bytes.length) {
                result += String.fromCharCode(((b & 0x0F) << 12) | ((bytes[i+1] & 0x3F) << 6) | (bytes[i+2] & 0x3F));
                i += 3;
            } else i++;
        } else {
            if (i + 3 < bytes.length) {
                var cp = ((b & 0x07) << 18) | ((bytes[i+1] & 0x3F) << 12) | ((bytes[i+2] & 0x3F) << 6) | (bytes[i+3] & 0x3F);
                if (cp > 0xFFFF) {
                    cp -= 0x10000;
                    result += String.fromCharCode(0xD800 + (cp >> 10), 0xDC00 + (cp & 0x3FF));
                } else {
                    result += String.fromCharCode(cp);
                }
                i += 4;
            } else i++;
        }
    }
    return result;
}

// Buffer.concat polyfill
var Buffer = {
    concat: function(a, b) {
        var result = new Uint8Array(a.length + b.length);
        result.set(a);
        result.set(b, a.length);
        return result;
    }
};

// Send captured text data to Python host
function saveCaptured(url, text, size) {
    // Create message for Python host
    var msg = {
        type: "text",
        url: url,
        size: size,
        preview: text.substring(0, 2000),
    };
    send(msg);
}

// Send captured binary data info
function saveCapturedBinary(url, data, size) {
    var msg = {
        type: "binary",
        url: url,
        size: size,
    };
    send(msg);

    // For .ts files, send the data so Python can save it
    if (url.indexOf(".ts") !== -1 || url.indexOf(".m3u8") !== -1) {
        // Send raw bytes
        send({
            type: "raw",
            url: url,
            size: size,
        }, data);
    }
}

// Runtime
rpc.exports = {
    init: function() {
        var ok = initHelpers();
        if (!ok) return false;
        hookUrlRequestInit();
        hookCallbacks();
        return true;
    }
};
"""


def on_message(message, data):
    """Handle messages from Frida."""
    if message["type"] == "send":
        payload = message["payload"]
        msg_type = payload.get("type")

        if msg_type == "text":
            url = payload["url"]
            text_preview = payload.get("preview", "")
            size = payload.get("size", 0)
            logging.info(f"[CAPTURE] {url} ({size} bytes)")

            # Save to URL registry
            url_record = {
                "time": datetime.now().isoformat(),
                "url": url,
                "size": size,
            }
            urls.append(url_record)

            # Save interesting text content
            save_text_content(url, text_preview)

        elif msg_type == "binary":
            url = payload["url"]
            size = payload.get("size", 0)
            logging.info(f"[BINARY] {url} ({size} bytes)")
            url_record = {
                "time": datetime.now().isoformat(),
                "url": url,
                "size": size,
                "type": "binary",
            }
            urls.append(url_record)

        elif msg_type == "raw":
            url = payload["url"]
            size = payload.get("size", 0)
            if data:
                save_raw_data(url, data)
                logging.info(f"[RAW] Saved {url} ({size} bytes)")

        # Periodically flush URL registry
        if len(urls) % 10 == 0:
            flush_urls()

    elif message["type"] == "error":
        logging.error(f"Frida error: {message.get('description', '')}")


def save_text_content(url, text):
    """Save interesting text content (HLS playlists, JSON APIs)."""
    try:
        # Save m3u8 playlists
        if ".m3u8" in url.lower() or "m3u8" in text[:100].lower():
            safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', url.split("?")[0][-60:])
            path = os.path.join(HLS_DIR, f"{safe_name}.m3u8")
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            logging.info(f"  -> Saved HLS playlist: {safe_name}.m3u8")

        # Save JSON responses
        if text.strip().startswith("{"):
            path = os.path.join(CAPTURE_DIR, "frida_api.json")
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "time": datetime.now().isoformat(),
                    "url": url,
                    "body": text[:5000],
                }, ensure_ascii=False) + "\n")
    except Exception as e:
        logging.error(f"Failed to save text content: {e}")


def save_raw_data(url, data):
    """Save raw binary data (video segments)."""
    try:
        if ".ts" in url.lower():
            safe_name = url.split("/")[-1].split("?")[0]
            if safe_name:
                path = os.path.join(HLS_DIR, safe_name)
                with open(path, "wb") as f:
                    f.write(data)
                logging.info(f"  -> Saved TS segment: {safe_name}")
    except Exception as e:
        logging.error(f"Failed to save raw data: {e}")


urls = []
import re


def flush_urls():
    """Flush URL registry to disk."""
    try:
        existing = []
        if os.path.exists(URLS_FILE):
            with open(URLS_FILE, "r", encoding="utf-8") as f:
                existing = json.load(f)
        existing.extend(urls)
        with open(URLS_FILE, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        urls.clear()
    except Exception as e:
        logging.error(f"Failed to flush URLs: {e}")


def find_radium_pid():
    """Find RadiumWMPF.bin PID."""
    import subprocess
    result = subprocess.run(
        ["tasklist", "/NH", "/FI", "IMAGENAME eq RadiumWMPF.bin"],
        capture_output=True, text=True, timeout=5,
    )
    for line in result.stdout.split("\n"):
        if "RadiumWMPF" in line:
            parts = line.split()
            if len(parts) > 1:
                try:
                    return int(parts[1])
                except ValueError:
                    pass
    return None


def main():
    import frida

    logging.info("=" * 60)
    logging.info("Frida Cronet Capture for 鹅直播")
    logging.info("=" * 60)

    # Wait for RadiumWMPF process
    pid = find_radium_pid()
    if not pid:
        logging.info("Waiting for RadiumWMPF.bin (鹅直播 mini-program)...")
        logging.info("Please open 鹅直播 in WeChat now!")
        for _ in range(120):  # Wait up to 2 minutes
            time.sleep(1)
            pid = find_radium_pid()
            if pid:
                break

    if not pid:
        logging.error("RadiumWMPF.bin not found after 2 minutes. Exiting.")
        return

    logging.info(f"Attaching to RadiumWMPF.bin (PID: {pid})")

    try:
        session = frida.attach(pid)
    except Exception as e:
        # Try spawning (if process exists but can't attach)
        logging.error(f"Failed to attach: {e}")
        # Fallback: try to enumerate all processes
        try:
            mgr = frida.get_device_manager()
            device = mgr.get_local_device()
            session = device.attach(pid)
        except Exception as e2:
            logging.error(f"All attachment methods failed: {e2}")
            return

    script = session.create_script(FRIDA_SCRIPT)
    script.on("message", on_message)
    script.load()

    # Initialize hooks via RPC
    result = script.exports.init()
    if not result:
        logging.error("Failed to initialize hooks!")
        return

    logging.info("Hooks installed. Capturing traffic...")
    logging.info("Browse 鹅直播 videos to capture URLs and content.")
    logging.info("Press Ctrl+C to stop.")

    try:
        script.exports.wait()  # Keep script alive
        # If wait() isn't available, loop instead
        import sys
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("Stopping capture...")
    finally:
        flush_urls()
        # Stop netlog if needed
        logging.info(f"Capture complete. Log: {LOG_FILE}")
        logging.info(f"URLs: {URLS_FILE}")
        logging.info(f"Videos: {HLS_DIR}")
        session.detach()


if __name__ == "__main__":
    main()
