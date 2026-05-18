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
        data=json.dumps(data_context, ensure_ascii=False, indent=2),
        market_state=market_state,
        mode=mode,
    )
    output = run_expert(EXPERT_ID, symbol, name, data_context,
                         prompt_template="", system_prompt=SYSTEM_PROMPT,
                         full_prompt=prompt)
    return output.to_dict()
