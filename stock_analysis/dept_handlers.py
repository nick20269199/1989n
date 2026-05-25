"""
dept_handlers.py — 飞书 Bot v2 部门处理器

每个部门一个 handler 函数，接收解析后的指令，返回结构化结果。
所有数据查询走 data_source_router，禁止直接调外部 API。

handler 签名: (action: str, params: dict, raw_text: str) -> dict | None
返回: {"title": str, "content": str, "source": str} 或 None (无法处理)
"""
import json
import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("dept_handlers")

STOCK_DATA = Path("D:/1989n/stock_data")
PROJECT_DIR = Path("D:/1989n/stock_analysis")
PYTHON = r"D:\Python314\python"
TASK_QUEUE = STOCK_DATA / "task_queue.json"

# ── 数据校验工具 ──

def _validate_price(price, max_pct=20) -> bool:
    """价格合理性检查: >0 且涨跌幅不异常。"""
    if price is None or price <= 0:
        return False
    return True


def _validate_code(code: str) -> bool:
    """检查股票代码是否在 portfolio.json 中。"""
    try:
        pf = json.loads((PROJECT_DIR / "data" / "portfolio.json").read_text("utf-8"))
        all_codes = {h.get("code", "") for h in pf.get("holdings", [])}
        all_codes.update(c.get("code", "") for c in pf.get("cleared", []))
        return code in all_codes
    except Exception:
        return True  # 无法验证时不阻断


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


# ── 任务队列 (B类任务: 需要 Claude 深度参与) ──

def _enqueue_task(dept: str, task: str, raw_text: str) -> str:
    """将需要 Claude 处理的任务写入队列。"""
    TASK_QUEUE.parent.mkdir(parents=True, exist_ok=True)
    existing = []
    if TASK_QUEUE.exists():
        try:
            existing = json.loads(TASK_QUEUE.read_text("utf-8"))
        except Exception:
            pass
    task_id = f"TK-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    entry = {
        "id": task_id,
        "dept": dept,
        "task": task,
        "raw": raw_text[:500],
        "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": "pending",
    }
    existing.append(entry)
    TASK_QUEUE.write_text(json.dumps(existing, ensure_ascii=False, indent=2), "utf-8")
    logger.info("Task enqueued: %s → %s", task_id, dept)
    return task_id


# ═══════════════════════════════════════════
# 1. 前厅部 — 行情/持仓/盘前/盘中/复盘
# ═══════════════════════════════════════════

