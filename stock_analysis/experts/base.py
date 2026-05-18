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


def _parse_structured_fields(output: ExpertOutput, text: str):
    """Parse JSON-like structured output from expert's response.

    Experts are instructed to output a JSON block at the end of their analysis.
    We try to extract and parse it.
    """
    import re

    # Try to find JSON block between ```json and ```
    json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group(1))
            output.direction = data.get("direction", output.direction)
            output.method = data.get("method", output.method)
            output.trajectory = data.get("trajectory", output.trajectory)
            output.margin = data.get("margin", output.margin)
            output.logic = data.get("logic", output.logic)
            output.confidence = data.get("confidence", output.confidence)
            return
        except json.JSONDecodeError:
            pass

    # Fallback: try to find lone {...} at the end of text
    brace_match = re.search(r'(\{[\s\S]*"confidence"[\s\S]*\})', text)
    if brace_match:
        try:
            data = json.loads(brace_match.group(1))
            output.direction = data.get("direction", output.direction)
            output.method = data.get("method", output.method)
            output.trajectory = data.get("trajectory", output.trajectory)
            output.margin = data.get("margin", output.margin)
            output.logic = data.get("logic", output.logic)
            output.confidence = data.get("confidence", output.confidence)
            return
        except json.JSONDecodeError:
            pass

    # Last resort: leave raw text only, set low confidence
    output.confidence = 0.3
