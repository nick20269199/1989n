"""
Packet capture using Windows pktmon + DNS analysis.
Captures traffic from Androws emulator to identify video CDN endpoints.
"""
import os
import subprocess
import time
import json
import re
import threading
from datetime import datetime

CAPTURE_DIR = "D:/1989n/stock_data/kae"
PKTMON_LOG = os.path.join(CAPTURE_DIR, "pktmon_capture.etl")
PKTMON_TXT = os.path.join(CAPTURE_DIR, "pktmon_output.txt")
CAPTURE_LOG = os.path.join(CAPTURE_DIR, "pktmon_capture.log")
DNS_LOG = os.path.join(CAPTURE_DIR, "pktmon_dns.txt")
SUMMARY_FILE = os.path.join(CAPTURE_DIR, "pktmon_summary.json")

os.makedirs(CAPTURE_DIR, exist_ok=True)


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(CAPTURE_LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def start_pktmon():
    """Start pktmon capture."""
    log("Starting pktmon capture (filtering Androws process)...")
    # Start pktmon in background
    cmd = [
        "pktmon", "start", "--etw",
        "-p", "32728",  # Androws.exe PID
        "-o", "--log-size", "100",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    if result.returncode != 0:
        # Try without PID filter - capture all
        log(f"PID filter failed: {result.stderr.strip()}")
        log("Falling back to all-traffic capture...")
        cmd = ["pktmon", "start", "--etw", "--log-size", "100"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            log(f"pktmon start failed: {result.stderr.strip()}")
            return False
    log("pktmon capture started (process filter: Androws PID 32728)")
    return True


def stop_pktmon():
    """Stop pktmon and save output."""
    log("Stopping pktmon capture...")
    subprocess.run(["pktmon", "stop"], capture_output=True, timeout=10)

    # Save as text for analysis
    log("Converting pktmon log to text...")
    result = subprocess.run(
        ["pktmon", "etl2txt", PKTMON_LOG, "--out", PKTMON_TXT],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode == 0:
        log(f"Packet log saved to {PKTMON_TXT}")
        return True
    else:
        log(f"etl2txt failed: {result.stderr.strip()}")
        return False


def analyze_packets():
    """Analyze captured packets for DNS queries and TLS handshakes."""
    if not os.path.exists(PKTMON_TXT):
        log("No packet log to analyze")
        return

    log("Analyzing packets for video-related endpoints...")

    # Extract DNS queries
    dns_queries = set()
    tls_sni = set()
    tcp_connections = set()
    http_urls = set()

    # Parse the text output - look for DNS and TLS patterns
    dns_pattern = re.compile(r'DNS.*Question.*(?:www\.)?([a-zA-Z0-9.-]+\.[a-z]{2,})')
    sni_pattern = re.compile(r'ServerName:\s*([a-zA-Z0-9.-]+\.[a-z]{2,})')
    http_pattern = re.compile(r'HTTP:\s*(?:GET|POST|PUT)\s+(https?://[^\s"\']+)')

    with open(PKTMON_TXT, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            # DNS queries
            m = dns_pattern.search(line)
            if m:
                dns_queries.add(m.group(1))

            # TLS SNI
            m = sni_pattern.search(line)
            if m:
                tls_sni.add(m.group(1))

            # HTTP URLs
            m = http_pattern.search(line)
            if m:
                http_urls.add(m.group(1))

    # Save DNS analysis
    domains = {
        "dns_queries": sorted(dns_queries),
        "tls_sni": sorted(tls_sni),
        "http_urls": sorted(http_urls),
        "total_dns": len(dns_queries),
        "total_sni": len(tls_sni),
        "total_http": len(http_urls),
    }

    with open(DNS_LOG, "w", encoding="utf-8") as f:
        f.write("DNS Queries:\n")
        for d in sorted(dns_queries):
            f.write(f"  {d}\n")
        f.write(f"\nTLS SNI:\n")
        for s in sorted(tls_sni):
            f.write(f"  {s}\n")
        f.write(f"\nHTTP URLs:\n")
        for h in sorted(http_urls):
            f.write(f"  {h}\n")

    with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
        json.dump(domains, f, ensure_ascii=False, indent=2)

    log(f"Found {len(dns_queries)} DNS queries, {len(tls_sni)} TLS SNI, {len(http_urls)} HTTP URLs")
    log(f"DNS log: {DNS_LOG}")
    log(f"Summary: {SUMMARY_FILE}")

    # Highlight video/live related domains
    video_keywords = ["video", "live", "stream", "cdn", "m3u8", "hls", "vod", "media"]
    interesting = []
    for d in sorted(dns_queries | tls_sni):
        if any(kw in d.lower() for kw in video_keywords):
            interesting.append(d)

    if interesting:
        log(f"\nVideo-related domains found ({len(interesting)}):")
        for d in interesting:
            log(f"  >>> {d}")
    else:
        log("\nNo video-related domains found in this capture")
        log("(Try playing a video in the app for at least 10 seconds)")

    return domains


def main():
    print("=" * 60)
    print("PKTMON Traffic Capture - 小鹅通学员版")
    print("=" * 60)
    print()
    print("请在小鹅通学员版中打开并播放一个视频（至少10秒）")
    print("然后按 Ctrl+C 停止抓取并分析结果")
    print()

    if not start_pktmon():
        log("Failed to start pktmon. Try running as Administrator?")
        return

    try:
        # Wait for user to press Ctrl+C
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        stop_pktmon()
        analyze_packets()

    print()
    print("Done. Check stock_data/kae/ for results.")


if __name__ == "__main__":
    main()