def handle_front_office(action: str, params: dict, raw_text: str) -> dict | None:
    """前厅部: 实时行情查询、持仓概览、盘前简报、盘中分析、收盘复盘。"""

    # 查行情
    if action in ("行情", "价格", "quote", "price") or any(
        kw in raw_text for kw in ("行情", "多少钱", "价格", "涨跌", "报价")
    ):
        code = params.get("code", "")
        if not code:
            # 从文本中提取股票代码
            import re
            m = re.search(r'\b(00\d{4}|30\d{4}|60\d{4}|68\d{4})\b', raw_text)
            code = m.group(0) if m else ""

        if not code:
            return {"title": "前厅部 · 行情查询", "content": "未识别到股票代码，请提供代码如 `002156`。",
                    "source": "dept:front-office"}

        try:
            from data_source_router import get_quotes
            q = get_quotes([code])
            if code in q:
                d = q[code]
                if not _validate_price(d.get("current", 0)):
                    return {"title": f"前厅部 · {code}", "content": f"**{d.get('name', code)}**: 当前数据不可用，请稍后重试。",
                            "source": "dept:front-office|data_source_router"}
                chg = d.get('change_pct', 0)
                arrow = "↑" if chg > 0 else "↓" if chg < 0 else "→"
                content = (
                    f"**{d['name']}** ({code})\n\n"
                    f"现价: **{d['current']:.2f}** {arrow}{abs(chg):.2f}%\n"
                    f"开盘: {d.get('open', 0):.2f}  最高: {d.get('high', 0):.2f}  最低: {d.get('low', 0):.2f}\n"
                    f"昨收: {d.get('prev_close', 0):.2f}  成交量: {d.get('volume', 0):,}\n"
                    f"---\n数据源: {d.get('source', '?')} | {_ts()}"
                )
                return {"title": f"前厅部 · {d['name']} 行情", "content": content,
                        "source": f"dept:front-office|{d.get('source', '?')}"}
            else:
                return {"title": f"前厅部 · {code}", "content": f"未获取到 {code} 的行情数据，可能通道暂时不可用。",
                        "source": "dept:front-office"}
        except Exception as e:
            logger.exception("Front office quote failed")
            return {"title": "前厅部 · 行情查询", "content": f"行情查询异常: {e}", "source": "dept:front-office|error"}

    # 持仓概览
    if action in ("持仓", "持仓盈亏", "portfolio") or any(
        kw in raw_text for kw in ("持仓", "仓位", "持有", "组合")
    ):
        try:
            pf = json.loads((PROJECT_DIR / "data" / "portfolio.json").read_text("utf-8"))
            holdings = pf.get("holdings", [])
            if not holdings:
                return {"title": "前厅部 · 持仓", "content": "当前无持仓。", "source": "dept:front-office|portfolio.json"}

            from data_source_router import get_quotes
            codes = [h["code"] for h in holdings]
            quotes = get_quotes(codes)

            lines = ["**当前持仓**\n"]
            total_value = 0
            total_cost = 0
            for h in holdings:
                code = h["code"]
                name = h["name"]
                shares = int(h.get("shares", 0))
                cost = float(h.get("cost", 0))
                q = quotes.get(code, {})
                current = q.get("current", 0) if q else 0
                chg_pct = q.get("change_pct", 0) if q else 0
                mv = current * shares if current > 0 else 0
                cost_total = cost * shares
                pnl = mv - cost_total if mv > 0 else 0
                arrow = "↑" if chg_pct > 0 else "↓" if chg_pct < 0 else "→"
                pnl_sign = "+" if pnl > 0 else ""
                lines.append(
                    f"**{name}** {code}: {current:.2f} {arrow}{abs(chg_pct):.2f}% | "
                    f"市值 {mv:,.0f} | 盈亏 {pnl_sign}{pnl:,.0f}"
                )
                total_value += mv
                total_cost += cost_total

            total_pnl = total_value - total_cost
            pnl_sign = "+" if total_pnl > 0 else ""
            lines.append(f"\n---\n总市值: {total_value:,.0f} | 总盈亏: {pnl_sign}{total_pnl:,.0f}")
            lines.append(f"数据源: data_source_router | {_ts()}")

            return {"title": "前厅部 · 持仓概览", "content": "\n".join(lines),
                    "source": "dept:front-office|portfolio.json|data_source_router"}
        except Exception as e:
            logger.exception("Portfolio overview failed")
            return {"title": "前厅部 · 持仓", "content": f"获取持仓失败: {e}", "source": "dept:front-office|error"}

    # 盘前简报 → B类任务 (需要 Claude 深度分析)
    if action in ("盘前", "早报", "morning") or any(kw in raw_text for kw in ("盘前", "晨报", "早间")):
        task_id = _enqueue_task("front-office", "盘前简报/晨报生成", raw_text)
        return {"title": "前厅部 · 任务已入队",
                "content": f"盘前简报需要 Claude 深度分析，已入队 [{task_id}]。\n回到电脑前 Claude 会自动处理并发送结果到此群。",
                "source": "dept:front-office|task_queue"}

    # 其他 → 入队
    task_id = _enqueue_task("front-office", action or "综合查询", raw_text)
    return {"title": "前厅部 · 任务已入队",
            "content": f"「{raw_text[:80]}」需要进一步分析，已入队 [{task_id}]。\nClaude 接续处理后会发结果到此群。",
            "source": "dept:front-office|task_queue"}


