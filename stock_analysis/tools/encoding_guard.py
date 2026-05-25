"""
encoding_guard.py — 数据文件编码自动检测

防止编码错误导致持仓/交易数据错位。
策略: UTF-8 → GBK → Latin-1 逐级回退，返回正确解码的文本或 None。

用法:
    from tools.encoding_guard import read_text_safe, read_json_safe
    text = read_text_safe("D:/1989n/stock_data/some_file.csv")
    data = read_json_safe("D:/1989n/stock_data/some_file.json")
"""
import json
from pathlib import Path

# 常见中文编码，按优先级排列
_ENCODINGS = ["utf-8", "gbk", "gb2312", "gb18030", "latin-1"]


def _has_garbled_text(text: str) -> bool:
    """检测文本是否有明显乱码特征 (替换字符/无效字节序列痕迹)。"""
    if not text:
        return False
    # Unicode 替换字符大量出现 = 解码错误
    replacement_count = text.count("�")
    if replacement_count > len(text) * 0.01:  # >1% 是替换字符
        return True
    return False


def read_text_safe(path: str | Path, encodings: list[str] | None = None) -> str | None:
    """安全读取文本文件，自动检测编码。

    依次尝试指定编码列表，返回首个无乱码的结果。
    默认: UTF-8 → GBK → GB2312 → GB18030 → Latin-1
    """
    p = Path(path)
    if not p.exists():
        return None

    encs = encodings or _ENCODINGS
    raw = p.read_bytes()

    best_result = None
    for enc in encs:
        try:
            text = raw.decode(enc)
            if not _has_garbled_text(text):
                return text
            if best_result is None:
                best_result = text
        except (UnicodeDecodeError, LookupError):
            continue

    # 所有编码都产生乱码，返回第一个结果
    return best_result


def read_json_safe(path: str | Path) -> dict | list | None:
    """安全读取 JSON 文件，自动检测编码。"""
    text = read_text_safe(path)
    if text is None:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None
