"""Expert 2: 资金面分析 — 主力资金流向、大单分布 (DeepSeek)"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from experts.base import run_expert

EXPERT_ID = "expert2_money"


# ============================================================
# FILL ZONE 1: Expert role definition
# Edit the text below to change what this expert focuses on.
# Current: capital flow, large orders,筹码 concentration
# ============================================================
SYSTEM_PROMPT = """你是一位专注A股资金面的分析师。你的职责是：给定一个持仓核心逻辑（thesis），从资金流和筹码变化中判断聪明钱是否在按这个逻辑布局。
你不是填空机器，你是推理者。你判断资金行为与 thesis 一致还是背离。
分析必须具体到数字，不得使用"资金有所流入"等模糊表述。
输出格式：分析文本结束后，输出一个JSON代码块包含结构化数据。"""
# ============================================================
# END OF FILL ZONE 1
# ============================================================


# ============================================================
# FILL ZONE 2: Analysis approach
# ============================================================
PROMPT_TEMPLATE = """对 {name}({symbol}) 进行资金面分析。

核心逻辑（thesis）：{thesis}
当前市场状态：{market_state}
分析模式：{mode}

可用数据：
{data}

你的任务是推理：**从资金行为看，这个 thesis 有没有聪明钱在布局？**
- 主力资金流动方向与 thesis 预期的方向一致吗？
- 是否有异常的大单/超大单活动？是埋伏还是出货？
- 筹码在集中还是分散？谁在买谁在卖？
- 资金行为是提前反应 thesis，还是无视 thesis 在跑？

不要罗列指标，要判断。给出你的 reasoning，然后输出结构化JSON。
# ============================================================
# END OF FILL ZONE 2
# ============================================================

最后，输出一个JSON代码块，包含以下字段。
**重要规则：**
- entry_zone 必须是**数字区间**如"44.5-45.5"，禁止写"待确认""等信号""共振时"等模糊词
- 没有价格数字时，根据量价关系推算一个合理区间，写明"基于XX推算"
- invalidated_if 必须写**具体价格+天数**
- confidence_decay 必须写**具体条件+新置信度**
- method 必须写明**具体指标+参数**如"超大单净额(逐单L2)""主力资金(5日累计)"
- if_wrong 必须写出**反向验证条件**

```json
{{"direction": "多", "method": ["主力资金(5日累计净额)", "超大单(L2逐单)", "大中小单分布(四象限)", "成交量结构(主动买/卖比)"], "trajectory": {{"entry_zone": "44.5-45.5", "target": "48.0", "timeframe": "1周", "key_levels": ["43.0支撑", "46.0阻力"]}}, "margin": {{"invalidated_if": "主力由流入转流出超2日", "confidence_decay": "连续3日流出→0.3, 缩量横盘5日→0.5", "black_swan": "大盘放量暴跌减仓避险"}}, "logic": {{"because": "超大单连续3日净流入+中单无跟风", "so": "看多", "if_wrong": "如果3日内股价不涨反跌,则超大单可能是对倒出货"}}, "confidence": 0.7}}
```"""


def analyze(symbol: str, name: str, data_context: dict,
            market_state: str = "unknown", mode: str = "full") -> dict:
    """Run money flow analysis expert."""
    prompt = PROMPT_TEMPLATE.format(
        symbol=symbol,
        name=name,
        thesis=data_context.get("holding_thesis", ""),
        data=json.dumps(data_context, ensure_ascii=False, indent=2),
        market_state=market_state,
        mode=mode,
    )
    output = run_expert(EXPERT_ID, symbol, name, data_context,
                         prompt_template="", system_prompt=SYSTEM_PROMPT,
                         full_prompt=prompt)
    return output.to_dict()