# ═══════════════════════════════════════════
# 2. 情报部 — 新闻/大V/情绪/涨停
# ═══════════════════════════════════════════

def handle_intelligence(action: str, params: dict, raw_text: str) -> dict | None:
    """情报部: 最新新闻、大V雷达、市场情绪、涨停池。"""

    # 新闻
    if action in ("新闻", "news") or any(kw in raw_text for kw in ("新闻", "快讯", "头条")):
        news_files = sorted(STOCK_DATA.glob("news_*.json"), reverse=True)
        if not news_files:
            return {"title": "情报部 · 新闻", "content": "当前无新闻数据。", "source": "dept:intelligence"}
        try:
            latest = json.loads(news_files[0].read_text("utf-8"))
            headlines = latest.get("data", []) if isinstance(latest, dict) else (latest if isinstance(latest, list) else [])
            if not headlines:
                return {"title": "情报部 · 新闻", "content": "新闻文件为空。", "source": "dept:intelligence"}
            lines = [f"**最新新闻** ({news_files[0].stem})\n"]
            for h in headlines[:10]:
                title = h.get("title", h.get("text", "")) if isinstance(h, dict) else str(h)
                lines.append(f"- {title[:100]}")
            lines.append(f"\n数据源: {news_files[0].name} | {_ts()}")
            return {"title": "情报部 · 最新新闻", "content": "\n".join(lines), "source": "dept:intelligence"}
        except Exception as e:
            return {"title": "情报部 · 新闻", "content": f"读取新闻失败: {e}", "source": "dept:intelligence|error"}

    # 大V雷达
    if any(kw in raw_text for kw in ("大V", "雷达", "视频", "vv")):
        try:
            result = subprocess.run(
                [PYTHON, str(PROJECT_DIR / "vv_insights.py")],
                capture_output=True, text=True, timeout=60, cwd=str(PROJECT_DIR)
            )
            if result.returncode == 0 and result.stdout.strip():
                return {"title": "情报部 · 大V雷达", "content": result.stdout.strip()[:3000],
                        "source": "dept:intelligence|vv_insights"}
            return {"title": "情报部 · 大V雷达", "content": "大V雷达暂无新数据。", "source": "dept:intelligence"}
        except Exception as e:
            return {"title": "情报部 · 大V雷达", "content": f"大V雷达查询异常: {e}", "source": "dept:intelligence|error"}

    # 其他 → 入队
    task_id = _enqueue_task("intelligence", action or "情报查询", raw_text)
    return {"title": "情报部 · 任务已入队",
            "content": f"「{raw_text[:80]}」已入队 [{task_id}]。Claude 接续后发结果到此群。",
            "source": "dept:intelligence|task_queue"}


# ═══════════════════════════════════════════
# 3. 工程部 — 健康检查/错误诊断/SEL/测试
# ═══════════════════════════════════════════

