"""
consistency_gate.py — 跨文件一致性校验

检查数据文件之间的关系是否一致:
- 持仓股票代码在 A 股全列表中是否存在
- 不再有股票同时出现在持仓和已清仓
- 数据通道至少有一个可用
- 盘中分析持仓代码 vs 实际持仓一致

用法:
    python tools/consistency_gate.py              # 全量检查
    python tools/consistency_gate.py --json       # JSON 输出
"""
import json
import sys
from pathlib import Path

STOCK_DATA = Path("D:/1989n/stock_data")
ANALYSIS_DATA = Path("D:/1989n/stock_analysis/data")


def _read_json(path: Path) -> dict | list | None:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        pass
    return None


def check_portfolio_in_stock_list() -> list[dict]:
    """持仓股票代码必须在 A 股全列表中能找到。"""
    issues = []
    port = _read_json(ANALYSIS_DATA / "portfolio.json")
    stocks = _read_json(STOCK_DATA / "a_stock_list.json")

    if not port:
        issues.append({"check": "portfolio_in_stock_list", "status": "skip",
                        "detail": "portfolio.json 不存在"})
        return issues
    if not stocks or not isinstance(stocks, dict):
        issues.append({"check": "portfolio_in_stock_list", "status": "error",
                        "detail": "a_stock_list.json 不存在或格式错误"})
        return issues

    stock_codes = {s["code"] for s in stocks.get("stocks", []) if isinstance(s, dict)}
    if not stock_codes:
        issues.append({"check": "portfolio_in_stock_list", "status": "error",
                        "detail": "a_stock_list.json 中无股票数据"})
        return issues

    all_port_codes = set()
    for item in port.get("holdings", []):
        code = item.get("code", "")
        all_port_codes.add(code)
        if code not in stock_codes:
            issues.append({
                "check": "portfolio_in_stock_list",
                "status": "violation",
                "detail": f"持仓 {code} {item.get('name','')} 未在 A 股全列表中找到",
            })
    # 已清仓股票可能已退市/更名，不强制检查，仅 advisory 提示
    for item in port.get("cleared", []):
        code = item.get("code", "")
        all_port_codes.add(code)
        if code not in stock_codes:
            issues.append({
                "check": "portfolio_in_stock_list",
                "status": "advisory",
                "detail": f"已清仓 {code} {item.get('name','')} 未在 A 股列表中（可能已退市/更名）",
            })

    if not issues:
        issues.append({"check": "portfolio_in_stock_list", "status": "pass",
                        "detail": f"全部 {len(all_port_codes)} 个股票代码在 A 股列表中"})
    return issues


def check_holdings_cleared_no_overlap() -> list[dict]:
    """同一只股票不应同时出现在持仓和已清仓。"""
    issues = []
    port = _read_json(ANALYSIS_DATA / "portfolio.json")
    if not port:
        return issues

    holding_codes = {h["code"] for h in port.get("holdings", []) if isinstance(h, dict)}
    cleared_codes = {c["code"] for c in port.get("cleared", []) if isinstance(c, dict)}
    overlap = holding_codes & cleared_codes

    if overlap:
        for code in overlap:
            issues.append({
                "check": "holdings_cleared_no_overlap",
                "status": "violation",
                "detail": f"{code} 同时出现在持仓和已清仓",
            })
    else:
        issues.append({"check": "holdings_cleared_no_overlap", "status": "pass",
                        "detail": "持仓和已清仓无重叠"})
    return issues


def check_channel_health() -> list[dict]:
    """数据通道至少有一个可用。"""
    issues = []
    ch = _read_json(STOCK_DATA / "channel_health_latest.json")
    if not ch:
        issues.append({"check": "channel_health", "status": "skip",
                        "detail": "channel_health_latest.json 不存在"})
        return issues

    if not ch.get("healthy", False):
        issues.append({
            "check": "channel_health",
            "status": "violation",
            "detail": "所有数据通道均不可用 (sina/tencent/eastmoney 全部 false)",
        })
    else:
        active = [k for k, v in ch.items() if v is True]
        issues.append({"check": "channel_health", "status": "pass",
                        "detail": f"可用通道: {', '.join(active)}"})
    return issues


