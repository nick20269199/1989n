"""XyStock (AI交易大师) 本地数据库读取器

从 XyStock 的 localmarket_3/ 和 offlinedata2/ 目录读取股票数据。
支持:
  - 股票编码表 (code ↔ 名称)
  - 财务基本面数据 (.fnc)

用法:
  reader = XyStockReader()
  stocks = reader.list_stocks(market='sh')  # 或 'sz' / 'all'
  finance = reader.get_finance('600000')
"""

import struct
import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

# --- Settings ---
XYSTOCK_ROOT = Path(os.environ.get("XYSTOCK_ROOT", "D:/XyStock"))
LOCALMARKET_DIR = XYSTOCK_ROOT / "localmarket_3"
OFFLINEDATA_DIR = XYSTOCK_ROOT / "offlinedata2"


# --- Data Models ---

@dataclass
class StockInfo:
    """一只股票的基本信息（来自 localmarket_3 .bin）"""
    code: str              # 6-digit 股票代码
    market: int            # 市场编号 (1=上海, 1001=深圳)
    market_name: str       # 市场名称 (SH/SZ)
    en_name: str           # 英文名称
    cn_name_simplified: str  # 简体中文名称
    cn_name_traditional: str # 繁体中文名称
    flag: int              # 标志位
    is_index: bool = False # 是否指数


@dataclass
class FinanceData:
    """财务基本面数据（来自 .fnc）"""
    code: str
    market: int
    # 解码后的原始 float 数据
    raw_floats: list = field(default_factory=list)


# --- Market Code Mapping ---
MARKET_MAP = {
    0:    ("SH", "上证指数"),
    1:    ("SH", "上海A股"),
    2:    ("SH", "上海B股"),
    3:    ("SH", "上海基金/ETF"),
    5:    ("SH", "上海债券"),
    7:    ("SH", "科创板"),
    1000: ("SZ", "深证指数"),
    1001: ("SZ", "深圳A股"),
    1002: ("SZ", "中小板"),
    1003: ("SZ", "创业板"),
    1006: ("SZ", "深圳债券"),
    1008: ("SZ", "深圳基金/ETF"),
}


# --- LocalMarket .bin Reader ---

_BIN_HEADER_FMT = "<IIIIIII"  # 28 bytes

def read_localmarket_file(market_code: int) -> dict:
    """读取单个市场 bin 文件，返回 {code: StockInfo}"""
    market_dir = LOCALMARKET_DIR
    bin_path = market_dir / f"{market_code}.bin"
    if not bin_path.exists():
        return {}

    # Fallback: also check without .bin suffix
    if not bin_path.suffix:
        bin_path = market_dir / f"{market_code}"

    with open(bin_path, "rb") as f:
        data = f.read()

    if len(data) < 32:
        return {}

    # 头部: 4*7 = 28 bytes
    header = struct.unpack_from(_BIN_HEADER_FMT, data, 0)
    count_sections = header[3]  # count field

    market_short, _ = MARKET_MAP.get(market_code, ("UNKNOWN", ""))

    result = {}
    pos = 32  # skip 32-byte header

    # Skip the initial string area (market name etc.) — variable length
    # First stock code should be at the first occurrence of a 6-digit code
    # We scan for the pattern: code(6) + len(4) + pad(4) + code(6)
    while pos < len(data):
        # Check if this looks like a valid record start: 6 ASCII digits
        segment = data[pos:pos+6]
        if len(segment) < 6:
            break
        try:
            code_str = segment.decode("ascii")
            if code_str.isdigit() and len(code_str) == 6:
                # Found a stock code — try to parse record
                rec = _parse_stock_record(data, pos, market_code, market_short)
                if rec and rec.code not in result:
                    result[rec.code] = rec
                    # Skip to next record
                    # Find next 6-digit code after this record
                    pos += 1
                    continue
        except (UnicodeDecodeError, ValueError):
            pass
        pos += 1

    return result


