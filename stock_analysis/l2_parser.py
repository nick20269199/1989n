"""
东方财富 Level-2 本地 .dat 文件解析器
=====================================
解析 D:/东方财富/dfcf/data/STOCK/ 下的 L2 逐笔成交数据。

支持两种格式:
  A. DealL2File (逐笔成交 — 17字节/记录):
     文件头: 16 bytes
     记录:   17 bytes × N
       [0:4]   时间 HHMMSS (uint32, 如 092500 = 9:25:00)
       [4:8]   序号 (uint32)
       [8:12]  价格 × 1000 (uint32)
       [12:16] 成交量/股 (uint32)
       [16]    方向 (1=买, 2=卖, 3=中性)

  B. TickData (分时成交 — 14字节/记录):
     文件头: 16 bytes
     记录:   14 bytes × N
       [0]     时 BCD (如 0x09=9)
       [1]     分 BCD (如 0x25=25)
       [2]     秒 BCD (高半字节可能含标记)
       [3]     子秒/标记
       [4:8]   价格 × 1000 (uint32 LE)
       [8:12]  成交量/股 (uint32 LE)
       [12]    标记
       [13]    方向 (0=卖, 1=买, 其他=中性) ← 置信度低于 DealL2File

校验规则:
  1. 解析结果必须与已知基准交叉验证 (如 push2 API 开盘价 vs L2 竞价价)
  2. 价格/成交量必须落在合理区间 (价格>0, 量>0)
  3. 时间值必须合法 (HHMMSS 解码后 0<=H<24, 0<=M<60, 0<=S<60)
"""
import struct
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

L2_DIR = Path("D:/东方财富/dfcf/data/STOCK/DealL2File")
TICK_DIR = Path("D:/东方财富/dfcf/data/STOCK/TickData")

# 竞价时间窗口
AUCTION_MORNING_START = 91500   # 9:15:00
AUCTION_MORNING_END   = 92500   # 9:25:00
AUCTION_AFTER_START   = 145700  # 14:57:00 (深市尾盘竞价)
AUCTION_AFTER_END     = 150000  # 15:00:00


def _decode_time(t: int) -> str:
    """HHMMSS uint32 → 'HH:MM:SS' 字符串。"""
    h = t // 10000
    m = (t % 10000) // 100
    s = t % 100
    return f"{h:02d}:{m:02d}:{s:02d}"


def _is_valid_time(t: int) -> bool:
    """校验 HHMMSS 值合法。"""
    h = t // 10000
    m = (t % 10000) // 100
    s = t % 100
    return 0 <= h < 24 and 0 <= m < 60 and 0 <= s < 60


def _is_auction_time(t: int) -> bool:
    """判断时间是否落在竞价窗口内。"""
    return (AUCTION_MORNING_START <= t <= AUCTION_MORNING_END or
            AUCTION_AFTER_START <= t <= AUCTION_AFTER_END)


def _bcd_byte(b: int) -> int:
    """BCD 字节 → 十进制: 0x25 → 25, 0x09 → 9"""
    return ((b >> 4) & 0x0F) * 10 + (b & 0x0F)


def _bcd_to_hhmmss(b0: int, b1: int, b2: int) -> int:
    """BCD时/分/秒 → HHMMSS int: (0x09, 0x25, 0x06) → 92506"""
    return _bcd_byte(b0) * 10000 + _bcd_byte(b1) * 100 + _bcd_byte(b2)


