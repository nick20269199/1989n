"""Lead Orchestrator — Multiagent 交易分析调度器

工作流：
1. 接收触发（symbol + mode）
2. 准备共享数据（market_pool / MCP / SQLite）
3. 并行启动专家 → wait全部完成
4. 汇总专家输出 → 送Grader
5. 通过 → 输出决策包；未通过 → 记录失败

用法：
    python -m stock_analysis.experts.lead --symbol 002156 --name 通富微电
    python -m stock_analysis.experts.lead --portfolio  # 全持仓扫描
"""

import argparse
import json
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from experts.base import ExpertOutput, repair_expert
from experts.config import (
    OUTPUT_DIR, EXPERT_WEIGHTS, EXPERT_TIMEOUT, LEAD_TIMEOUT,
    PORTFOLIO_FILE, STOCK_DB,
)
from experts.grader import grade, save_grade_result, GRADER_ID
from lib.tdx_finance import get_financial_metrics as _get_financial_metrics
from lib.market_stats import get_market_summary as _get_market_summary

# Expert registry — lazy imports inside functions to avoid circular deps

logger = logging.getLogger("experts.lead")

# --- Expert registry: (id, analyze_func) — lazy loaded ---
EXPERT_REGISTRY = []

def _load_experts():
    """Import expert modules lazily at first use."""
    global EXPERT_REGISTRY
    if EXPERT_REGISTRY:
        return
    for module_name, exp_id in [
        ("experts.expert1_tech", "expert1_tech"),
        ("experts.expert2_money", "expert2_money"),
        ("experts.expert3_sentiment", "expert3_sentiment"),
        ("experts.expert4_macro", "expert4_macro"),
        ("experts.expert5_risk", "expert5_risk"),
    ]:
        try:
            mod = __import__(module_name, fromlist=["analyze"])
            EXPERT_REGISTRY.append((exp_id, mod.analyze))
        except ImportError as e:
            logger.warning(f"{exp_id} not loaded: {e}")


def load_portfolio() -> list[dict]:
    """Load current holdings from portfolio.json."""
    if not PORTFOLIO_FILE.exists():
        logger.error(f"Portfolio file not found: {PORTFOLIO_FILE}")
        return []
    data = json.loads(PORTFOLIO_FILE.read_text(encoding="utf-8"))
    return data.get("holdings", [])


