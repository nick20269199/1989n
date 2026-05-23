"""Daily task command: tech_scan — run_tech_scan"""
import json
from datetime import datetime

from daily_task import (
    logger, ensure_data_dir, timestamp_now, send_feishu_message,
    load_portfolio, _SKILL_AVAILABLE, scan_vcp, scan_watchlist_tech,
)


def run_tech_scan():
    """技术形态扫描 (15:30 执行)"""
    logger.info("=" * 50)
    logger.info("执行 tech_scan — 技术形态扫描")
    ensure_data_dir()

    timestamp = timestamp_now()
    holdings = load_portfolio()
    codes = [h["code"] for h in holdings]

    logger.info(f"运行 VCP 扫描 ({len(codes)} 只股票)...")
    if _SKILL_AVAILABLE:
        vcp_result = scan_vcp(codes)
    else:
        vcp_result = {"scan_type": "vcp", "param": None, "time": timestamp, "count": 0, "results": []}

    vcp_result["time"] = timestamp
    vcp_path = ensure_data_dir() / "scan_vcp_default.json"
    vcp_path.write_text(json.dumps(vcp_result, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"VCP 输出: {vcp_path} ({vcp_result.get('count', 0)} 个信号)")

    logger.info(f"运行技术指标扫描...")
    if _SKILL_AVAILABLE:
        tech_result = scan_watchlist_tech(codes)
    else:
        tech_result = {"scan_type": "watchlist_tech", "param": None, "time": timestamp, "count": 0, "results": []}

    tech_result["time"] = timestamp
    tech_path = ensure_data_dir() / "scan_watchlist_tech_default.json"
    tech_path.write_text(json.dumps(tech_result, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"技术指标 输出: {tech_path} ({tech_result.get('count', 0)} 个信号)")

    feishu_lines = []
    feishu_lines.append(f"**VCP形态扫描** — {vcp_result.get('count', 0)} 个信号\n")
    for r in vcp_result.get("results", [])[:8]:
        feishu_lines.append(
            f"- {r.get('code','')}: {r.get('phase','')} "
            f"评分{r.get('score','')} | 现价{r.get('price','')}"
        )

    feishu_lines.append(f"\n**技术指标扫描** — {tech_result.get('count', 0)} 个信号\n")
    for r in tech_result.get("results", [])[:8]:
        feishu_lines.append(
            f"- {r.get('code','')}: {r.get('trend','')} "
            f"RSI{r.get('rsi','')} | 量比{r.get('vol_ratio','')}"
        )

    ok = send_feishu_message(f"技术扫描 | {datetime.now().strftime('%m/%d %H:%M')}", "\n".join(feishu_lines), chat_id="closing")
    logger.info(f"飞书发送: {'成功' if ok else '失败'}")

    logger.info("tech_scan 完成")