@dataclass
class L2Record:
    seq: int
    trade_time: int    # HHMMSS 格式, 如 092500
    price: float       # 元
    volume: int        # 股
    direction: int     # 1=买 2=卖 3=中性


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
        return self.buy_volume - self.sell_volume

    @property
    def buy_ratio(self) -> float:
        total = self.buy_volume + self.sell_volume
        return self.buy_volume / total if total > 0 else 0

    @property
    def time_range(self) -> tuple:
        """返回 (最早时间, 最晚时间) 的 HHMMSS 元组。"""
        times = [r.trade_time for r in self.records if r.trade_time > 0]
        return (min(times), max(times)) if times else (0, 0)

    @property
    def auction_records(self) -> list:
        """竞价时段 (9:15-9:25, 14:57-15:00) 的记录。"""
        return [r for r in self.records if _is_auction_time(r.trade_time)]

    @property
    def auction_buy_volume(self) -> int:
        return sum(r.volume for r in self.auction_records if r.direction == 1)

    @property
    def auction_sell_volume(self) -> int:
        return sum(r.volume for r in self.auction_records if r.direction == 2)

    @property
    def auction_neutral_volume(self) -> int:
        """竞价撮合中性盘 (方向=3) 的成交量，通常发生在 09:25 集合竞价撮合价。"""
        return sum(r.volume for r in self.auction_records if r.direction == 3)

    @property
    def auction_net_flow(self) -> int:
        return self.auction_buy_volume - self.auction_sell_volume

    @property
    def auction_buy_ratio(self) -> float:
        total = self.auction_buy_volume + self.auction_sell_volume
        return self.auction_buy_volume / total if total > 0 else 0

    @property
    def has_directional_auction(self) -> bool:
        """是否包含方向性 (买/卖) 竞价数据，而非纯中性撮合。"""
        return self.auction_buy_volume + self.auction_sell_volume > 0

    def validate(self) -> list[str]:
        """自校验: 返回发现的问题列表。"""
        issues = []
        if not self.records:
            issues.append("无记录")
            return issues

        # 时间合法性
        bad_times = [r.trade_time for r in self.records
                     if not _is_valid_time(r.trade_time)]
        if bad_times:
            issues.append(f"{len(bad_times)} 条记录时间不合法: {bad_times[:5]}")

        # 价格合法性
        bad_prices = [r.price for r in self.records
                      if r.price <= 0 or r.price > 10000]
        if bad_prices:
            issues.append(f"{len(bad_prices)} 条记录价格异常: {bad_prices[:5]}")

        # 方向合法性
        bad_dirs = [r.direction for r in self.records
                    if r.direction not in (1, 2, 3)]
        if bad_dirs:
            issues.append(f"{len(bad_dirs)} 条记录方向字段异常: {bad_dirs[:5]}")

        # 成交量合法性
        zero_vol = sum(1 for r in self.records if r.volume == 0)
        if zero_vol > len(self.records) * 0.5:
            issues.append(f"超过半数记录成交量为零 ({zero_vol}/{len(self.records)})")

        return issues


def _code_to_filename(code: str) -> str:
    """002156 → 0_002156.dat, 600498 → 1_600498.dat"""
    prefix = "1" if code.startswith("6") else "0"
    return f"{prefix}_{code}.dat"


def parse_tickdata_file(code: str) -> Optional[L2File]:
    """解析单只股票的分时成交 TickData 文件 (14字节记录, BCD时间)。"""
    fname = _code_to_filename(code)
    fpath = TICK_DIR / fname
    if not fpath.exists():
        return None

    data = fpath.read_bytes()
    if len(data) < 16:
        return None

    count = struct.unpack("<I", data[8:12])[0]
    if count <= 0 or count > 1000000:
        return None

    stat = fpath.stat()
    result = L2File(code=code, path=fpath, mtime=stat.st_mtime)

    offset = 16
    parsed = 0
    while offset + 14 <= len(data) and parsed < count:
        chunk = data[offset:offset + 14]
        trade_time = _bcd_to_hhmmss(chunk[0], chunk[1], chunk[2])
        if not _is_valid_time(trade_time):
            offset += 14
            parsed += 1
            continue
        price_raw = struct.unpack("<I", chunk[4:8])[0]
        volume = struct.unpack("<I", chunk[8:12])[0]
        flag = chunk[13]
        if flag == 1:
            direction = 1
        elif flag == 0:
            direction = 2
        else:
            direction = 3

        if price_raw == 0 and volume == 0:
            offset += 14
            parsed += 1
            continue

        result.records.append(L2Record(
            seq=parsed,
            trade_time=trade_time,
            price=price_raw / 1000,
            volume=volume,
            direction=direction,
        ))
        offset += 14
        parsed += 1

    return result


