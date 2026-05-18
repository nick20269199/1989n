#!/usr/bin/env python3
"""
market_pool.cli — 命令行入口

用法:
  python -m market_pool.cli update                  # 全市场增量更新
  python -m market_pool.cli update --watch           # 仅更新持仓
  python -m market_pool.cli quote 002156             # 查询持仓行情
  python -m market_pool.cli kline 002156             # 查询K线(最近60天)
  python -m market_pool.cli indices                  # 指数行情
  python -m market_pool.cli stats                    # 数据池状态
  python -m market_pool.cli check                    # 通道健康检查
"""
import json
import logging
import sys
from datetime import datetime

from .pool import MarketPool


def setup_logging(verbose=False):
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(level=level, format=fmt, datefmt="%H:%M:%S")


def cmd_update(args):
    pool = MarketPool()
    days = int(args.get("--days", "5"))
    if args.get("--watch"):
        result = pool.update_watchlist(days=days)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        workers = int(args.get("--workers", "15"))
        result = pool.update_all(days=days, workers=workers)
        print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_quote(args):
    codes = args.get("_extra", [])
    if not codes:
        pool = MarketPool()
        codes = pool._watchlist_codes()
    pool = MarketPool()
    quotes = pool.refresh_quotes(codes)
    print(json.dumps(quotes, ensure_ascii=False, indent=2, default=str))


def cmd_kline(args):
    codes = args.get("_extra", [])
    days = int(args.get("--days", "60"))
    pool = MarketPool()
    for code in codes:
        df = pool.get_kline(code, days)
        if df is not None:
            print(f"\n=== {code} (最近{min(days, len(df))}天) ===")
            print(df.tail(min(days, len(df))).to_string(index=False))
        else:
            print(f"{code}: 无数据")


def cmd_indices(args):
    pool = MarketPool()
    indices = pool.get_indices()
    print(json.dumps(indices, ensure_ascii=False, indent=2))


def cmd_stats(args):
    pool = MarketPool()
    stats = pool.stats()
    print(f"数据池: {stats['stored_count']} 只K线已缓存")
    print(f"  元数据: {stats['meta_count']} 只")
    print(f"  磁盘: {stats['size_mb']:.1f} MB")
    print(f"  持仓: {stats['watchlist_count']} 只")


def cmd_import_tdx(args):
    """从通达信导入日线数据到本地缓存"""
    from .tdx_loader import import_tdx_to_pool
    workers = int(args.get("--workers", "8"))
    result = import_tdx_to_pool(workers=workers)
    print(f"通达信导入完成: {result['imported']}/{result['total']} 只导入, "
          f"{result['skipped']} 只跳过, {result['failed']} 只失败")
    return result


def cmd_check(args):
    """通道健康检查"""
    from .fetcher import fetch_quotes, fetch_kline, fetch_indices
    channels = {}

    # 实时行情
    try:
        q = fetch_quotes(["000001"])
        channels["quotes"] = "000001" in q
    except Exception:
        channels["quotes"] = False

    # K线
    try:
        k = fetch_kline("000001", 5)
        channels["kline"] = k is not None
    except Exception:
        channels["kline"] = False

    # 指数
    try:
        ind = fetch_indices()
        channels["indices"] = len(ind) > 0
    except Exception:
        channels["indices"] = False

    print(json.dumps(channels, indent=2))
    all_ok = all(channels.values())
    print(f"\n状态: {'✅ 全部正常' if all_ok else '❌ 有异常'}")
    return all_ok


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return

    verbose = "-v" in args or "--verbose" in args
    setup_logging(verbose)

    cmd = args[0]
    params = {"_extra": []}
    i = 1
    while i < len(args):
        a = args[i]
        if a.startswith("--"):
            if i + 1 < len(args) and not args[i + 1].startswith("--"):
                params[a] = args[i + 1]
                i += 2
            else:
                params[a] = True
                i += 1
        else:
            params["_extra"].append(a)
            i += 1

    commands = {
        "update": cmd_update,
        "quote": cmd_quote,
        "kline": cmd_kline,
        "indices": cmd_indices,
        "stats": cmd_stats,
        "check": cmd_check,
        "import-tdx": cmd_import_tdx,
    }
    fn = commands.get(cmd)
    if fn:
        fn(params)
    else:
        print(f"未知命令: {cmd}")
        print(__doc__)


if __name__ == "__main__":
    main()