def prepare_data_for_expert(symbol: str, name: str, mode: str = "full") -> dict:
    """Prepare shared data context from local data sources.

    Phase 0: reads from market_pool kline parquet files.
    Will be enhanced with MCP data in Phase 1.
    """
    import pyarrow.parquet as pq
    import pandas as pd

    data = {
        "symbol": symbol,
        "name": name,
        "mode": mode,
        "kline": {},
        "recent_news": [],
        "market_state": "unknown",
    }

    # 1. Read kline from market_pool
    kline_path = Path("D:/1989n/stock_data/market_pool/kline") / f"{symbol}.parquet"
    if kline_path.exists():
        try:
            pf = pq.ParquetFile(kline_path)
            df = pf.read().to_pandas()

            # Sort by date descending, take last 120 bars
            if "date" in df.columns:
                df = df.sort_values("date", ascending=False)

            # Recent 5 days
            recent = df.head(5).to_dict(orient="records")
            # Last 120 days for MA calculation
            history = df.head(120).to_dict(orient="records")

            # Compute basic stats
            closes = [r.get("close", 0) for r in recent if r.get("close")]
            volumes = [r.get("volume", 0) for r in recent if r.get("volume")]

            # Last 20 days avg volume
            hist20 = df.head(20)
            avg_volume_20 = hist20["volume"].mean() if "volume" in hist20.columns else 0
            latest_volume = volumes[0] if volumes else 0

            # Simple trend detection
            ma5 = df.head(5)["close"].mean() if "close" in df.columns else 0
            ma20 = df.head(20)["close"].mean() if "close" in df.columns else 0
            ma60 = df.head(60)["close"].mean() if len(df) >= 60 and "close" in df.columns else 0

            latest_price = closes[0] if closes else 0

            data["kline"] = {
                "latest_price": latest_price,
                "recent_5d": recent,
                "total_bars": len(df),
                "date_range": f"{df['date'].iloc[-1] if len(df) > 0 else '?'} ~ {df['date'].iloc[0] if len(df) > 0 else '?'}",
                "ma5": round(ma5, 2),
                "ma20": round(ma20, 2),
                "ma60": round(ma60, 2),
                "volume_ratio": round(latest_volume / avg_volume_20, 2) if avg_volume_20 > 0 else 0,
                "latest_close": latest_price,
                "high_5d": max(r.get("high", 0) for r in recent),
                "low_5d": min(r.get("low", 99999) for r in recent),
            }

            # Determine market state
            if latest_price > ma20 and volumes and volumes[0] > avg_volume_20 * 1.2:
                data["market_state"] = "trend"
            elif latest_price < ma20 * 0.95 and volumes and volumes[0] > avg_volume_20 * 1.5:
                data["market_state"] = "crisis"
            elif abs(latest_price - ma20) / ma20 < 0.03:
                data["market_state"] = "oscillating"
            else:
                data["market_state"] = "unknown"

        except Exception as e:
            logger.warning(f"Failed to read kline for {symbol}: {e}")

    # 2. Read recent news from SQLite
    try:
        import sqlite3
        conn = sqlite3.connect(STOCK_DB)
        rows = conn.execute(
            "SELECT title, pub_time, source, sentiment, category FROM news WHERE title LIKE ? ORDER BY pub_time DESC LIMIT 5",
            (f"%{name}%",)
        ).fetchall()
        conn.close()
        data["recent_news"] = [
            {"title": r[0], "time": r[1], "source": r[2], "sentiment": r[3], "category": r[4]}
            for r in rows
        ]
    except Exception as e:
        logger.warning(f"Failed to read news for {symbol}: {e}")

    # 3. Financial metrics from TDX base.dbf (local, zero network)
    fin = _get_financial_metrics(symbol)
    if fin:
        data["financial"] = fin

    # 4. Holdings for risk/concentration checks
    holdings = load_portfolio()
    data["holdings"] = holdings

    # 4b. Holding thesis (core logic for each position)
    thesis_path = Path("D:/1989n/stock_analysis/data/holdings_thesis.json")
    thesis_data = json.loads(thesis_path.read_text(encoding="utf-8")) if thesis_path.exists() else {}
    data["holding_thesis"] = thesis_data.get(symbol, {}).get("thesis", "")

    # 5. Market-wide stats (from all .day files, ~0.9s, cached)
    summary = _get_market_summary()
    data["market_summary"] = summary

    return data


def build_decision_packet(symbol: str, name: str,
                          expert_outputs: list[dict],
                          grader_result: dict) -> dict:
    """Build the final decision packet from expert outputs + grader."""
    # Merge expert directions with weights
    directions = []
    for eo in expert_outputs:
        if eo.get("status") == "done" and eo.get("direction"):
            wt = EXPERT_WEIGHTS.get(eo["expert_id"], 1.0)
            directions.append({
                "expert": eo["expert_id"],
                "direction": eo["direction"],
                "confidence": eo.get("confidence", 0),
                "weight": wt,
            })

    packet = {
        "symbol": symbol,
        "name": name,
        "timestamp": datetime.now().isoformat(),
        "pipeline_status": "passed" if grader_result.get("passed") else "rejected",
        "grader": {
            "passed": grader_result.get("passed", False),
            "score": grader_result.get("average_score", 0),
            "scores": grader_result.get("scores", {}),
            "failures": grader_result.get("failures", []),
            "merged_direction": grader_result.get("merged_direction", "不确定"),
            "merged_confidence": grader_result.get("merged_confidence", 0),
            "summary": grader_result.get("summary", ""),
            "_raw": grader_result.get("_raw_grader", ""),
        },
        "expert_directions": directions,
        "expert_count": len(expert_outputs),
        "expert_success": sum(1 for eo in expert_outputs if eo.get("status") == "done"),
        "expert_errors": sum(1 for eo in expert_outputs if eo.get("status") == "error"),
        "mode": "full",
        "actionable": grader_result.get("passed", False) and grader_result.get("average_score", 0) >= 0.6,
    }

    return packet


