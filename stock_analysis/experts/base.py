"""Base expert class — shared API calling + file I/O + prompt pattern."""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import (
    DEEPSEEK_API_KEY, DASHSCOPE_API_KEY, DASHSCOPE_API_KEY_RESEARCH,
    DASHSCOPE_API_KEY_PARALLEL,
)
from ai_router import query_deepseek, query_qwen, query_qwen_parallel, query_qwen_research

from .config import OUTPUT_DIR, EXPERT_MODEL, EXPERT_CHANNEL, EXPERT_TIMEOUT

logger = logging.getLogger("experts.base")

# Output subdirectories per expert (created on demand)
EXPERT_DIRS = {}


def _get_expert_dir(expert_id: str) -> Path:
    """Get or create the output directory for an expert."""
    if expert_id not in EXPERT_DIRS:
        d = OUTPUT_DIR / expert_id
        d.mkdir(parents=True, exist_ok=True)
        EXPERT_DIRS[expert_id] = d
    return EXPERT_DIRS[expert_id]


class ExpertOutput:
    """Structured output from an expert analysis."""

    def __init__(self, expert_id: str, symbol: str, name: str = ""):
        self.expert_id = expert_id
        self.symbol = symbol
        self.name = name
        self.timestamp = datetime.now().isoformat()
        self.direction = ""          # 多/空/观望
        self.method = []             # 分析方式列表
        self.trajectory = {}         # 轨迹
        self.margin = {}             # 边际
        self.logic = {}              # 逻辑
        self.confidence = 0.0
        self.raw_analysis = ""
        self.full_prompt = ""        # 原始完整prompt，用于repair
        self.error: Optional[str] = None
        self.status = "pending"      # pending / done / error

    def to_dict(self) -> dict:
        return {
            "expert_id": self.expert_id,
            "symbol": self.symbol,
            "name": self.name,
            "timestamp": self.timestamp,
            "direction": self.direction,
            "method": self.method,
            "trajectory": self.trajectory,
            "margin": self.margin,
            "logic": self.logic,
            "confidence": self.confidence,
            "raw_analysis": self.raw_analysis,
            "full_prompt": self.full_prompt,
            "error": self.error,
            "status": self.status,
        }

    def save(self):
        """Write output to expert-specific directory."""
        d = _get_expert_dir(self.expert_id)
        safe_name = self.name or self.symbol
        path = d / f"{self.symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    @staticmethod
    def from_dict(d: dict) -> "ExpertOutput":
        o = ExpertOutput(d["expert_id"], d["symbol"], d.get("name", ""))
        o.timestamp = d.get("timestamp", o.timestamp)
        o.direction = d.get("direction", "")
        o.method = d.get("method", [])
        o.trajectory = d.get("trajectory", {})
        o.margin = d.get("margin", {})
        o.logic = d.get("logic", {})
        o.confidence = d.get("confidence", 0.0)
        o.raw_analysis = d.get("raw_analysis", "")
        o.full_prompt = d.get("full_prompt", "")
        o.error = d.get("error")
        o.status = d.get("status", "done")
        return o


def call_llm(expert_id: str, prompt: str, system_prompt: str = "") -> str:
    """Route API call based on expert's configured model.

    Returns the raw text response, or error message prefixed with [ERROR].
    """
    model = EXPERT_MODEL.get(expert_id, "qwen")
    channel = EXPERT_CHANNEL.get(expert_id)

    try:
        if model == "deepseek":
            result = query_deepseek(prompt)
            if result.startswith("[DeepSeek"):
                return f"[ERROR] {result}"
            return result
        elif model == "qwen":
            if channel == "research":
                result = query_qwen_research(prompt)
            elif channel == "parallel":
                result = query_qwen_parallel(prompt)
            else:
                result = query_qwen(prompt)
            if result.startswith("[千问"):
                return f"[ERROR] {result}"
            return result
    except Exception as e:
        logger.exception(f"{expert_id} API call failed")
        return f"[ERROR] {e}"

    return "[ERROR] Unknown model configuration"


def run_expert(expert_id: str, symbol: str, name: str,
               data_context: dict, prompt_template: str,
               system_prompt: str = "",
               full_prompt: str = "",
               **extra_format_kwargs) -> ExpertOutput:
    """Run a single expert analysis.

    Args:
        expert_id: e.g. "expert1_tech"
        symbol: stock code e.g. "002156"
        name: stock name e.g. "通富微电"
        data_context: dict with data this expert needs
        prompt_template: the prompt template with {placeholders}
        system_prompt: optional system role prompt
        full_prompt: if provided, use directly instead of formatting template
        extra_format_kwargs: additional format args for the template

    Returns:
        ExpertOutput with structured fields parsed from LLM response
    """
    output = ExpertOutput(expert_id, symbol, name)

    # Format prompt: use full_prompt if given, otherwise format template
    if full_prompt:
        full_prompt_text = full_prompt
    else:
        data_str = json.dumps(data_context, ensure_ascii=False, indent=2)
        format_kwargs = {"symbol": symbol, "name": name, "data": data_str}
        format_kwargs.update(extra_format_kwargs)
        full_prompt_text = prompt_template.format(**format_kwargs)

    output.full_prompt = full_prompt_text

    # Call API
    raw = call_llm(expert_id, full_prompt_text, system_prompt)

    if raw.startswith("[ERROR]"):
        output.error = raw
        output.status = "error"
        output.save()
        return output

    output.raw_analysis = raw
    output.status = "done"

    # Try to parse structured fields from raw response
    _parse_structured_fields(output, raw)

    output.save()
    return output


