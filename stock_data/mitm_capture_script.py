
import logging

def request(flow):
    url = flow.request.pretty_url
    if any(kw in url for kw in ['live', 'video', 'stream', 'room', 'play', '.m3u8', '.ts', '.flv']):
        logging.info(f"MEDIA: {url}")
    if 'wx13a74d0d3ab0942e' in url or 'qq.com' in url or 'live' in url:
        with open('D:/1989n/stock_data/mitm_capture.log', 'a') as f:
            f.write(f"REQ: {url}
")
            f.write(f"  headers: {dict(flow.request.headers)}

")

def response(flow):
    url = flow.request.pretty_url
    content_type = flow.response.headers.get('content-type', '')
    if 'wx13a74d0d3ab0942e' in url or 'live' in url or 'video' in url or 'm3u8' in url:
        with open('D:/1989n/stock_data/mitm_capture.log', 'a') as f:
            f.write(f"RES: {url}
")
            f.write(f"  content-type: {content_type}
")
            f.write(f"  size: {len(flow.response.content)}

")
        if 'json' in content_type:
            with open('D:/1989n/stock_data/mitm_capture.log', 'a') as f:
                f.write(f"  body: {flow.response.text[:500]}

")