def _parse_stock_record(data: bytes, start: int, market_code: int, market_short: str) -> Optional[StockInfo]:
    """Parse a single stock record starting at `start`."""
    try:
        code_str = data[start:start+6].decode("ascii")
    except (UnicodeDecodeError, IndexError):
        return None
    if not code_str.isdigit() or len(code_str) != 6:
        return None

    # Layout: code(6) + code_len(4) + pad(4) + code_again(6) + en_name_len(4) + pad(4)
    pos = start + 20
    if pos + 8 > len(data):
        return None
    en_name_len = struct.unpack_from("<I", data, pos)[0]
    pos += 8

    if en_name_len > 0 and pos + en_name_len <= len(data):
        en_name = data[pos:pos+en_name_len].decode("utf-8", errors="replace").rstrip("\x00")
        pos += en_name_len
    else:
        en_name = ""

    # Skip inter-field zeros (padding), then find Chinese name fields
    cn_name_s = ""
    cn_name_t = ""
    flag = 0
    cn_count = 0

    while pos < len(data) - 12:
        # skip zeros
        while pos < len(data) and data[pos] == 0:
            pos += 1
        if pos + 8 > len(data):
            break
        name_len = struct.unpack_from("<I", data, pos)[0]
        if name_len == 0 or name_len > 300:
            break
        pos += 8
        if pos + name_len > len(data):
            break
        try:
            name_str = data[pos:pos+name_len].decode("utf-8", errors="replace").rstrip("\x00")
        except:
            break
        if not name_str:
            break
        if cn_count == 0:
            cn_name_s = name_str
        elif cn_count == 1:
            cn_name_t = name_str
        else:
            break
        cn_count += 1
        pos += name_len

    # Find flag: small uint after names section
    while pos < len(data) - 4:
        candidate = struct.unpack_from("<I", data, pos)[0]
        if 0 < candidate < 100:
            flag = candidate
            break
        pos += 1

    return StockInfo(
        code=code_str,
        market=market_code,
        market_name=market_short,
        en_name=en_name,
        cn_name_simplified=cn_name_s,
        cn_name_traditional=cn_name_t,
        flag=flag,
        is_index=market_code in (0, 1000),
    )


# --- Finance .fnc Reader ---

_FNC_HEADER_FMT = "<HHHHI"  # file_size(2) + field2(2) + field3(2) + market(2) + code_bytes(6)

def read_finance_file(stock_code: str) -> Optional[FinanceData]:
    """Read .fnc financial data for a stock.

    .fnc 文件结构:
      [0-1]  file_size  (uint16)
      [2-3]  field2     (uint16, usually 0x0027=39)
      [4-5]  field3     (uint16, usually 1)
      [6-7]  market_code (uint16)
      [8-13] stock_code  (6 bytes ASCII)
      [14-23] padding
      [24+]  data section (mixed types)
    """
    # Determine market from code prefix
    if stock_code.startswith("6"):
        market_dir = "1"
    elif stock_code.startswith("0") or stock_code.startswith("3"):
        market_dir = "1001"
    elif stock_code.startswith("00"):
        market_dir = "2"
    elif stock_code.startswith("688"):
        market_dir = "7"
    else:
        return None

    fnc_path = OFFLINEDATA_DIR / market_dir / "finance" / f"{market_dir}_{stock_code}.fnc"
    if not fnc_path.exists():
        return None

    with open(fnc_path, "rb") as f:
        data = f.read()

    if len(data) < 24:
        return None

    file_size = struct.unpack_from("<H", data, 0)[0]
    market_code = struct.unpack_from("<H", data, 6)[0]
    code_raw = data[8:14].decode("ascii", errors="replace").strip("\x00")

    # Extract financial indicator floats from the tail of the data.
    # Last 20 bytes = 5 float32 values: [?, ?, PE, ?, PE_repeated]
    # PE ratio is always at position [-1] (last 4 bytes).
    floats = []
    tail_start = len(data) - 20
    if tail_start < 24:
        tail_start = 24
    for off in range(0, 20, 4):
        flt = struct.unpack_from("<f", data, tail_start + off)[0]
        floats.append(flt)

    return FinanceData(
        code=code_raw or stock_code,
        market=market_code,
        raw_floats=floats,
    )


