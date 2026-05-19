"""TDX Base DBF reader — local financial data, zero network.

Reads D:/TDX/T0002/hq_cache/base.dbf for:
  - Total shares, tradable shares
  - Total assets, net assets
  - Main revenue, net profit
  - EPS, net asset per share
  - Industry code
  - Listing date
"""

import struct
from pathlib import Path
from typing import Optional

DBF_PATH = Path("D:/TDX/T0002/hq_cache/base.dbf")
TDX_BASE = Path("D:/TDX")

# TDX numeric HY code → industry name (deduced from known stocks)
INDUSTRY_MAP = {
    "1": "金融", "2": "传媒", "3": "钢铁", "4": "化工",
    "5": "石油石化", "6": "基础化工", "7": "汽车", "8": "交通运输",
    "9": "食品饮料", "10": "纺织服装", "11": "房地产", "12": "医药生物",
    "13": "轻工制造", "14": "食品饮料", "15": "休闲服务",
    "16": "公用事业", "17": "农林牧渔", "18": "综合",
    "19": "建筑材料", "20": "煤炭", "21": "建筑装饰",
    "22": "建筑材料", "23": "家用电器", "24": "信息技术",
    "25": "国防军工", "26": "机械设备", "27": "医药生物",
    "28": "电子", "29": "通信", "30": "电力设备",
    "31": "环保", "32": "商业贸易", "33": "国防军工",
    "34": "商贸零售", "35": "电子", "36": "有色金属",
    "37": "食品饮料", "38": "国防军工", "39": "医药生物",
    "40": "汽车零部件", "41": "电力设备", "42": "商贸零售",
    "43": "电力设备", "44": "纺织服装", "45": "综合",
    "46": "有色金属", "47": "医药生物", "48": "建筑材料",
    "49": "房地产", "50": "综合", "51": "计算机",
    "52": "国防军工", "53": "综合",
}

_dbf_cache: Optional[dict] = None

# DBF field definitions for base.dbf
FIELDS = [
    ("SC", "C", 1),       # market (0=shenzhen, 1=shanghai)
    ("GPDM", "C", 6),     # stock code
    ("GXRQ", "N", 8),     # update date (YYYYMMDD)
    ("ZGB", "N", 14),     # total shares (万股)
    ("GJG", "N", 14),     # 高管股
    ("FQRFRG", "N", 14),  #
    ("FRG", "N", 14),     #
    ("BG", "N", 14),      # B股
    ("HG", "N", 14),      # H股
    ("LTAG", "N", 14),    # tradable A shares (万股)
    ("ZGG", "N", 14),     # 最高价?
    ("ZPG", "N", 14),     # 最低价?
    ("ZZC", "N", 14),     # total assets (总资产, 万元)
    ("LDZC", "N", 14),    # current assets (流动资产)
    ("GDZC", "N", 14),    # fixed assets (固定资产)
    ("WXZC", "N", 14),    # intangible assets (无形资产)
    ("CQTZ", "N", 14),    # long-term investments (长期投资)
    ("LDFZ", "N", 14),    # current liabilities (流动负债)
    ("CQFZ", "N", 14),    # long-term liabilities (长期负债)
    ("ZBGJJ", "N", 14),   # 资本公积金
    ("JZC", "N", 14),     # net assets (净资产, 万元)
    ("ZYSY", "N", 14),    # main revenue (主营业务收入, 万元)
    ("ZYLY", "N", 14),    # main profit (主营业务利润)
    ("QTLY", "N", 14),    # other profit (其它利润)
    ("YYLY", "N", 14),    # operating profit (营业利润)
    ("TZSY", "N", 14),    # investment income (投资收益)
    ("BTSY", "N", 14),    # non-recurring income (补贴收入)
    ("YYWSZ", "N", 14),   # non-operating income (营业外收支)
    ("SNSYTZ", "N", 14),  # income tax (所得税)
    ("LYZE", "N", 14),    # profit before tax (利润总额)
    ("SHLY", "N", 14),    # minority interest (少数利润)
    ("JLY", "N", 14),     # net profit (净利润, 万元)
    ("WFPLY", "N", 14),   # 未分配利润
    ("TZMGJZ", "N", 14),  # net asset per share (每股净资产, 元)
    ("DY", "C", 3),       # dividend (分红?)
    ("HY", "C", 4),       # industry code
    ("ZBNB", "N", 2),     # 指标年份?
    ("SSDATE", "C", 8),   # listing date (YYYYMMDD)
    ("MODIDATE", "C", 6), # modify date
    ("GDRS", "N", 8),     # shareholder count (股东人数)
]