def save_decision_packet(packet: dict) -> Path:
    """Save decision packet to output directory."""
    d = OUTPUT_DIR / "decision_packets"
    d.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = d / f"{packet['symbol']}_{ts}.json"
    path.write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def log_to_sqlite(symbol: str, name: str, packet: dict):
    """Log decision to stock.db decision_log table."""
    try:
        import sqlite3
        conn = sqlite3.connect(STOCK_DB)
        conn.execute(
            "INSERT INTO decision_log (stock_code, stock_name, timestamp, decision_type, summary, confidence, factors) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                symbol, name,
                packet["timestamp"],
                packet["pipeline_status"],
                packet["grader"].get("summary", ""),
                str(packet["grader"].get("merged_confidence", 0)),
                json.dumps(packet, ensure_ascii=False),
            )
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"Failed to log decision: {e}")


def run_single(symbol: str, name: str = "", mode: str = "full") -> Optional[dict]:
    """Run the full pipeline for a single symbol."""
    _load_experts()  # ensure experts are loaded
    logger.info(f"Starting pipeline for {symbol} {name} mode={mode}")

    start = time.time()

    # 1. Prepare shared data
    data_context = prepare_data_for_expert(symbol, name, mode)
    market_state = data_context.get("market_state", "unknown")

    # 2. Run experts in parallel
    expert_outputs = []
    with ThreadPoolExecutor(max_workers=len(EXPERT_REGISTRY)) as executor:
        future_map = {}
        for expert_id, analyze_func in EXPERT_REGISTRY:
            weight = EXPERT_WEIGHTS.get(expert_id, 1.0)
            if weight <= 0:
                logger.info(f"Skipping {expert_id} (weight={weight})")
                continue
            future = executor.submit(
                analyze_func, symbol, name, data_context, market_state, mode
            )
            future_map[future] = expert_id

        for future in as_completed(future_map, timeout=EXPERT_TIMEOUT):
            expert_id = future_map[future]
            try:
                result = future.result()
                expert_outputs.append(result)
                logger.info(f"{expert_id}: done (status={result.get('status')}, dir={result.get('direction', '?')})")
            except Exception as e:
                logger.error(f"{expert_id}: failed - {e}")
                expert_outputs.append({
                    "expert_id": expert_id,
                    "symbol": symbol,
                    "status": "error",
                    "error": str(e),
                })

    # 3. Run grader
    thesis = data_context.get("holding_thesis", "")
    grader_result = grade(symbol, name, expert_outputs, thesis=thesis)
    save_grade_result(symbol, name, grader_result)

    # 3b. Repair loop — if grader didn't pass, try repairing LLM-based experts
    REPAIRABLE_EXPERTS = {"expert1_tech", "expert2_money", "expert3_sentiment"}
    MAX_REPAIR_ROUNDS = 2
    repair_round = 0

    while not grader_result.get("passed") and repair_round < MAX_REPAIR_ROUNDS:
        repair_round += 1
        failures = grader_result.get("failures", [])
        grader_summary = grader_result.get("summary", "")
        scores = grader_result.get("scores", {})

        # Identify failing dimensions
        weak_dims = [dim for dim, score in scores.items()
                     if isinstance(score, (int, float)) and score < 0.5]
        feedback_parts = list(failures)
        if weak_dims:
            feedback_parts.append(f"低分维度: {', '.join(weak_dims)}")
        if grader_summary:
            feedback_parts.append(f"综合意见: {grader_summary}")
        feedback_text = "\n".join(feedback_parts)

        logger.info(f"Repair round {repair_round}/{MAX_REPAIR_ROUNDS}: repairing LLM experts. Failures: {len(failures)}, weak dims: {weak_dims}")

        # Repair each LLM-based expert
        repaired_count = 0
        for i, eo in enumerate(expert_outputs):
            if eo.get("status") != "done":
                continue
            eid = eo.get("expert_id", "")
            if eid not in REPAIRABLE_EXPERTS:
                continue

            # Wrap dict back into ExpertOutput for repair
            orig = ExpertOutput.from_dict(eo)
            repaired = repair_expert(orig, feedback_text, data_context, market_state)
            if repaired and repaired.status == "done":
                expert_outputs[i] = repaired.to_dict()
                repaired_count += 1
                logger.info(f"  Repaired {eid}: dir={repaired.direction}, conf={repaired.confidence}")

        if repaired_count == 0:
            logger.warning("No experts repaired in this round, aborting repair loop")
            break

        # Re-grade with repaired outputs
        grader_result = grade(symbol, name, expert_outputs, thesis=thesis)
        save_grade_result(symbol, name, grader_result)
        logger.info(f"Re-grade after repair round {repair_round}: passed={grader_result.get('passed')}, score={grader_result.get('average_score', 0):.2f}")

    # 4. Build decision packet
    packet = build_decision_packet(symbol, name, expert_outputs, grader_result)
    packet["repair_rounds"] = repair_round
    packet_path = save_decision_packet(packet)
    packet["_output_path"] = str(packet_path)

    # 5. Log to SQLite
    log_to_sqlite(symbol, name, packet)

    elapsed = time.time() - start
    packet["elapsed_seconds"] = round(elapsed, 1)
    logger.info(f"Pipeline completed for {symbol} in {elapsed:.1f}s: {packet['pipeline_status']}")

    return packet


