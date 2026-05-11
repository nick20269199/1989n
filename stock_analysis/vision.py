"""
多模态分析工具 — Qwen3.6 / Qwen-VL 系列
支持: 图片分析 / OCR / 图表分析 / 视频分析 / 通用推理

API: 阿里云百炼 DashScope OpenAI-compatible
  endpoint: https://dashscope.aliyuncs.com/compatible-mode/v1
  vision:   qwen-vl-plus
  reason:   qwen3.6-plus

Usage:
  python vision.py <image_path> ["prompt"]
  python vision.py chart <image_path>
  python vision.py ocr <image_path>
  python vision.py reason "<text question>"
  python vision.py video <video_url_or_path> ["prompt"]
"""

import base64
import logging
import os
import sys
from pathlib import Path

from config import DASHSCOPE_API_KEY

logger = logging.getLogger("vision")

# === API 配置 ===
API_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
VISION_MODEL = "qwen-vl-plus"
REASON_MODEL = "qwen3.6-plus"
DEFAULT_MAX_TOKENS = 2000

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    logger.warning("requests 不可用，多模态功能受限")


def _get_api_key() -> str:
    key = DASHSCOPE_API_KEY or os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
    if not key:
        logger.error("DASHSCOPE_API_KEY 未配置")
    return key


def _encode_image(image_path: str) -> str:
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"图片文件不存在: {image_path}")

    suffix = path.suffix.lower()
    mime_map = {
        ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp",
    }
    mime_type = mime_map.get(suffix, "image/png")

    with open(path, "rb") as f:
        data = base64.b64encode(f.read()).decode("ascii")
    return f"data:{mime_type};base64,{data}"


def _call_api(messages: list[dict], model: str = None,
              max_tokens: int = DEFAULT_MAX_TOKENS) -> str:
    api_key = _get_api_key()
    if not api_key:
        return "[错误] API Key 未配置，请在 .env 中设置 DASHSCOPE_API_KEY"
    if not REQUESTS_AVAILABLE:
        return "[错误] requests 库未安装"

    payload = {
        "model": model or VISION_MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
    }

    try:
        resp = requests.post(
            API_BASE_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=120,
        )
        resp.raise_for_status()
        result = resp.json()
        return result["choices"][0]["message"]["content"]
    except requests.exceptions.Timeout:
        logger.error("API 请求超时")
        return "[错误] API 请求超时"
    except requests.exceptions.RequestException as e:
        logger.error(f"API 请求失败: {e}")
        return f"[错误] API 请求失败: {e}"
    except (KeyError, IndexError) as e:
        logger.error(f"API 响应格式异常: {e}")
        return "[错误] API 响应格式异常"


def _build_vision_content(source: str, media_type: str = "image") -> dict:
    """构建图片或视频消息块。"""
    if source.startswith(("http://", "https://")):
        if media_type == "video":
            return {"type": "video_url", "video_url": {"url": source}}
        return {"type": "image_url", "image_url": {"url": source}}
    else:
        data_url = _encode_image(source)
        return {"type": "image_url", "image_url": {"url": data_url}}


# ============================================================
# 公共 API
# ============================================================

def analyze_image(image_path: str, prompt: str = "") -> str:
    """分析图片内容。支持本地路径或 URL。"""
    logger.info(f"分析图片: {image_path}")
    user_prompt = prompt or (
        "请详细描述这张图片的内容。包括:\n"
        "1. 图片类型和整体内容\n2. 可见的文字信息 (如有)\n"
        "3. 图表和数据 (如有)\n4. 关键视觉元素\n5. 值得注意的细节"
    )
    msg = _build_vision_content(image_path)
    messages = [
        {"role": "system", "content": "你是一个专业的图片分析助手，请用中文回答。"},
        {"role": "user", "content": [msg, {"type": "text", "text": user_prompt}]},
    ]
    result = _call_api(messages)
    logger.info(f"分析完成 ({len(result)} 字符)")
    return result