DIRECTION_MAP = {
    "多": "多", "看多": "多", "做多": "多", "多头": "多",
    "谨慎看多": "多", "谨慎做多": "多",
    "空": "空", "看空": "空", "做空": "空", "空头": "空",
    "谨慎看空": "空", "谨慎做空": "空",
    "观望": "观望", "中性": "观望", "震荡": "观望", "持有": "观望",
    "多转震荡": "多", "震荡偏多": "多", "偏多": "多",
    "震荡偏空": "空", "偏空": "空", "中性偏多": "观望",
    "中性偏空": "观望", "中性偏谨慎": "观望",
}


def _normalize_direction(raw: str) -> str:
    """Map non-standard direction labels to 多/空/观望."""
    raw = raw.strip()
    if not raw:
        return "观望"
    return DIRECTION_MAP.get(raw, "观望")


def _repair_truncated_json(text: str) -> str | None:
    """Try to fix a truncated JSON block — find the outermost {} and close it.

    Handles cases where the model output was cut off mid-JSON.
    """
    start = text.find("{")
    if start == -1:
        return None

    # Walk char by char counting brace depth
    depth = 0
    last_valid_end = -1
    i = start
    in_string = False
    escape = False

    while i < len(text):
        ch = text[i]
        if escape:
            escape = False
        elif ch == "\\":
            escape = True
        elif ch == '"' and not escape:
            in_string = not in_string
        elif not in_string:
            if ch == "{":
                if depth == 0:
                    start = i  # outermost opening brace
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    last_valid_end = i  # complete close
                elif depth < 0:
                    return None  # mismatched
        i += 1

    if last_valid_end > 0:
        # Found properly closed JSON
        return text[start : last_valid_end + 1]

    if depth > 0 and start >= 0:
        # JSON was truncated — close remaining braces
        partial = text[start:]
        # Try to find the last complete key-value pair
        # Simple approach: append closing braces and try to parse
        closed = partial + "}" * depth
        try:
            json.loads(closed)
            return closed
        except json.JSONDecodeError:
            pass

        # More aggressive: strip trailing incomplete value, then close
        # Find last `"key":` pattern and truncate after it if incomplete
        import re
        lines = partial.rstrip().split("\n")
        clean_lines = []
        for line in lines:
            stripped = line.rstrip()
            if stripped.endswith(","):
                clean_lines.append(stripped)
            elif stripped.endswith((":", "[")):
                break
            elif re.match(r'\s*"[^"]*"\s*:\s*("[^"]*"|\d+\.?\d*|true|false|null)\s*,?\s*$', stripped):
                clean_lines.append(stripped.rstrip(","))
            elif re.match(r'\s*"[^"]*"\s*:\s*\{', stripped):
                clean_lines.append(stripped)
            elif re.match(r'\s*\}', stripped):
                clean_lines.append(stripped)
            elif re.match(r'\s*\]', stripped):
                clean_lines.append(stripped)
            elif re.match(r'\s*"[^"]*"\s*:\s*$', stripped):
                # Incomplete value — truncate this line
                break
            elif re.match(r'\s*"[^"]*"\s*:\s*\[', stripped):
                # Array start — keep
                clean_lines.append(stripped)
            else:
                # Unknown content — skip if it's after we've started JSON
                if clean_lines:
                    break

        if clean_lines:
            repaired = "\n".join(clean_lines)
            repaired += "}" * depth
            try:
                json.loads(repaired)
                return repaired
            except json.JSONDecodeError:
                pass

    return None


