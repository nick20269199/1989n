"""
StratEvo Wrapper — 遗传算法策略分析
======================================
集成: 2026-05-12
用途: 对持仓/观察池进行多策略分析(Value Seeker/Momentum Rider/Mean Reverter共识投票)

安装: pip install stratevo
依赖: yfinance (pip install yfinance)

用法:
  python stratevo_wrapper.py 002156.SZ          # 单票分析
  python stratevo_wrapper.py --watchlist         # 全部持仓分析
  python stratevo_wrapper.py --mcp               # 启动MCP Server
"""

import subprocess
import sys
import json
from pathlib import Path

HOLDINGS = [
    "002156.SZ",  # 通富微电
    "300480.SZ",  # 光力科技
    "002407.SZ",  # 多氟多
    "300342.SZ",  # 天银机电
    "300739.SZ",  # 明阳电路
    "601789.SS",  # 宁波建工
    "600236.SS",  # 桂冠电力
]


def analyze_one(ticker: str) -> dict:
    """运行 StratEvo analyze 并解析输出。"""
    result = subprocess.run(
        ["stratevo", "analyze", ticker, "--ensemble", "5"],
        capture_output=True, text=True, timeout=60
    )
    stdout = result.stdout + result.stderr
    # 简单解析: 提取 Consensus 行
    lines = stdout.strip().split("\n")
    consensus = "UNKNOWN"
    for line in lines:
        if "Consensus:" in line:
            consensus = line.split("Consensus:")[1].strip()
        if "Combined Score:" in line:
            score = line.split("Combined Score:")[1].strip()

    return {
        "ticker": ticker,
        "consensus": consensus,
        "raw": stdout[:500]  # 截断保存
    }


def analyze_watchlist() -> list:
    """分析所有持仓。"""
    results = []
    for ticker in HOLDINGS:
        print(f"  [{ticker}] 分析中...")
        try:
            r = analyze_one(ticker)
            results.append(r)
            print(f"    → {r['consensus']}")
        except Exception as e:
            results.append({"ticker": ticker, "error": str(e)})
            print(f"    → 失败: {e}")
    return results


def start_mcp():
    """启动 StratEvo MCP Server。"""
    subprocess.run(["stratevo", "mcp", "serve"])


if __name__ == "__main__":
    if "--watchlist" in sys.argv:
        results = analyze_watchlist()
        Path("stock_data/stratevo_scan.json").write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\n结果已写入 stock_data/stratevo_scan.json")
    elif "--mcp" in sys.argv:
        start_mcp()
    else:
        ticker = sys.argv[1] if len(sys.argv) > 1 else "002156.SZ"
        r = analyze_one(ticker)
        print(json.dumps(r, ensure_ascii=False, indent=2))
