"""
Sector Tracker — 每日板块数据采集 + 周度轮动分析

职责:
  collect_daily_snapshot() — 每日收盘后采集行业/概念/资金流向快照
  generate_rotation_report() — 基于多日数据生成轮动信号

数据流:
  akshare → stock_data/sector_daily/YYYY-MM-DD.json → 周对比 → 飞书推送
"""
import json
import sys
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))
from data_source_router import safe_akshare_call
from config import STOCK_DATA_DIR


SECTOR_DAILY_DIR = Path(STOCK_DATA_DIR) / "sector_daily"
SECTOR_WEEKLY_DIR = Path(STOCK_DATA_DIR) / "sector_weekly"
ALLOWED_SAMPLE_SIZE = 3  # 至少3天数据才参与周度计算


# ── 采集 ─────────────────────────────────────────────────────


def collect_daily_snapshot() -> dict:
    """每日板块数据采集：行业+概念涨跌排名 + 资金流向排名。

    使用 akshare 实时拉取，存到 stock_data/sector_daily/{date}.json。
    当天已存在则覆盖（幂等）。
    """
    SECTOR_DAILY_DIR.mkdir(parents=True, exist_ok=True)
    import akshare as ak

    today = datetime.now().strftime("%Y-%m-%d")
    result = {
        "date": today,
        "time": datetime.now().strftime("%H:%M:%S"),
        "industry_boards": [],
        "concept_boards": [],
        "industry_summary": {},  # THS 行业的净流入/成交量汇总
    }

    # ── 行业板块 (同花顺 THS summary: 90行业 + 涨跌幅/净流入/上涨数) ──
    try:
        df = safe_akshare_call(ak.stock_board_industry_summary_ths)
        if df is not None and not df.empty:
            df_sorted = df.sort_values("涨跌幅", ascending=False)
            boards = []
            total_net_inflow = 0
            for i, (_, row) in enumerate(df_sorted.iterrows()):
                inflow = _parse_float(row.get("净流入", 0))
                boards.append({
                    "name": str(row["板块"]),
                    "change_pct": _parse_float(row.get("涨跌幅", 0)),
                    "up_count": _parse_int(row.get("上涨家数", 0)),
                    "down_count": _parse_int(row.get("下跌家数", 0)),
                    "net_inflow": inflow,
                    "volume": str(row.get("总成交量", "")),
                    "amount": str(row.get("总成交额", "")),
                    "leader": str(row.get("领涨股", "")),
                    "rank": i + 1,
                })
                total_net_inflow += inflow
            result["industry_boards"] = boards
            result["industry_summary"] = {
                "total_sectors": len(boards),
                "total_net_inflow": round(total_net_inflow, 2),
                "up_sectors": sum(1 for b in boards if b["change_pct"] > 0),
                "down_sectors": sum(1 for b in boards if b["change_pct"] < 0),
            }
    except Exception as e:
        _log_warning(f"行业(THS)采集失败: {e}")

    # ── 概念板块 (同花顺: 375概念名 + 30热概念摘要) ──
    try:
        df = safe_akshare_call(ak.stock_board_concept_name_ths)
        if df is not None and not df.empty:
            result["concept_total"] = len(df)
            result["concept_names"] = df["name"].tolist()
    except Exception as e:
        _log_warning(f"概念名称获取失败: {e}")

    try:
        df = safe_akshare_call(ak.stock_board_concept_summary_ths)
        if df is not None and not df.empty:
            result["hot_concepts"] = [
                {
                    "name": row["概念名称"],
                    "driver": str(row.get("驱动事件", "")),
                    "leader": str(row.get("龙头股", "")),
                    "member_count": _parse_int(row.get("成分股数量", 0)),
                }
                for _, row in df.iterrows()
            ]
    except Exception as e:
        _log_warning(f"热概念摘要获取失败: {e}")

    # ── Fallback: Tencent sector spot (49个板块实时行情) ──
    if not result["industry_boards"]:
        try:
            df = safe_akshare_call(ak.stock_sector_spot)
            if df is not None and not df.empty:
                result["industry_boards"] = [
                    {
                        "name": row["板块"],
                        "change_pct": _parse_float(row.get("涨跌幅", 0)),
                        "leader": str(row.get("股票名称", "")),
                        "rank": i + 1,
                    }
                    for i, (_, row) in enumerate(df_sorted.iterrows())
                ]
        except Exception as e:
            _log_warning(f"腾讯板块回退失败: {e}")

    # 写文件
    path = SECTOR_DAILY_DIR / f"{today}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[sector_tracker] 已采集 {today}: {len(result['industry_boards'])}行业 "
          f"[source: THS] {path}")

    return result


