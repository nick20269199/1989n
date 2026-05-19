"""Grader — 五维门禁：方向/方式/轨迹/边际/逻辑 质量评估 (Qwen research)"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from .base import call_llm
from .config import OUTPUT_DIR, GRADER_MIN_SCORE

logger = logging.getLogger("experts.grader")

GRADER_ID = "grader"

SYSTEM_PROMPT = """你是一位交易决策质量审核官。你的职责是评估分析报告是否达到可执行标准。
你只评估质量，不进行额外的市场分析。
你必须严格按五维标准评分，不因报告内容与你的判断一致而放松标准。

**重要：持仓核心逻辑（thesis）是用户提供的事实前提。你的任务是评估专家对这个 thesis 的运用质量，
而不是质疑 thesis 本身是否属实。如果专家逻辑自洽地使用了 thesis，就是合格的推理。

**重要：多位专家从不同维度（技术/资金/情绪/宏观/风控）分析同一标的，得出不同方向判断是正常的——
这不等于报告质量差。方向维度评分应基于「各专家是否清晰陈述了自己的方向判断」，
而不是「所有专家是否方向一致」。对于merged_direction，使用置信度加权投票或多数决来合成统一判断。

**重要：专家角色差异**
- expert1_tech(技术面), expert2_money(资金面), expert3_sentiment(情绪面) 是个股级LLM分析师，应提供完整轨迹/边际/逻辑
- expert4_macro(宏观) 是规则驱动的市场环境评估，不产生个股价格轨迹。它的输出是"当前市场是否适合交易"，不评估个股的入场/目标/关键位
- expert5_risk(风控) 是规则驱动的风险检查，不产生个股价格轨迹。它的输出是"是否触发止损/集中度/持仓时长等风控规则"
- 因此expert4_macro和expert5_risk的trajectory维度不适用个股价格轨迹要求，评估时应基于各自角色做合理判断
- 不同专家给出不同entry_zone/target是正常的分歧，不是报告质量问题。评分只看每个专家在自己角色内的轨迹是否清晰自洽"""

GRADER_PROMPT = """请评估以下交易分析报告的质量。

## 评估标准（五维门禁）

每个维度评分0-1，平均分 >= {min_score} 为通过。

### 1. 方向 (direction)
- **评估每位专家是否清晰给出了自己的多/空/观望判断**（不是看他们是否一致）
- 任何一份报告含糊其辞或回避方向就会扣分
- 0.0 = 多数专家没有方向, 0.5 = 有倾向但部分含糊, 1.0 = 每位专家都清晰陈述了方向
- **专家之间的方向分歧不影响此项评分**（分歧应反映在merged_direction的置信度上）

### 2. 方式 (method)
- 是否明确使用了哪些分析方法？
- 数据来源和分析路径是否透明？
- 0.0 = 没说用了什么方法, 0.5 = 部分说明, 1.0 = 完全透明

### 3. 轨迹 (trajectory)
- 个股级专家(expert1/2/3)必须给出入场区间、目标位、时间框架和关键价格水平
- 宏观(expert4)和风控(expert5)不要求个股价格轨迹——按各自角色评价即可
- 不同专家轨迹中的entry_zone/target分歧是正常的不同视角，不应扣分
- 0.0 = 没有轨迹, 0.5 = 部分给出, 1.0 = 完整轨迹（按角色合理评估）

### 4. 边际 (margin)
- 个股级专家(expert1/2/3)必须给出invalidated_if(价格+天数+条件三段)、confidence_decay(≥2组映射)、black_swan(可观测事件)
- 宏观(expert4)和风控(expert5)按各自角色评估——expert4给出市况边际条件、expert5给出风控阈值即可
- 0.0 = 没有边际, 0.5 = 部分给出, 1.0 = 完整边际

### 5. 逻辑 (logic)
- 因果链是否完整？（因为A所以B，如果非B则A假）
- 是否有"如果错了"的反思？
- 0.0 = 没有逻辑, 0.5 = 部分因果, 1.0 = 完整因果链

## 待评估报告

分析标的：{name}({symbol})
分析时间：{timestamp}
持仓核心逻辑（thesis）：{thesis}

以下为 {expert_count} 位专家的分析报告：

{expert_reports}

## 输出要求

请输出一个JSON代码块(```json ... ```)，包含以下字段：
```json
{{
  "passed": true/false,
  "average_score": 0.0,
  "scores": {{
    "direction": 0.0,
    "method": 0.0,
    "trajectory": 0.0,
    "margin": 0.0,
    "logic": 0.0
  }},
  "failures": ["具体的失败原因列表"],
  "merged_direction": "最终综合判断（多/空/观望）",
  "merged_confidence": 0.0,
  "summary": "一句话综合结论"
}}
```