def read_dbf(path: Path = DBF_PATH) -> dict[str, dict]:
    """Read base.dbf, return dict of {code: {field: value}}.

    Cached in memory after first read (file is read-only 116KB, fast).
    """
    global _dbf_cache
    if _dbf_cache is not None and path == DBF_PATH:
        return _dbf_cache

    if not path.exists():
        return {}

    data = path.read_bytes()

    # DBF header
    num_records = struct.unpack("<I", data[4:8])[0]
    header_len = struct.unpack("<H", data[8:10])[0]
    rec_len = struct.unpack("<H", data[10:12])[0]

    result = {}
    offset = header_len
    for _ in range(num_records):
        if offset + rec_len > len(data):
            break
        rec = data[offset : offset + rec_len]
        offset += rec_len

        deleted = rec[0]
        if deleted != 0x20:  # space = active, * = deleted
            continue

        stock = _parse_record(rec)
        if stock:
            result[stock["GPDM"]] = stock

    if path == DBF_PATH:
        _dbf_cache = result
    return result


def _parse_record(rec: bytes) -> Optional[dict]:
    """Parse a single DBF record into a dict."""
    stock = {}
    pos = 1  # skip deleted flag
    for name, ftype, flen in FIELDS:
        if pos + flen > len(rec):
            break
        raw = rec[pos : pos + flen]
        pos += flen

        if ftype == "C":
            val = raw.rstrip(b"\x00").rstrip().decode("gbk", errors="ignore").strip()
        elif ftype == "N":
            val = raw.decode("ascii", errors="ignore").strip()
            if val:
                is_float = "." in val
                val = float(val) if is_float else int(val)
            else:
                val = None
        else:
            val = None

        stock[name] = val

    return stock


def get_financial_metrics(code: str) -> dict:
    """Get key financial metrics for a single stock code.

    Returns human-readable dict with computed ratios.
    """
    all_data = read_dbf()
    raw = all_data.get(code)
    if not raw:
        return {}

    zzc = raw.get("ZZC") or 0
    jzc = raw.get("JZC") or 0
    jly = raw.get("JLY") or 0
    zysy = raw.get("ZYSY") or 0
    ltag = raw.get("LTAG") or 0  # tradable shares in 万股
    zgb = raw.get("ZGB") or 0  # total shares in 万股
    hy_code = str(raw.get("HY", "") or "").strip()

    metrics = {
        "total_assets_wan": round(zzc, 2) if zzc else None,       # 总资产(万元)
        "net_assets_wan": round(jzc, 2) if jzc else None,         # 净资产(万元)
        "net_profit_wan": round(jly, 2) if jly else None,         # 净利润(万元)
        "main_revenue_wan": round(zysy, 2) if zysy else None,     # 主营收入(万元)
        "net_asset_per_share": raw.get("TZMGJZ"),                 # 每股净资产(元)
        "tradable_shares_wan": ltag,                              # 流通股(万股)
        "total_shares_wan": zgb,                                  # 总股本(万股)
        "industry_code": hy_code,                                 # 行业代码
        "industry_name": INDUSTRY_MAP.get(hy_code, "未知"),       # 行业名称
        "listing_date": raw.get("SSDATE"),                        # 上市日期
        "shareholders": raw.get("GDRS"),                          # 股东人数
    }

    # Computed ratios
    if zgb and zgb > 0:
        metrics["tradable_ratio"] = round(ltag / zgb, 4) if ltag else None
    if jzc and jzc > 0 and jly is not None:
        metrics["roe"] = round(jly / jzc, 4)  # return on equity
    if zysy and zysy > 0 and jly is not None:
        metrics["net_margin"] = round(jly / zysy, 4)

    return metrics


if __name__ == "__main__":
    import sys
    code = sys.argv[1] if len(sys.argv) > 1 else "002156"
    m = get_financial_metrics(code)
    if m:
        print(f"Financial Metrics for {code}:")
        for k, v in m.items():
            print(f"  {k}: {v}")
    else:
        print(f"No data for {code}")