# --- High-level API ---

class XyStockReader:
    """XyStock 本地数据库统一读取器"""

    def __init__(self, xy_root: str = None):
        global XYSTOCK_ROOT, LOCALMARKET_DIR, OFFLINEDATA_DIR
        if xy_root:
            XYSTOCK_ROOT = Path(xy_root)
            LOCALMARKET_DIR = XYSTOCK_ROOT / "localmarket_3"
            OFFLINEDATA_DIR = XYSTOCK_ROOT / "offlinedata2"
        self._by_code: dict[str, StockInfo] = {}
        self._by_market: dict[int, dict[str, StockInfo]] = {}
        self._loaded = False

    def list_stocks(self, market: str = "all") -> list[StockInfo]:
        if not self._loaded:
            self._load_all()
        if market == "sh":
            return list(self._by_market.get(1, {}).values())
        elif market == "sz":
            return list(self._by_market.get(1001, {}).values())
        elif market == "star":
            return list(self._by_market.get(7, {}).values())
        elif market == "chinet":
            return list(self._by_market.get(1003, {}).values())
        else:
            result = []
            for m in self._by_market.values():
                result.extend(m.values())
            return result

    def get_stock(self, code: str) -> Optional[StockInfo]:
        if not self._loaded:
            self._load_all()
        return self._by_code.get(code)

    def get_finance(self, code: str) -> Optional[FinanceData]:
        return read_finance_file(code)

    def _load_all(self):
        for market_code in [1, 1001, 1002, 1003, 1008, 7, 0, 1000]:
            stocks = read_localmarket_file(market_code)
            self._by_market[market_code] = stocks
            for code, info in stocks.items():
                self._by_code[code] = info
        self._loaded = True

    def search_by_name(self, keyword: str) -> list[StockInfo]:
        if not self._loaded:
            self._load_all()
        seen = set()
        results = []
        for stocks in self._by_market.values():
            for s in stocks.values():
                if keyword in s.cn_name_simplified or keyword in s.cn_name_traditional:
                    key = (s.code, s.market)
                    if key not in seen:
                        seen.add(key)
                        results.append(s)
        return results

    def count_by_market(self) -> dict:
        if not self._loaded:
            self._load_all()
        return {m: len(self._by_market[m]) for m in sorted(self._by_market)}


# --- Quick test ---
if __name__ == "__main__":
    import json

    reader = XyStockReader()

    print("=" * 60)
    print("XyStock 本地数据库读取器 — 测试")
    print("=" * 60)

    # 统计各市场
    counts = reader.count_by_market()
    print(f"\n各市场股票数量: {counts}")
    total = sum(counts.values())
    print(f"总计: {total} 只")

    # 查特定股票
    for code in ["600000", "000001", "688981"]:
        s = reader.get_stock(code)
        if s:
            print(f"\n{s.code} ({s.market_name}): {s.cn_name_simplified}")
            print(f"  EN: {s.en_name}")
            print(f"  CN trad: {s.cn_name_traditional}")
            print(f"  Flag: {s.flag}")

            # 查财务
            fin = reader.get_finance(code)
            if fin:
                print(f"  财务数据: {len(fin.raw_floats)} floats")
                print(f"    后5项: {[f'{v:.2f}' for v in fin.raw_floats[-6:] if abs(v) < 1e6]}")

    # 搜索
    print("\n搜索 '银行':")
    for s in reader.search_by_name("银行")[:5]:
        print(f"  {s.code} {s.cn_name_simplified} ({s.market_name})")
