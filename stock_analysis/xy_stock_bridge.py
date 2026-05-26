"""XyStock 数据桥接 — 接入情报部数据管线

将 XyStock (AI交易大师) 本地数据库接入当前系统。
数据流:
  XyStock localmarket_3/ → xy_stock_reader → xy_stock_bridge → 情报部管线

用法:
  from xy_stock_bridge import XyStockBridge
  bridge = XyStockBridge()
  name = bridge.get_stock_name("600000")
  pe = bridge.get_pe_ratio("600000")
  latest = bridge.get_latest_quotes(["600000", "000001"])
"""

import logging
import json
from datetime import datetime
from typing import Optional
from xy_stock_reader import XyStockReader, FinanceData

logger = logging.getLogger("xy_stock_bridge")

# 懒加载单例
_READER = None


def _get_reader() -> XyStockReader:
    global _READER
    if _READER is None:
        _READER = XyStockReader()
    return _READER


class XyStockBridge:
    """XyStock 数据桥接器 — 情报部数据管线中的辅助数据源"""

    def __init__(self):
        self.reader = _get_reader()

    def get_stock_name(self, code: str) -> Optional[str]:
        """获取股票中文名称（精简模式）"""
        s = self.reader.get_stock(code)
        return s.cn_name_simplified if s else None

    def get_pe_ratio(self, code: str) -> Optional[float]:
        """从 .fnc 提取市盈率 (最后一个 float 字段)"""
        fin = self.reader.get_finance(code)
        if not fin or not fin.raw_floats:
            return None
        # 最后一个 float 是 PE
        return fin.raw_floats[-1]

    def get_stock_info(self, code: str) -> Optional[dict]:
        """获取股票完整信息（含财务）"""
        s = self.reader.get_stock(code)
        if not s:
            return None
        info = {
            "code": s.code,
            "name": s.cn_name_simplified or s.en_name,
            "market": s.market_name,
            "en_name": s.en_name or "",
        }
        # 附加财务数据
        fin = self.reader.get_finance(code)
        if fin and fin.raw_floats:
            floats = fin.raw_floats
            # 最后一个 float 是 PE
            if floats and abs(floats[-1]) < 1e6:
                info["pe"] = round(floats[-1], 2)
        return info

    def batch_get_names(self, codes: list[str]) -> dict:
        """批量查询股票名称，返回 {code: name}"""
        return {c: self.get_stock_name(c) for c in codes}

    def get_coverage_report(self) -> dict:
        """返回数据覆盖报告"""
        reader = self.reader
        market_counts = reader.count_by_market()
        total = sum(market_counts.values())
        return {
            "total_stocks": total,
            "by_market": market_counts,
            "source": "XyStock localmarket_3",
            "updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }


# ── 快速自检 ──
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    bridge = XyStockBridge()

    print("=" * 60)
    print("XyStock 数据桥接 — 接入测试")
    print("=" * 60)

    # 1. 数据覆盖
    report = bridge.get_coverage_report()
    print(f"\n数据覆盖: {report['total_stocks']} 只")

    # 2. 查名 + 查 PE
    for code in ["600000", "600004", "000001", "002156", "688981"]:
        name = bridge.get_stock_name(code)
        pe = bridge.get_pe_ratio(code)
        if name:
            pe_str = f", PE={pe:.2f}" if pe else ""
            print(f"  {code}: {name}{pe_str}")

    # 3. 完整信息
    print("\n完整信息:")
    info = bridge.get_stock_info("600000")
    if info:
        print(f"  {json.dumps(info, ensure_ascii=False, indent=2)}")