def _parse_deall2_file(code: str) -> Optional[L2File]:
    """解析 DealL2File 格式 (17字节记录, HHMMSS时间)。"""
    fname = _code_to_filename(code)
    fpath = L2_DIR / fname
    if not fpath.exists():
        return None

    data = fpath.read_bytes()
    if len(data) < 16:
        return None

    stat = fpath.stat()
    result = L2File(code=code, path=fpath, mtime=stat.st_mtime)

    offset = 16
    while offset + 17 <= len(data):
        chunk = data[offset:offset + 17]
        trade_time = struct.unpack("<I", chunk[0:4])[0]
        seq = struct.unpack("<I", chunk[4:8])[0]
        price_raw = struct.unpack("<I", chunk[8:12])[0]
        volume = struct.unpack("<I", chunk[12:16])[0]
        direction = chunk[16]

        if price_raw == 0 and volume == 0:
            offset += 17
            continue

        result.records.append(L2Record(
            seq=seq,
            trade_time=trade_time,
            price=price_raw / 1000,
            volume=volume,
            direction=direction,
        ))
        offset += 17

    return result


def parse_l2_file(code: str) -> Optional[L2File]:
    """
    解析单只股票的 L2 逐笔成交数据。
    优先 DealL2File (17字节逐笔)，若不存在则回退到 TickData (14字节分时)。
    """
    result = _parse_deall2_file(code)
    if result and result.records:
        return result
    return parse_tickdata_file(code)


