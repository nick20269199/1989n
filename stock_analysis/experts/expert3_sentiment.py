"""Expert 3: 题材情绪分析 — 板块轮动、市场情绪、新闻映射 (Qwen)"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from experts.base import run_expert

EXPERT_ID = "expert3_sentiment"

SYSTEM_PROMPT = """你是一位专注A股市场情绪和题材轮动的分析师。你的职责是分析板块效应、市场情绪、新闻事件对个股的影响。
你只回答题材和情绪面的问题，不涉及具体技术指标。
分析必须具体到数字和事实，不得使用"市场情绪较好"等模糊表述。
输出格式：分析文本结束后，输出一个JSON代码块包含结构化数据。"""

PROMPT_TEMPLATE = """请对 {name}({symbol}) 进行题材情绪面分析。

当前市场状态：{market_state}
分析模式：{mode}

可用数据：
{data}

请按以下顺序分析：
1. **所属板块表现**：该股所属板块今日/近5日涨跌幅，板块内排名，板块资金流向
2. **板块联动性**：同板块其他龙头表现如何？该股在板块中是领涨还是跟涨？
3. **市场情绪**：全市场涨跌比、涨停/跌停家数、连板高度、炸板率
4. **新闻事件映射**：最近24h相关新闻是利好还是利空？与股价反应是否一致？
5. **情绪周期位置**：当前处于情绪上升期/高潮期/退潮期/冰点期？

最后，输出一个JSON代码块，包含以下字段。
**重要规则：**
- entry_zone 必须写**具体价格区间**（结合技术面数据），禁止"板块启动初期""等信号"等模糊词
- 情绪相关描述放在trajectory的notes里，entry_zone/target必须用数字
- method 必须写明**具体数据来源**如"板块涨跌幅(同花顺行业)""涨停家数(全市场)"
- invalidated_if 必须写**价格条件**+"叠加什么情绪条件"
- if_wrong 必须写出**反向验证条件**

```json
{{"direction": "多", "method": ["板块表现(近5日涨跌幅)", "资金流向(板块净额)", "情绪周期(涨停/连板高度)", "新闻映射(24h利好/利空)","龙头联动(板块内排名)"], "trajectory": {{"entry_zone": "44.5-45.5", "target": "48.0", "timeframe": "1周", "key_levels": ["板块龙头涨停", "板块跟涨2%以上"], "notes": "情绪处于上升初期,连板高度3板"}}, "margin": {{"invalidated_if": "跌破44.0+板块龙头炸板", "confidence_decay": "3天无板块效应→0.3, 指数跌1.5%→0.5", "black_swan": "政策利空导致板块退潮减仓"}}, "logic": {{"because": "板块近3日资金净流入+连板高度提升", "so": "看多", "if_wrong": "如果板块3日内没有跟涨,则轮动判断错误"}}, "confidence": 0.7}}
```
"""

def analyze(symbol: str, name: str, data_context: dict,
            market_state: str = "unknown", mode: str = "full") -> dict:
    """Run sentiment analysis expert."""
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