def check_intraday_portfolio_consistency() -> list[dict]:
    """盘中分析中的持仓代码应与 portfolio.json 一致。"""
    issues = []
    port = _read_json(ANALYSIS_DATA / "portfolio.json")
    if not port:
        return issues

    holding_codes = sorted(h["code"] for h in port.get("holdings", []) if isinstance(h, dict))

    # 找最新的盘中分析文件
    analysis_files = sorted(STOCK_DATA.glob("analysis_30min_*.json"), reverse=True)
    if not analysis_files:
        return issues

    latest = analysis_files[0]
    data = _read_json(latest)
    if not data or not isinstance(data, dict):
        return issues

    # 盘中分析可能包含 holdings 字段
    analysis_holdings = data.get("holdings", [])
    if not analysis_holdings:
        return issues

    analysis_codes = set()
    if isinstance(analysis_holdings, list):
        analysis_codes = {h.get("code", "") for h in analysis_holdings if isinstance(h, dict)}

    port_set = set(holding_codes)
    missing_in_analysis = port_set - analysis_codes
    extra_in_analysis = analysis_codes - port_set

    if missing_in_analysis:
        issues.append({
            "check": "intraday_portfolio_consistency",
            "status": "violation",
            "detail": f"持仓缺少盘中分析: {', '.join(sorted(missing_in_analysis))}",
        })
    if extra_in_analysis:
        issues.append({
            "check": "intraday_portfolio_consistency",
            "status": "violation",
            "detail": f"盘中分析含非持仓代码: {', '.join(sorted(extra_in_analysis))}",
        })
    if not missing_in_analysis and not extra_in_analysis and analysis_codes:
        issues.append({"check": "intraday_portfolio_consistency", "status": "pass",
                        "detail": f"盘中分析 {latest.name} 与持仓一致 ({len(holding_codes)} 只)"})
    return issues


def check_producer_consumer_links() -> list[dict]:
    """校验每个生产型模块的产出有至少一个消费者引用。
    防止新增模块产出无人消费、整条链路空转。"""
    issues = []
    map_path = STOCK_DATA / "schemas" / "producer_consumer_map.json"
    pc_map = _read_json(map_path)
    if not pc_map:
        issues.append({"check": "producer_consumer_links", "status": "skip",
                        "detail": "producer_consumer_map.json 不存在"})
        return issues

    orphan_producers = []
    for prod in pc_map.get("producers", []):
        consumers = prod.get("consumers", [])
        if not consumers:
            orphan_producers.append(prod["module"])
            issues.append({
                "check": "producer_consumer_links",
                "status": "violation",
                "detail": f"{prod['module']} 产出无消费者注册 — 链路可能空转",
            })

    if not orphan_producers:
        total = len(pc_map.get("producers", []))
        issues.append({"check": "producer_consumer_links", "status": "pass",
                        "detail": f"全部 {total} 个生产模块均有消费者注册"})
    return issues


def check_critical_outputs() -> list[dict]:
    """校验关键产出文件存在且非空。
    防止重构/拆分模块时遗漏副作用导致关键数据静默丢失。"""
    issues = []
    map_path = STOCK_DATA / "schemas" / "producer_consumer_map.json"
    pc_map = _read_json(map_path)
    if not pc_map:
        return issues

    critical = pc_map.get("critical_outputs", [])
    if not critical:
        return issues

    missing_or_empty = []
    for path_str in critical:
        p = Path(path_str)
        if not p.exists():
            missing_or_empty.append(f"{p.name} (缺失)")
            issues.append({
                "check": "critical_outputs",
                "status": "violation",
                "detail": f"关键产出文件缺失: {p.name}",
            })
        elif p.stat().st_size == 0:
            missing_or_empty.append(f"{p.name} (空文件)")
            issues.append({
                "check": "critical_outputs",
                "status": "violation",
                "detail": f"关键产出文件为空: {p.name}",
            })

    if not missing_or_empty:
        issues.append({"check": "critical_outputs", "status": "pass",
                        "detail": f"全部 {len(critical)} 个关键产出文件存在且非空"})
    return issues


def run_all() -> dict:
    """运行全部一致性检查。"""
    all_issues = []
    for check in [
        check_portfolio_in_stock_list,
        check_holdings_cleared_no_overlap,
        check_channel_health,
        check_intraday_portfolio_consistency,
        check_producer_consumer_links,
        check_critical_outputs,
    ]:
        all_issues.extend(check())

    violations = [i for i in all_issues if i.get("status") == "violation"]
    return {
        "checks": len(all_issues),
        "violations": len(violations),
        "passed": len(violations) == 0,
        "details": all_issues,
    }


def main():
    as_json = "--json" in sys.argv
    result = run_all()

    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if result["passed"]:
            print(f"[CONSISTENCY_GATE] 全部 {result['checks']} 项检查通过")
        else:
            print(f"[CONSISTENCY_GATE] {result['violations']}/{result['checks']} 项异常:")
            for d in result["details"]:
                if d.get("status") == "violation":
                    print(f"  ✗ {d['check']}: {d['detail']}")

    sys.exit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