def handle_engineering(action: str, params: dict, raw_text: str) -> dict | None:
    """工程部: 系统健康检查、错误诊断、SEL lint、跑测试。"""

    # 健康检查
    if action in ("健康", "health") or any(kw in raw_text for kw in ("健康", "状态", "检查")):
        try:
            from tools.consistency_gate import run_all
            cr = run_all()
            ch = json.loads((STOCK_DATA / "channel_health_latest.json").read_text("utf-8"))
            active = [k for k, v in ch.items() if v is True]
            lines = [
                "**系统健康**\n",
                f"通道: {'✅' if active else '❌'} {', '.join(active) if active else '无可用通道'}",
                f"一致性: {'✅' if cr['passed'] else '❌'} {cr['checks']}检查/{cr['violations']}违规",
                f"时间: {_ts()}",
            ]
            eng_status = STOCK_DATA / "status" / "engineering_status.json"
            if eng_status.exists():
                es = json.loads(eng_status.read_text("utf-8"))
                issues = es.get("issues", [])
                if issues:
                    lines.append(f"\n工程部 issues: {len(issues)} 项")
                    for iss in issues[:3]:
                        lines.append(f"  - {iss}")
            return {"title": "工程部 · 系统健康", "content": "\n".join(lines),
                    "source": "dept:engineering|consistency_gate"}
        except Exception as e:
            return {"title": "工程部 · 健康", "content": f"健康检查异常: {e}", "source": "dept:engineering|error"}

    # 错误诊断
    if any(kw in raw_text for kw in ("错误", "报错", "error", "bug", "故障")):
        err_file = STOCK_DATA / "last_error.txt"
        if not err_file.exists():
            return {"title": "工程部 · 错误诊断", "content": "最近无错误记录。", "source": "dept:engineering"}
        err_text = err_file.read_text("utf-8", errors="replace")
        # 提取关键信息
        lines = err_text.splitlines()
        key_lines = [l for l in lines[:30] if l.strip() and any(
            kw in l for kw in ("Error", "Traceback", "File \"", "line ", "=== LAST")
        )]
        content = "**最近错误**\n\n```\n" + "\n".join(key_lines[:15]) + "\n```"
        if len(key_lines) > 15:
            content += f"\n... (共 {len(key_lines)} 行, 完整日志: last_error.txt)"
        content += f"\n\n{_ts()}"
        return {"title": "工程部 · 错误诊断", "content": content, "source": "dept:engineering|last_error.txt"}

    # SEL Lint
    if any(kw in raw_text for kw in ("lint", "SEL", "巡检")):
        try:
            result = subprocess.run(
                [PYTHON, str(PROJECT_DIR / "_sel_lint.py")],
                capture_output=True, text=True, timeout=30, cwd=str(PROJECT_DIR)
            )
            output = result.stdout.strip()[:2000] or "(无输出)"
            return {"title": "工程部 · SEL 巡检", "content": f"```\n{output}\n```\n\n{_ts()}",
                    "source": "dept:engineering|_sel_lint"}
        except Exception as e:
            return {"title": "工程部 · SEL", "content": f"SEL 巡检异常: {e}", "source": "dept:engineering|error"}

    # 其他 → 入队
    task_id = _enqueue_task("engineering", action or "工程查询", raw_text)
    return {"title": "工程部 · 任务已入队",
            "content": f"已入队 [{task_id}]。Claude 接续后发结果。", "source": "dept:engineering|task_queue"}


# ═══════════════════════════════════════════
# 4. 财务部 — 盈亏/成本/收益
# ═══════════════════════════════════════════

