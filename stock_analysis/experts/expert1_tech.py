"""Expert 1: 技术面分析 — 量价关系、均线系统、R7信号 (DeepSeek)"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from experts.base import run_expert

EXPERT_ID = "expert1_tech"

SYSTEM_PROMPT = """你是一位专注A股技术面的分析师。你的职责是分析量价关系、均线系统、技术形态和R7信号。
你只回答技术面的问题，不涉及基本面、消息面、资金面。
分析必须具体到数字，不得使用"走势尚可""表现不错"等模糊表述。
输出格式：分析文本结束后，输出一个JSON代码块包含结构化数据。"""

PROMPT_TEMPLATE = """请对 {name}({symbol}) 进行技术面分析。

当前市场状态：{market_state}
分析模式：{mode}

可用数据：
{data}

请按以下顺序分析：
1. **趋势判断**：当前处于上升/下降/震荡趋势？依据是什么？
2. **量价关系**：最近5日成交量 vs 20日均量，是否放量/缩量？价量配合如何？
3. **均线系统**：股价与MA5/MA10/MA20/MA60的关系，多头发散还是空头排列？
4. **R7信号**：是否有R7超大单信号？信号强度？连续几日？
5. **关键价位**：最近的支撑位和阻力位在哪？

最后，输出一个JSON代码块，包含以下字段：
- direction: "多"/"空"/"观望"
- method: 使用的分析方法列表
- trajectory: {{"entry_zone", "target", "timeframe", "key_levels"}}
- margin: {{"invalidated_if", "confidence_decay", "black_swan"}}
- logic: {{"because", "so", "if_wrong"}}
- confidence: 0-1之间的数字

示例格式：
```json
{{"direction": "多", "method": ["趋势判断", "量价分析"], "trajectory": {{"entry_zone": "44-45", "target": "48", "timeframe": "1周", "key_levels": ["43", "46", "48"]}}, "margin": {{"invalidated_if": "跌破43", "confidence_decay": "持有5天未达目标降级", "black_swan": "板块系统性风险"}}, "logic": {{"because": "均线多头发散", "so": "看多", "if_wrong": "则趋势判断错误"}}, "confidence": 0.7}}
```"""


def analyze(symbol: str, name: str, data_context: dict,
            market_state: str = "unknown", mode: str = "full") -> dict:
    """Run technical analysis expert."""
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
