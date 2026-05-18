"""Expert 2: 资金面分析 — 主力资金流向、大单分布 (DeepSeek)"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from experts.base import run_expert

EXPERT_ID = "expert2_money"

SYSTEM_PROMPT = """你是一位专注A股资金面的分析师。你的职责是分析主力资金动向、超大单/大单分布、筹码集中度。
你只回答资金面的问题，不涉及技术形态、基本面、消息面。
分析必须具体到数字，不得使用"资金有所流入"等模糊表述。
输出格式：分析文本结束后，输出一个JSON代码块包含结构化数据。"""

PROMPT_TEMPLATE = """请对 {name}({symbol}) 进行资金面分析。

当前市场状态：{market_state}
分析模式：{mode}

可用数据：
{data}

请按以下顺序分析：
1. **主力资金流向**：最近5日主力净流入/流出趋势，与股价是否背离？
2. **超大单异动**：是否有R7或类似的大单异动信号？持续性和强度如何？
3. **大中小单分布**：超大单、大单、中单、小单的占比变化，散户在接盘还是出货？
4. **筹码分布**：近期筹码是集中还是分散？获利盘比例？
5. **成交量结构**：放量是出现在上涨还是下跌中？主动性买盘 vs 卖盘？

最后，输出一个JSON代码块，包含以下字段：
- direction: "多"/"空"/"观望"
- method: 使用的分析方法列表
- trajectory: {{"entry_zone", "target", "timeframe", "key_levels"}}
- margin: {{"invalidated_if", "confidence_decay", "black_swan"}}
- logic: {{"because", "so", "if_wrong"}}
- confidence: 0-1之间的数字

示例格式：
```json
{{"direction": "多", "method": ["主力资金", "超大单分析"], "trajectory": {{"entry_zone": "44-45", "target": "48", "timeframe": "1周", "key_levels": ["43", "46", "48"]}}, "margin": {{"invalidated_if": "主力由流入转流出", "confidence_decay": "持续流出3日降级", "black_swan": "系统性资金撤退"}}, "logic": {{"because": "超大单连续净流入", "so": "看多", "if_wrong": "则大单是出货不是建仓"}}, "confidence": 0.7}}
```"""


def analyze(symbol: str, name: str, data_context: dict,
            market_state: str = "unknown", mode: str = "full") -> dict:
    """Run money flow analysis expert."""
    prompt = PROMPT_TEMPLATE.format(
        symbol=symbol,
        name=name,
        data=json.dumps(data_context, ensure_ascii=False, indent=2),
        market_state=market_state,
        mode=mode,
    )
    output = run_expert(EXPERT_ID, symbol, name, data_context,
                         prompt_template="", system_prompt=SYSTEM_PROMPT,
                         full_prompt=prompt)
    return output.to_dict()