def handle_finance(action: str, params: dict, raw_text: str) -> dict | None:
    """财务部: 持仓盈亏明细、已清仓结算、交易成本。"""
    try:
        pf = json.loads((PROJECT_DIR / "data" / "portfolio.json").read_text("utf-8"))
    except Exception:
        return {"title": "财务部", "content": "无法读取持仓数据。", "source": "dept:finance|error"}

    # 已清仓结算
    if any(kw in raw_text for kw in ("已清仓", "结算", "历史", "清仓")):
        cleared = pf.get("cleared", [])
        if not cleared:
            return {"title": "财务部 · 已清仓", "content": "无已清仓记录。", "source": "dept:finance|portfolio.json"}
        lines = ["**已清仓结算**\n"]
        total_pnl = 0
        for c in cleared:
            name = c.get("name", "?")
            code = c.get("code", "?")
            exit_price = float(c.get("exit_price", c.get("price", 0)))
            cost = float(c.get("cost", 0))
            shares = int(c.get("shares", 0))
            pnl = (exit_price - cost) * shares
            pnl_sign = "+" if pnl > 0 else ""
            total_pnl += pnl
            exit_date = c.get("exit_date", c.get("date", "?"))
            lines.append(f"{name} {code}: 出清 {exit_price:.2f} | 盈亏 {pnl_sign}{pnl:,.0f} | {exit_date}")
        total_sign = "+" if total_pnl > 0 else ""
        lines.append(f"\n累计清仓盈亏: **{total_sign}{total_pnl:,.0f}**")
        return {"title": "财务部 · 已清仓结算", "content": "\n".join(lines),
                "source": "dept:finance|portfolio.json"}

    # 持仓盈亏 (默认)
    try:
        from data_source_router import get_quotes
        holdings = pf.get("holdings", [])
        codes = [h["code"] for h in holdings]
        quotes = get_quotes(codes)
        lines = ["**盈亏明细**\n"]
        total_pnl = 0
        for h in holdings:
            code = h["code"]
            name = h["name"]
            shares = int(h.get("shares", 0))
            cost = float(h.get("cost", 0))
            q = quotes.get(code, {})
            current = q.get("current", 0) if q else 0
            pnl = (current - cost) * shares if current > 0 else 0
            pnl_pct = ((current - cost) / cost * 100) if cost and current > 0 else 0
            total_pnl += pnl
            pnl_sign = "+" if pnl > 0 else ""
            price_str = f"{current:.2f}" if current else "?"
            lines.append(
                f"**{name}** {code}: 成本 {cost:.2f} -> 现价 {price_str} | "
                f"盈亏 {pnl_sign}{pnl:,.0f} ({pnl_sign}{pnl_pct:.1f}%)"
            )
        total_sign = "+" if total_pnl > 0 else ""
        lines.append(f"\n浮动盈亏合计: **{total_sign}{total_pnl:,.0f}**")
        lines.append(f"数据源: data_source_router | {_ts()}")
        return {"title": "财务部 · 盈亏明细", "content": "\n".join(lines),
                "source": "dept:finance|portfolio.json|data_source_router"}
    except Exception as e:
        return {"title": "财务部 · 盈亏", "content": f"盈亏计算异常: {e}", "source": "dept:finance|error"}


# ═══════════════════════════════════════════
# 5. 研发部 — 代码查询/bug追踪
# ═══════════════════════════════════════════

def handle_rd(action: str, params: dict, raw_text: str) -> dict | None:
    """研发部: 函数定义查询、调用链追踪、最近 bug 状态。"""

    # Bug 状态
    if any(kw in raw_text for kw in ("bug", "模式", "pattern", "pending")):
        pp = STOCK_DATA / "status" / "pending_patterns.json"
        if pp.exists():
            data = json.loads(pp.read_text("utf-8"))
            candidates = data.get("candidates", [])
            auto_blocked = data.get("auto_blocked_ids", [])
            lines = [f"**Bug 模式** 候选: {len(candidates)} 个, 自动阻断: {len(auto_blocked)} 个\n"]
            for c in candidates[:5]:
                desc = c.get("description", "?")
                occ = c.get("occurrences", 0)
                blocked = "🚫" if c.get("auto_block") else ""
                lines.append(f"- {blocked} [{occ}次] {desc[:80]}")
            return {"title": "研发部 · Bug 追踪", "content": "\n".join(lines),
                    "source": "dept:rd|pending_patterns.json"}
        return {"title": "研发部 · Bug", "content": "无 bug 模式记录。", "source": "dept:rd"}

    # 代码查询 → 入队 (需要 Claude 理解代码)
    task_id = _enqueue_task("rd", action or "代码查询", raw_text)
    return {"title": "研发部 · 任务已入队",
            "content": f"代码相关查询已入队 [{task_id}]。Claude 接续后处理。", "source": "dept:rd|task_queue"}


# ═══════════════════════════════════════════
# 6. 读书郎 — 读书笔记/交易穿透
# ═══════════════════════════════════════════

