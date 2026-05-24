"""
东方财富 Level-2 本地 .dat 文件解析器
=====================================
解析 D:/东方财富/dfcf/data/STOCK/DealL2File/ 下的 L2 逐笔成交数据。

文件格式 (小端序):
  文件头: 16 bytes
  记录:   17 bytes × N
    [0:4]   类型标记 (Ti = 逐笔成交, K-T = 订单簿快照帧)
    [4:8]   序号 (uint32)
    [8:12]  价格 × 1000 (uint32)
    [12:16] 成交量/手 (uint32)
    [16]    方向 (1=买, 2=卖, 3=中性)
"""
import struct
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

L2_DIR = Path("D:/东方财富/dfcf/data/STOCK/DealL2File")


@dataclass
class L2Record:
    seq: int
    price: float       # 元
    volume: int        # 手
    direction: int     # 1=买 2=卖 3=中性
    marker: str        # "Ti" / "Ko" / "Lo" ...


@dataclass
class L2File:
    code: str
    path: Path
    mtime: float
    records: list[L2Record] = field(default_factory=list)

    @property
    def record_count(self) -> int:
        return len(self.records)

    @property
    def buy_volume(self) -> int:
        return sum(r.volume for r in self.records if r.direction == 1)

    @property
    def sell_volume(self) -> int:
        return sum(r.volume for r in self.records if r.direction == 2)

    @property
    def prices(self) -> set[float]:
        return {r.price for r in self.records if r.price > 0}

    @property
    def vwap(self) -> float:
        total_val = sum(r.price * r.volume for r in self.records if r.price > 0)
        total_vol = sum(r.volume for r in self.records if r.price > 0)
        return total_val / total_vol if total_vol > 0 else 0

    @property
    def net_flow(self) -> int:
        """净主动买入量 (买量 - 卖量)"""
        return self.buy_volume - self.sell_volume

    @property
    def buy_ratio(self) -> float:
        total = self.buy_volume + self.sell_volume
        return self.buy_volume / total if total > 0 else 0


def _code_to_filename(code: str) -> str:
    """002156 → 0_002156.dat, 600498 → 1_600498.dat"""
    prefix = "1" if code.startswith("6") else "0"
    return f"{prefix}_{code}.dat"


def parse_l2_file(code: str) -> Optional[L2File]:
    """解析单只股票的 L2 逐笔成交文件。"""
    fname = _code_to_filename(code)
    fpath = L2_DIR / fname
    if not fpath.exists():
        return None

    data = fpath.read_bytes()
    if len(data) < 16:
        return None

    stat = fpath.stat()
    result = L2File(code=code, path=fpath, mtime=stat.st_mtime)

    # 从 offset 16 开始解析 17 字节记录
    offset = 16
    while offset + 17 <= len(data):
        chunk = data[offset:offset + 17]
        marker_bytes = chunk[0:4]
        try:
            marker = marker_bytes.decode("ascii", errors="replace").rstrip("\x00")
        except UnicodeDecodeError:
            marker = marker_bytes.hex()

        seq = struct.unpack("<I", chunk[4:8])[0]
        price_raw = struct.unpack("<I", chunk[8:12])[0]
        volume = struct.unpack("<I", chunk[12:16])[0]
        direction = chunk[16]

        if price_raw == 0 and volume == 0:
            offset += 17
            continue

        result.records.append(L2Record(
            seq=seq,
            price=price_raw / 1000,
            volume=volume,
            direction=direction,
            marker=marker,
        ))
        offset += 17

    return result


def parse_auction_summary(code: str) -> dict:
    """
    解析竞价期间的 L2 数据摘要。
    返回竞价期间的买卖力量对比。
    """
    l2 = parse_l2_file(code)
    if not l2 or not l2.records:
        return {"code": code, "records": 0, "error": "无 L2 数据"}

    # 按标记类型分组
    tick_records = [r for r in l2.records if r.marker == "Ti"]
    depth_records = [r for r in l2.records if r.marker != "Ti"]

    # 竞价价格: 取 Ti 记录中成交量加权均价
    if tick_records:
        auction_price = sum(r.price * r.volume for r in tick_records) / sum(r.volume for r in tick_records)
    elif depth_records:
        auction_price = depth_records[0].price
    else:
        auction_price = 0

    return {
        "code": code,
        "records": l2.record_count,
        "tick_count": len(tick_records),
        "depth_snapshots": len(depth_records),
        "auction_price": round(auction_price, 2),
        "buy_volume": l2.buy_volume,
        "sell_volume": l2.sell_volume,
        "net_flow": l2.net_flow,
        "buy_ratio": round(l2.buy_ratio, 3),
        "prices": sorted(l2.prices),
        "vwap": round(l2.vwap, 2),
        "file_mtime": datetime.fromtimestamp(l2.mtime).strftime("%Y-%m-%d %H:%M:%S"),
    }


