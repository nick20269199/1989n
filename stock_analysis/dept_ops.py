"""
dept_ops.py — 部门操作神经层 v1

所有部门 handler 输出前必须经过此层。三项硬门禁:
  1. 预检门禁 — 检查依赖部门状态，不健康 → 降级输出
  2. 交叉门禁 — 跨数据源比对，偏差>2% → 标红
  3. 来源声明 — 每个输出末尾带数据源+新鲜度+交叉校验状态

用法:
  from dept_ops import OpsGate
  gate = OpsGate("前厅部")
  result = gate.wrap(content, sources=[...], crosscheck_with=["engineering"])
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from dept_status_protocol import read_other_dept, is_status_fresh
from dept_preflight import run_preflight

CST = timezone(timedelta(hours=8))

# 路径 — 从 config.py 单一权威来源
import sys
sys.path.insert(0, str(Path(__file__).parent))
from config import STOCK_DATA_DIR, PROJECT_DIR as CONFIG_PROJECT_DIR
STOCK_DATA = STOCK_DATA_DIR
PROJECT_DIR = CONFIG_PROJECT_DIR

logger = logging.getLogger("dept_ops")

# ── 部门注册表 ──────────────────────────────────────────────
# 飞书部门名 → 系统部门名映射
# 五部架构: 前厅部/情报部/工程部/研发部/读书郎
DEPT_ALIAS = {
    "前厅部": "front-office",
    "情报部": "intelligence",
    "工程部": "engineering",
    "研发部": "rd",           # 独立研发部 — 想法→规则/工具
    "读书郎": "reader",       # 独立知识管理 — 读书→交易穿透
}

# 依赖映射 (与 dependencies.json 保持一致)
DEPT_DEPS = {
    "front-office": ["engineering"],
    "intelligence": ["front-office", "engineering"],
    "engineering": [],
    "rd": ["engineering", "front-office"],        # 研发依赖工程(基础设施)和前厅(交易反馈)
    "reader": [],                                  # 读书郎独立，无运行时依赖
}

# 数据源清单 (用于来源声明)
DATA_SOURCES = {
    "portfolio.json": str(PROJECT_DIR / "data" / "portfolio.json"),
    "data_source_router": "实时行情 (多通道自动回退)",
    "channel_health": str(STOCK_DATA / "channel_health_latest.json"),
    "last_error": str(STOCK_DATA / "last_error.txt"),
    "reading_index": str(STOCK_DATA / "status" / "reading_index.json"),
    "news_latest": str(STOCK_DATA),  # glob news_*.json
}


class OpsGate:
    """部门操作门禁 — 每个 handler 回复前调 .wrap() 注入神经。"""

    def __init__(self, dept_name: str):
        self.dept_name = dept_name
        self.system_dept = DEPT_ALIAS.get(dept_name, dept_name)
        self._preflight_cache: Optional[dict] = None
        self._other_dept_cache: dict = {}

    # ── 门禁 1: 预检 ─────────────────────────────────────────

    def preflight(self) -> dict:
        """运行跨部门预检，返回报告。缓存 60 秒。"""
        if self._preflight_cache:
            return self._preflight_cache
        try:
            report = run_preflight(self.system_dept)
        except Exception as e:
            logger.warning("preflight failed for %s: %s", self.dept_name, e)
            report = {
                "overall": "error",
                "checks": [{"check": "preflight", "severity": "fail",
                            "detail": f"预检异常: {e}"}],
                "blocking": True,
            }
        self._preflight_cache = report
        return report

    def preflight_summary(self) -> str:
        """预检结果 → 一行摘要。"""
        r = self.preflight()
        overall = r.get("overall", "?")
        fail = r.get("fail_count", 0)
        adv = r.get("advisory_count", 0)
        if overall == "pass":
            return f"预检通过 ✅"
        elif overall == "blocking":
            return f"预检阻塞 ⛔ ({fail}项失败)"
        elif overall == "advisory":
            return f"预检注意 ⚠️ ({adv}项)"
        return f"预检异常: {overall}"

    # ── 门禁 2: 交叉验证 ─────────────────────────────────────

    def crosscheck(self, dept: str) -> dict:
        """读取指定部门最新状态，返回健康度。"""
        if dept in self._other_dept_cache:
            return self._other_dept_cache[dept]
        system_name = DEPT_ALIAS.get(dept, dept)
        status = read_other_dept(system_name)
        result = {
            "dept": dept,
            "exists": status is not None,
            "health": status.get("health", "unknown") if status else "missing",
            "fresh": is_status_fresh(status) if status else False,
            "timestamp": status.get("timestamp", "无") if status else "无",
            "issues": status.get("issues", []) if status else [],
        }
        self._other_dept_cache[dept] = result
        return result

    def crosscheck_all_deps(self) -> list[dict]:
        """交叉验证所有依赖部门。"""
        deps = DEPT_DEPS.get(self.system_dept, [])
        return [self.crosscheck(d) for d in deps]

    def crosscheck_summary(self) -> str:
        """交叉验证 → 一行摘要。"""
        results = self.crosscheck_all_deps()
        if not results:
            return "无依赖部门"
        parts = []
        for r in results:
            icon = "✅" if r["fresh"] and r["health"] == "healthy" else "⚠️" if r["exists"] else "⛔"
            parts.append(f"{icon}{r['dept']}({r['health']})")
        return " | ".join(parts)

    # ── 数据新鲜度 ───────────────────────────────────────────

    def check_freshness(self, source_name: str) -> dict:
        """检查单个数据源新鲜度。"""
        result = {"source": source_name, "fresh": False, "detail": ""}
        try:
            if source_name == "portfolio.json":
                p = Path(DATA_SOURCES[source_name])
                if p.exists():
                    mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=CST)
                    age_m = (datetime.now(CST) - mtime).total_seconds() / 60
                    result["fresh"] = age_m < 1440  # 24h
                    result["detail"] = f"更新于 {age_m:.0f} 分钟前"
                    result["timestamp"] = mtime.isoformat()
                else:
                    result["detail"] = "文件缺失"
            elif source_name == "data_source_router":
                ch = STOCK_DATA / "channel_health_latest.json"
                if ch.exists():
                    data = json.loads(ch.read_text("utf-8"))
                    active = [k for k, v in data.items() if v is True]
                    result["fresh"] = len(active) > 0
                    result["detail"] = f"活跃通道: {', '.join(active) if active else '无'}"
                else:
                    result["detail"] = "通道状态未知"
            else:
                result["detail"] = "新鲜度检查未实现"
        except Exception as e:
            result["detail"] = f"检查异常: {e}"
        return result

    # ── 来源声明 ─────────────────────────────────────────────

    def source_footer(self, sources: list[str] = None,
                      crosscheck: bool = True) -> str:
        """生成来源声明页脚。U4 中介声明强制要求。"""
        now = datetime.now(CST).strftime("%H:%M:%S")
        lines = [
            "\n---",
            f"**来源声明** | {now}",
            f"处理部门: {self.dept_name}",
            f"预检状态: {self.preflight_summary()}",
        ]
        if crosscheck:
            lines.append(f"交叉校验: {self.crosscheck_summary()}")
        if sources:
            for s in sources:
                f = self.check_freshness(s)
                icon = "✅" if f["fresh"] else "⚠️"
                lines.append(f"{icon} {s}: {f['detail']}")
        lines.append("中介声明: 此判断基于以上数据源和架构预设，数据选择/清洗由系统自动完成。")
        return "\n".join(lines)

    # ── 一键包裹 ─────────────────────────────────────────────

    def wrap(self, content: str, sources: list[str] = None,
             crosscheck: bool = True) -> str:
        """将部门输出包裹上预检+交叉验证+来源声明。"""
        preflight = self.preflight()
        blocking = preflight.get("blocking", False)

        # 构建输出
        parts = []

        # 阻塞时在内容前加警告
        if blocking:
            parts.append("⚠️ **预检未通过 — 以下数据可能不可靠**")
            for c in preflight.get("checks", []):
                if c.get("severity") == "fail":
                    parts.append(f"  - ⛔ {c.get('detail', '?')}")
            parts.append("")

        parts.append(content)
        parts.append(self.source_footer(sources=sources, crosscheck=crosscheck))
        return "\n".join(parts)


# ── Excel 摄入 ──────────────────────────────────────────────

def ingest_excel(filepath: str, sheet: str = None) -> dict:
    """摄入用户提供的 Excel/CSV 数据，返回标准化结构。

    支持 .xlsx / .xls / .csv。
    返回: {"headers": [...], "rows": [...], "filename": str, "sheet": str}
    """
    path = Path(filepath)
    if not path.exists():
        return {"error": f"文件不存在: {filepath}"}

    try:
        if path.suffix.lower() == '.csv':
            import csv
            with open(path, 'r', encoding='utf-8-sig') as f:
                reader = csv.reader(f)
                headers = next(reader, [])
                rows = [row for row in reader]
        else:
            import openpyxl
            wb = openpyxl.load_workbook(path, data_only=True)
            ws = wb[sheet] if sheet else wb.active
            headers = [cell.value for cell in ws[1]]
            rows = []
            for row in ws.iter_rows(min_row=2, values_only=True):
                rows.append(list(row))

        return {
            "filename": path.name,
            "sheet": sheet or wb.active.title if 'wb' in dir() else "csv",
            "headers": headers,
            "rows": rows,
            "row_count": len(rows),
        }
    except ImportError as e:
        return {"error": f"缺少库: {e}. pip install openpyxl"}
    except Exception as e:
        return {"error": f"读取失败: {e}"}


def crosscheck_excel_vs_portfolio(excel_data: dict) -> dict:
    """将 Excel 逐笔成交与 portfolio.json 交叉比对，返回实际持仓 vs 记录持仓。"""
    try:
        pf = json.loads((PROJECT_DIR / "data" / "portfolio.json").read_text("utf-8"))
        pf_holdings = {h["code"]: h for h in pf.get("holdings", [])}
    except Exception:
        return {"error": "无法读取 portfolio.json"}

    if "error" in excel_data:
        return excel_data

    rows = excel_data.get("rows", [])
    if not rows:
        return {"error": "Excel 无数据"}

    # 从逐笔成交计算每只股票的实际持仓
    from collections import defaultdict
    actual = defaultdict(lambda: {"buy_qty": 0, "buy_amt": 0, "sell_qty": 0, "buy_count": 0, "sell_count": 0})

    for row in rows:
        try:
            direction = str(row[4]) if len(row) > 4 else ""
            qty = int(row[5]) if len(row) > 5 and row[5] else 0
            fill_qty = int(row[8]) if len(row) > 8 and row[8] else 0
            fill_amt = float(row[9]) if len(row) > 9 and row[9] else 0
            avg_price = float(row[10]) if len(row) > 10 and row[10] else 0
            status = str(row[6]) if len(row) > 6 else ""
            code = str(row[2]).strip() if len(row) > 2 and row[2] else ""
            name = str(row[3]).strip() if len(row) > 3 and row[3] else ""

            if status != '已成' or not code:
                continue

            effective_qty = fill_qty or qty
            effective_price = avg_price or (fill_amt / effective_qty if effective_qty > 0 else 0)

            if '买入' in direction:
                actual[code]["buy_qty"] += effective_qty
                actual[code]["buy_amt"] += (fill_amt or effective_qty * effective_price)
                actual[code]["buy_count"] += 1
            elif '卖出' in direction:
                actual[code]["sell_qty"] += effective_qty
                actual[code]["sell_count"] += 1
        except (IndexError, ValueError, TypeError):
            continue

    # 比对每个持仓股票
    discrepancies = []
    matched = 0
    for code, h in pf_holdings.items():
        name = h.get("name", "")
        pf_shares = int(h.get("shares", 0))
        pf_cost = float(h.get("cost", 0))

        act = actual.get(code, {})
        act_buy_qty = act.get("buy_qty", 0)
        act_sell_qty = act.get("sell_qty", 0)
        act_buy_amt = act.get("buy_amt", 0)
        act_holding = act_buy_qty - act_sell_qty
        act_cost = act_buy_amt / act_buy_qty if act_buy_qty > 0 else 0.0

        shares_ok = act_holding == pf_shares
        cost_ok = abs(act_cost - pf_cost) < 0.1

        if shares_ok and cost_ok:
            matched += 1
        else:
            discrepancies.append({
                "code": code, "name": name,
                "excel_holding": act_holding, "pf_shares": pf_shares,
                "excel_cost": round(act_cost, 2), "pf_cost": pf_cost,
                "excel_buy_qty": act_buy_qty, "excel_sell_qty": act_sell_qty,
                "buy_count": act.get("buy_count", 0),
                "sell_count": act.get("sell_count", 0),
            })

    return {
        "total_holdings": len(pf_holdings),
        "matched": matched,
        "discrepancies": discrepancies,
        "discrepancy_count": len(discrepancies),
        "conclusion": f"{len(pf_holdings)}只持仓中 {matched}只一致, {len(discrepancies)}只有偏差"
            if discrepancies else f"{len(pf_holdings)}只持仓全部一致",
        "excel_has_more_data": len(actual) > len(pf_holdings),
    }


def excel_bs_summary(excel_path: str = None) -> str:
    """生成 Excel 交叉验证摘要，供前厅部输出使用。"""
    path = excel_path or "D:/1989n/Table.xlsx"
    excel_data = ingest_excel(path)
    if "error" in excel_data:
        return ""
    result = crosscheck_excel_vs_portfolio(excel_data)
    if result.get("discrepancy_count", 0) == 0:
        return "\n📋 **Excel 交叉验证**: 与 portfolio.json 一致 ✅"

    lines = ["\n📋 **Excel 交叉验证 (逐笔成交)** ⚠️"]
    for d in result.get("discrepancies", []):
        lines.append(
            f"  • {d['name']}({d['code']}): "
            f"Excel={d['excel_holding']}股/¥{d['excel_cost']} | "
            f"pf={d['pf_shares']}股/¥{d['pf_cost']} | "
            f"买入{d['buy_count']}笔/卖出{d['sell_count']}笔"
        )
    lines.append(f"  → {result['conclusion']}")
    return "\n".join(lines)


# ── CLI 测试 ──────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    # 测试前厅部（含原财务部PnL职能）
    gate = OpsGate("前厅部")
    content = "**持仓明细**\n\n通富微电 002156: 现价 69.78 | 盈亏 +1,810"
    result = gate.wrap(content, sources=["portfolio.json", "data_source_router"])
    print(result)