pass条件: 平均分 >= {min_score} 且 方向得分 >= 0.5"""


def grade(symbol: str, name: str, expert_outputs: list[dict], thesis: str = "") -> dict:
    """Grade expert outputs using 5-dimension gate.

    Args:
        thesis: core holding logic (user-provided fact premise)

    Returns:
        dict with passed, scores, failures, merged_direction
    """
    if not expert_outputs:
        return {
            "passed": False,
            "error": "No expert outputs to grade",
            "scores": {},
        }

    # Build report text from all expert outputs
    reports = []
    for i, eo in enumerate(expert_outputs, 1):
        if eo.get("status") == "error":
            reports.append(f"【专家{i} {eo['expert_id']}】执行错误: {eo.get('error', 'unknown')}")
            continue
        reports.append(
            f"【专家{i} {eo['expert_id']}】\n"
            f"方向: {eo.get('direction', '未提供')}\n"
            f"方法: {', '.join(eo.get('method', []))}\n"
            f"轨迹: {json.dumps(eo.get('trajectory', {}), ensure_ascii=False)}\n"
            f"边际: {json.dumps(eo.get('margin', {}), ensure_ascii=False)}\n"
            f"逻辑: {json.dumps(eo.get('logic', {}), ensure_ascii=False)}\n"
            f"置信度: {eo.get('confidence', 0)}\n"
            f"原始分析:\n{eo.get('raw_analysis', '')[:600]}..."
        )

    prompt = GRADER_PROMPT.format(
        symbol=symbol,
        name=name,
        timestamp=datetime.now().isoformat(),
        thesis=thesis,
        expert_count=len(expert_outputs),
        expert_reports="\n\n".join(reports),
        min_score=GRADER_MIN_SCORE,
    )

    raw = call_llm(GRADER_ID, prompt, SYSTEM_PROMPT)

    if raw.startswith("[ERROR"):
        logger.error(f"Grader API call failed: {raw}")
        return {
            "passed": False,
            "error": raw,
            "scores": {},
            "failures": ["Grader API 调用失败"],
        }

    # Parse JSON from response
    result = {"passed": False, "scores": {}, "failures": ["无法解析Grader输出"]}

    # Strategy 1: find content between ```json and ``` markers
    import re
    json_block = re.search(r'```(?:json)?\s*([\s\S]*?)```', raw)
    if json_block:
        candidate = json_block.group(1).strip()
        parsed = _try_parse_json(candidate)
        if parsed:
            parsed["_raw_grader"] = raw
            _ensure_passed(parsed)
            return parsed

    # Strategy 2: find first { and last }, attempt direct parse + repair
    start = raw.find('{')
    end = raw.rfind('}')
    if start != -1 and end != -1 and end > start:
        candidate = raw[start:end + 1]
        parsed = _try_parse_json(candidate)
        if parsed:
            parsed["_raw_grader"] = raw
            _ensure_passed(parsed)
            return parsed

    result["_raw_grader"] = raw
    _ensure_passed(result)
    return result


def _ensure_passed(parsed: dict):
    """If 'passed' not set by LLM, compute from score + direction."""
    if parsed.get("passed") is not None:
        return
    score = parsed.get("average_score", 0) or 0
    dir_score = (parsed.get("scores", {}) or {}).get("direction", 0) or 0
    parsed["passed"] = score >= GRADER_MIN_SCORE and dir_score >= 0.5


def _try_parse_json(text: str) -> dict | None:
    """Try to parse JSON, auto-repairing common LLM mistakes.

    Handles:
    - `[ ... }` (array closed with brace instead of bracket)
    - Trailing commas before } or ]
    - Brace/bracket mismatch
    """
    import json
    import re

    # Attempt 1: direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Attempt 2: remove trailing commas before } or ] (common LLM mistake)
    try:
        cleaned = re.sub(r',\s*([}\]])', r'\1', text)
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Attempt 3: fix bracket/brace mismatch — [...] } → [...] ]
    # Walk from right, replace } with ] and retry
    for i in range(len(text) - 1, -1, -1):
        if text[i] == '}':
            fixed = text[:i] + ']' + text[i + 1:]
            try:
                return json.loads(fixed)
            except json.JSONDecodeError:
                continue

    # Attempt 4: reverse — ] where } expected
    for i in range(len(text) - 1, -1, -1):
        if text[i] == ']':
            fixed = text[:i] + '}' + text[i + 1:]
            try:
                return json.loads(fixed)
            except json.JSONDecodeError:
                continue

    return None


def save_grade_result(symbol: str, name: str, result: dict):
    """Save grader result to file."""
    d = OUTPUT_DIR / GRADER_ID
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
