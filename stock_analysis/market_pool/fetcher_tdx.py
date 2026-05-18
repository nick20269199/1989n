"""
fetcher_tdx — 通达信本地离线数据读取器

从 TDX 安装目录的 vipdoc/ 读取 .day 文件，零延迟，不依赖网络。
返回格式与 fetcher.py 的在线 API 完全兼容，可直接替换/补充。
"""
import logging
from pathlib import Path
from typing import Optional

from pytdx.reader import TdxDailyBarReader

logger = logging.getLogger("market_pool.fetcher_tdx")

# ── TDX 安装路径 ──
# 如果你改了 TDX 安装目录，改这个就行
TDX_ROOT = Path("D:/TDX")


def _code_to_file(code: str) -> Optional[Path]:
    """将6位股票代码映射到 TDX .day 文件路径"""
    code = code.strip()
    if code.startswith(("60", "68", "90", "9")):
        market = "sh"
    else:
        market = "sz"
    fpath = TDX_ROOT / "vipdoc" / market / "lday" / f"{market}{code}.day"
    if fpath.exists():
        return fpath
    # 也可能在 bj/ 下 (北交所)
    fpath_bj = TDX_ROOT / "vipdoc" / "bj" / "lday" / f"bj{code}.day"
    if fpath_bj.exists():
        return fpath_bj
    return None


def fetch_kline_tdx(code: str) -> Optional[list]:
    """从通达信本地 .day 文件读取日K线。

    Args:
        code: 6位股票代码，如 "600519"

    Returns:
        [{date, open, close, high, low, volume, amount}, ...]
        按日期升序，与 fetch_kline_tencent() 格式一致。
        文件不存在或解析失败返回 None。
    """
    fpath = _code_to_file(code)
    if fpath is None:
        return None

    try:
        reader = TdxDailyBarReader()
        df = reader.get_df_by_file(str(fpath))
    except Exception as e:
        logger.debug("TDX读取失败 %s: %s", code, e)
        return None

    if df is None or df.empty:
        return None

    bars = []
    for date_idx, row in df.iterrows():
        try:
            bars.append({
                "date": str(date_idx)[:10],
                "open": float(row["open"]),
                "close": float(row["close"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "volume": float(row["volume"]),
                "amount": float(row["amount"]),
            })
        except (ValueError, TypeError):
            continue

    return bars if bars else None


def fetch_kline_tdx_batch(codes: list[str]) -> dict:
    """批量读取多只股票的TDX本地K线，返回 {code: [bars...]}"""
    result = {}
    for code in codes:
        bars = fetch_kline_tdx(code)
        if bars:
            result[code] = bars
    return result


def stats() -> dict:
    """检查TDX数据情况"""
    sh_count = len(list((TDX_ROOT / "vipdoc" / "sh" / "lday").glob("*.day")))
    sz_count = len(list((TDX_ROOT / "vipdoc" / "sz" / "lday").glob("*.day")))
    return {
        "tdx_root": str(TDX_ROOT),
        "sh_files": sh_count,
        "sz_files": sz_count,
        "total": sh_count + sz_count,
    }