def run_portfolio(mode: str = "full") -> list[dict]:
    """Run pipeline for all holdings in portfolio."""
    holdings = load_portfolio()
    if not holdings:
        logger.warning("No holdings found in portfolio")
        return []

    results = []
    for h in holdings:
        result = run_single(h["code"], h["name"], mode)
        if result:
            results.append(result)

    # Save portfolio summary
    summary = {
        "timestamp": datetime.now().isoformat(),
        "total": len(results),
        "passed": sum(1 for r in results if r.get("pipeline_status") == "passed"),
        "rejected": sum(1 for r in results if r.get("pipeline_status") == "rejected"),
        "results": [{"symbol": r["symbol"], "name": r["name"],
                      "status": r["pipeline_status"],
                      "score": r["grader"]["score"],
                      "direction": r["grader"]["merged_direction"],
                      "actionable": r.get("actionable", False)} for r in results],
    }
    d = OUTPUT_DIR / "portfolio_scans"
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"portfolio_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"Portfolio scan complete: {summary['passed']}/{summary['total']} passed")

    return results


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="Lead Orchestrator - Multiagent Analysis Pipeline")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--symbol", type=str, help="Stock code e.g. 002156")
    group.add_argument("--portfolio", action="store_true", help="Scan all portfolio holdings")
    parser.add_argument("--name", type=str, default="", help="Stock name")
    parser.add_argument("--mode", type=str, default="full", choices=["full", "quick", "risk"],
                        help="Analysis mode (default: full)")

    args = parser.parse_args()

    if args.portfolio:
        results = run_portfolio(args.mode)
        # Print summary
        print(f"\n=== Portfolio Scan Results ===")
        for r in results:
            status_icon = "✅" if r.get("actionable") else "❌" if r["pipeline_status"] == "rejected" else "⚠️"
            print(f"  {status_icon} {r['name']}({r['symbol']}): "
                  f"score={r['grader']['score']:.2f} dir={r['grader']['merged_direction']} "
                  f"actionable={r.get('actionable', False)}")
    elif args.symbol:
        result = run_single(args.symbol, args.name, args.mode)
        if result:
            status = "✅" if result.get("actionable") else "❌" if result["pipeline_status"] == "rejected" else "⚠️"
            print(f"\n{status} {result['name']}({result['symbol']})")
            print(f"  状态: {result['pipeline_status']}")
            print(f"  Grader评分: {result['grader']['score']:.2f}")
            print(f"  综合方向: {result['grader']['merged_direction']}")
            print(f"  置信度: {result['grader']['merged_confidence']:.2f}")
            print(f"  摘要: {result['grader']['summary']}")
            print(f"  耗时: {result['elapsed_seconds']:.1f}s")
            print(f"  输出: {result['_output_path']}")
            if result.get("grader", {}).get("failures"):
                print(f"  失败原因: {result['grader']['failures']}")


if __name__ == "__main__":
    main()