def _parse_structured_fields(output: ExpertOutput, text: str):
    """Parse JSON-like structured output from expert's response."""
    import re

    # Strategy 1: find ```json ... ``` block
    json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if json_match:
        raw = json_match.group(1)
        data = _try_parse_json(raw)
        if data:
            _apply_parsed(output, data)
            return

    # Strategy 2: find ```json ... (unclosed) block
    uq_match = re.search(r'```(?:json)?\s*(\{[\s\S]*?)\s*$', text)
    if uq_match:
        raw = uq_match.group(1)
        repaired = _repair_truncated_json(raw)
        if repaired:
            data = _try_parse_json(repaired)
            if data:
                output.direction = _normalize_direction(data.get("direction", ""))
                output.method = data.get("method", output.method)
                output.trajectory = data.get("trajectory", output.trajectory)
                output.margin = data.get("margin", output.margin)
                output.logic = data.get("logic", output.logic)
                output.confidence = data.get("confidence", output.confidence)
                logger.warning(f"{output.expert_id}: JSON was truncated, repaired {len(raw)}->{len(repaired)} chars")
                return

    # Strategy 3: find lone {...} containing "confidence"
    brace_match = re.search(r'(\{[\s\S]*"confidence"[\s\S]*\})', text)
    if brace_match:
        raw = brace_match.group(1)
        data = _try_parse_json(raw)
        if data:
            _apply_parsed(output, data)
            return

    # Strategy 4: lone truncated {...}
    brace_match2 = re.search(r'(\{[\s\S]*"direction"[\s\S]*\})', text)
    if brace_match2:
        raw = brace_match2.group(1)
        repaired = _repair_truncated_json(raw)
        if repaired:
            data = _try_parse_json(repaired)
            if data:
                _apply_parsed(output, data)
                return

    # Last resort: leave raw text, set low confidence
    output.confidence = 0.3


def _try_parse_json(text: str) -> dict | None:
    """Try to parse JSON, returns dict or None."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _apply_parsed(output: ExpertOutput, data: dict):
    """Apply parsed JSON dict to ExpertOutput fields."""
    output.direction = _normalize_direction(data.get("direction", ""))
    output.method = data.get("method", output.method)
    output.trajectory = data.get("trajectory", output.trajectory)
    output.margin = data.get("margin", output.margin)
    output.logic = data.get("logic", output.logic)
    output.confidence = data.get("confidence", output.confidence)


# ============================================================
# Repair — 基于Grader反馈的定向修复
# ============================================================

REPAIR_SYSTEM_PROMPT = """你是一位交易分析师。你的分析报告被质量审核官驳回了。
你的任务是根据驳回原因修复报告，而不是辩护。
保持你的核心判断不变（除非审核明确指出判断依据有误），
只修复结构性和逻辑性问题。"""


def repair_expert(original_output: ExpertOutput,
                  grader_feedback: str,
                  data_context: dict | None = None,
                  market_state: str = "unknown") -> ExpertOutput | None:
    """Re-run an expert with targeted repair feedback from grader.

    Uses the original full_prompt + grader feedback to generate a fix.
    If full_prompt is empty (pre-repair era), returns None.

    Returns:
        New ExpertOutput with repaired analysis, or None if repair not possible
    """
    if not original_output.full_prompt:
        logger.warning(f"{original_output.expert_id}: no full_prompt stored, cannot repair")
        return None

    expert_id = original_output.expert_id
    symbol = original_output.symbol
    name = original_output.name

    # Build repair prompt: original prompt + previous output + grader feedback
    repair_prompt = (
        f"{original_output.full_prompt}\n\n"
        f"===== 修复任务 =====\n"
        f"你的上一次输出被质量审核驳回。驳回原因：\n{grader_feedback}\n\n"
        f"你的上一次输出（供参考）：\n{original_output.raw_analysis}\n\n"
        f"修复要求：\n"
        f"1. 修复上述所有驳回问题\n"
        f"2. 保持JSON格式正确（```json ... ```）\n"
        f"3. 核心判断可以修改——如果审核指出逻辑链断裂（如if_wrong不是逆否命题、因果链缺失），优先保证逻辑闭环，必要时调整direction/confidence\n"
        f"4. 确保if_wrong使用逆否命题结构（若非Y则X假），并且直接针对thesis的前提条件\n"
        f"5. 确保invalidated_if包含价格+天数+条件三段，每个条件必须有显式数字阈值（不能说「主力净流出较大」，要说「主力净流出>成交额8%」）\n"
        f"6. 确保confidence_decay包含至少2组条件→置信度映射，每组条件的数值阈值必须写出具体数字（「10日均量」这种变量名必须附带数字如「10日均量=7亿手」）\n"
        f"7. black_swan必须是可观测的具体事件（不是「政策突变」「大盘不好」等模糊词）\n"
        f"8. 检查所有条件是否都有明确的数字/可观测锚点——含糊的立即补数字\n"
    )

    logger.info(f"Repairing {expert_id} for {symbol}...")

    raw = call_llm(expert_id, repair_prompt, REPAIR_SYSTEM_PROMPT)
    if raw.startswith("[ERROR]"):
        logger.error(f"Repair failed for {expert_id}: {raw}")
        return None

    output = ExpertOutput(expert_id, symbol, name)
    output.full_prompt = original_output.full_prompt
    output.raw_analysis = raw
    output.status = "done"

    _parse_structured_fields(output, raw)
    output.save()
    return output
