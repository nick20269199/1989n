"""
store — 本地数据存储层 (Parquet + JSON)

设计要点:
- 每只股票一只 Parquet 文件, 按日期升序存储日K线
- 增量追加: 只在有新股时追加, 不重复拉历史
- 元数据文件记录每只股票的最新更新日期
- 兼容旧版 JSON kline_cache (读, 不写)
"""
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

from .config import POOL_DIR, KLINE_DIR, META_FILE, OLD_KLINE_DIR

logger = logging.getLogger("market_pool.store")

# Parquet 列定义
KLINE_COLUMNS = ["date", "open", "close", "high", "low", "volume", "amount"]
KLINE_DTYPES = {
    "date": "str", "open": "float32", "close": "float32",
    "high": "float32", "low": "float32", "volume": "float64", "amount": "float64",
}


# ── 初始化 ──

def ensure_dirs():
    POOL_DIR.mkdir(parents=True, exist_ok=True)
    KLINE_DIR.mkdir(parents=True, exist_ok=True)


# ── 元数据读写 ──

def _load_meta() -> dict:
    """加载更新元数据 {code: last_date_str, ...}"""
    if META_FILE.exists():
        with open(META_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_meta(meta: dict):
    META_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(META_FILE, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)


# ── 代码文件路径 ──

def _kline_path(code: str) -> Path:
    return KLINE_DIR / f"{code}.parquet"


# ── 写入/追加K线 ──

def save_kline(code: str, bars: list[dict]):
    """保存/追加日K线到 Parquet。
    - 如果文件不存在: 创建
    - 如果已存在: 读取旧数据, 按日期去重合并, 写回
    """
    if not bars:
        return

    df_new = pd.DataFrame(bars)
    df_new["date"] = df_new["date"].astype(str)
    df_new = df_new.sort_values("date").drop_duplicates(subset="date")

    fpath = _kline_path(code)
    if fpath.exists():
        df_old = pd.read_parquet(fpath)
        df_old["date"] = df_old["date"].astype(str)
        combined = pd.concat([df_old, df_new], ignore_index=True)
        combined = combined.sort_values("date").drop_duplicates(subset="date", keep="last")
        combined = combined.reset_index(drop=True)
    else:
        combined = df_new.reset_index(drop=True)

    combined.to_parquet(fpath, index=False)
    logger.debug("K线已保存 %s: %d 条", code, len(combined))


def get_kline_df(code: str, days: Optional[int] = None) -> Optional[pd.DataFrame]:
    """获取本地缓存的日K线 DataFrame。
    - days: 取最近N天, 不填则返回全部
    返回 None 表示无数据。
    """
    fpath = _kline_path(code)
    if not fpath.exists():
        # 尝试旧版 JSON 缓存
        return _load_old_json_kline(code, days)
    try:
        df = pd.read_parquet(fpath)
    except Exception as e:
        logger.warning("读取K线失败 %s: %s, 尝试旧版JSON", code, e)
        return _load_old_json_kline(code, days)
    if df.empty:
        return None
    df = df.sort_values("date").reset_index(drop=True)
    if days and len(df) > days:
        df = df.tail(days).reset_index(drop=True)
    return df


def _load_old_json_kline(code: str, days: Optional[int] = None) -> Optional[pd.DataFrame]:
    """兼容: 从旧版 JSON kline_cache 读取 (只读不写)"""
    fpath = OLD_KLINE_DIR / f"{code}.json"
    if not fpath.exists():
        return None
    try:
        with open(fpath, encoding="utf-8") as f:
            data = json.load(f)
        bars = data.get("data", [])
        if not bars:
            return None
        df = pd.DataFrame(bars)
        if "date" not in df.columns:
            return None
        df = df.sort_values("date").reset_index(drop=True)
        if days and len(df) > days:
            df = df.tail(days).reset_index(drop=True)
        return df
    except Exception as e:
        logger.debug("旧版JSON K线读取失败 %s: %s", code, e)
        return None


def get_latest_kline_date(code: str) -> Optional[str]:
    """获取本地最新K线日期, 用于增量更新判断。"""
    meta = _load_meta()
    if code in meta:
        return meta[code]
    # fallback: 读文件
    df = get_kline_df(code, days=5)
    if df is not None and not df.empty:
        return str(df["date"].iloc[-1])
    return None


def update_meta(codes: list[str]):
    """批量写入元数据: 从 Parquet 文件读取最新日期。
    在批量更新结束后调用一次, 避免并发写冲突。
    与已有元数据合并, 不覆盖。
    """
    meta = {}
    # 加载已有meta
    if META_FILE.exists():
        try:
            with open(META_FILE, encoding="utf-8") as f:
                existing = json.load(f)
            if isinstance(existing, dict):
                meta.update(existing)
        except Exception:
            pass
    # 读取新文件的日期
    for code in codes:
        path = _kline_path(code)
        if path.exists():
            try:
                df = pd.read_parquet(path, columns=["date"])
                if not df.empty:
                    meta[code] = str(df["date"].iloc[-1])
            except Exception:
                continue
    if meta:
        META_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(META_FILE, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        logger.info("元数据已写入: %d 只", len(meta))


def get_latest_kline_date(code: str) -> Optional[str]:
    """获取本地最新K线日期, 用于增量更新判断。"""
    # 优先读 Parquet 文件头
    path = _kline_path(code)
    if path.exists():
        try:
            df = pd.read_parquet(path, columns=["date"])
            if not df.empty:
                return str(df["date"].iloc[-1])
        except Exception:
            pass
    # fallback: 旧版JSON
    try:
        old = OLD_KLINE_DIR / f"{code}.json"
        if old.exists():
            with open(old, encoding="utf-8") as f:
                data = json.load(f)
            bars = data.get("data", [])
            if bars:
                return bars[-1].get("date")
    except Exception:
        pass
    return None


def has_kline(code: str) -> bool:
    """是否已有K线缓存"""
    fpath = _kline_path(code)
    if fpath.exists():
        return True
    return (OLD_KLINE_DIR / f"{code}.json").exists()


# ── 批量状态查询 ──

def pool_stats() -> dict:
    """数据池统计"""
    ensure_dirs()
    parquet_files = list(KLINE_DIR.glob("*.parquet"))
    meta = _load_meta()
    return {
        "stored_count": len(parquet_files),
        "meta_count": len(meta),
        "size_mb": sum(f.stat().st_size for f in parquet_files) / 1e6,
    }