def _parse_float(val) -> float:
    """安全解析浮点数（处理 akshare 返回的各种格式）"""
    try:
        return float(str(val).replace(",", "").replace("亿", "").replace("万", ""))
    except (ValueError, TypeError):
        return 0.0


def _parse_int(val) -> int:
    """安全解析整数"""
    try:
        return int(str(val).replace(",", ""))
    except (ValueError, TypeError):
        return 0


# ── 周度轮动分析 ──────────────────────────────────────────────


def generate_rotation_report(days: int = 14) -> dict:
    """基于近 N 天的日快照生成轮动分析报告。

    days: 回溯天数（通常 14 = 两周）
    返回含轮动信号的 dict，自动写入 JSON + 飞书推送
    """
    from daily_task import send_feishu_message, date_today

    SECTOR_WEEKLY_DIR.mkdir(parents=True, exist_ok=True)

    # 1. 加载所有日快照
    snapshots = _load_snapshots(days)
    if len(snapshots) < 2:
        msg = f"数据不足: 仅 {len(snapshots)} 天快照, 需要至少 2 天"
        print(f"[sector_tracker] {msg}")
        return {"error": msg, "snapshot_count": len(snapshots)}

    # 2. 按周分组
    w1_snapshots, w2_snapshots = _split_into_two_weeks(snapshots)
    report_date = datetime.now().strftime("%Y-%m-%d")

    # 3. 计算行业动量
    sector_momentum = _calc_sector_momentum(w1_snapshots, w2_snapshots)

    # 4. 检测轮动信号
    signals = _detect_rotation_signals(sector_momentum)

    # 5. 计算轮动速度
    rotation_speed = _calc_rotation_speed(w1_snapshots, w2_snapshots)

    # 6. 热点/冷门
    hot = [s for s in sector_momentum if s.get("momentum_score", 0) >= 70][:8]
    cold = [s for s in sector_momentum if s.get("momentum_score", 0) <= 30][:8]

    report = {
        "report_date": report_date,
        "period": f"{snapshots[0]['date']}~{snapshots[-1]['date']}",
        "snapshot_count": len(snapshots),
        "rotation_signals": signals[:10],
        "sector_momentum": sorted(sector_momentum, key=lambda x: x.get("momentum_score", 0), reverse=True),
        "rotation_speed": round(rotation_speed, 2),
        "hot_sectors": hot,
        "cold_sectors": cold,
    }

    # 写 JSON
    report_path = SECTOR_WEEKLY_DIR / f"rotation_report_{report_date}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    # 飞书推送
    feishu_ok = _push_rotation_report(report)

    print(f"\n[sector_tracker] 轮动报告: {report_path}")
    print(f"  周期: {report['period']}")
    print(f"  快照数: {len(snapshots)}天")
    print(f"  轮动速度: {rotation_speed:.0%}")
    print(f"  信号数: {len(signals)}")
    print(f"  热点: {[s['name'] for s in hot]}")
    print(f"  冷门: {[s['name'] for s in cold]}")
    print(f"  飞书推送: {'成功' if feishu_ok else '失败'}")

    return report