def parse_auction_summary(code: str) -> dict:
    """
    解析竞价期间的 L2 数据摘要。
    按时间窗口 (9:15-9:25) 筛选，而非依赖特定标记值。
    """
    l2 = parse_l2_file(code)
    if not l2 or not l2.records:
        return {"code": code, "records": 0, "error": "无 L2 数据"}

    # 自校验
    issues = l2.validate()
    if issues:
        # 有严重问题时仍然返回，但标注警告
        pass

    auction = l2.auction_records
    if not auction:
        auction = l2.records  # 无竞价窗口数据时回退到全部

    # 成交量加权竞价价
    total_vol = sum(r.volume for r in auction)
    if total_vol > 0:
        auction_price = sum(r.price * r.volume for r in auction) / total_vol
    else:
        auction_price = auction[0].price if auction else 0

    non_auction = [r for r in l2.records if not _is_auction_time(r.trade_time)]

    return {
        "code": code,
        "records": l2.record_count,
        "auction_records": len(auction),
        "continuous_records": len(non_auction),
        "auction_price": round(auction_price, 2),
        "buy_volume": l2.auction_buy_volume,
        "sell_volume": l2.auction_sell_volume,
        "neutral_volume": l2.auction_neutral_volume,
        "net_flow": l2.auction_net_flow,
        "buy_ratio": round(l2.auction_buy_ratio, 3),
        "has_directional": l2.has_directional_auction,
        "vwap": round(l2.vwap, 2),
        "prices": sorted(l2.prices),
        "time_range": f"{_decode_time(l2.time_range[0])} ~ {_decode_time(l2.time_range[1])}",
        "file_mtime": datetime.fromtimestamp(l2.mtime).strftime("%Y-%m-%d %H:%M:%S"),
        "warnings": issues if issues else None,
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
    from datetime import datetime as dt

    init_db()

    fname = _code_to_filename(code)
    fpath_deal = L2_DIR / fname
    fpath_tick = TICK_DIR / fname
    fpath = fpath_deal if fpath_deal.exists() else (fpath_tick if fpath_tick.exists() else None)
    if not fpath:
        return {"code": code, "status": "no_file", "records": 0}

    file_mtime = fpath.stat().st_mtime
    data_source = "deall2" if fpath == fpath_deal else "tickdata"
    last_mtime = get_l2_sync_state(code)
    if trade_date is None:
        trade_date = dt.fromtimestamp(file_mtime).strftime("%Y-%m-%d")

    # 快速路径：文件未变，直接从 DB 返回
    if last_mtime is not None and abs(file_mtime - last_mtime) < 1.0:
        rows = get_l2_auction_summary(code, 1)
        if rows:
            r = rows[0]
            return {"code": code, "status": "cached",
                    "records": r.get("tick_count", 0),
                    "auction_price": r.get("auction_price"),
                    "buy_volume": r.get("buy_volume"),
                    "sell_volume": r.get("sell_volume"),
                    "neutral_volume": r.get("neutral_volume", 0),
                    "net_flow": r.get("net_flow"),
                    "buy_ratio": r.get("buy_ratio"),
                    "vwap": r.get("vwap"),
                    "has_directional": bool(r.get("has_directional", 1)),
                    "trade_date": r.get("trade_date")}

    # 解析路径
    l2 = parse_l2_file(code)
    if not l2 or not l2.records:
        return {"code": code, "status": "empty", "records": 0}

    # 自校验
    issues = l2.validate()
    if issues:
        for issue in issues:
            pass  # 后续可接入日志/告警

    # 写入逐笔记录
    records = [
        {"trade_time": r.trade_time, "seq": r.seq, "price": r.price,
         "volume": r.volume, "direction": r.direction}
        for r in l2.records
    ]
    save_l2_tick(code, trade_date, records)

    # 写入竞价摘要
    summary = parse_auction_summary(code)
    save_l2_auction_summary(code, trade_date, {
        "auction_price": summary["auction_price"],
        "buy_volume": summary["buy_volume"],
        "sell_volume": summary["sell_volume"],
        "neutral_volume": summary.get("neutral_volume", 0),
        "net_flow": summary["net_flow"],
        "buy_ratio": summary["buy_ratio"],
        "vwap": summary["vwap"],
        "tick_count": summary["auction_records"],
        "depth_snapshot_count": summary["continuous_records"],
        "has_directional": summary.get("has_directional", True),
    })

    set_l2_sync_state(code, file_mtime, dt.now().strftime("%Y-%m-%d %H:%M:%S"))

    return {"code": code, "status": "synced", "records": l2.record_count,
            "auction_price": summary["auction_price"],
            "buy_volume": summary["buy_volume"],
            "sell_volume": summary["sell_volume"],
            "neutral_volume": summary.get("neutral_volume", 0),
            "net_flow": summary["net_flow"],
            "buy_ratio": summary["buy_ratio"],
            "vwap": summary["vwap"],
            "has_directional": summary.get("has_directional", True),
            "warnings": issues if issues else None}


def sync_portfolio_l2(portfolio: list[dict] = None) -> list[dict]:
    """同步全持仓 L2 数据到数据库。"""
    import json
    from pathlib import Path as _Path

    if portfolio is None:
        pf = json.loads(_Path("D:/1989n/stock_analysis/data/portfolio.json").read_text("utf-8"))
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


# ═══════════════════════════════════════════════════════════════════
#  交叉验证
# ═══════════════════════════════════════════════════════════════════

def cross_check_auction_price(code: str, push2_price: float = None) -> dict:
    """
    交叉验证 L2 竞价价 vs push2 API 竞价价。
    如果 push2_price 未提供，则仅返回 L2 数据。
    偏差超过 1% 视为异常。
    """
    summary = parse_auction_summary(code)
    result = {
        "code": code,
        "l2_auction_price": summary.get("auction_price"),
        "l2_records": summary.get("records"),
        "warnings": summary.get("warnings"),
    }
    if push2_price is not None and push2_price > 0:
        l2p = summary.get("auction_price", 0)
        if l2p > 0:
            deviation = abs(l2p - push2_price) / push2_price
            result["push2_price"] = push2_price
            result["deviation"] = round(deviation, 4)
            result["match"] = deviation < 0.01
    return result


if __name__ == "__main__":
    # 测试: 解析 002156 通富微电
    l2 = parse_l2_file("002156")
    if l2:
        print(f"=== 002156 通富微电 L2 数据 ===")
        print(f"总记录: {l2.record_count}")
        print(f"时间范围: {_decode_time(l2.time_range[0])} ~ {_decode_time(l2.time_range[1])}")
        print(f"竞价记录: {len(l2.auction_records)}")
        print(f"竞价买量: {l2.auction_buy_volume} 股")
        print(f"竞价卖量: {l2.auction_sell_volume} 股")
        print(f"竞价净流向: {l2.auction_net_flow} 股")
        print(f"竞价买盘占比: {l2.auction_buy_ratio:.1%}")
        print(f"全量VWAP: {l2.vwap}")
        print(f"校验: {l2.validate() or '通过'}")
        print(f"\n前5条记录:")
        for r in l2.records[:5]:
            print(f"  {_decode_time(r.trade_time)} #{r.seq} price={r.price} vol={r.volume} dir={r.direction}")

    print("\n=== 全持仓 L2 竞价摘要 ===")
    for s in parse_portfolio_l2():
        print(f"  {s['code']} {s.get('name','')}: "
              f"竞价价={s['auction_price']} "
              f"买{s['buy_volume']}/卖{s['sell_volume']} "
              f"净={s['net_flow']} "
              f"买占比={s['buy_ratio']:.1%} "
              f"竞价{s['auction_records']}条/连续{s['continuous_records']}条 "
              f"时间={s['time_range']}")
