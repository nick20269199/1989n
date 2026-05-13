"""
pool — MarketPool 统一入口

职责:
  1. 全市场/持仓 日K线增量更新 → Parquet
  2. 实时行情缓存 + 批量查询
  3. 统一查询接口 (K线/行情)
"""
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd

from . import store
from .config import (
    POOL_DIR, QUOTES_FILE, QUOTES_CACHE_TTL,
    UPDATE_WORKERS, STOCK_ANALYSIS_DIR,
)
from .fetcher import (
    fetch_kline, fetch_quotes, fetch_indices, A_INDICES,
    fetch_quotes_tencent, fetch_quotes_sina,
)
from .stock_list import load_stock_list, filter_stocks

logger = logging.getLogger("market_pool")


class MarketPool:
    """A股本地数据池"""

    def __init__(self):
        store.ensure_dirs()

    # ── 全量更新 ──

    def update_all(self, days: int = 365, workers: int = UPDATE_WORKERS) -> dict:
        """全市场增量更新: 遍历所有A股, 补K线。
        - 有缓存的跳过
        - 无缓存的拉取 days 天历史
        - 已有老数据的跳过
        返回 {total, skipped, updated, failed}
        """
        stocks = load_stock_list()
        # 过滤北交所 (92xxxx 腾讯无数据) + 科创板 (可选)
        filtered = [s for s in stocks
                    if not s["code"].startswith("92")]
        codes = [s["code"] for s in filtered]
        logger.info("全市场 %d 只(过滤后), 原列表 %d 只",
                     len(codes), len(stocks))

        # 过滤已有完整缓存的
        to_fetch = []
        skipped = 0
        for code in codes:
            last_date = store.get_latest_kline_date(code)
            if last_date:
                today_str = datetime.now().strftime("%Y-%m-%d")
                if last_date >= today_str:
                    skipped += 1
                    continue
            to_fetch.append(code)

        logger.info("全市场更新: %d 只待更新, %d 只已是最新",
                     len(to_fetch), skipped)

        if not to_fetch:
            return {"total": len(codes), "skipped": skipped,
                    "updated": 0, "failed": 0}

        updated = 0
        updated_codes = []
        failed = []
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {ex.submit(self._update_one, code, days): code
                       for code in to_fetch}
            for f in as_completed(futures):
                code = futures[f]
                try:
                    if f.result():
                        updated += 1
                        updated_codes.append(code)
                except Exception as e:
                    failed.append(code)
                    logger.debug("更新失败 %s: %s", code, e)

        # 批量写入元数据 (一次性, 避免并发写)
        if updated_codes:
            store.update_meta(updated_codes)

        result = {
            "total": len(codes),
            "skipped": skipped,
            "updated": updated,
            "failed": len(failed),
            "failed_codes": failed[:10],
        }
        logger.info("全市场更新完成: total=%d, skip=%d, ok=%d, fail=%d",
                     result["total"], result["skipped"],
                     result["updated"], result["failed"])
        return result

    def _update_one(self, code: str, days: int) -> bool:
        """更新单只股票的K线缓存"""
        try:
            bars = fetch_kline(code, days)
            if not bars:
                return False
            store.save_kline(code, bars)
            return True
        except Exception as e:
            logger.debug("_update_one(%s): %s", code, e)
            return False

    # ── 持仓更新 ──

    def update_watchlist(self, days: int = 365) -> dict:
        """仅更新持仓+跟踪标的的K线"""
        codes = self._watchlist_codes()
        logger.info("更新持仓: %s", codes)
        ok, fail = 0, []
        updated_codes = []
        for code in codes:
            try:
                bars = fetch_kline(code, days)
                if bars:
                    store.save_kline(code, bars)
                    ok += 1
                    updated_codes.append(code)
                else:
                    fail.append(code)
            except Exception as e:
                fail.append(code)
                logger.debug("持仓更新失败 %s: %s", code, e)
        if updated_codes:
            store.update_meta(updated_codes)
        return {"ok": ok, "fail": fail}

    @staticmethod
    def _watchlist_codes() -> list[str]:
        """从 portfolio.json 读取持仓代码"""
        pf = STOCK_ANALYSIS_DIR / "data" / "portfolio.json"
        if not pf.exists():
            logger.warning("portfolio.json 不存在: %s", pf)
            return []
        with open(pf, encoding="utf-8") as f:
            data = json.load(f)
        codes = [h["code"] for h in data.get("holdings", [])]
        codes.extend(h["code"] for h in data.get("cleared", []))
        return list(set(codes))

    # ── K 线查询 ──

    def get_kline(self, code: str, days: Optional[int] = None) -> Optional[pd.DataFrame]:
        """获取日K线 (本地缓存优先, 无缓存自动拉取并缓存)

        Args:
            code: 6位股票代码
            days: 取最近N天, 不填则全部

        Returns:
            DataFrame 或 None
        """
        df = store.get_kline_df(code, days)
        if df is not None:
            return df

        # 无缓存, 拉取
        logger.info("本地无K线, 远程拉取 %s", code)
        bars = fetch_kline(code, min(days or 365, 365))
        if not bars:
            return None
        store.save_kline(code, bars)
        return store.get_kline_df(code, days)

    # ── 实时行情 ──

    def get_quotes(self, codes: list[str], force_refresh=False) -> dict:
        """获取实时行情 (60秒缓存)

        Args:
            codes: 股票代码列表
            force_refresh: 强制刷新缓存

        Returns:
            {code: {name, current, change_pct, ...}, ...}
        """
        cached = self._load_quotes_cache()
        if not force_refresh and cached and self._cache_fresh(cached):
            # 从缓存查
            result = {c: cached["data"].get(c) for c in codes
                      if c in cached["data"]}
            missing = [c for c in codes if c not in cached["data"]]
            if missing:
                fresh = fetch_quotes(missing)
                result.update(fresh)
                if fresh:
                    cached["data"].update(fresh)
                    self._save_quotes_cache(cached)
            return result

        # 刷新全部
        quotes = fetch_quotes(codes)
        if quotes:
            self._save_quotes_cache({
                "time": time.time(),
                "data": quotes,
            })
        return quotes

    def refresh_quotes(self, codes: Optional[list[str]] = None) -> dict:
        """强制刷新行情缓存"""
        if codes is None:
            codes = self._watchlist_codes() or ["000001", "399001"]
        return self.get_quotes(codes, force_refresh=True)

    def get_indices(self) -> list[dict]:
        """获取主要指数行情"""
        return fetch_indices()

    # ── 缓存管理 ──

    def _quotes_cache_path(self):
        return QUOTES_FILE

    def _load_quotes_cache(self) -> Optional[dict]:
        p = self._quotes_cache_path()
        if p.exists():
            try:
                with open(p, encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        return None

    def _save_quotes_cache(self, data: dict):
        p = self._quotes_cache_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

    @staticmethod
    def _cache_fresh(cached: dict) -> bool:
        elapsed = time.time() - cached.get("time", 0)
        return elapsed < QUOTES_CACHE_TTL

    # ── 状态 ──

    def stats(self) -> dict:
        """数据池状态统计"""
        s = store.pool_stats()
        s["watchlist_count"] = len(self._watchlist_codes())
        return s