def handle_reader(action: str, params: dict, raw_text: str) -> dict | None:
    """读书郎: 读书笔记查询、交易穿透检索、书单进度。"""

    notes_dir = STOCK_DATA / "reading_notes"
    index_file = STOCK_DATA / "status" / "reading_index.json"

    # 读书进度
    if any(kw in raw_text for kw in ("进度", "书单", "已读", "读了")):
        try:
            idx = json.loads(index_file.read_text("utf-8")) if index_file.exists() else {}
            notes = idx.get("notes", [])
            total = len(notes)
            total_injected = idx.get("total_injected", "?")
            lines = [f"**读书进度**\n累计: {total} 本 | 知识注入: {total_injected} 条\n"]
            # 最近 5 本
            recent = sorted(notes, key=lambda n: n.get("date", ""), reverse=True)[:5]
            if recent:
                lines.append("最近:")
                for r in recent:
                    date = r.get("date", "?")
                    src = r.get("title", r.get("filename", "?"))
                    lines.append(f"  - {date} {src}")
            return {"title": "读书郎 · 进度", "content": "\n".join(lines),
                    "source": "dept:reader|reading_index.json"}
        except Exception as e:
            return {"title": "读书郎 · 进度", "content": f"读进度失败: {e}", "source": "dept:reader|error"}

    # 穿透检索
    if any(kw in raw_text for kw in ("穿透", "笔记", "交易穿透")):
        query = params.get("keyword", raw_text)
        if notes_dir.exists():
            matches = []
            for f in sorted(notes_dir.glob("*.md"), reverse=True)[:50]:
                try:
                    text = f.read_text("utf-8", errors="replace")
                    for kw in query.split():
                        if kw in text and len(kw) >= 2:
                            matches.append(f"- {f.stem}: 匹配「{kw}」")
                            break
                except Exception:
                    continue
            if matches:
                content = "**穿透检索**\n\n" + "\n".join(matches[:10])
                if len(matches) > 10:
                    content += f"\n... (共 {len(matches)} 条)"
                return {"title": "读书郎 · 穿透检索", "content": content, "source": "dept:reader|reading_notes"}
        return {"title": "读书郎 · 检索", "content": f"未找到「{query}」相关的读书笔记。", "source": "dept:reader"}

    # 其他 → 入队
    task_id = _enqueue_task("reader", action or "读书查询", raw_text)
    return {"title": "读书郎 · 任务已入队",
            "content": f"已入队 [{task_id}]。Claude 接续后处理。", "source": "dept:reader|task_queue"}


# ═══════════════════════════════════════════
# 7. 通用问答 — 走 DeepSeek Agent
# ═══════════════════════════════════════════

def handle_general(raw_text: str, chat_id: str = "") -> dict:
    """通用问答: 委派给 feishu_claude_agent (DeepSeek + 工具调用)。"""
    try:
        from feishu_claude_agent import process_message
        response = process_message(raw_text, chat_id=chat_id)
        # 解析分类标签
        lines = response.strip().split("\n", 2)
        first = lines[0].strip()
        title = first if first.startswith("📊") or first.startswith("📈") or first.startswith("⚠️") or first.startswith("💬") else "AI 回复"
        body = lines[2].strip() if len(lines) > 2 else lines[1].strip() if len(lines) > 1 else response
        return {"title": title, "content": body, "source": "dept:general|deepseek-agent"}
    except Exception as e:
        logger.exception("DeepSeek agent failed")
        return {"title": "AI 回复", "content": f"AI 代理暂时不可用: {e}\n\n请稍后重试，或使用部门指令如「@前厅部 查行情 002156」。",
                "source": "dept:general|error"}


# ═══════════════════════════════════════════
# 路由表
# ═══════════════════════════════════════════

DEPT_MAP = {
    "前厅部": handle_front_office,
    "情报部": handle_intelligence,
    "工程部": handle_engineering,
    "财务部": handle_finance,
    "研发部": handle_rd,
    "读书郎": handle_reader,
}

