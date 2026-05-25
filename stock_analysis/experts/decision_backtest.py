"""
T+5 决策回测 — 将 decision_log 中的预测与实际走势比对

数据流:
  decision_log (outcome=NULL)
    → 读 kline parquet (market_pool/kline/*.parquet)
    → 算 T+5 涨跌 vs 专家方向
    → add_outcome() 填充 outcome
"""
import json
import sys
from pathlib import Path
from datetime import datetime, timedelta

import pyarrow.parquet as pq
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from knowledge_db import get_db, add_outcome
from config import STOCK_DATA_DIR


BASE_DIR = Path(STOCK_DATA_DIR)
KLINE_DIR = BASE_DIR / "market_pool" / "kline"
PRICE_CHANGE_THRESHOLD = 0.005  # ±0.5% 作为"持平"阈值


def _load_kline(code: str) -> pd.DataFrame | None:
    """加载股票的日线 parquet 数据"""
    path = KLINE_DIR / f"{code}.parquet"
    if not path.exists():
        return None
    try:
        pf = pq.ParquetFile(path)
        df = pf.read().to_pandas()
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
            df = df.sort_values("date", ascending=True).reset_index(drop=True)
        return df
    except Exception:
        return None


def _find_closes_at(df: pd.DataFrame, target_dt: datetime) -> tuple[float | None, float | None]:
    """
    在日线 df 中找 target_dt 当天的 close 价和 5 个交易日后的 close 价。
    返回 (entry_close, exit_close) — 找不到则为 (None, None)
    """
    target_date = target_dt.date()

    # 找 target 日或之后最近的交易日
    mask = df["date"].dt.date >= target_date
    if not mask.any():
        return None, None
    entry_idx = mask.idxmax()
    entry_row = df.iloc[entry_idx]
    entry_close = entry_row["close"]

    # 找 entry 之后第5个交易日
    exit_idx = entry_idx + 5
    if exit_idx >= len(df):
        return entry_close, None  # 数据不足，无法回测
    exit_row = df.iloc[exit_idx]
    exit_close = exit_row["close"]

    return entry_close, exit_close


def _judge_outcome(direction: str, entry_close: float, exit_close: float) -> tuple[str, str]:
    """
    判断单一方向预测的正确/错误。
    返回 (outcome_label, detail_str)
    """
    change_pct = (exit_close - entry_close) / entry_close * 100

    if direction == "多":
        if change_pct >= PRICE_CHANGE_THRESHOLD * 100:
            return "正确", f"看多✓ 涨{change_pct:+.1f}%"
        else:
            return "错误", f"看多✗ 跌{change_pct:+.1f}%"
    elif direction == "空":
        if change_pct <= -PRICE_CHANGE_THRESHOLD * 100:
            return "正确", f"看空✓ 跌{change_pct:+.1f}%"
        else:
            return "错误", f"看空✗ 涨{change_pct:+.1f}%"
    elif direction in ("观望", "中性"):
        if abs(change_pct) <= PRICE_CHANGE_THRESHOLD * 100:
            return "正确", f"观望✓ 平{change_pct:+.1f}%"
        else:
            return "错误", f"观望✗ 变动{change_pct:+.1f}%"
    else:
        return "未知", f"方向'{direction}'无法判定"


def _build_review_notes(
    entry_close: float, exit_close: float,
    expert_results: list[dict], grader: dict
) -> str:
    """构造 review_notes 摘要"""
    change_pct = (exit_close - entry_close) / entry_close * 100
    correct = sum(1 for r in expert_results if r["result"] == "正确")
    total = len(expert_results)
    lines = [
        f"入场价:{entry_close:.2f} 出场价:{exit_close:.2f} 涨跌:{change_pct:+.1f}%",
        f"专家准确率:{correct}/{total}({correct/total*100:.0f}%)",
    ]
    for r in expert_results:
        lines.append(f"  {r['expert']}:{r['direction']} → {r['detail']}")
    if grader.get("summary"):
        lines.append(f"  Grader:{grader['summary'][:100]}")
    return "\n".join(lines)


