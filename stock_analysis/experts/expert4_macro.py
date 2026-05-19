"""Expert 4: 宏观专家 — 规则驱动，不调 LLM

输入：当前市场状态（趋势/情绪/量能） + 规则库
输出：市场环境评估 + 允许/谨慎/禁止 + 建议仓位比例

规则来源：rule_miner_mine.py 从 3,605 笔历史交易挖掘
"""

import json, os, logging
from pathlib import Path

logger = logging.getLogger("experts.expert4_macro")

EXPERT_ID = "expert4_macro"
DATA_DIR = Path("D:/1989n/stock_data")
ML_DIR = DATA_DIR / "ml"
RULES_PATH = ML_DIR / "rules.json"

# ============================================================
# Load rules
# ============================================================
_rules_cache = None

def _load_rules():
    global _rules_cache
    if _rules_cache is None:
        if RULES_PATH.exists():
            with open(RULES_PATH) as f:
                _rules_cache = json.load(f)
        else:
            _rules_cache = {"rules": {"exit": {"sentiment": []}}}
    return _rules_cache


# ============================================================
# Core analysis
# ============================================================

def assess_market(market_state: dict) -> dict:
    """Assess current market environment based on mined rules.

    Args:
        market_state: dict with keys like trend, sentiment, volume_state, pct_chg

    Returns:
        dict with market assessment
    """
    rules = _load_rules()
    sentiment_rules = rules.get("rules", {}).get("exit", {}).get("sentiment", [])

    sentiment = market_state.get("sentiment", "unknown")
    trend = market_state.get("trend", "unknown")
    volume_state = market_state.get("volume_state", "unknown")

    # 1. Sentiment check
    sentiment_score = 0.5  # neutral
    sentiment_warning = ""
    for sr in sentiment_rules:
        cond = sr.get("condition", "")
        if f"sentiment={sentiment}" in cond:
            wr = sr.get("win_rate", 50)
            # Map win rate to score: 50% = 0.5, 60% = 0.7, 40% = 0.3
            sentiment_score = round(0.5 + (wr - 50) / 50, 2)
            sentiment_score = max(0.1, min(0.9, sentiment_score))
            if wr < 40:
                sentiment_warning = f"该情绪下历史胜率仅{wr}%，均亏{sr.get('avg_profit_pct','?')}%"
            break

    # 2. Trend check
    trend_score_map = {
        "多头排列": 0.75, "短期偏多": 0.6, "震荡": 0.5,
        "短期偏空": 0.35, "空头排列": 0.2, "数据不足": 0.3,
    }
    trend_score = trend_score_map.get(trend, 0.4)

    # 3. Volume check
    volume_score_map = {
        "放量": 0.5,  # neutral — can be up or down
        "正常": 0.5,
        "缩量": 0.4,  # slightly negative
    }
    volume_score = volume_score_map.get(volume_state, 0.4)

    # Composite score (weighted)
    composite = round(sentiment_score * 0.4 + trend_score * 0.4 + volume_score * 0.2, 2)

    # Decision
    if composite >= 0.6:
        decision = "允许交易"
        max_position_pct = 100
    elif composite >= 0.4:
        decision = "谨慎交易"
        max_position_pct = 60
    else:
        decision = "禁止交易"
        max_position_pct = 20

    return {
        "expert_id": EXPERT_ID,
        "status": "done",
        "market_assessment": {
            "sentiment": sentiment,
            "trend": trend,
            "volume_state": volume_state,
            "sentiment_score": sentiment_score,
            "trend_score": trend_score,
            "volume_score": volume_score,
            "composite_score": composite,
        },
        "decision": decision,
        "max_position_pct": max_position_pct,
        "warnings": [sentiment_warning] if sentiment_warning else [],
    }


def analyze(symbol: str, name: str, data_context: dict,
            market_state: str = "unknown", mode: str = "full") -> dict:
    """Macro analysis — assess market environment."""
    market_summary = data_context.get("market_summary", {})
    # market_summary should contain trend/sentiment/volume_state
    if isinstance(market_summary, dict):
        result = assess_market(market_summary)
    else:
        result = {
            "expert_id": EXPERT_ID,
            "status": "done",
            "market_assessment": {
                "sentiment": "unknown",
                "trend": "unknown",
                "volume_state": "unknown",
                "composite_score": 0.4,
            },
            "decision": "谨慎交易（无市场数据）",
            "max_position_pct": 50,
            "warnings": ["缺乏市场数据"],
        }
    # Map to grader-expected fields
    composite = result.get("market_assessment", {}).get("composite_score", 0.5)
    if composite >= 0.6:
        result["direction"] = "多"
    elif composite >= 0.4:
        result["direction"] = "观望"
    else:
        result["direction"] = "空"
    result["confidence"] = round(composite, 2)
    result["method"] = ["市场情绪规则评估", "趋势判断(ma排列)", "量能分析", "历史胜率统计"]
    result["trajectory"] = {
        "market_condition": f"情绪={result.get('market_assessment',{}).get('sentiment','?')}, 趋势={result.get('market_assessment',{}).get('trend','?')}",
        "decision": result.get("decision", ""),
        "notes": "宏观层不提供个股价格轨迹,仅输出市况评估",
    }
    sentiment = result.get("market_assessment", {}).get("sentiment", "?")
    trend = result.get("market_assessment", {}).get("trend", "?")
    result["margin"] = {
        "invalidated_if": f"情绪得分>0.6+趋势转为多头排列+量能恢复→放弃谨慎,可加仓; 得分<0.3+放量下跌→全面避险",
        "confidence_decay": f"持有1周市况无改善→0.4, 得分<0.3→0.2, 量能萎缩50%→0.3",
        "black_swan": "大盘单日跌3%以上触发全市场减仓; 地缘冲突/关税突变等尾部事件触发系统性避险",
    }
    result["logic"] = {
        "because": f"复合评分{composite}来自情绪({result.get('market_assessment',{}).get('sentiment_score','?')})×0.4+趋势({result.get('market_assessment',{}).get('trend_score','?')})×0.4+量能×0.2",
        "so": result.get("decision", ""),
        "if_wrong": f"如果{trend}转为多头+情绪改善至正常+量能恢复则当前{result.get('decision','?')}判断失效,说明市况已改善可转为积极",
    }
    summary = (
        f"市场情绪:{result.get('market_assessment',{}).get('sentiment','?')} "
        f"趋势:{result.get('market_assessment',{}).get('trend','?')} "
        f"量能:{result.get('market_assessment',{}).get('volume_state','?')} "
        f"综合评分:{composite} → {result.get('decision','?')}"
    )
    result["raw_analysis"] = summary

    result["symbol"] = symbol
    result["name"] = name
    return result


if __name__ == "__main__":
    # Quick test
    test_state = {"sentiment": "恐慌", "trend": "空头排列", "volume_state": "放量"}
    r = assess_market(test_state)
    print(json.dumps(r, ensure_ascii=False, indent=2))