def extract_text_from_image(image_path: str) -> str:
    """从图片提取文字 (OCR)。"""
    logger.info(f"OCR: {image_path}")
    msg = _build_vision_content(image_path)
    messages = [
        {"role": "system", "content": "你是一个OCR助手。提取图片中所有文字，保持原有格式。请用中文回答。"},
        {"role": "user", "content": [msg, {"type": "text", "text": "提取这张图片中的所有文字内容，保持原有格式。"}]},
    ]
    result = _call_api(messages, max_tokens=4000)
    logger.info(f"OCR 完成 ({len(result)} 字符)")
    return result


def analyze_chart(image_path: str) -> str:
    """分析股票图表截图 (K线/分时/技术指标)。"""
    logger.info(f"分析图表: {image_path}")
    chart_prompt = (
        "请仔细分析这张股票/金融图表。包括:\n"
        "1. 图表类型: K线图/分时图/成交量/技术指标图等\n"
        "2. 股票信息: 代码、名称 (如果可见)\n"
        "3. 关键数据: 价格、涨跌幅、成交量、换手率等\n"
        "4. 技术信号: 均线排列(多头/空头)、MACD金叉/死叉、RSI超买/超卖、布林带位置、支撑/阻力位\n"
        "5. 盘面特征: 大单成交、分时异动、量价配合\n"
        "6. 综合判断: 技术面偏多/中性/偏空\n"
        "请用中文输出，格式清晰。"
    )
    msg = _build_vision_content(image_path)
    messages = [
        {"role": "system", "content": "你是专业股票技术分析师，擅长解读K线图和技术指标。请用中文回答。"},
        {"role": "user", "content": [msg, {"type": "text", "text": chart_prompt}]},
    ]
    result = _call_api(messages, max_tokens=3000)
    logger.info(f"图表分析完成 ({len(result)} 字符)")
    return result


def analyze_video(video_source: str, prompt: str = "") -> str:
    """分析视频内容。支持本地文件路径或 URL。"""
    logger.info(f"分析视频: {video_source}")
    user_prompt = prompt or (
        "请详细描述这个视频的内容。包括:\n"
        "1. 视频主题和场景\n2. 关键人物和对话内容\n"
        "3. 重要画面和数据信息\n4. 视频表达的核心观点\n5. 时间线上的关键节点"
    )
    msg = _build_vision_content(video_source, media_type="video")
    messages = [
        {"role": "system", "content": "你是专业视频内容分析助手，请用中文回答。"},
        {"role": "user", "content": [msg, {"type": "text", "text": user_prompt}]},
    ]
    result = _call_api(messages, max_tokens=4000)
    logger.info(f"视频分析完成 ({len(result)} 字符)")
    return result


def reason(text: str, model: str = None) -> str:
    """纯文本推理。使用 qwen3.6-plus (Always-on Thinking)。"""
    logger.info(f"推理: {text[:50]}...")
    messages = [{"role": "user", "content": text}]
    result = _call_api(messages, model=model or REASON_MODEL, max_tokens=4000)
    logger.info(f"推理完成 ({len(result)} 字符)")
    return result


# ============================================================
# 主入口
# ============================================================

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if len(sys.argv) < 2:
        print("用法:")
        print("  python vision.py <image_path> [prompt]     — 通用图片分析")
        print("  python vision.py chart <image_path>        — 股票图表分析")
        print("  python vision.py ocr <image_path>          — 文字提取")
        print("  python vision.py video <url_or_path> [p]   — 视频分析")
        print("  python vision.py reason \"<question>\"       — 纯文本推理")
        sys.exit(1)

    mode = sys.argv[1].lower()

    if mode == "chart" and len(sys.argv) >= 3:
        print(analyze_chart(sys.argv[2]))
    elif mode == "ocr" and len(sys.argv) >= 3:
        print(extract_text_from_image(sys.argv[2]))
    elif mode == "video" and len(sys.argv) >= 3:
        prompt = sys.argv[3] if len(sys.argv) > 3 else ""
        print(analyze_video(sys.argv[2], prompt))
    elif mode == "reason" and len(sys.argv) >= 3:
        print(reason(sys.argv[2]))
    elif mode in ("chart", "ocr", "video", "reason"):
        print(f"错误: {mode} 模式需要提供输入")
        sys.exit(1)
    else:
        image_path = sys.argv[1]
        prompt = sys.argv[2] if len(sys.argv) > 2 else ""
        print(analyze_image(image_path, prompt))


if __name__ == "__main__":
    main()