def run_backtest(days: int = 90, limit: int = 500) -> dict:
    """
    遍历 decision_log 中 outcome=NULL 或 outcome='待回测' 的记录，做 T+5 回测。
    days: 只回测最近 N 天的决策
    limit: 最多处理条数
    返回汇总统计
    """
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d 00:00:00")

    with get_db() as db:
        rows = db.execute(
            """SELECT id, timestamp, stock_code, stock_name, factors
               FROM decision_log
               WHERE outcome = '待回测' AND timestamp >= ?
               ORDER BY timestamp DESC LIMIT ?""",
            (cutoff, limit),
        ).fetchall()

    total = len(rows)
    if total == 0:
        return {"total": 0, "message": "没有需要回测的记录"}

    updated = 0
    skipped = 0
    stats = {
        "total": total,
        "updated": 0,
        "no_kline": 0,
        "no_exit_price": 0,
        "expert_stats": {},
        "merged_stats": {"correct": 0, "wrong": 0, "total": 0},
    }

    for row in rows:
        decision_id = row["id"]
        ts_str = row["timestamp"]
        code = row["stock_code"]

        # 解析 factors JSON
        try:
            packet = json.loads(row["factors"])
        except (json.JSONDecodeError, TypeError):
            skipped += 1
            continue

        if not isinstance(packet, dict):
            skipped += 1
            continue

        experts = packet.get("expert_directions", packet.get("expert_outputs", []))
        grader = packet.get("grader", {})
        merged_dir = grader.get("merged_direction", "")

        # 解析决策时间
        try:
            dt = datetime.fromisoformat(ts_str)
        except (ValueError, TypeError):
            dt = datetime.now()

        # 读 kline
        df = _load_kline(code)
        if df is None:
            add_outcome(decision_id, "数据不足", f"无日线数据({code})")
            stats["no_kline"] += 1
            skipped += 1
            continue

        entry_close, exit_close = _find_closes_at(df, dt)
        if entry_close is None:
            add_outcome(decision_id, "数据不足", f"决策日{dt.date()}无行情")
            stats["no_kline"] += 1
            skipped += 1
            continue
        if exit_close is None:
            add_outcome(decision_id, "待回测", f"T+5数据尚未产生(最新数据仅到{df['date'].max().date()})")
            stats["no_exit_price"] += 1
            skipped += 1
            continue

        # 逐专家判定
        expert_results = []
        for e in experts:
            eid = e.get("expert", e.get("expert_id", "unknown"))
            direction = e.get("direction", "")
            if not direction:
                continue
            result, detail = _judge_outcome(direction, entry_close, exit_close)
            expert_results.append({
                "expert": eid,
                "direction": direction,
                "result": result,
                "detail": detail,
            })

            # 聚合专家统计
            if eid not in stats["expert_stats"]:
                stats["expert_stats"][eid] = {"correct": 0, "wrong": 0, "total": 0}
            if result == "正确":
                stats["expert_stats"][eid]["correct"] += 1
            else:
                stats["expert_stats"][eid]["wrong"] += 1
            stats["expert_stats"][eid]["total"] += 1

        # 合并方向判定
        if merged_dir:
            merged_result, _ = _judge_outcome(merged_dir, entry_close, exit_close)
            stats["merged_stats"]["total"] += 1
            if merged_result == "正确":
                stats["merged_stats"]["correct"] += 1
            else:
                stats["merged_stats"]["wrong"] += 1

        # 确定最终 outcome — 多数专家正确则为正确
        correct_count = sum(1 for r in expert_results if r["result"] == "正确")
        wrong_count = sum(1 for r in expert_results if r["result"] == "错误")
        if correct_count > wrong_count:
            outcome = "正确"
        elif wrong_count > correct_count:
            outcome = "错误"
        else:
            outcome = "模糊"

        review = _build_review_notes(entry_close, exit_close, expert_results, grader)
        add_outcome(decision_id, outcome, review)
        updated += 1
        stats["updated"] = updated

    # 计算每专家准确率
    for eid, est in stats["expert_stats"].items():
        est["accuracy"] = round(est["correct"] / est["total"] * 100, 1) if est["total"] > 0 else 0

    merged_t = stats["merged_stats"]["total"]
    if merged_t > 0:
        stats["merged_stats"]["accuracy"] = round(
            stats["merged_stats"]["correct"] / merged_t * 100, 1
        )

    print(f"\n回测完成: {updated} 条已填充 / {skipped} 条跳过 / {total} 条总处理")
    for eid, est in stats["expert_stats"].items():
        print(f"  {eid}: {est['accuracy']}% ({est['correct']}/{est['total']})")

    return stats


def run_backtest_and_report() -> dict:
    """运行回测并输出报告到 JSON 文件（供 Dreamer 和飞书使用）"""
    stats = run_backtest()
    report_path = Path("D:/1989n/stock_data") / "decision_backtest_report.json"
    report_path.write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return stats


def run_smart_backtest_and_dreamer() -> dict:
    """
    智能回测入口 — 供定时任务调用。
    1. 检查是否有待回测记录
    2. 执行 T+5 回测
    3. 如果有新填充的 outcome，自动触发 Dreamer 更新权重
    4. 返回执行报告
    """
    from experts.dreamer import run_dreamer

    stats = run_backtest()
    filled = stats.get("updated", 0)

    result = {
        "timestamp": datetime.now().isoformat(),
        "backtest": stats,
        "dreamer_triggered": False,
        "dreamer_result": None,
    }

    if filled > 0:
        print(f"\n[智能回测] 新填充 {filled} 条 outcome，自动触发 Dreamer...")
        dreamer_result = run_dreamer()
        result["dreamer_triggered"] = True
        result["dreamer_result"] = {
            "total_records": dreamer_result["total_records"],
            "merged_accuracy": dreamer_result["merged_accuracy"],
            "new_weights": dreamer_result["new_weights"],
        }
    else:
        print(f"\n[智能回测] 无新 outcome，跳过 Dreamer")

    # 写报告
    report_path = Path("D:/1989n/stock_data") / "decision_backtest_report.json"
    report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    s = run_smart_backtest_and_dreamer()
    print(f"\n报告写入: D:/1989n/stock_data/decision_backtest_report.json")