def parse_portfolio_l2(portfolio: list[dict] = None) -> list[dict]:
    """批量解析持仓股票的 L2 竞价摘要。"""
    if portfolio is None:
        import json
        pf = json.loads(Path("D:/1989n/stock_analysis/data/portfolio.json").read_text("utf-8"))
        if isinstance(pf, dict):
            pf = pf.get("holdings", pf.get("data", []))
        portfolio = pf

    results = []
    for p in portfolio:
        code = p.get("code", p.get("stock_code", ""))
        if not code:
            continue
        summary = parse_auction_summary(code)
        summary["name"] = p.get("name", "")
        results.append(summary)
    return results


# ═══════════════════════════════════════════════════════════════════
#  DB 同步管道 — 检测文件 mtime 变化，增量写入 SQLite
# ═══════════════════════════════════════════════════════════════════

def sync_l2_to_db(code: str, trade_date: str = None) -> dict:
    """
    同步单只股票的 L2 数据到数据库。
    仅当文件 mtime 发生变化时才重新解析，否则秒返。
    """
    from database import (
        init_db, save_l2_tick, save_l2_auction_summary,
        get_l2_sync_state, set_l2_sync_state, get_l2_auction_summary,
    )
    from datetime import datetime

    init_db()

    fname = _code_to_filename(code)
    fpath = L2_DIR / fname
    if not fpath.exists():
        return {"code": code, "status": "no_file", "records": 0}

    file_mtime = fpath.stat().st_mtime
    last_mtime = get_l2_sync_state(code)
    if trade_date is None:
        trade_date = datetime.fromtimestamp(file_mtime).strftime("%Y-%m-%d")

    # 快速路径：文件未变，直接从 DB 返回
    if last_mtime is not None and abs(file_mtime - last_mtime) < 1.0:
        rows = get_l2_auction_summary(code, 1)
        if rows:
            return {"code": code, "status": "cached", "records": rows[0]["tick_count"],
                    **{k: v for k, v in rows[0].items() if k != "tick_count"}}

    # 解析路径：文件有变化或首次同步
    l2 = parse_l2_file(code)
    if not l2 or not l2.records:
        return {"code": code, "status": "empty", "records": 0}

    # 写入逐笔记录
    records = [
        {"marker": r.marker, "seq": r.seq, "price": r.price,
         "volume": r.volume, "direction": r.direction}
        for r in l2.records
    ]
    save_l2_tick(code, trade_date, records)

    # 写入摘要
    tick_records = [r for r in l2.records if r.marker == "Ti"]
    depth_records = [r for r in l2.records if r.marker != "Ti"]
    if tick_records:
        total_vol = sum(r.volume for r in tick_records)
        auction_price = sum(r.price * r.volume for r in tick_records) / total_vol if total_vol > 0 else 0
    elif depth_records:
        auction_price = depth_records[0].price
    else:
        auction_price = 0

    summary = {
        "auction_price": round(auction_price, 2),
        "buy_volume": l2.buy_volume,
        "sell_volume": l2.sell_volume,
        "net_flow": l2.net_flow,
        "buy_ratio": round(l2.buy_ratio, 3),
        "vwap": round(l2.vwap, 2),
        "tick_count": len(tick_records),
        "depth_snapshot_count": len(depth_records),
    }
    save_l2_auction_summary(code, trade_date, summary)

    # 记录同步状态
    set_l2_sync_state(code, file_mtime, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    return {"code": code, "status": "synced", "records": l2.record_count, **summary}


def sync_portfolio_l2(portfolio: list[dict] = None) -> list[dict]:
    """同步全持仓 L2 数据到数据库。"""
    import json
    from pathlib import Path

    if portfolio is None:
        pf = json.loads(Path("D:/1989n/stock_analysis/data/portfolio.json").read_text("utf-8"))
        if isinstance(pf, dict):
            pf = pf.get("holdings", pf.get("data", []))
        portfolio = pf

    results = []
    for p in portfolio:
        code = p.get("code", p.get("stock_code", ""))
        if not code:
            continue
        r = sync_l2_to_db(code)
        r["name"] = p.get("name", "")
        results.append(r)
    return results


if __name__ == "__main__":
    # 测试: 解析 002156 通富微电
    l2 = parse_l2_file("002156")
    if l2:
        print(f"=== 002156 通富微电 L2 数据 ===")
        print(f"总记录: {l2.record_count}")
        print(f"价格: {l2.prices}")
        print(f"买量: {l2.buy_volume} 手")
        print(f"卖量: {l2.sell_volume} 手")
        print(f"净主动买入: {l2.net_flow} 手")
        print(f"买盘占比: {l2.buy_ratio:.1%}")
        print(f"VWAP: {l2.vwap}")
        print(f"时间: {datetime.fromtimestamp(l2.mtime)}")
        print(f"\n前5条记录:")
        for r in l2.records[:5]:
            print(f"  [{r.marker}] #{r.seq} price={r.price} vol={r.volume} dir={r.direction}")

    print("\n=== 全持仓 L2 竞价摘要 ===")
    for s in parse_portfolio_l2():
        print(f"  {s['code']} {s.get('name','')}: "
              f"竞价价={s['auction_price']} "
              f"买{s['buy_volume']}手/卖{s['sell_volume']}手 "
              f"净={s['net_flow']}手 "
              f"买占比={s['buy_ratio']:.1%} "
              f"记录={s['records']}")