# 每个部门的触发关键词 (用于模糊匹配)
DEPT_KEYWORDS = {
    "前厅部": ("前厅", "front", "行情", "持仓", "收盘", "复盘", "盘前", "晨报", "盘中"),
    "情报部": ("情报", "intel", "新闻", "大V", "涨停", "情绪", "雷达"),
    "工程部": ("工程", "eng", "健康", "lint", "错误", "error", "测试", "SEL"),
    "财务部": ("财务", "fin", "盈亏", "成本", "收益", "清仓", "结算"),
    "研发部": ("研发", "rd", "代码", "函数", "bug", "pattern"),
    "读书郎": ("读书", "read", "书单", "穿透", "笔记"),
}


def route_message(text: str, chat_id: str = "") -> dict:
    """解析消息，路由到对应部门处理器。

    解析优先级:
    1. 明确 @部门名 → 直接路由
    2. 关键词匹配 → 推测路由 (低置信度入队)
    3. 都不匹配 → 通用问答 (DeepSeek Agent)
    """
    text = text.strip()

    # ── 第1层: 明确 @部门名 ──
    for dept_name, handler in DEPT_MAP.items():
        if dept_name in text:
            # 提取部门名之后的文本作为查询
            idx = text.index(dept_name)
            query = text[idx + len(dept_name):].strip()
            action = _extract_action(query)
            params = _extract_params(query)
            result = handler(action, params, query)
            if result:
                return result

    # ── 第2层: 关键词模糊匹配 ──
    matched_depts = []
    for dept_name, keywords in DEPT_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text)
        if score >= 2:  # 至少匹配 2 个关键词
            matched_depts.append((dept_name, score))

    if matched_depts:
        matched_depts.sort(key=lambda x: -x[1])
        dept_name = matched_depts[0][0]
        handler = DEPT_MAP[dept_name]
        action = _extract_action(text)
        result = handler(action, _extract_params(text), text)
        if result:
            return result

    # ── 第3层: 通用问答 ──
    return handle_general(text, chat_id)


def _extract_action(text: str) -> str:
    """从文本提取动作关键词。"""
    action_map = {
        "行情": "行情", "价格": "行情", "报价": "行情", "多少钱": "行情",
        "持仓": "持仓", "仓位": "持仓", "组合": "持仓", "持有": "持仓",
        "新闻": "新闻", "快讯": "新闻", "头条": "新闻",
        "健康": "健康", "状态": "健康", "检查": "健康",
        "盈亏": "盈亏", "成本": "盈亏", "收益": "盈亏", "赚": "盈亏", "亏": "盈亏",
        "清仓": "已清仓", "结算": "已清仓", "已清": "已清仓",
        "错误": "错误", "报错": "错误", "故障": "错误",
        "bug": "错误", "error": "错误",
        "盘前": "盘前", "晨报": "盘前", "早报": "盘前",
        "lint": "lint", "SEL": "lint",
        "大V": "vv", "雷达": "vv", "视频": "vv",
        "书单": "进度", "进度": "进度", "读了": "进度",
        "读书": "穿透", "穿透": "穿透", "笔记": "穿透",
    }
    for kw, act in action_map.items():
        if kw in text:
            return act
    return ""


def _extract_params(text: str) -> dict:
    """从文本提取参数 (股票代码等)。"""
    import re
    params = {}
    m = re.search(r'\b(00\d{4}|30\d{4}|60\d{4}|68\d{4})\b', text)
    if m:
        params["code"] = m.group(0)
    # 提取关键词用于穿透检索
    params["keyword"] = text
    return params


# ── CLI 测试 ──
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    test_msgs = [
        "前厅部 查行情 002156",
        "情报部 今天有什么新闻",
        "工程部 系统健康检查",
        "财务部 持仓盈亏",
        "读书郎 读书进度",
        "帮我分析一下通富微电",
    ]
    for msg in test_msgs:
        print(f"\n{'='*60}")
        print(f"MSG: {msg}")
        result = route_message(msg, "test")
        print(f"DEPT: {result.get('source', '?')}")
        print(f"TITLE: {result.get('title', '?')}")
        print(f"CONTENT: {result['content'][:200]}...")
