"""
tdx_loader — 通达信离线日线数据读取器

从通达信本地 vipdoc 目录读取 .day 二进制日线文件。
格式: 32字节/条, 前复权价格。

用法:
  from market_pool.tdx_loader import read_tdx_day, import_tdx_to_pool
  bars = read_tdx_day("000001")        # 返回K线列表
  stats = import_tdx_to_pool()          # 批量导入到 market_pool
"""
import logging
import struct
from pathlib import Path
from typing import Optional

logger = logging.getLogger("market_pool.tdx_loader")

# 通达信安装目录 (用户的实际路径)
TDX_ROOT = Path("D:/TDX")
TDX_VIPDOC = TDX_ROOT / "vipdoc"

# .day 文件目录结构: {vipdoc}/{sh|sz}/lday/{prefix}{code}.day
DAY_DIRS = {
    "sh": TDX_VIPDOC / "sh" / "lday",
    "sz": TDX_VIPDOC / "sz" / "lday",
}

# 32字节/条
RECORD_BYTES = 32


def _prefix(code: str) -> str:
    return "sh" if code.startswith(("6", "9")) else "sz"


def _day_path(code: str) -> Optional[Path]:
    """返回 .day 文件路径, 不存在则返回 None。"""
    market = _prefix(code)
    fpath = DAY_DIRS[market] / f"{market}{code}.day"
    return fpath if fpath.exists() else None


def read_tdx_day(code: str) -> Optional[list[dict]]:
    """读取单只股票的TDX日线数据。

    返回 [{date, open, close, high, low, volume, amount}, ...] 按日期升序。
    文件不存在或解析失败返回 None。
    """
    fpath = _day_path(code)
    if fpath is None:
        return None

    try:
        raw = fpath.read_bytes()
    except Exception as e:
        logger.warning("读取失败 %s: %s", code, e)
        return None

    n = len(raw) // RECORD_BYTES
    if n == 0:
        return None

    bars = []
    for i in range(n):
        rec = raw[i * RECORD_BYTES : (i + 1) * RECORD_BYTES]
        try:
            dt, op, hi, lo, cl, amt, vol, _ = struct.unpack("iiiiifii", rec)
        except struct.error:
            continue

        bars.append({
            "date": str(dt),
            "open": round(op / 100, 2),
            "close": round(cl / 100, 2),
            "high": round(hi / 100, 2),
            "low": round(lo / 100, 2),
            "volume": vol,
            "amount": amt,
        })

    return bars if bars else None


def get_tdx_stock_codes() -> list[str]:
    """列出TDX目录下所有A股代码 (0xxxxx / 3xxxxx / 6xxxxx)。

    返回 sorted(["000001", "000002", ..., "603999"])。
    """
    codes = []
    for market, d in DAY_DIRS.items():
        if not d.exists():
            continue
        for f in d.iterdir():
            if f.suffix != ".day":
                continue
            code = f.stem[2:]  # "sh600000" → "600000"
            if len(code) != 6 or not code.isdigit():
                continue
            # 只保留 A 股: 0 / 3 / 6 开头
            if market == "sh" and code.startswith("6"):
                codes.append(code)
            elif market == "sz" and code.startswith(("0", "3")):
                codes.append(code)
    return sorted(codes)


def import_tdx_to_pool(workers: int = 8) -> dict:
    """批量将通达信日线数据导入 market_pool 的 Parquet 缓存。

    返回 {total, imported, skipped, failed, failed_codes}
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from .store import save_kline

    codes = get_tdx_stock_codes()
    total = len(codes)
    imported = 0
    skipped = 0
    failed = []
    failed_codes = []

    logger.info("通达信导入: 发现 %d 只A股日线文件", total)

    def _import_one(code: str) -> bool:
        bars = read_tdx_day(code)
        if not bars:
            return False
        try:
            save_kline(code, bars)
            return True
        except Exception:
            return False

    with ThreadPoolExecutor(max_workers=workers) as executor:
        fut_map = {executor.submit(_import_one, code): code for code in codes}
        for fut in as_completed(fut_map):
            code = fut_map[fut]
            try:
                if fut.result():
                    imported += 1
                else:
                    skipped += 1
            except Exception:
                failed.append(code)
                failed_codes.append(code)
                skipped += 1

    result = {
        "total": total,
        "imported": imported,
        "skipped": skipped,
        "failed": len(failed),
    }
    if failed_codes:
        result["failed_codes"] = failed_codes[:10]

    logger.info("通达信导入完成: total=%d, imported=%d, skip=%d, fail=%d",
                total, imported, skipped, len(failed))
    return result