def _load_snapshots(days: int) -> list[dict]:
    """按日期排序加载日快照"""
    snapshots = []
    cutoff = datetime.now() - timedelta(days=days)
    for path in sorted(SECTOR_DAILY_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            snapshots.append(data)
        except (json.JSONDecodeError, Exception):
            continue
    # 只保留 cutoff 之后的
    snapshots = [s for s in snapshots if s.get("date", "") >= cutoff.strftime("%Y-%m-%d")]
    return snapshots


def _split_into_two_weeks(snapshots: list[dict]) -> tuple[list[dict], list[dict]]:
    """将快照按最近两周和更早一周拆分（如果有 2+ 周数据）"""
    if len(snapshots) <= 5:
        # 数据不足一周: 前半/后半对比
            mid = len(snapshots) // 2
            return snapshots[:mid], snapshots[mid:]

    # 按日期分布拆分
    dates = sorted(set(s["date"] for s in snapshots))
    mid_idx = len(dates) // 2
    # 至少 2 天在第二组
    if len(dates) - mid_idx < 2:
        mid_idx = len(dates) - 2
    cutoff_date = dates[mid_idx]

    week1 = [s for s in snapshots if s["date"] < cutoff_date]
    week2 = [s for s in snapshots if s["date"] >= cutoff_date]
    if not week1:
        week1 = week2[:1]
        week2 = week2[1:]
    return week1, week2


def _calc_sector_momentum(w1: list[dict], w2: list[dict]) -> list[dict]:
    """计算每行业板块的动量得分 (0-100)

    动量得分 = (周排名变化权重 + 资金流向排名变化权重 + 平均涨跌幅权重) * 归一化
    """
    w1_rank = _build_rank_map(w1, "industry_boards")
    w2_rank = _build_rank_map(w2, "industry_boards")
    w1_flow = _build_flow_rank_map(w1)
    w2_flow = _build_flow_rank_map(w2)

    all_sectors = set(w2_rank.keys()) | set(w1_rank.keys())
    results = []

    for sector in all_sectors:
        r2 = w2_rank.get(sector)
        r1 = w1_rank.get(sector)
        f2 = w2_flow.get(sector)
        f1 = w1_flow.get(sector)

        if r2 is None:
            continue

        # 排名变化（正数 = 上升）
        rank_change = (r1.get("avg_rank", 50) - r2.get("avg_rank", 50)) if r1 else 0

        # 本周平均涨跌幅
        avg_change = r2.get("avg_change", 0)

        # 资金流向排名变化
        flow_change = (f1.get("avg_rank", 50) - f2.get("avg_rank", 50)) if f1 and f2 else 0

        # 动量得分 (0-100)
        score = min(100, max(0,
            35 * _normalize(rank_change, -40, 40) +
            25 * _normalize(avg_change, -3, 4) +
            25 * _normalize(flow_change, -30, 30) +
            15 * _normalize(r2.get("sample_count", 1), 0, 5)
        ))

        results.append({
            "name": sector,
            "avg_change": round(avg_change, 2),
            "rank_change": rank_change,
            "flow_rank_change": flow_change,
            "week1_rank": r1.get("avg_rank", "N/A") if r1 else "N/A",
            "week2_rank": r2.get("avg_rank", "N/A"),
            "momentum_score": round(score),
        })

    return results


def _build_rank_map(snapshots: list[dict], board_key: str = "industry_boards") -> dict:
    """构建板块→{平均涨跌幅, 平均排名, 样本数} 的映射"""
    accum = defaultdict(lambda: {"changes": [], "ranks": []})
    for snap in snapshots:
        for board in snap.get(board_key, []):
            name = board["name"]
            accum[name]["changes"].append(board.get("change_pct", 0))
            accum[name]["ranks"].append(board.get("rank", 50))
    return {
        name: {
            "avg_change": sum(v["changes"]) / len(v["changes"]),
            "avg_rank": sum(v["ranks"]) / len(v["ranks"]),
            "sample_count": len(v["changes"]),
        }
        for name, v in accum.items()
        if len(v["changes"]) >= ALLOWED_SAMPLE_SIZE
    }


def _build_flow_rank_map(snapshots: list[dict]) -> dict:
    """构建资金流向排名映射（基于 industry_boards 中的 net_inflow）"""
    accum = defaultdict(list)
    for snap in snapshots:
        for board in snap.get("industry_boards", []):
            inflow = board.get("net_inflow", 0)
            name = board["name"]
            accum[name].append(inflow)
    return {
        name: {
            "avg_rank": sum(v) / len(v) if v else 50
        }
        for name, v in accum.items()
    }


def _detect_rotation_signals(momentum: list[dict]) -> list[dict]:
    """检测轮动信号"""
    signals = []
    sorted_by_rank_change = sorted(momentum, key=lambda x: x.get("rank_change", 0), reverse=True)

    # 资金迁移: 上周靠后本周靠前
    for s in sorted_by_rank_change[:5]:
        if s.get("week1_rank", "N/A") != "N/A":
            try:
                w1 = float(s["week1_rank"]) if s["week1_rank"] != "N/A" else 50
                w2 = float(s["week2_rank"]) if s["week2_rank"] != "N/A" else 50
                if w1 >= 15 and w2 <= 10 and s.get("rank_change", 0) >= 5:
                    signals.append({
                        "type": "资金迁移",
                        "sector": s["name"],
                        "rank_change": f"+{int(s['rank_change'])}",
                        "detail": f"上周第{int(w1)}→本周第{int(w2)}, 动量{int(s['momentum_score'])}",
                    })
            except (ValueError, TypeError):
                pass

    # 持续性热点
    for s in momentum[:5]:
        if s.get("week1_rank", "N/A") != "N/A":
            try:
                w1 = float(s["week1_rank"]) if s["week1_rank"] != "N/A" else 50
                w2 = float(s["week2_rank"]) if s["week2_rank"] != "N/A" else 50
                if w1 <= 10 and w2 <= 8:
                    signals.append({
                        "type": "持续热点",
                        "sector": s["name"],
                        "rank_change": f"+{int(s['rank_change'])}" if s["rank_change"] > 0 else str(int(s["rank_change"])),
                        "detail": f"连续两周排名前10, 本周第{int(w2)}, 动量{int(s['momentum_score'])}",
                    })
            except (ValueError, TypeError):
                pass

    # 退潮: 上周前排本周大幅下滑
    for s in sorted_by_rank_change[-5:]:
        if s.get("week1_rank", "N/A") != "N/A" and s.get("rank_change", 0) < -5:
            try:
                w1 = float(s["week1_rank"]) if s["week1_rank"] != "N/A" else 50
                w2 = float(s["week2_rank"]) if s["week2_rank"] != "N/A" else 50
                if w1 <= 10:
                    signals.append({
                        "type": "退潮",
                        "sector": s["name"],
                        "rank_change": str(int(s["rank_change"])),
                        "detail": f"上周第{int(w1)}→本周第{int(w2)}, 回落{abs(s['rank_change'])}位",
                    })
            except (ValueError, TypeError):
                pass

    return signals


def _calc_rotation_speed(w1: list[dict], w2: list[dict]) -> float:
    """计算轮动速度: 上周前10本周还在前10的比例"""
    w1_top = set()
    for snap in w1:
        for board in snap.get("industry_boards", [])[:10]:
            w1_top.add(board["name"])

    w2_top = set()
    for snap in w2:
        for board in snap.get("industry_boards", [])[:10]:
            w2_top.add(board["name"])

    if not w1_top:
        return 0.5

    overlap = w1_top & w2_top
    return 1 - (len(overlap) / len(w1_top))


def _normalize(value: float, min_val: float, max_val: float) -> float:
    """将值线性归一化到 [0, 1]"""
    if max_val <= min_val:
        return 0.5
    clamped = max(min_val, min(max_val, value))
    return (clamped - min_val) / (max_val - min_val)


def _push_rotation_report(report: dict) -> bool:
    """推送轮动报告到飞书"""
    try:
        from daily_task import send_feishu_message
        lines = [f"**板块轮动报告** | {report['report_date']}\\n"]
        lines.append(f"周期: {report['period']} | 轮动速度: {report['rotation_speed']:.0%}\\n")

        if report.get("rotation_signals"):
            lines.append("\\n**轮动信号**\\n")
            for s in report["rotation_signals"][:6]:
                lines.append(f"- [{s['type']}] {s['sector']} ({s['rank_change']}): {s['detail']}\\n")

        if report.get("hot_sectors"):
            lines.append("\\n**热点板块**\\n")
            for s in report["hot_sectors"][:5]:
                lines.append(f"- {s['name']}: 动量{s['momentum_score']} 涨跌{s['avg_change']:+.1f}%\\n")

        if report.get("cold_sectors"):
            lines.append("\\n**冷门板块**\\n")
            for s in report["cold_sectors"][:5]:
                lines.append(f"- {s['name']}: 动量{s['momentum_score']} 涨跌{s['avg_change']:+.1f}%\\n")

        return send_feishu_message(
            f"板块轮动 | {report['report_date']}",
            "".join(lines),
        )
    except Exception as e:
        _log_warning(f"飞书推送失败: {e}")
        return False


def _log_warning(msg: str):
    """统一警告输出"""
    print(f"[sector_tracker] WARNING: {msg}")


# ── 独立入口 ────────────────────────────────────────────────


if __name__ == "__main__":
    import sys as _sys
    if len(_sys.argv) > 1 and _sys.argv[1] == "report":
        generate_rotation_report()
    else:
        collect_daily_snapshot()
